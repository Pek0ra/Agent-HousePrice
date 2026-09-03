package com.lgcollege.exception;

public class CsvValidationException extends RuntimeException {
    private final long totalRows;
    private final long successRows;
    private final long failedRows;

    public CsvValidationException(
            String message,
            long totalRows,
            long successRows,
            long failedRows) {
        super(message);
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
