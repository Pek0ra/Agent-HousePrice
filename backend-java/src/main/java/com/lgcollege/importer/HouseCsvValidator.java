package com.lgcollege.importer;

import com.lgcollege.exception.CsvValidationException;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVPrinter;
import org.apache.commons.csv.CSVRecord;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

@Component
public class HouseCsvValidator {
    public static final List<String> HEADERS = List.of(
            "source_record_id", "listing_type", "title", "city", "district",
            "community", "address", "total_price", "unit_price", "monthly_rent",
            "area", "bedroom_count", "living_room_count", "layout", "orientation",
            "floor_description", "floor_level", "total_floors", "decoration",
            "surrounding_description", "listing_date", "data_source");
    private static final BigDecimal TEN_THOUSAND = new BigDecimal("10000");
    private static final int MAX_REPORTED_ERRORS = 100;
    private final long maxRows;
    private final BigDecimal tolerancePercent;

    public HouseCsvValidator(
            @Value("${app.import.max-rows:500000}") long maxRows,
            @Value("${app.import.unit-price-tolerance-percent:1.0}") BigDecimal tolerancePercent) {
        this.maxRows = maxRows;
        this.tolerancePercent = tolerancePercent;
    }

    public CsvValidationResult validate(Path source, Path errorReport, Path normalizedFile) {
        long total = 0;
        long failed = 0;
        List<NormalizedHouseListing> listings = new ArrayList<>();
        List<String> reported = new ArrayList<>();
        Set<String> keys = new HashSet<>();
        CSVFormat input = CSVFormat.DEFAULT.builder().setHeader().setSkipHeaderRecord(true)
                .setIgnoreEmptyLines(true).setTrim(true).build();
        CSVFormat output = CSVFormat.DEFAULT.builder()
                .setHeader(HEADERS.toArray(String[]::new)).setRecordSeparator("\n").build();
        try (BufferedReader reader = newUtf8Reader(source);
             CSVParser parser = input.parse(reader);
             CSVPrinter errors = new CSVPrinter(Files.newBufferedWriter(errorReport, StandardCharsets.UTF_8),
                     CSVFormat.DEFAULT.builder().setHeader("row_number", "error_message", "original_record").build());
             CSVPrinter normalized = new CSVPrinter(Files.newBufferedWriter(normalizedFile, StandardCharsets.UTF_8), output)) {
            validateHeaders(removeBom(parser.getHeaderNames()));
            for (CSVRecord record : parser) {
                total++;
                if (total > maxRows) {
                    throw new CsvValidationException("CSV 数据行数超过限制：" + maxRows, total, listings.size(), failed);
                }
                try {
                    NormalizedHouseListing listing = normalize(record);
                    String key = listing.dataSource() + "\u0001" + listing.sourceRecordId();
                    if (!keys.add(key)) throw new IllegalArgumentException("同一 CSV 中业务键重复：" + key.replace('\u0001', '/'));
                    listings.add(listing);
                    normalized.printRecord(toCsvRow(listing));
                } catch (IllegalArgumentException exception) {
                    failed++;
                    errors.printRecord(record.getRecordNumber(), exception.getMessage(), safeRecord(record));
                    if (reported.size() < MAX_REPORTED_ERRORS) reported.add("第 " + record.getRecordNumber() + " 行：" + exception.getMessage());
                }
            }
        } catch (CsvValidationException exception) {
            deleteQuietly(normalizedFile);
            throw exception;
        } catch (IOException | IllegalArgumentException exception) {
            deleteQuietly(normalizedFile);
            throw new CsvValidationException("CSV 解析或表头校验失败：" + exception.getMessage(), total, listings.size(), failed);
        }
        if (total == 0) {
            deleteQuietly(normalizedFile);
            throw new CsvValidationException("CSV 不包含数据行", 0, 0, 0);
        }
        if (failed > 0) {
            deleteQuietly(normalizedFile);
            throw new CsvValidationException("CSV 校验失败，共 " + failed + " 行错误；" + String.join("；", reported), total, listings.size(), failed);
        }
        return new CsvValidationResult(total, listings.size(), 0, listings, normalizedFile);
    }

    private NormalizedHouseListing normalize(CSVRecord row) {
        String sourceId = required(row, "source_record_id");
        String dataSource = required(row, "data_source");
        rejectPathSegment(sourceId, "source_record_id");
        rejectPathSegment(dataSource, "data_source");
        ListingType type;
        try { type = ListingType.valueOf(required(row, "listing_type").toUpperCase()); }
        catch (IllegalArgumentException exception) { throw new IllegalArgumentException("listing_type 只允许 SALE 或 RENT"); }

        BigDecimal area = positive(row, "area", true);
        BigDecimal totalPrice = positive(row, "total_price", type == ListingType.SALE);
        BigDecimal suppliedUnitPrice = positive(row, "unit_price", false);
        BigDecimal monthlyRent = positive(row, "monthly_rent", type == ListingType.RENT);
        BigDecimal unitPrice = null;
        if (type == ListingType.SALE) {
            requireEmpty(monthlyRent, "SALE 的 monthly_rent 必须为空");
            unitPrice = totalPrice.multiply(TEN_THOUSAND).divide(area, 2, RoundingMode.HALF_UP);
            if (suppliedUnitPrice != null) {
                BigDecimal errorPercent = suppliedUnitPrice.subtract(unitPrice).abs()
                        .multiply(new BigDecimal("100")).divide(unitPrice, 4, RoundingMode.HALF_UP);
                if (errorPercent.compareTo(tolerancePercent) > 0) {
                    throw new IllegalArgumentException("unit_price 与 total_price/area 计算值误差超过 " + tolerancePercent + "%");
                }
            }
        } else {
            requireEmpty(totalPrice, "RENT 的 total_price 必须为空");
            requireEmpty(suppliedUnitPrice, "RENT 的 unit_price 必须为空");
        }
        return new NormalizedHouseListing(
                sourceId, type, optional(row, "title"), required(row, "city"), required(row, "district"),
                required(row, "community"), optional(row, "address"), scale(totalPrice), scale(unitPrice),
                scale(monthlyRent), scale(area), integer(row, "bedroom_count", false),
                integer(row, "living_room_count", false), optional(row, "layout"), optional(row, "orientation"),
                optional(row, "floor_description"), optional(row, "floor_level"), integer(row, "total_floors", true),
                optional(row, "decoration"), optional(row, "surrounding_description"), date(row, "listing_date"), dataSource);
    }

    private void validateHeaders(List<String> actual) {
        if (!actual.equals(HEADERS)) throw new IllegalArgumentException("表头必须严格匹配统一模板，期望：" + String.join(",", HEADERS));
    }

    private String required(CSVRecord row, String name) {
        String value = optional(row, name);
        if (value == null) throw new IllegalArgumentException(name + " 不能为空");
        return value;
    }

    private String optional(CSVRecord row, String name) {
        String value = row.get(name).trim();
        if (value.isEmpty()) return null;
        if (value.indexOf('\0') >= 0 || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0)
            throw new IllegalArgumentException(name + " 包含多行或控制字符");
        if ("=+-@".indexOf(value.charAt(0)) >= 0) throw new IllegalArgumentException(name + " 不能以公式控制字符开头");
        return value;
    }

    private BigDecimal positive(CSVRecord row, String name, boolean required) {
        String value = row.get(name).trim();
        if (value.isEmpty()) {
            if (required) throw new IllegalArgumentException(name + " 不能为空");
            return null;
        }
        try {
            BigDecimal number = new BigDecimal(value);
            if (number.signum() <= 0) throw new IllegalArgumentException(name + " 必须大于 0");
            return number;
        } catch (NumberFormatException exception) { throw new IllegalArgumentException(name + " 不是合法数字"); }
    }

    private Integer integer(CSVRecord row, String name, boolean positive) {
        String value = row.get(name).trim();
        if (value.isEmpty()) return null;
        try {
            int number = Integer.parseInt(value);
            if (positive ? number <= 0 : number < 0) throw new IllegalArgumentException(name + (positive ? " 必须大于 0" : " 不能为负数"));
            return number;
        } catch (NumberFormatException exception) { throw new IllegalArgumentException(name + " 不是合法整数"); }
    }

    private LocalDate date(CSVRecord row, String name) {
        try { return LocalDate.parse(required(row, name)); }
        catch (DateTimeParseException exception) { throw new IllegalArgumentException(name + " 必须使用 yyyy-MM-dd"); }
    }

    private void rejectPathSegment(String value, String name) {
        if (value.contains("..") || value.contains("/") || value.contains("\\") || value.contains(";"))
            throw new IllegalArgumentException(name + " 包含不安全的路径或 SQL 字符");
    }

    private List<Object> toCsvRow(NormalizedHouseListing r) {
        return List.of(value(r.sourceRecordId()), value(r.listingType()), value(r.title()), value(r.city()),
                value(r.district()), value(r.community()), value(r.address()), value(r.totalPrice()), value(r.unitPrice()),
                value(r.monthlyRent()), value(r.area()), value(r.bedroomCount()), value(r.livingRoomCount()), value(r.layout()),
                value(r.orientation()), value(r.floorDescription()), value(r.floorLevel()), value(r.totalFloors()),
                value(r.decoration()), value(r.surroundingDescription()), value(r.listingDate()), value(r.dataSource()));
    }

    private String safeRecord(CSVRecord record) {
        List<String> values = new ArrayList<>();
        for (String value : record) {
            String safe = value != null && !value.isEmpty() && "=+-@".indexOf(value.charAt(0)) >= 0 ? "'" + value : value;
            values.add(safe == null ? "" : safe.replace("\r", " ").replace("\n", " "));
        }
        return String.join("|", values);
    }

    private List<String> removeBom(List<String> headers) {
        List<String> result = new ArrayList<>(headers);
        if (!result.isEmpty()) result.set(0, result.get(0).replace("\uFEFF", ""));
        return result;
    }

    private BufferedReader newUtf8Reader(Path source) throws IOException {
        BufferedReader reader = Files.newBufferedReader(source, StandardCharsets.UTF_8);
        reader.mark(1);
        if (reader.read() != '\uFEFF') reader.reset();
        return reader;
    }

    private void requireEmpty(Object value, String message) { if (value != null) throw new IllegalArgumentException(message); }
    private Object value(Object value) { return value == null ? "" : value; }
    private BigDecimal scale(BigDecimal value) { return value == null ? null : value.setScale(2, RoundingMode.HALF_UP); }
    private void deleteQuietly(Path file) { try { Files.deleteIfExists(file); } catch (IOException ignored) { } }
}
