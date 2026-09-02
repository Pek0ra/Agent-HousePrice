package com.lgcollege.service.impl;

import com.lgcollege.analytics.MysqlHouseStatisticsRepository;
import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import com.lgcollege.service.HouseStatisticsService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class HouseStatisticsServiceImpl implements HouseStatisticsService {
    private final MysqlHouseStatisticsRepository repository;

    public HouseStatisticsServiceImpl(MysqlHouseStatisticsRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public AnalyticsOverview overview(String month, String city) {
        return repository.overview(normalizeMonth(month), trimToNull(city));
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public List<RegionAverage> regionAverages(
            String month, String city, int limit) {
        return repository.regionAverages(
                normalizeMonth(month), trimToNull(city), requireRange(limit, 1, 50, "limit"));
    }

    @Override
    @Transactional(readOnly = true, transactionManager = "mysqlTransactionManager")
    public List<PriceTrend> priceTrends(String city, int months) {
        return repository.priceTrends(
                trimToNull(city), requireRange(months, 1, 60, "months"));
    }

    private String normalizeMonth(String value) {
        String month = trimToNull(value);
        if (month != null && !month.matches("\\d{4}-(0[1-9]|1[0-2])")) {
            throw new IllegalArgumentException("month必须使用yyyy-MM格式");
        }
        return month;
    }

    private int requireRange(int value, int min, int max, String field) {
        if (value < min || value > max) {
            throw new IllegalArgumentException(field + "必须在" + min + "到" + max + "之间");
        }
        return value;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
