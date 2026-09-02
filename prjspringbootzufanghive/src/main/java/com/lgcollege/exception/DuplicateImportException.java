package com.lgcollege.exception;

public class DuplicateImportException extends RuntimeException {
    private final Long existingTaskId;

    public DuplicateImportException(Long existingTaskId) {
        super("相同内容的文件已经成功导入");
        this.existingTaskId = existingTaskId;
    }

    public Long getExistingTaskId() {
        return existingTaskId;
    }
}
