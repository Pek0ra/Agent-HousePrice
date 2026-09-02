package com.lgcollege.controller;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.entity.mysql.HouseImportTask;
import com.lgcollege.exception.ResourceNotFoundException;
import com.lgcollege.importer.HouseCsvValidator;
import com.lgcollege.service.HouseImportService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.validation.constraints.Positive;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

@RestController
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
@RequestMapping("/api/house-imports")
@Validated
public class HouseImportController {
    private final HouseImportService importService;

    public HouseImportController(HouseImportService importService) {
        this.importService = importService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ApiResponse<HouseImportTask>> upload(
            @RequestPart("file") MultipartFile file) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.success(importService.importCsv(file)));
    }

    @GetMapping("/{id}")
    public ApiResponse<HouseImportTask> findById(
            @Positive(message = "id必须大于0") @PathVariable Long id) {
        HouseImportTask task = importService.findTask(id);
        if (task == null) {
            throw new ResourceNotFoundException("导入任务不存在，id=" + id);
        }
        return ApiResponse.success(task);
    }

    @PostMapping("/{id}/retry")
    public ApiResponse<HouseImportTask> retry(
            @Positive(message = "id必须大于0") @PathVariable Long id) {
        HouseImportTask task = importService.findTask(id);
        if (task == null) {
            throw new ResourceNotFoundException("导入任务不存在，id=" + id);
        }
        return ApiResponse.success(importService.retry(id));
    }

    @GetMapping(value = "/{id}/errors", produces = "text/csv;charset=UTF-8")
    public ResponseEntity<byte[]> downloadErrors(
            @Positive(message = "id必须大于0") @PathVariable Long id) throws IOException {
        HouseImportTask task = importService.findTask(id);
        if (task == null) {
            throw new ResourceNotFoundException("导入任务不存在，id=" + id);
        }
        Path report = importService.findErrorReport(id);
        if (report == null) {
            throw new ResourceNotFoundException("该任务没有错误行报告，id=" + id);
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentDisposition(ContentDisposition.attachment()
                .filename("house_import_errors_" + id + ".csv", StandardCharsets.UTF_8)
                .build());
        return new ResponseEntity<>(
                Files.readAllBytes(report), headers, HttpStatus.OK);
    }

    @GetMapping(value = "/template", produces = "text/csv;charset=UTF-8")
    public ResponseEntity<byte[]> downloadTemplate() {
        String csv = "\uFEFF" + String.join(",", HouseCsvValidator.HEADERS) + "\r\n";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentDisposition(ContentDisposition.attachment()
                .filename("house_info_import_template.csv", StandardCharsets.UTF_8)
                .build());
        return new ResponseEntity<>(
                csv.getBytes(StandardCharsets.UTF_8), headers, HttpStatus.OK);
    }
}
