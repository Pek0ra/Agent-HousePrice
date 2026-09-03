package com.lgcollege.mapper.mysql;

import com.lgcollege.entity.mysql.HouseImportTask;
import com.lgcollege.entity.mysql.ImportTaskStatus;
import org.apache.ibatis.annotations.Param;

public interface HouseImportTaskMapper {
    int insert(HouseImportTask task);

    HouseImportTask findById(@Param("id") Long id);

    HouseImportTask findSuccessfulByHash(@Param("fileSha256") String fileSha256);

    int transitionStatus(
            @Param("id") Long id,
            @Param("expectedStatus") ImportTaskStatus expectedStatus,
            @Param("nextStatus") ImportTaskStatus nextStatus,
            @Param("incrementRetry") boolean incrementRetry);

    int updateDetails(
            @Param("id") Long id,
            @Param("totalRows") long totalRows,
            @Param("successRows") long successRows,
            @Param("failedRows") long failedRows,
            @Param("hdfsPath") String hdfsPath,
            @Param("errorReportPath") String errorReportPath,
            @Param("stagingPath") String stagingPath);

    int markSuccess(
            @Param("id") Long id,
            @Param("expectedStatus") ImportTaskStatus expectedStatus);

    int markFailed(
            @Param("id") Long id,
            @Param("expectedStatus") ImportTaskStatus expectedStatus,
            @Param("failureStage") ImportTaskStatus failureStage,
            @Param("totalRows") long totalRows,
            @Param("successRows") long successRows,
            @Param("failedRows") long failedRows,
            @Param("errorMessage") String errorMessage,
            @Param("errorReportPath") String errorReportPath);
}
