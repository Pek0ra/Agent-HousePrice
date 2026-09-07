package com.lgcollege.importer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;
import java.util.TreeMap;

@Component
@ConditionalOnProperty(prefix="app.big-data", name="enabled", havingValue="true")
public class JdbcHiveImportLoader implements HiveImportLoader {
    private final DataSource dataSource;
    private final int timeout;

    public JdbcHiveImportLoader(
            @Qualifier("hiveDataSource") DataSource dataSource,
            @Value("${app.hive.query-timeout-seconds:300}") int timeout) {
        this.dataSource = dataSource;
        this.timeout = timeout;
    }

    @Override
    public void load(Long taskId, String datasetId, String hdfsDirectory) {
        String id = safeDatasetId(datasetId);
        String location = hdfsDirectory.replace("'", "''");
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(timeout);
            statement.execute("ALTER TABLE house_info_raw DROP IF EXISTS PARTITION(dataset_id='"+id+"',import_task_id="+taskId+")");
            statement.execute("ALTER TABLE house_info_raw ADD PARTITION(dataset_id='"+id+"',import_task_id="+taskId+") LOCATION '"+location+"'");
            statement.execute(detailSql(taskId, id));
            statement.execute(analysisSql(id));
            statement.execute(qualitySql(taskId, id));
        } catch (SQLException exception) {
            throw new IllegalStateException("Hive 加载失败：" + exception.getMessage(), exception);
        }
    }

    private String detailSql(long taskId, String id) {
        return "INSERT OVERWRITE TABLE house_info_detail PARTITION(dataset_id='"+id+"') " +
                "SELECT source_record_id,listing_type,title,city,district,community,address,"+
                "CAST(NULLIF(total_price,'') AS DECIMAL(12,2)),CAST(NULLIF(unit_price,'') AS DECIMAL(12,2)),"+
                "CAST(NULLIF(monthly_rent,'') AS DECIMAL(12,2)),CAST(area AS DECIMAL(10,2)),"+
                "CAST(NULLIF(bedroom_count,'') AS INT),CAST(NULLIF(living_room_count,'') AS INT),layout,orientation,"+
                "floor_description,floor_level,CAST(NULLIF(total_floors,'') AS INT),decoration,surrounding_description,"+
                "CAST(listing_date AS DATE),data_source,"+taskId+" FROM house_info_raw " +
                "WHERE dataset_id='"+id+"' AND import_task_id="+taskId;
    }

    private String analysisSql(String id) {
        return "INSERT OVERWRITE TABLE house_info_analysis PARTITION(dataset_id='"+id+"',listing_month) " +
                "SELECT source_record_id,listing_type,title,city,district,community,total_price,unit_price,monthly_rent,"+
                "area,bedroom_count,living_room_count,layout,orientation,floor_level,total_floors,decoration,listing_date,"+
                "data_source,source_import_task_id,date_format(listing_date,'yyyy-MM') FROM house_info_detail WHERE dataset_id='"+id+"'";
    }

    private String qualitySql(long taskId, String id) {
        return "INSERT OVERWRITE TABLE house_data_quality_summary PARTITION(dataset_id='"+id+"',import_task_id="+taskId+") " +
                "SELECT COUNT(*),COUNT(*),SUM(CASE WHEN listing_type='SALE' THEN 1 ELSE 0 END),"+
                "SUM(CASE WHEN listing_type='RENT' THEN 1 ELSE 0 END),0,0,0,0,"+
                "CAST(CASE WHEN COUNT(*)=0 THEN 0 ELSE 100 END AS DECIMAL(5,2)) FROM house_info_detail WHERE dataset_id='"+id+"'";
    }

    @Override
    public HiveDatasetCounts counts(String datasetId) {
        String id = safeDatasetId(datasetId);
        String sql = "SELECT COUNT(*),"+
                "SUM(CASE WHEN listing_type='SALE' THEN 1 ELSE 0 END),"+
                "SUM(CASE WHEN listing_type='RENT' THEN 1 ELSE 0 END) FROM house_info_analysis WHERE dataset_id='"+id+"'";
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(timeout);
            long analysis;
            long sale;
            long rent;
            try (ResultSet result = statement.executeQuery(sql)) {
                result.next();
                analysis = result.getLong(1);
                sale = result.getLong(2);
                rent = result.getLong(3);
            }
            long detail = scalar(statement, "SELECT COUNT(*) FROM house_info_detail WHERE dataset_id='"+id+"'");
            return new HiveDatasetCounts(detail, analysis, sale, rent);
        } catch (SQLException exception) {
            throw new IllegalStateException("Hive 对账失败：" + exception.getMessage(), exception);
        }
    }

    @Override
    public Map<String, Long> groupedCounts(String datasetId) {
        String id = safeDatasetId(datasetId);
        String sql = "SELECT listing_type,city,listing_month,COUNT(*) FROM house_info_analysis " +
                "WHERE dataset_id='" + id + "' GROUP BY listing_type,city,listing_month";
        Map<String, Long> result = new TreeMap<>();
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(timeout);
            try (ResultSet rows = statement.executeQuery(sql)) {
                while (rows.next()) {
                    result.put(rows.getString(1) + "|" + rows.getString(2) + "|" + rows.getString(3), rows.getLong(4));
                }
            }
            return result;
        } catch (SQLException exception) {
            throw new IllegalStateException("Hive grouped reconciliation failed: " + exception.getMessage(), exception);
        }
    }

    @Override public void activate(String datasetId) { replaceActivation(datasetId); }
    @Override public void restore(String datasetId) { replaceActivation(datasetId); }

    private void replaceActivation(String datasetId) {
        String select = datasetId == null
                ? "SELECT CAST(NULL AS STRING),CURRENT_TIMESTAMP WHERE 1=0"
                : "SELECT '"+safeDatasetId(datasetId)+"',CURRENT_TIMESTAMP";
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(timeout);
            statement.execute("INSERT OVERWRITE TABLE house_active_dataset " + select);
        } catch (SQLException exception) {
            throw new IllegalStateException("Hive 数据集激活失败：" + exception.getMessage(), exception);
        }
    }

    private long scalar(Statement statement, String sql) throws SQLException {
        try (ResultSet result = statement.executeQuery(sql)) { result.next(); return result.getLong(1); }
    }

    private String safeDatasetId(String value) {
        if (value == null || !value.matches("[0-9a-fA-F-]{36}")) throw new IllegalArgumentException("非法 dataset_id");
        return value;
    }
}
