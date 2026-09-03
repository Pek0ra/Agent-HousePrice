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
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

@Component
public class HouseCsvValidator {
    public static final List<String> HEADERS = Arrays.asList(
            "source_record_id", "title", "city", "district", "community",
            "address", "total_price", "area", "bedroom_count",
            "living_room_count", "layout", "orientation", "floor_description",
            "floor_level", "total_floors", "decoration",
            "surrounding_description", "listing_date", "data_source"
    );
    private static final int MAX_REPORTED_ERRORS = 20;

    private final long maxRows;

    public HouseCsvValidator(@Value("${app.import.max-rows:500000}") long maxRows) {
        this.maxRows = maxRows;
    }

    public CsvValidationResult validate(Path csvFile, Path errorReportFile) {
        long total = 0;
        long success = 0;
        long failed = 0;
        List<String> errors = new ArrayList<>();

        CSVFormat format = CSVFormat.DEFAULT.builder()
                .setHeader()
                .setSkipHeaderRecord(true)
                .setIgnoreEmptyLines(true)
                .setTrim(true)
                .build();

        try (BufferedReader reader = Files.newBufferedReader(csvFile, StandardCharsets.UTF_8);
             CSVParser parser = format.parse(reader);
             CSVPrinter errorPrinter = new CSVPrinter(
                     Files.newBufferedWriter(errorReportFile, StandardCharsets.UTF_8),
                     CSVFormat.DEFAULT.builder()
                             .setHeader("row_number", "error_message", "original_record")
                             .build())) {
            validateHeaders(removeBom(parser.getHeaderNames()));
            for (CSVRecord record : parser) {
                total++;
                if (total > maxRows) {
                    throw new CsvValidationException(
                            "CSV数据行数超过限制：" + maxRows,
                            total, success, failed);
                }
                List<String> rowErrors = validateRecord(record);
                if (rowErrors.isEmpty()) {
                    success++;
                } else {
                    failed++;
                    errorPrinter.printRecord(
                            record.getRecordNumber(),
                            String.join("；", rowErrors),
                            String.join("|", record.toList()));
                    if (errors.size() < MAX_REPORTED_ERRORS) {
                        errors.add("第" + record.getRecordNumber() + "行：" +
                                String.join("；", rowErrors));
                    }
                }
            }
        } catch (CsvValidationException exception) {
            writeGeneralError(errorReportFile, exception.getMessage());
            throw exception;
        } catch (IOException | IllegalArgumentException exception) {
            writeGeneralError(errorReportFile, exception.getMessage());
            throw new CsvValidationException(
                    "CSV无法解析：" + exception.getMessage(), total, success, failed);
        }

        if (total == 0) {
            throw new CsvValidationException("CSV中没有数据行", 0, 0, 0);
        }
        if (failed > 0) {
            throw new CsvValidationException(
                    "CSV存在" + failed + "行错误。" + String.join(" | ", errors),
                    total, success, failed);
        }
        return new CsvValidationResult(total, success, failed);
    }

    private void writeGeneralError(Path errorReportFile, String message) {
        try (CSVPrinter printer = new CSVPrinter(
                Files.newBufferedWriter(errorReportFile, StandardCharsets.UTF_8),
                CSVFormat.DEFAULT.builder()
                        .setHeader("row_number", "error_message", "original_record")
                        .build())) {
            printer.printRecord(0, message, "");
        } catch (IOException ignored) {
            // The original validation exception remains the primary failure.
        }
    }

    private void validateHeaders(List<String> actualHeaders) {
        if (!HEADERS.equals(actualHeaders)) {
            throw new CsvValidationException(
                    "CSV表头不匹配，必须严格按照模板顺序：" + String.join(",", HEADERS),
                    0, 0, 0);
        }
    }

    private List<String> removeBom(List<String> headers) {
        List<String> normalized = new ArrayList<>(headers);
        if (!normalized.isEmpty()) {
            normalized.set(0, normalized.get(0).replace("\uFEFF", ""));
        }
        return normalized;
    }

    private List<String> validateRecord(CSVRecord record) {
        List<String> errors = new ArrayList<>();
        requireText(record, "city", errors);
        requireText(record, "district", errors);
        requireText(record, "community", errors);
        requirePositiveDecimal(record, "total_price", errors);
        requirePositiveDecimal(record, "area", errors);
        optionalNonNegativeInteger(record, "bedroom_count", errors);
        optionalNonNegativeInteger(record, "living_room_count", errors);
        optionalPositiveInteger(record, "total_floors", errors);
        optionalDate(record, "listing_date", errors);
        return errors;
    }

    private void requireText(CSVRecord record, String field, List<String> errors) {
        if (value(record, field).isEmpty()) {
            errors.add(field + "不能为空");
        }
    }

    private void requirePositiveDecimal(
            CSVRecord record, String field, List<String> errors) {
        String value = value(record, field);
        try {
            if (value.isEmpty() || new BigDecimal(value).signum() <= 0) {
                errors.add(field + "必须是大于0的数字");
            }
        } catch (NumberFormatException exception) {
            errors.add(field + "不是合法数字");
        }
    }

    private void optionalNonNegativeInteger(
            CSVRecord record, String field, List<String> errors) {
        String value = value(record, field);
        if (value.isEmpty()) {
            return;
        }
        try {
            if (Integer.parseInt(value) < 0) {
                errors.add(field + "不能为负数");
            }
        } catch (NumberFormatException exception) {
            errors.add(field + "不是合法整数");
        }
    }

    private void optionalPositiveInteger(
            CSVRecord record, String field, List<String> errors) {
        String value = value(record, field);
        if (value.isEmpty()) {
            return;
        }
        try {
            if (Integer.parseInt(value) <= 0) {
                errors.add(field + "必须大于0");
            }
        } catch (NumberFormatException exception) {
            errors.add(field + "不是合法整数");
        }
    }

    private void optionalDate(CSVRecord record, String field, List<String> errors) {
        String value = value(record, field);
        if (value.isEmpty()) {
            return;
        }
        try {
            LocalDate.parse(value);
        } catch (DateTimeParseException exception) {
            errors.add(field + "必须使用yyyy-MM-dd格式");
        }
    }

    private String value(CSVRecord record, String field) {
        String value = record.get(field);
        return value == null ? "" : value.trim();
    }
}
