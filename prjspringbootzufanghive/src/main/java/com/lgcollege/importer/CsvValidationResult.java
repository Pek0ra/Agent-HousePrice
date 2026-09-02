package com.lgcollege.importer;

public class CsvValidationResult {
    private final long totalRows;
    private final long successRows;
    private final long failedRows;

    public CsvValidationResult(long totalRows, long successRows, long failedRows) {
        this.totalRows = totalRows;
        this.successRows = successRows;
        this.failedRows = failedRows;
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
}
