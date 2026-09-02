package com.lgcollege.exception;

public class ImportPipelineException extends RuntimeException {
    private final Long taskId;

    public ImportPipelineException(Long taskId, String message, Throwable cause) {
        super(message, cause);
        this.taskId = taskId;
    }

    public Long getTaskId() {
        return taskId;
    }
}
