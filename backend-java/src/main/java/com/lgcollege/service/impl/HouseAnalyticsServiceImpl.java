package com.lgcollege.service.impl;

import com.lgcollege.analytics.HouseAnalyticsRepository;
import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.CompactionResult;
import com.lgcollege.dto.analytics.DataQualitySummary;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import com.lgcollege.service.HouseAnalyticsService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
public class HouseAnalyticsServiceImpl implements HouseAnalyticsService {
    private static final Logger log = LoggerFactory.getLogger(HouseAnalyticsServiceImpl.class);
    private final HouseAnalyticsRepository repository;

    public HouseAnalyticsServiceImpl(HouseAnalyticsRepository repository) {
        this.repository = repository;
    }

    @Override
    public AnalyticsOverview overview(String month, String city) {
        return repository.overview(normalizeMonth(month), trimToNull(city));
    }

    @Override
    public List<RegionAverage> regionAverages(
            String month, String city, int limit) {
        return repository.regionAverages(
                normalizeMonth(month), trimToNull(city), requireRange(limit, 1, 50, "limit"));
    }

    @Override
    public List<PriceTrend> priceTrends(String city, int months) {
        return repository.priceTrends(
                trimToNull(city), requireRange(months, 1, 60, "months"));
    }

    @Override
    public List<DataQualitySummary> qualitySummaries(int limit) {
        return repository.qualitySummaries(requireRange(limit, 1, 100, "limit"));
    }

    @Override
    public CompactionResult compact() {
        log.info("Hive analysis compaction started");
        CompactionResult result = repository.compactAnalysisTable();
        log.info("Hive analysis compaction completed elapsedMs={}", result.elapsedMillis());
        return result;
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
            throw new IllegalArgumentException(
                    field + "必须在" + min + "到" + max + "之间");
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
