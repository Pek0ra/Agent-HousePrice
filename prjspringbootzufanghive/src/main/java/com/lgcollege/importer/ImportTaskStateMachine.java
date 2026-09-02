package com.lgcollege.importer;

import com.lgcollege.entity.mysql.ImportTaskStatus;
import com.lgcollege.service.HouseImportTaskStore;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

@Component
public class ImportTaskStateMachine {
    private final Map<ImportTaskStatus, Set<ImportTaskStatus>> allowed =
            new EnumMap<>(ImportTaskStatus.class);
    private final HouseImportTaskStore taskStore;

    public ImportTaskStateMachine(HouseImportTaskStore taskStore) {
        this.taskStore = taskStore;
        allow(ImportTaskStatus.PENDING,
                ImportTaskStatus.VALIDATING, ImportTaskStatus.FAILED);
        allow(ImportTaskStatus.VALIDATING,
                ImportTaskStatus.UPLOADING_HDFS, ImportTaskStatus.FAILED);
        allow(ImportTaskStatus.UPLOADING_HDFS,
                ImportTaskStatus.LOADING_HIVE, ImportTaskStatus.FAILED);
        allow(ImportTaskStatus.LOADING_HIVE,
                ImportTaskStatus.SUCCESS, ImportTaskStatus.FAILED);
        allow(ImportTaskStatus.FAILED, ImportTaskStatus.RETRYING);
        allow(ImportTaskStatus.RETRYING,
                ImportTaskStatus.UPLOADING_HDFS, ImportTaskStatus.LOADING_HIVE,
                ImportTaskStatus.FAILED);
    }

    public void transition(
            Long taskId,
            ImportTaskStatus current,
            ImportTaskStatus next) {
        Set<ImportTaskStatus> nextStatuses = allowed.get(current);
        if (nextStatuses == null || !nextStatuses.contains(next)) {
            throw new IllegalStateException(
                    "非法任务状态迁移：" + current + " -> " + next);
        }
        taskStore.transition(
                taskId, current, next,
                current == ImportTaskStatus.FAILED && next == ImportTaskStatus.RETRYING);
    }

    public void succeed(Long taskId, ImportTaskStatus current) {
        requireAllowed(current, ImportTaskStatus.SUCCESS);
        taskStore.markSuccess(taskId, current);
    }

    public void fail(
            Long taskId,
            ImportTaskStatus current,
            long totalRows,
            long successRows,
            long failedRows,
            String errorMessage,
            String errorReportPath) {
        requireAllowed(current, ImportTaskStatus.FAILED);
        taskStore.markFailed(
                taskId, current, current,
                totalRows, successRows, failedRows,
                errorMessage, errorReportPath);
    }

    private void requireAllowed(
            ImportTaskStatus current,
            ImportTaskStatus next) {
        Set<ImportTaskStatus> nextStatuses = allowed.get(current);
        if (nextStatuses == null || !nextStatuses.contains(next)) {
            throw new IllegalStateException(
                    "非法任务状态迁移：" + current + " -> " + next);
        }
    }

    private void allow(ImportTaskStatus from, ImportTaskStatus... targets) {
        allowed.put(from, EnumSet.of(targets[0], targets));
    }
}
