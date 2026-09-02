package com.lgcollege.dto.analytics;

import java.math.BigDecimal;

public record DataQualitySummary(
        String importDate,
        long importTaskId,
        long totalRows,
        long validRows,
        long missingLocationRows,
        long invalidPriceRows,
        long invalidAreaRows,
        long duplicateSourceRows,
        BigDecimal qualityScore) {
}
