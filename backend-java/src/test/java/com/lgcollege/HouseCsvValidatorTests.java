package com.lgcollege;

import com.lgcollege.exception.CsvValidationException;
import com.lgcollege.importer.CsvValidationResult;
import com.lgcollege.importer.HouseCsvValidator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HouseCsvValidatorTests {
    private static final String HEADER = String.join(",", HouseCsvValidator.HEADERS) + "\n";
    @TempDir Path temp;

    @Test
    void acceptsBomAndMixedSaleRentAndCalculatesUnitPrice() throws Exception {
        String csv = "\uFEFF" + HEADER
                + "S-1,SALE,中文出售,上海市,浦东新区,测试小区,,300,,,60,3,1,3室1厅,,,,,,,2026-01-01,TEST\n"
                + "R-1,RENT,中文出租,深圳市,南山区,测试小区,,,,9000,68,2,1,2室1厅,,,,,,,2026-02-01,TEST\n";
        CsvValidationResult result = validate(csv);
        assertEquals(2, result.getSuccessRows());
        assertEquals(1, result.getSaleRows());
        assertEquals(1, result.getRentRows());
        assertEquals(new BigDecimal("50000.00"), result.getListings().get(0).unitPrice());
        assertTrue(Files.readString(result.getNormalizedFile(), StandardCharsets.UTF_8).contains("中文出租"));
    }

    @Test
    void rejectsMissingColumn() {
        assertInvalid("source_record_id,listing_type\nS-1,SALE\n", "表头");
    }

    @Test
    void rejectsInvalidTypesNumbersDatesAndDuplicateBusinessKeys() {
        assertInvalid(HEADER + "X,OTHER,t,上海市,浦东新区,c,,,,1,60,,,,,,,,,,2026-01-01,TEST\n", "listing_type");
        assertInvalid(HEADER + "X,SALE,t,上海市,浦东新区,c,,-1,,,0,,,,,,,,,,bad,TEST\n", "校验失败");
        String duplicate = "D,RENT,t,上海市,浦东新区,c,,,,1000,20,,,,,,,,,,2026-01-01,TEST\n";
        assertInvalid(HEADER + duplicate + duplicate, "业务键重复");
    }

    @Test
    void rejectsFormulaAndPathInjection() {
        assertInvalid(HEADER + "../X,RENT,=CMD(),上海市,浦东新区,c,,,,1000,20,,,,,,,,,,2026-01-01,TEST\n",
                "不安全");
    }

    @Test
    void sharedFixtureHasDeterministicCountsAndAggregates() throws Exception {
        Path fixture = Path.of(Objects.requireNonNull(
                getClass().getResource("/fixtures/house_listings.csv")).toURI());
        CsvValidationResult result = new HouseCsvValidator(100, new BigDecimal("1.0"))
                .validate(fixture, temp.resolve("fixture-errors.csv"), temp.resolve("fixture-normalized.csv"));
        assertEquals(20, result.getSuccessRows());
        assertEquals(8, result.getSaleRows());
        assertEquals(12, result.getRentRows());
        long beijingSales = result.getListings().stream()
                .filter(row -> row.listingType().name().equals("SALE") && row.city().equals("北京市")).count();
        assertEquals(7, beijingSales);
    }

    private CsvValidationResult validate(String csv) throws Exception {
        Path source = temp.resolve("source.csv");
        Files.writeString(source, csv, StandardCharsets.UTF_8);
        return new HouseCsvValidator(100, new BigDecimal("1.0"))
                .validate(source, temp.resolve("errors.csv"), temp.resolve("normalized.csv"));
    }

    private void assertInvalid(String csv, String message) {
        CsvValidationException exception = assertThrows(CsvValidationException.class, () -> validate(csv));
        assertTrue(exception.getMessage().contains(message), exception.getMessage());
    }
}
