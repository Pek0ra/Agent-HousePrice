package com.lgcollege.exception;

public class TaskStateConflictException extends RuntimeException {
    public TaskStateConflictException(String message) {
        super(message);
    }
}
