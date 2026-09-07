package com.lgcollege.importer;

import java.math.BigDecimal;
import java.time.LocalDate;

public record NormalizedHouseListing(
        String sourceRecordId,
        ListingType listingType,
        String title,
        String city,
        String district,
        String community,
        String address,
        BigDecimal totalPrice,
        BigDecimal unitPrice,
        BigDecimal monthlyRent,
        BigDecimal area,
        Integer bedroomCount,
        Integer livingRoomCount,
        String layout,
        String orientation,
        String floorDescription,
        String floorLevel,
        Integer totalFloors,
        String decoration,
        String surroundingDescription,
        LocalDate listingDate,
        String dataSource) {
}
