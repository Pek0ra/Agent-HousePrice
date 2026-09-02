package com.lgcollege.dto.analytics;

import java.math.BigDecimal;

public record RegionAverage(
        String city,
        String district,
        long listingCount,
        BigDecimal averageTotalPrice,
        BigDecimal averageUnitPrice,
        BigDecimal averageArea) {
}
