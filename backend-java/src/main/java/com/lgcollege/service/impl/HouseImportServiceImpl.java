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
import com.lgcollege.importer.MysqlDatasetWriter;
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
import java.util.Comparator;
import java.util.UUID;
import java.util.stream.Stream;

@Service
@ConditionalOnProperty(prefix = "app.big-data", name = "enabled", havingValue = "true")
public class HouseImportServiceImpl implements HouseImportService {
    private static final Logger log = LoggerFactory.getLogger(HouseImportServiceImpl.class);

    private final HouseImportTaskStore taskStore;
    private final ImportTaskStateMachine stateMachine;
    private final HouseCsvValidator csvValidator;
    private final MysqlDatasetWriter mysqlWriter;
    private final HdfsStorage hdfsStorage;
    private final HiveImportLoader hiveLoader;
    private final String hdfsBasePath;
    private final Path stagingRoot;
    private final long maxFileSizeBytes;
    private final int maxRetries;

    public HouseImportServiceImpl(
            HouseImportTaskStore taskStore,
            ImportTaskStateMachine stateMachine,
            HouseCsvValidator csvValidator,
            MysqlDatasetWriter mysqlWriter,
            HdfsStorage hdfsStorage,
            HiveImportLoader hiveLoader,
            @Value("${app.hdfs.base-path}") String hdfsBasePath,
            @Value("${app.import.staging-path}") String stagingPath,
            @Value("${app.import.max-file-size-bytes:52428800}") long maxFileSizeBytes,
            @Value("${app.import.max-retries:2}") int maxRetries) {
        this.taskStore = taskStore;
        this.stateMachine = stateMachine;
        this.csvValidator = csvValidator;
        this.mysqlWriter = mysqlWriter;
        this.hdfsStorage = hdfsStorage;
        this.hiveLoader = hiveLoader;
        this.hdfsBasePath = normalizeBasePath(hdfsBasePath);
        this.stagingRoot = Path.of(stagingPath).toAbsolutePath().normalize();
        this.maxFileSizeBytes = maxFileSizeBytes;
        this.maxRetries = maxRetries;
    }

    @Override
    public HouseImportTask importCsv(MultipartFile file) {
        validateUpload(file);
        Path incoming = null;
        HouseImportTask task = null;
        try {
            Files.createDirectories(stagingRoot);
            incoming = Files.createTempFile(stagingRoot, "incoming-", ".csv");
            file.transferTo(incoming);
            String sha256 = calculateSha256(incoming);
            HouseImportTask duplicate = taskStore.findSuccessfulByHash(sha256);
            if (duplicate != null) {
                throw new DuplicateImportException(duplicate.getId());
            }

            Path taskDirectory = Files.createTempDirectory(stagingRoot, "task-");
            Path source = taskDirectory.resolve("source.csv");
            Files.move(incoming, source, StandardCopyOption.REPLACE_EXISTING);
            incoming = null;
            String datasetId = UUID.randomUUID().toString();
            task = taskStore.create(safeOriginalFilename(file.getOriginalFilename()), file.getSize(),
                    sha256, source.toString(), datasetId, mysqlWriter.currentDatasetId());
            log.info("Created house import taskId={} datasetId={} file={} sha256={}",
                    task.getId(), datasetId, task.getOriginalFilename(), sha256);
            return runPipeline(task, ImportTaskStatus.PENDING, source);
        } catch (DuplicateImportException | ImportPipelineException exception) {
            throw exception;
        } catch (Exception exception) {
            if (task != null) {
                failTask(task, ImportTaskStatus.PENDING, 0, 0, 0, exception, null);
            }
            throw new IllegalStateException("Unable to create import task: " + safeMessage(exception), exception);
        } finally {
            deleteIfExists(incoming);
        }
    }

    @Override
    public HouseImportTask retry(Long id) {
        HouseImportTask task = requireTask(id);
        if (task.getStatus() != ImportTaskStatus.FAILED) {
            throw new IllegalArgumentException("Only FAILED import tasks can be retried");
        }
        if (task.getFailureStage() == ImportTaskStatus.VALIDATING || task.getFailureStage() == ImportTaskStatus.PENDING) {
            throw new IllegalArgumentException("Validation failures require a corrected CSV upload");
        }
        if (value(task.getRetryCount()) >= maxRetries) {
            throw new IllegalArgumentException("Maximum retry count reached: " + maxRetries);
        }
        Path source = requireStagingFile(task);
        stateMachine.transition(id, ImportTaskStatus.FAILED, ImportTaskStatus.RETRYING);
        return runPipeline(taskStore.findById(id), ImportTaskStatus.RETRYING, source);
    }

    @Override
    public HouseImportTask activateDataset(Long id) {
        HouseImportTask task = requireTask(id);
        if (task.getStatus() != ImportTaskStatus.SUCCESS || !"MATCHED".equals(task.getReconciliationStatus())) {
            throw new IllegalArgumentException("Only a reconciled SUCCESS dataset can be activated");
        }
        String previous = mysqlWriter.currentDatasetId();
        try {
            hiveLoader.activate(task.getDatasetId());
            mysqlWriter.activate(task.getDatasetId());
            return taskStore.findById(id);
        } catch (Exception exception) {
            compensateActivation(previous);
            throw new IllegalStateException("Dataset activation failed: " + safeMessage(exception), exception);
        }
    }

    @Override
    public HouseImportTask findTask(Long id) {
        return requireTask(id);
    }

    @Override
    public Path findErrorReport(Long id) {
        HouseImportTask task = requireTask(id);
        if (task.getErrorReportPath() == null) return null;
        Path report = Path.of(task.getErrorReportPath()).toAbsolutePath().normalize();
        return report.startsWith(stagingRoot) && Files.isRegularFile(report) ? report : null;
    }

    private HouseImportTask runPipeline(HouseImportTask task, ImportTaskStatus initial, Path source) {
        ImportTaskStatus current = initial;
        long total = 0;
        long valid = 0;
        long failed = 0;
        long mysqlRows = 0;
        long hiveRows = 0;
        long hiveAnalysisRows = 0;
        Path taskDirectory = source.getParent();
        Path errorReport = taskDirectory.resolve("errors.csv");
        Path normalized = taskDirectory.resolve("normalized.csv");
        boolean activationStarted = false;
        long startedAt = System.nanoTime();
        try {
            stateMachine.transition(task.getId(), current, ImportTaskStatus.VALIDATING);
            current = ImportTaskStatus.VALIDATING;
            CsvValidationResult validation = csvValidator.validate(source, errorReport, normalized);
            total = validation.getTotalRows();
            valid = validation.getSuccessRows();
            failed = validation.getFailedRows();
            deleteIfExists(errorReport);

            String hdfsDirectory = hdfsBasePath + "/" + task.getDatasetId();
            String hdfsPath = hdfsDirectory + "/house_listings.csv";
            taskStore.updateDetails(task.getId(), total, valid, failed, hdfsPath, null, source.toString());

            stateMachine.transition(task.getId(), current, ImportTaskStatus.LOADING_MYSQL);
            current = ImportTaskStatus.LOADING_MYSQL;
            mysqlWriter.stage(task.getDatasetId(), task.getId(), task.getFileSha256(), validation.getListings());
            MysqlDatasetWriter.DatasetCounts mysqlCounts = mysqlWriter.counts(task.getDatasetId());
            mysqlRows = mysqlCounts.totalRows();
            taskStore.updateReconciliation(task.getId(), valid, mysqlRows, 0, 0, "PENDING");

            stateMachine.transition(task.getId(), current, ImportTaskStatus.UPLOADING_HDFS);
            current = ImportTaskStatus.UPLOADING_HDFS;
            hdfsStorage.upload(validation.getNormalizedFile(), hdfsPath, true);

            stateMachine.transition(task.getId(), current, ImportTaskStatus.LOADING_HIVE);
            current = ImportTaskStatus.LOADING_HIVE;
            hiveLoader.load(task.getId(), task.getDatasetId(), hdfsDirectory);

            stateMachine.transition(task.getId(), current, ImportTaskStatus.COMPACTING_HIVE);
            current = ImportTaskStatus.COMPACTING_HIVE;
            HiveImportLoader.HiveDatasetCounts hiveCounts = hiveLoader.counts(task.getDatasetId());
            hiveRows = hiveCounts.detailRows();
            hiveAnalysisRows = hiveCounts.analysisRows();
            taskStore.updateReconciliation(task.getId(), valid, mysqlRows,
                    hiveRows, hiveAnalysisRows, "PENDING");

            stateMachine.transition(task.getId(), current, ImportTaskStatus.VERIFYING);
            current = ImportTaskStatus.VERIFYING;
            reconcile(validation, mysqlCounts, hiveCounts);
            if (!mysqlWriter.groupedCounts(task.getDatasetId()).equals(hiveLoader.groupedCounts(task.getDatasetId()))) {
                throw new IllegalStateException("Dataset grouped reconciliation failed for listing_type/city/month");
            }
            mysqlWriter.recordHiveCounts(task.getDatasetId(), hiveCounts.detailRows());
            taskStore.updateReconciliation(task.getId(), valid, mysqlCounts.totalRows(),
                    hiveCounts.detailRows(), hiveCounts.analysisRows(), "MATCHED");

            stateMachine.transition(task.getId(), current, ImportTaskStatus.ACTIVATING);
            current = ImportTaskStatus.ACTIVATING;
            activationStarted = true;
            hiveLoader.activate(task.getDatasetId());
            mysqlWriter.activate(task.getDatasetId());

            stateMachine.succeed(task.getId(), current);
            cleanupTaskDirectory(taskDirectory);
            log.info("House import succeeded taskId={} datasetId={} rows={} elapsedMs={}",
                    task.getId(), task.getDatasetId(), valid, elapsedMillis(startedAt));
            return taskStore.findById(task.getId());
        } catch (CsvValidationException exception) {
            failTask(task, current, exception.getTotalRows(), exception.getSuccessRows(),
                    exception.getFailedRows(), exception, errorReport.toString());
            throw new ImportPipelineException(task.getId(), exception.getMessage(), exception);
        } catch (Exception exception) {
            if (activationStarted) compensateActivation(task.getPreviousDatasetId());
            try { mysqlWriter.markFailed(task.getDatasetId()); }
            catch (RuntimeException cleanupException) {
                log.error("Unable to mark staged dataset failed datasetId={}", task.getDatasetId(), cleanupException);
            }
            try { taskStore.updateReconciliation(task.getId(), valid, mysqlRows,
                    hiveRows, hiveAnalysisRows, "FAILED"); }
            catch (RuntimeException reconciliationException) {
                log.error("Unable to persist failed reconciliation taskId={}", task.getId(), reconciliationException);
            }
            failTask(task, current, total, valid, failed, exception,
                    Files.exists(errorReport) ? errorReport.toString() : null);
            throw new ImportPipelineException(task.getId(), safeMessage(exception), exception);
        }
    }

    private void reconcile(CsvValidationResult csv, MysqlDatasetWriter.DatasetCounts mysql,
                           HiveImportLoader.HiveDatasetCounts hive) {
        boolean matched = csv.getSuccessRows() == mysql.totalRows()
                && csv.getSuccessRows() == hive.detailRows()
                && csv.getSuccessRows() == hive.analysisRows()
                && csv.getSaleRows() == mysql.saleRows()
                && csv.getRentRows() == mysql.rentRows()
                && csv.getSaleRows() == hive.saleRows()
                && csv.getRentRows() == hive.rentRows();
        if (!matched) {
            throw new IllegalStateException("Dataset reconciliation failed: csv=" + csv.getSuccessRows()
                    + ", mysql=" + mysql.totalRows() + ", hiveDetail=" + hive.detailRows()
                    + ", hiveAnalysis=" + hive.analysisRows());
        }
    }

    private void compensateActivation(String previousDatasetId) {
        try { hiveLoader.restore(previousDatasetId); }
        catch (RuntimeException exception) {
            log.error("Hive activation compensation failed previousDatasetId={}", previousDatasetId, exception);
        }
        try { mysqlWriter.restore(previousDatasetId); }
        catch (RuntimeException exception) {
            log.error("MySQL activation compensation failed previousDatasetId={}", previousDatasetId, exception);
        }
    }

    private void failTask(HouseImportTask task, ImportTaskStatus current, long total, long valid,
                          long failed, Exception exception, String errorReportPath) {
        stateMachine.fail(task.getId(), current, total, valid, failed,
                safeMessage(exception), errorReportPath);
        log.warn("House import failed taskId={} datasetId={} stage={} message={}",
                task.getId(), task.getDatasetId(), current, safeMessage(exception));
    }

    private HouseImportTask requireTask(Long id) {
        if (id == null || id <= 0) throw new IllegalArgumentException("id must be positive");
        HouseImportTask task = taskStore.findById(id);
        if (task == null) throw new ResourceNotFoundException("Import task does not exist, id=" + id);
        return task;
    }

    private Path requireStagingFile(HouseImportTask task) {
        if (task.getStagingPath() == null) throw new IllegalArgumentException("Staged source file is unavailable");
        Path path = Path.of(task.getStagingPath()).toAbsolutePath().normalize();
        if (!path.startsWith(stagingRoot) || !Files.isRegularFile(path)) {
            throw new IllegalArgumentException("Staged source file is unavailable");
        }
        return path;
    }

    private void validateUpload(MultipartFile file) {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("CSV file must not be empty");
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".csv")) {
            throw new IllegalArgumentException("Only .csv files are accepted");
        }
        if (file.getSize() > maxFileSizeBytes) {
            throw new IllegalArgumentException("CSV exceeds size limit: " + maxFileSizeBytes + " bytes");
        }
    }

    private String safeOriginalFilename(String filename) {
        String normalized = filename == null ? "unknown.csv" : filename.replace('\\', '/');
        normalized = normalized.substring(normalized.lastIndexOf('/') + 1);
        return normalized.length() <= 255 ? normalized : normalized.substring(normalized.length() - 255);
    }

    private String calculateSha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
            }
            StringBuilder result = new StringBuilder();
            for (byte value : digest.digest()) result.append(String.format("%02x", value));
            return result.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private void cleanupTaskDirectory(Path directory) {
        if (directory == null) return;
        Path normalized = directory.toAbsolutePath().normalize();
        if (!normalized.startsWith(stagingRoot)) return;
        try (Stream<Path> paths = Files.walk(normalized)) {
            paths.sorted(Comparator.reverseOrder()).forEach(this::deleteIfExists);
        } catch (IOException exception) {
            log.warn("Unable to clean import staging directory path={}", normalized);
        }
    }

    private void deleteIfExists(Path path) {
        if (path == null) return;
        try { Files.deleteIfExists(path); }
        catch (IOException exception) { log.warn("Unable to delete temporary import file path={}", path); }
    }

    private String normalizeBasePath(String path) {
        if (path == null || path.isBlank() || !path.trim().startsWith("/")) {
            throw new IllegalArgumentException("HDFS base path must be absolute");
        }
        String normalized = path.trim();
        return normalized.endsWith("/") ? normalized.substring(0, normalized.length() - 1) : normalized;
    }

    private int value(Integer number) { return number == null ? 0 : number; }
    private String safeMessage(Exception exception) {
        return exception.getMessage() == null || exception.getMessage().isBlank()
                ? exception.getClass().getSimpleName() : exception.getMessage();
    }
    private long elapsedMillis(long startedAt) { return (System.nanoTime() - startedAt) / 1_000_000; }
}
