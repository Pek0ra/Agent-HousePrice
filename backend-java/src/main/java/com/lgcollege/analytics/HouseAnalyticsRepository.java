package com.lgcollege.analytics;

import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.CompactionResult;
import com.lgcollege.dto.analytics.DataQualitySummary;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Repository
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class HouseAnalyticsRepository {
    private final DataSource hiveDataSource;
    private final String analysisTable;
    private final String detailTable;
    private final String qualityTable;
    private final int queryTimeoutSeconds;

    public HouseAnalyticsRepository(
            @Qualifier("hiveDataSource") DataSource hiveDataSource,
            @Value("${app.hive.analysis-table}") String analysisTable,
            @Value("${app.hive.detail-table}") String detailTable,
            @Value("${app.hive.quality-table}") String qualityTable,
            @Value("${app.hive.query-timeout-seconds:300}") int queryTimeoutSeconds) {
        this.hiveDataSource = hiveDataSource;
        this.analysisTable = safeIdentifier(analysisTable);
        this.detailTable = safeIdentifier(detailTable);
        this.qualityTable = safeIdentifier(qualityTable);
        this.queryTimeoutSeconds = queryTimeoutSeconds;
    }

    public AnalyticsOverview overview(String month, String city) {
        FilterSql filter = filter(month, city);
        String sql = "SELECT COUNT(1), COUNT(DISTINCT city), " +
                "COUNT(DISTINCT CONCAT(city, '\\u0001', district)), " +
                "AVG(total_price), AVG(unit_price), AVG(area), MAX(listing_date) " +
                "FROM " + analysisTable + filter.whereClause();
        try (Connection connection = hiveDataSource.getConnection();
             PreparedStatement statement = prepare(connection, sql, filter.parameters());
             ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return emptyOverview();
            }
            Date latestDate = result.getDate(7);
            return new AnalyticsOverview(
                    result.getLong(1),
                    result.getLong(2),
                    result.getLong(3),
                    decimal(result, 4),
                    decimal(result, 5),
                    decimal(result, 6),
                    latestDate == null ? null : latestDate.toLocalDate());
        } catch (SQLException exception) {
            throw analyticsFailure(exception);
        }
    }

    public List<RegionAverage> regionAverages(
            String month, String city, int limit) {
        FilterSql filter = filter(month, city);
        String sql = "SELECT city, district, COUNT(1), AVG(total_price), " +
                "AVG(unit_price), AVG(area) FROM " + analysisTable +
                filter.whereClause() +
                " GROUP BY city, district ORDER BY AVG(unit_price) DESC LIMIT " + limit;
        List<RegionAverage> rows = new ArrayList<>();
        try (Connection connection = hiveDataSource.getConnection();
             PreparedStatement statement = prepare(connection, sql, filter.parameters());
             ResultSet result = statement.executeQuery()) {
            while (result.next()) {
                rows.add(new RegionAverage(
                        result.getString(1),
                        result.getString(2),
                        result.getLong(3),
                        decimal(result, 4),
                        decimal(result, 5),
                        decimal(result, 6)));
            }
            return rows;
        } catch (SQLException exception) {
            throw analyticsFailure(exception);
        }
    }

    public List<PriceTrend> priceTrends(String city, int months) {
        List<Object> parameters = city == null
                ? Collections.emptyList() : Collections.singletonList(city);
        String where = city == null ? " WHERE listing_type = 'SALE'"
                : " WHERE listing_type = 'SALE' AND city = ?";
        String sql = "SELECT listing_month, listing_count, avg_total_price, " +
                "avg_unit_price FROM (" +
                "SELECT listing_month, COUNT(1) listing_count, " +
                "AVG(total_price) avg_total_price, AVG(unit_price) avg_unit_price " +
                "FROM " + analysisTable + where +
                " GROUP BY listing_month ORDER BY listing_month DESC LIMIT " + months +
                ") recent_months ORDER BY listing_month";
        List<PriceTrend> rows = new ArrayList<>();
        try (Connection connection = hiveDataSource.getConnection();
             PreparedStatement statement = prepare(connection, sql, parameters);
             ResultSet result = statement.executeQuery()) {
            while (result.next()) {
                rows.add(new PriceTrend(
                        result.getString(1),
                        result.getLong(2),
                        decimal(result, 3),
                        decimal(result, 4)));
            }
            return rows;
        } catch (SQLException exception) {
            throw analyticsFailure(exception);
        }
    }

    public List<DataQualitySummary> qualitySummaries(int limit) {
        String sql = "SELECT dataset_id, import_task_id, total_rows, valid_rows, sale_rows, rent_rows, " +
                "missing_location_rows, invalid_price_rows, invalid_area_rows, " +
                "duplicate_source_rows, quality_score FROM " + qualityTable +
                " ORDER BY import_task_id DESC LIMIT " + limit;
        List<DataQualitySummary> rows = new ArrayList<>();
        try (Connection connection = hiveDataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.setQueryTimeout(queryTimeoutSeconds);
            try (ResultSet result = statement.executeQuery(sql)) {
                while (result.next()) {
                    rows.add(new DataQualitySummary(
                            result.getString(1),
                            result.getLong(2),
                            result.getLong(3),
                            result.getLong(4),
                            result.getLong(5),
                            result.getLong(6),
                            result.getLong(7),
                            result.getLong(8),
                            result.getLong(9),
                            result.getLong(10),
                            decimal(result, 11)));
                }
            }
            return rows;
        } catch (SQLException exception) {
            throw analyticsFailure(exception);
        }
    }

    public CompactionResult compactAnalysisTable() {
        // Analysis partitions are rebuilt and reconciled inside every successful import.
        // Keeping this endpoint as a non-destructive compatibility operation prevents
        // an operator from accidentally compacting failed or archived datasets together.
        return new CompactionResult("ALREADY_COMPACTED", 0, analysisTable);
    }

    private FilterSql filter(String month, String city) {
        List<String> conditions = new ArrayList<>();
        conditions.add("listing_type = 'SALE'");
        List<Object> parameters = new ArrayList<>();
        if (month != null) {
            conditions.add("listing_month = ?");
            parameters.add(month);
        }
        if (city != null) {
            conditions.add("city = ?");
            parameters.add(city);
        }
        return new FilterSql(
                conditions.isEmpty() ? "" : " WHERE " + String.join(" AND ", conditions),
                parameters);
    }

    private PreparedStatement prepare(
            Connection connection,
            String sql,
            List<Object> parameters) throws SQLException {
        PreparedStatement statement = connection.prepareStatement(sql);
        statement.setQueryTimeout(queryTimeoutSeconds);
        for (int index = 0; index < parameters.size(); index++) {
            statement.setObject(index + 1, parameters.get(index));
        }
        return statement;
    }

    private BigDecimal decimal(ResultSet result, int column) throws SQLException {
        BigDecimal value = result.getBigDecimal(column);
        return value == null ? BigDecimal.ZERO : value.setScale(2, java.math.RoundingMode.HALF_UP);
    }

    private AnalyticsOverview emptyOverview() {
        return new AnalyticsOverview(
                0, 0, 0,
                BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, null);
    }

    private String safeIdentifier(String value) {
        if (value == null || !value.matches("[A-Za-z_][A-Za-z0-9_]*")) {
            throw new IllegalArgumentException("非法Hive表名：" + value);
        }
        return value;
    }

    private IllegalStateException analyticsFailure(SQLException exception) {
        return new IllegalStateException("Hive分析查询失败：" + exception.getMessage(), exception);
    }

    private record FilterSql(String whereClause, List<Object> parameters) {
    }
}
