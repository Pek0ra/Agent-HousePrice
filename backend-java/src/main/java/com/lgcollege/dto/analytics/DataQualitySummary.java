package com.lgcollege.dto.analytics;

import java.math.BigDecimal;

public record DataQualitySummary(
        String datasetId,
        long importTaskId,
        long totalRows,
        long validRows,
        long saleRows,
        long rentRows,
        long missingLocationRows,
        long invalidPriceRows,
        long invalidAreaRows,
        long duplicateSourceRows,
        BigDecimal qualityScore) {
}
