package com.lgcollege.importer;

import java.nio.file.Path;
import java.util.List;

public class CsvValidationResult {
    private final long totalRows;
    private final long successRows;
    private final long failedRows;
    private final List<NormalizedHouseListing> listings;
    private final Path normalizedFile;

    public CsvValidationResult(
            long totalRows,
            long successRows,
            long failedRows,
            List<NormalizedHouseListing> listings,
            Path normalizedFile) {
        this.totalRows = totalRows;
        this.successRows = successRows;
        this.failedRows = failedRows;
        this.listings = List.copyOf(listings);
        this.normalizedFile = normalizedFile;
    }

    public long getTotalRows() {
        return totalRows;
    }

    public long getSuccessRows() {
        return successRows;
    }

    public long getFailedRows() {
        return failedRows;
    }

    public List<NormalizedHouseListing> getListings() {
        return listings;
    }

    public Path getNormalizedFile() {
        return normalizedFile;
    }

    public long getSaleRows() {
        return listings.stream().filter(row -> row.listingType() == ListingType.SALE).count();
    }

    public long getRentRows() {
        return listings.stream().filter(row -> row.listingType() == ListingType.RENT).count();
    }
}
