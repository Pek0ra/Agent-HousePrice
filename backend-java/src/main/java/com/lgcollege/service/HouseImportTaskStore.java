package com.lgcollege.service;

import com.lgcollege.entity.mysql.HouseImportTask;
import com.lgcollege.entity.mysql.ImportTaskStatus;

public interface HouseImportTaskStore {
    HouseImportTask create(
            String originalFilename,
            long fileSize,
            String fileSha256,
            String stagingPath);

    HouseImportTask findSuccessfulByHash(String fileSha256);

    void transition(
            Long id,
            ImportTaskStatus expectedStatus,
            ImportTaskStatus nextStatus,
            boolean incrementRetry);

    void updateDetails(
            Long id,
            long totalRows,
            long successRows,
            long failedRows,
            String hdfsPath,
            String errorReportPath,
            String stagingPath);

    void markSuccess(Long id, ImportTaskStatus expectedStatus);

    void markFailed(
            Long id,
            ImportTaskStatus expectedStatus,
            ImportTaskStatus failureStage,
            long totalRows,
            long successRows,
            long failedRows,
            String errorMessage,
            String errorReportPath);

    HouseImportTask findById(Long id);
}
