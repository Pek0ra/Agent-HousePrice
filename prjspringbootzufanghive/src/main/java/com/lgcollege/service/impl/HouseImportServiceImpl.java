package com.lgcollege.service.impl;

import com.lgcollege.entity.mysql.HouseImportTask;
import com.lgcollege.entity.mysql.ImportTaskStatus;
import com.lgcollege.exception.CsvValidationException;
import com.lgcollege.exception.DuplicateImportException;
import com.lgcollege.exception.ImportPipelineException;
import com.lgcollege.exception.ResourceNotFoundException;
import com.lgcollege.importer.CsvValidationResult;
import com.lgcollege.importer.HdfsStorage;
import com.lgcollege.importer.HiveImportLoader;
import com.lgcollege.importer.HouseCsvValidator;
import com.lgcollege.importer.ImportTaskStateMachine;
import com.lgcollege.service.HouseImportService;
import com.lgcollege.service.HouseImportTaskStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.stream.Stream;

@Service
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class HouseImportServiceImpl implements HouseImportService {
    private static final Logger log = LoggerFactory.getLogger(HouseImportServiceImpl.class);

    private final HouseImportTaskStore taskStore;
    private final ImportTaskStateMachine stateMachine;
    private final HouseCsvValidator csvValidator;
    private final HdfsStorage hdfsStorage;
    private final HiveImportLoader hiveImportLoader;
    private final String hdfsBasePath;
    private final Path stagingRoot;
    private final long maxFileSizeBytes;
    private final int maxRetries;

    public HouseImportServiceImpl(
            HouseImportTaskStore taskStore,
            ImportTaskStateMachine stateMachine,
            HouseCsvValidator csvValidator,
            HdfsStorage hdfsStorage,
            HiveImportLoader hiveImportLoader,
            @Value("${app.hdfs.base-path}") String hdfsBasePath,
            @Value("${app.import.staging-path}") String stagingPath,
            @Value("${app.import.max-file-size-bytes:52428800}") long maxFileSizeBytes,
            @Value("${app.import.max-retries:3}") int maxRetries) {
        this.taskStore = taskStore;
        this.stateMachine = stateMachine;
        this.csvValidator = csvValidator;
        this.hdfsStorage = hdfsStorage;
        this.hiveImportLoader = hiveImportLoader;
        this.hdfsBasePath = normalizeBasePath(hdfsBasePath);
        this.stagingRoot = Path.of(stagingPath).toAbsolutePath().normalize();
        this.maxFileSizeBytes = maxFileSizeBytes;
        this.maxRetries = maxRetries;
    }

    @Override
    public HouseImportTask importCsv(MultipartFile file) {
        validateUpload(file);
        Path incomingFile = null;
        HouseImportTask task = null;
        try {
            Files.createDirectories(stagingRoot);
            incomingFile = Files.createTempFile(stagingRoot, "incoming-", ".csv");
            file.transferTo(incomingFile);
            String sha256 = calculateSha256(incomingFile);
            HouseImportTask duplicate = taskStore.findSuccessfulByHash(sha256);
            if (duplicate != null) {
                throw new DuplicateImportException(duplicate.getId());
            }

            Path taskDirectory = Files.createTempDirectory(stagingRoot, "task-");
            Path sourceFile = taskDirectory.resolve("source.csv");
            Files.move(incomingFile, sourceFile, StandardCopyOption.REPLACE_EXISTING);
            incomingFile = null;
            task = taskStore.create(
                    safeOriginalFilename(file.getOriginalFilename()),
                    file.getSize(),
                    sha256,
                    sourceFile.toString());
            log.info("House import created taskId={} filename={} size={} sha256={}",
                    task.getId(), task.getOriginalFilename(), task.getFileSize(), sha256);
            return executeNewImport(task, sourceFile, taskDirectory.resolve("errors.csv"));
        } catch (DuplicateImportException exception) {
            throw exception;
        } catch (ImportPipelineException exception) {
            throw exception;
        } catch (Exception exception) {
            if (task != null) {
                failTask(task, ImportTaskStatus.PENDING, 0, 0, 0, exception, null);
            }
            throw new IllegalStateException("创建导入任务失败：" + exception.getMessage(), exception);
        } finally {
            deleteIfExists(incomingFile);
        }
    }

    @Override
    public HouseImportTask retry(Long id) {
        HouseImportTask task = requireTask(id);
        if (task.getStatus() != ImportTaskStatus.FAILED) {
            throw new IllegalArgumentException("只有FAILED任务可以重试");
        }
        if (task.getFailureStage() != ImportTaskStatus.UPLOADING_HDFS
                && task.getFailureStage() != ImportTaskStatus.LOADING_HIVE) {
            throw new IllegalArgumentException("数据校验失败不能原文件重试，请修正CSV后重新上传");
        }
        if (task.getRetryCount() != null && task.getRetryCount() >= maxRetries) {
            throw new IllegalArgumentException("任务已达到最大重试次数：" + maxRetries);
        }
        Path sourceFile = requireStagingFile(task);
        stateMachine.transition(
                task.getId(), ImportTaskStatus.FAILED, ImportTaskStatus.RETRYING);
        ImportTaskStatus current = ImportTaskStatus.RETRYING;
        long startedAt = System.nanoTime();
        try {
            log.info("House import retry started taskId={} retryCount={} failureStage={}",
                    task.getId(), task.getRetryCount() + 1, task.getFailureStage());

            LocalDate importDate = task.getStartedAt().toLocalDate();
            String hdfsPath = task.getHdfsPath();
            String hdfsDirectory = parentHdfsPath(hdfsPath);
            if (task.getFailureStage() == ImportTaskStatus.UPLOADING_HDFS) {
                stateMachine.transition(
                        task.getId(), current, ImportTaskStatus.UPLOADING_HDFS);
                current = ImportTaskStatus.UPLOADING_HDFS;
                hdfsStorage.upload(sourceFile, hdfsPath, true);
                stateMachine.transition(
                        task.getId(), current, ImportTaskStatus.LOADING_HIVE);
                current = ImportTaskStatus.LOADING_HIVE;
            } else {
                stateMachine.transition(
                        task.getId(), current, ImportTaskStatus.LOADING_HIVE);
                current = ImportTaskStatus.LOADING_HIVE;
            }

            hiveImportLoader.load(task.getId(), importDate, hdfsDirectory);
            stateMachine.succeed(task.getId(), current);
            cleanupTaskDirectory(sourceFile.getParent());
            log.info("House import retry succeeded taskId={} elapsedMs={}",
                    task.getId(), elapsedMillis(startedAt));
            return taskStore.findById(task.getId());
        } catch (Exception exception) {
            failTask(
                    task, current,
                    task.getTotalRows(), task.getSuccessRows(), task.getFailedRows(),
                    exception, task.getErrorReportPath());
            throw new ImportPipelineException(task.getId(), exception.getMessage(), exception);
        }
    }

    @Override
    public HouseImportTask findTask(Long id) {
        return requireTask(id);
    }

    @Override
    public Path findErrorReport(Long id) {
        HouseImportTask task = requireTask(id);
        if (task.getErrorReportPath() == null) {
            return null;
        }
        Path report = Path.of(task.getErrorReportPath()).toAbsolutePath().normalize();
        if (!report.startsWith(stagingRoot) || !Files.isRegularFile(report)) {
            return null;
        }
        return report;
    }

    private HouseImportTask executeNewImport(
            HouseImportTask task,
            Path sourceFile,
            Path errorReport) {
        ImportTaskStatus current = ImportTaskStatus.PENDING;
        long totalRows = 0;
        long successRows = 0;
        long failedRows = 0;
        long startedAt = System.nanoTime();
        try {
            stateMachine.transition(task.getId(), current, ImportTaskStatus.VALIDATING);
            current = ImportTaskStatus.VALIDATING;
            CsvValidationResult validation = csvValidator.validate(sourceFile, errorReport);
            totalRows = validation.getTotalRows();
            successRows = validation.getSuccessRows();
            failedRows = validation.getFailedRows();
            deleteIfExists(errorReport);

            LocalDate importDate = task.getStartedAt().toLocalDate();
            String hdfsDirectory = hdfsBasePath + "/" + importDate +
                    "/task-" + task.getId();
            String hdfsPath = hdfsDirectory + "/house_info.csv";
            taskStore.updateDetails(
                    task.getId(), totalRows, successRows, failedRows,
                    hdfsPath, null, sourceFile.toString());

            stateMachine.transition(
                    task.getId(), current, ImportTaskStatus.UPLOADING_HDFS);
            current = ImportTaskStatus.UPLOADING_HDFS;
            hdfsStorage.upload(sourceFile, hdfsPath, true);

            stateMachine.transition(
                    task.getId(), current, ImportTaskStatus.LOADING_HIVE);
            current = ImportTaskStatus.LOADING_HIVE;
            hiveImportLoader.load(task.getId(), importDate, hdfsDirectory);

            stateMachine.succeed(task.getId(), current);
            cleanupTaskDirectory(sourceFile.getParent());
            log.info("House import succeeded taskId={} rows={} elapsedMs={}",
                    task.getId(), totalRows, elapsedMillis(startedAt));
            return taskStore.findById(task.getId());
        } catch (CsvValidationException exception) {
            totalRows = exception.getTotalRows();
            successRows = exception.getSuccessRows();
            failedRows = exception.getFailedRows();
            failTask(
                    task, current, totalRows, successRows, failedRows,
                    exception, errorReport.toString());
            deleteIfExists(sourceFile);
            throw new ImportPipelineException(task.getId(), exception.getMessage(), exception);
        } catch (Exception exception) {
            failTask(
                    task, current, totalRows, successRows, failedRows,
                    exception, Files.exists(errorReport) ? errorReport.toString() : null);
            throw new ImportPipelineException(task.getId(), exception.getMessage(), exception);
        }
    }

    private void failTask(
            HouseImportTask task,
            ImportTaskStatus current,
            long totalRows,
            long successRows,
            long failedRows,
            Exception exception,
            String errorReportPath) {
        stateMachine.fail(
                task.getId(), current,
                totalRows, successRows, failedRows,
                safeMessage(exception), errorReportPath);
        log.warn("House import failed taskId={} stage={} message={}",
                task.getId(), current, safeMessage(exception));
    }

    private HouseImportTask requireTask(Long id) {
        if (id == null || id <= 0) {
            throw new IllegalArgumentException("id必须大于0");
        }
        HouseImportTask task = taskStore.findById(id);
        if (task == null) {
            throw new ResourceNotFoundException("导入任务不存在，id=" + id);
        }
        return task;
    }

    private Path requireStagingFile(HouseImportTask task) {
        if (task.getStagingPath() == null) {
            throw new IllegalArgumentException("任务暂存文件不存在，无法重试");
        }
        Path path = Path.of(task.getStagingPath()).toAbsolutePath().normalize();
        if (!path.startsWith(stagingRoot) || !Files.isRegularFile(path)) {
            throw new IllegalArgumentException("任务暂存文件不存在，无法重试");
        }
        return path;
    }

    private void validateUpload(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("CSV文件不能为空");
        }
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".csv")) {
            throw new IllegalArgumentException("只允许上传.csv文件");
        }
        if (file.getSize() > maxFileSizeBytes) {
            throw new IllegalArgumentException(
                    "CSV文件超过业务限制：" + maxFileSizeBytes + "字节");
        }
    }

    private String safeOriginalFilename(String filename) {
        String normalized = filename == null ? "unknown.csv"
                : filename.replace('\\', '/');
        normalized = normalized.substring(normalized.lastIndexOf('/') + 1);
        return normalized.length() <= 255
                ? normalized : normalized.substring(normalized.length() - 255);
    }

    private String calculateSha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    digest.update(buffer, 0, read);
                }
            }
            StringBuilder result = new StringBuilder();
            for (byte value : digest.digest()) {
                result.append(String.format("%02x", value));
            }
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前JDK不支持SHA-256", exception);
        }
    }

    private String parentHdfsPath(String path) {
        if (path == null || !path.contains("/")) {
            throw new IllegalArgumentException("任务HDFS路径不存在，无法重试");
        }
        return path.substring(0, path.lastIndexOf('/'));
    }

    private String safeMessage(Exception exception) {
        String message = exception.getMessage();
        return message == null || message.isBlank()
                ? exception.getClass().getSimpleName() : message;
    }

    private void cleanupTaskDirectory(Path directory) {
        if (directory == null) {
            return;
        }
        Path normalized = directory.toAbsolutePath().normalize();
        if (!normalized.startsWith(stagingRoot)) {
            return;
        }
        try (Stream<Path> paths = Files.walk(normalized)) {
            paths.sorted(Comparator.reverseOrder()).forEach(this::deleteIfExists);
        } catch (IOException exception) {
            log.warn("Unable to clean import staging directory path={}", normalized);
        }
    }

    private void deleteIfExists(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException exception) {
            log.warn("Unable to delete temporary import file path={}", path);
        }
    }

    private String normalizeBasePath(String path) {
        if (path == null || path.trim().isEmpty() || !path.trim().startsWith("/")) {
            throw new IllegalArgumentException("HDFS基础路径必须是绝对路径");
        }
        String normalized = path.trim();
        return normalized.endsWith("/")
                ? normalized.substring(0, normalized.length() - 1)
                : normalized;
    }

    private long elapsedMillis(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000;
    }
}
