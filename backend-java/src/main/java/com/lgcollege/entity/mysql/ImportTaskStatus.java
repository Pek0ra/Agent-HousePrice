package com.lgcollege.entity.mysql;

public enum ImportTaskStatus {
    PENDING,
    VALIDATING,
    LOADING_MYSQL,
    UPLOADING_HDFS,
    LOADING_HIVE,
    COMPACTING_HIVE,
    VERIFYING,
    ACTIVATING,
    RETRYING,
    SUCCESS,
    FAILED
}
