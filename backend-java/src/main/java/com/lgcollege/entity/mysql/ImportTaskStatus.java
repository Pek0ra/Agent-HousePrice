package com.lgcollege.entity.mysql;

public enum ImportTaskStatus {
    PENDING,
    VALIDATING,
    UPLOADING_HDFS,
    LOADING_HIVE,
    RETRYING,
    SUCCESS,
    FAILED
}
