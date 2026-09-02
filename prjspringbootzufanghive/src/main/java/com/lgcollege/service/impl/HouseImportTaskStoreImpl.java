package com.lgcollege.service.impl;

import com.lgcollege.entity.mysql.HouseImportTask;
import com.lgcollege.entity.mysql.ImportTaskStatus;
import com.lgcollege.exception.TaskStateConflictException;
import com.lgcollege.mapper.mysql.HouseImportTaskMapper;
import com.lgcollege.service.HouseImportTaskStore;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HouseImportTaskStoreImpl implements HouseImportTaskStore {
    private static final int MAX_ERROR_LENGTH = 1000;
    private final HouseImportTaskMapper mapper;

    public HouseImportTaskStoreImpl(HouseImportTaskMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public HouseImportTask create(
            String originalFilename,
            long fileSize,
            String fileSha256,
            String stagingPath) {
        HouseImportTask task = new HouseImportTask();
        task.setOriginalFilename(originalFilename);
        task.setFileSize(fileSize);
        task.setFileSha256(fileSha256);
        task.setStatus(ImportTaskStatus.PENDING);
        task.setStagingPath(stagingPath);
        mapper.insert(task);
        return mapper.findById(task.getId());
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public HouseImportTask findSuccessfulByHash(String fileSha256) {
        return mapper.findSuccessfulByHash(fileSha256);
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public void transition(
            Long id,
            ImportTaskStatus expectedStatus,
            ImportTaskStatus nextStatus,
            boolean incrementRetry) {
        if (mapper.transitionStatus(
                id, expectedStatus, nextStatus, incrementRetry) != 1) {
            throw new TaskStateConflictException(
                    "任务状态已变化，期望状态=" + expectedStatus);
        }
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public void updateDetails(
            Long id,
            long totalRows,
            long successRows,
            long failedRows,
            String hdfsPath,
            String errorReportPath,
            String stagingPath) {
        mapper.updateDetails(
                id, totalRows, successRows, failedRows,
                hdfsPath, errorReportPath, stagingPath);
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public void markSuccess(Long id, ImportTaskStatus expectedStatus) {
        if (mapper.markSuccess(id, expectedStatus) != 1) {
            throw new TaskStateConflictException("任务状态已变化，无法标记成功");
        }
    }

    @Override
    @Transactional(transactionManager = "mysqlTransactionManager")
    public void markFailed(
            Long id,
            ImportTaskStatus expectedStatus,
            ImportTaskStatus failureStage,
            long totalRows,
            long successRows,
            long failedRows,
            String errorMessage,
            String errorReportPath) {
        if (mapper.markFailed(
                id, expectedStatus, failureStage,
                totalRows, successRows, failedRows,
                truncate(errorMessage), errorReportPath) != 1) {
            throw new TaskStateConflictException("任务状态已变化，无法标记失败");
        }
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public HouseImportTask findById(Long id) {
        return mapper.findById(id);
    }

    private String truncate(String value) {
        if (value == null) {
            return "未知导入错误";
        }
        return value.length() <= MAX_ERROR_LENGTH
                ? value : value.substring(0, MAX_ERROR_LENGTH);
    }
}
