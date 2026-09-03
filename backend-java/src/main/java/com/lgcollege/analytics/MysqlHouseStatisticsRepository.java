package com.lgcollege.analytics;

import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Date;
import java.util.ArrayList;
import java.util.List;

@Repository
public class MysqlHouseStatisticsRepository {
    private final JdbcTemplate jdbcTemplate;

    public MysqlHouseStatisticsRepository(
            @Qualifier("mysqlDataSource") DataSource mysqlDataSource) {
        this.jdbcTemplate = new JdbcTemplate(mysqlDataSource);
    }

    public AnalyticsOverview overview(String month, String city) {
        FilterSql filter = filter(month, city);
        String sql = "SELECT COUNT(*), COUNT(DISTINCT city), "
                + "COUNT(DISTINCT CONCAT_WS(CHAR(1), city, district)), "
                + "AVG(total_price), AVG(unit_price), AVG(area), MAX(listing_date) "
                + "FROM house_info" + filter.whereClause();
        return jdbcTemplate.queryForObject(
                sql,
                (result, rowNumber) -> {
                    Date latestDate = result.getDate(7);
                    return new AnalyticsOverview(
                            result.getLong(1),
                            result.getLong(2),
                            result.getLong(3),
                            decimal(result.getBigDecimal(4)),
                            decimal(result.getBigDecimal(5)),
                            decimal(result.getBigDecimal(6)),
                            latestDate == null ? null : latestDate.toLocalDate());
                },
                filter.parameters().toArray());
    }

    public List<RegionAverage> regionAverages(
            String month, String city, int limit) {
        FilterSql filter = filter(month, city);
        String sql = "SELECT city, district, COUNT(*), AVG(total_price), "
                + "AVG(unit_price), AVG(area) FROM house_info"
                + filter.whereClause()
                + " GROUP BY city, district ORDER BY AVG(unit_price) DESC LIMIT " + limit;
        return jdbcTemplate.query(
                sql,
                (result, rowNumber) -> new RegionAverage(
                        result.getString(1),
                        result.getString(2),
                        result.getLong(3),
                        decimal(result.getBigDecimal(4)),
                        decimal(result.getBigDecimal(5)),
                        decimal(result.getBigDecimal(6))),
                filter.parameters().toArray());
    }

    public List<PriceTrend> priceTrends(String city, int months) {
        List<Object> parameters = new ArrayList<>();
        String cityCondition = "";
        if (city != null) {
            cityCondition = " AND city = ?";
            parameters.add(city);
        }
        String sql = "SELECT listing_month, listing_count, avg_total_price, avg_unit_price "
                + "FROM (SELECT DATE_FORMAT(listing_date, '%Y-%m') listing_month, "
                + "COUNT(*) listing_count, AVG(total_price) avg_total_price, "
                + "AVG(unit_price) avg_unit_price FROM house_info "
                + "WHERE deleted = 0 AND listing_date IS NOT NULL" + cityCondition
                + " GROUP BY DATE_FORMAT(listing_date, '%Y-%m') "
                + "ORDER BY listing_month DESC LIMIT " + months
                + ") recent_months ORDER BY listing_month";
        return jdbcTemplate.query(
                sql,
                (result, rowNumber) -> new PriceTrend(
                        result.getString(1),
                        result.getLong(2),
                        decimal(result.getBigDecimal(3)),
                        decimal(result.getBigDecimal(4))),
                parameters.toArray());
    }

    private FilterSql filter(String month, String city) {
        List<String> conditions = new ArrayList<>();
        List<Object> parameters = new ArrayList<>();
        conditions.add("deleted = 0");
        if (month != null) {
            conditions.add("DATE_FORMAT(listing_date, '%Y-%m') = ?");
            parameters.add(month);
        }
        if (city != null) {
            conditions.add("city = ?");
            parameters.add(city);
        }
        return new FilterSql(" WHERE " + String.join(" AND ", conditions), parameters);
    }

    private BigDecimal decimal(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value.setScale(2, RoundingMode.HALF_UP);
    }

    private record FilterSql(String whereClause, List<Object> parameters) {
    }
}
