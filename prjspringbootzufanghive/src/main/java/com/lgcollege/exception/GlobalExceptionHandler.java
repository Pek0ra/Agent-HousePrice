package com.lgcollege.exception;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.common.ApiCodes;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import javax.validation.ConstraintViolationException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Collections;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler({MethodArgumentNotValidException.class, BindException.class})
    public ResponseEntity<ApiResponse<Map<String, String>>> handleFieldValidation(Exception exception) {
        Map<String, String> errors = new LinkedHashMap<>();
        if (exception instanceof MethodArgumentNotValidException) {
            MethodArgumentNotValidException validationException =
                    (MethodArgumentNotValidException) exception;
            collectFieldErrors(validationException.getBindingResult().getFieldErrors(), errors);
        } else {
            BindException bindException = (BindException) exception;
            collectFieldErrors(bindException.getBindingResult().getFieldErrors(), errors);
        }
        return ResponseEntity.badRequest()
                .body(ApiResponse.error(ApiCodes.VALIDATION_ERROR, "请求参数校验失败", errors));
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiResponse<Void>> handleConstraintViolation(
            ConstraintViolationException exception) {
        return ResponseEntity.badRequest()
                .body(ApiResponse.error(ApiCodes.VALIDATION_ERROR, exception.getMessage(), null));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleIllegalArgument(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(ApiResponse.error(ApiCodes.BUSINESS_ERROR, exception.getMessage(), null));
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNotFound(ResourceNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiResponse.error(ApiCodes.RESOURCE_NOT_FOUND, exception.getMessage(), null));
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<ApiResponse<Void>> handleDuplicateKey(DuplicateKeyException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiResponse.error(
                        ApiCodes.DUPLICATE_RESOURCE, "数据已存在，请勿重复提交", null));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<Void>> handleUnreadableMessage(
            HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest()
                .body(ApiResponse.error(ApiCodes.MALFORMED_REQUEST, "请求体格式错误", null));
    }

    @ExceptionHandler(MissingServletRequestPartException.class)
    public ResponseEntity<ApiResponse<Void>> handleMissingPart(
            MissingServletRequestPartException exception) {
        return ResponseEntity.badRequest()
                .body(ApiResponse.error(ApiCodes.MISSING_FILE, "缺少上传文件file", null));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiResponse<Void>> handleFileTooLarge(
            MaxUploadSizeExceededException exception) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(ApiResponse.error(ApiCodes.FILE_TOO_LARGE, "上传文件超过大小限制", null));
    }

    @ExceptionHandler(ImportPipelineException.class)
    public ResponseEntity<ApiResponse<Map<String, Long>>> handleImportFailure(
            ImportPipelineException exception) {
        return ResponseEntity.unprocessableEntity()
                .body(ApiResponse.error(
                        ApiCodes.IMPORT_FAILED,
                        exception.getMessage(),
                        Collections.singletonMap("taskId", exception.getTaskId())));
    }

    @ExceptionHandler(DuplicateImportException.class)
    public ResponseEntity<ApiResponse<Map<String, Long>>> handleDuplicateImport(
            DuplicateImportException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiResponse.error(
                        ApiCodes.DUPLICATE_IMPORT,
                        exception.getMessage(),
                        Collections.singletonMap(
                                "existingTaskId", exception.getExistingTaskId())));
    }

    @ExceptionHandler(TaskStateConflictException.class)
    public ResponseEntity<ApiResponse<Void>> handleTaskStateConflict(
            TaskStateConflictException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiResponse.error(
                        ApiCodes.TASK_STATE_CONFLICT, exception.getMessage(), null));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleUnexpected(Exception exception) {
        log.error("Unhandled request exception", exception);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error(ApiCodes.INTERNAL_ERROR, "服务器内部错误", null));
    }

    private void collectFieldErrors(
            Iterable<FieldError> fieldErrors,
            Map<String, String> errors) {
        for (FieldError fieldError : fieldErrors) {
            errors.putIfAbsent(fieldError.getField(), fieldError.getDefaultMessage());
        }
    }
}
