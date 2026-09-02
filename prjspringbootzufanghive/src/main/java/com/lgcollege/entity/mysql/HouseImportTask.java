package com.lgcollege.entity.mysql;

import com.fasterxml.jackson.annotation.JsonIgnore;

import java.time.LocalDateTime;

public class HouseImportTask {
    private Long id;
    private String originalFilename;
    private Long fileSize;
    private String fileSha256;
    private ImportTaskStatus status;
    private Long totalRows;
    private Long successRows;
    private Long failedRows;
    private String hdfsPath;
    private String errorReportPath;
    private ImportTaskStatus failureStage;
    private Integer retryCount;
    private String stagingPath;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getOriginalFilename() {
        return originalFilename;
    }

    public void setOriginalFilename(String originalFilename) {
        this.originalFilename = originalFilename;
    }

    public Long getFileSize() {
        return fileSize;
    }

    public void setFileSize(Long fileSize) {
        this.fileSize = fileSize;
    }

    public String getFileSha256() {
        return fileSha256;
    }

    public void setFileSha256(String fileSha256) {
        this.fileSha256 = fileSha256;
    }

    public ImportTaskStatus getStatus() {
        return status;
    }

    public void setStatus(ImportTaskStatus status) {
        this.status = status;
    }

    public Long getTotalRows() {
        return totalRows;
    }

    public void setTotalRows(Long totalRows) {
        this.totalRows = totalRows;
    }

    public Long getSuccessRows() {
        return successRows;
    }

    public void setSuccessRows(Long successRows) {
        this.successRows = successRows;
    }

    public Long getFailedRows() {
        return failedRows;
    }

    public void setFailedRows(Long failedRows) {
        this.failedRows = failedRows;
    }

    public String getHdfsPath() {
        return hdfsPath;
    }

    public void setHdfsPath(String hdfsPath) {
        this.hdfsPath = hdfsPath;
    }

    @JsonIgnore
    public String getErrorReportPath() {
        return errorReportPath;
    }

    public void setErrorReportPath(String errorReportPath) {
        this.errorReportPath = errorReportPath;
    }

    public boolean isErrorReportAvailable() {
        return errorReportPath != null && !errorReportPath.isEmpty();
    }

    public ImportTaskStatus getFailureStage() {
        return failureStage;
    }

    public void setFailureStage(ImportTaskStatus failureStage) {
        this.failureStage = failureStage;
    }

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    @JsonIgnore
    public String getStagingPath() {
        return stagingPath;
    }

    public void setStagingPath(String stagingPath) {
        this.stagingPath = stagingPath;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(LocalDateTime startedAt) {
        this.startedAt = startedAt;
    }

    public LocalDateTime getFinishedAt() {
        return finishedAt;
    }

    public void setFinishedAt(LocalDateTime finishedAt) {
        this.finishedAt = finishedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
