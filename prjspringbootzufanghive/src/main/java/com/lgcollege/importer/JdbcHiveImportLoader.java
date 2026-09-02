package com.lgcollege.importer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.LocalDate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class JdbcHiveImportLoader implements HiveImportLoader {
    private static final Logger log = LoggerFactory.getLogger(JdbcHiveImportLoader.class);
    private final DataSource hiveDataSource;
    private final String rawTable;
    private final String detailTable;
    private final String qualityTable;
    private final int queryTimeoutSeconds;

    public JdbcHiveImportLoader(
            @Qualifier("hiveDataSource") DataSource hiveDataSource,
            @Value("${app.hive.raw-table}") String rawTable,
            @Value("${app.hive.detail-table}") String detailTable,
            @Value("${app.hive.quality-table}") String qualityTable,
            @Value("${app.hive.query-timeout-seconds:300}") int queryTimeoutSeconds) {
        this.hiveDataSource = hiveDataSource;
        this.rawTable = requireSafeIdentifier(rawTable);
        this.detailTable = requireSafeIdentifier(detailTable);
        this.qualityTable = requireSafeIdentifier(qualityTable);
        this.queryTimeoutSeconds = queryTimeoutSeconds;
    }

    @Override
    public void load(Long taskId, LocalDate importDate, String hdfsDirectory) {
        long startedAt = System.nanoTime();
        String safeLocation = hdfsDirectory.replace("'", "''");
        String addPartition = "ALTER TABLE " + rawTable +
                " ADD IF NOT EXISTS PARTITION (import_task_id=" + taskId + ")" +
                " LOCATION '" + safeLocation + "'";
        String insertDetail = buildInsertSql(taskId, importDate);
        String insertQuality = buildQualitySql(taskId, importDate);

        try (Connection connection = hiveDataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(queryTimeoutSeconds);
            statement.execute(addPartition);
            statement.execute(insertDetail);
            statement.execute(insertQuality);
            log.info("Hive import completed taskId={} elapsedMs={}",
                    taskId, (System.nanoTime() - startedAt) / 1_000_000);
        } catch (SQLException exception) {
            throw new IllegalStateException("Hive加载失败：" + exception.getMessage(), exception);
        }
    }

    private String buildInsertSql(Long taskId, LocalDate importDate) {
        return "INSERT OVERWRITE TABLE " + detailTable +
                " PARTITION (import_date='" + importDate + "', import_task_id=" + taskId + ") " +
                "SELECT source_record_id, title, city, district, community, address, " +
                "CAST(total_price AS DECIMAL(12,2)), " +
                "CAST((CAST(total_price AS DECIMAL(12,2)) * 10000) / " +
                "CAST(area AS DECIMAL(10,2)) AS DECIMAL(12,2)), " +
                "CAST(area AS DECIMAL(10,2)), " +
                "CAST(NULLIF(TRIM(bedroom_count), '') AS INT), " +
                "CAST(NULLIF(TRIM(living_room_count), '') AS INT), " +
                "layout, orientation, floor_description, floor_level, " +
                "CAST(NULLIF(TRIM(total_floors), '') AS INT), decoration, " +
                "surrounding_description, " +
                "CAST(NULLIF(TRIM(listing_date), '') AS DATE), data_source " +
                "FROM " + rawTable + " WHERE import_task_id=" + taskId;
    }

    private String buildQualitySql(Long taskId, LocalDate importDate) {
        String validCondition =
                "TRIM(city) <> '' AND TRIM(district) <> '' AND " +
                "TRIM(community) <> '' AND " +
                "CAST(total_price AS DECIMAL(12,2)) > 0 AND " +
                "CAST(area AS DECIMAL(10,2)) > 0";
        String keyedRows =
                "CASE WHEN TRIM(source_record_id) <> '' AND TRIM(data_source) <> '' " +
                "THEN 1 ELSE 0 END";
        String distinctKey =
                "CASE WHEN TRIM(source_record_id) <> '' AND TRIM(data_source) <> '' " +
                "THEN CONCAT(data_source, '\\u0001', source_record_id) ELSE NULL END";
        return "INSERT OVERWRITE TABLE " + qualityTable +
                " PARTITION (import_date='" + importDate + "', import_task_id=" + taskId + ") " +
                "SELECT COUNT(1), " +
                "SUM(CASE WHEN " + validCondition + " THEN 1 ELSE 0 END), " +
                "SUM(CASE WHEN TRIM(city) = '' OR TRIM(district) = '' OR " +
                "TRIM(community) = '' THEN 1 ELSE 0 END), " +
                "SUM(CASE WHEN CAST(total_price AS DECIMAL(12,2)) IS NULL OR " +
                "CAST(total_price AS DECIMAL(12,2)) <= 0 THEN 1 ELSE 0 END), " +
                "SUM(CASE WHEN CAST(area AS DECIMAL(10,2)) IS NULL OR " +
                "CAST(area AS DECIMAL(10,2)) <= 0 THEN 1 ELSE 0 END), " +
                "SUM(" + keyedRows + ") - COUNT(DISTINCT " + distinctKey + "), " +
                "CAST(CASE WHEN COUNT(1) = 0 THEN 0 ELSE " +
                "100.0 * SUM(CASE WHEN " + validCondition + " THEN 1 ELSE 0 END) " +
                "/ COUNT(1) END AS DECIMAL(5,2)) " +
                "FROM " + rawTable + " WHERE import_task_id=" + taskId;
    }

    private String requireSafeIdentifier(String value) {
        if (value == null || !value.matches("[A-Za-z_][A-Za-z0-9_]*")) {
            throw new IllegalArgumentException("非法Hive表名：" + value);
        }
        return value;
    }
}
