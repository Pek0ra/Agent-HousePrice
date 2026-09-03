package com.lgcollege.dto.analytics;

import java.math.BigDecimal;

public record PriceTrend(
        String month,
        long listingCount,
        BigDecimal averageTotalPrice,
        BigDecimal averageUnitPrice) {
}
