package com.lgcollege.dto.analytics;

import java.math.BigDecimal;
import java.time.LocalDate;

public record AnalyticsOverview(
        long listingCount,
        long cityCount,
        long districtCount,
        BigDecimal averageTotalPrice,
        BigDecimal averageUnitPrice,
        BigDecimal averageArea,
        LocalDate latestListingDate) {
}
