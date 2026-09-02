package com.lgcollege.service;

import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.CompactionResult;
import com.lgcollege.dto.analytics.DataQualitySummary;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;

import java.util.List;

public interface HouseAnalyticsService {
    AnalyticsOverview overview(String month, String city);

    List<RegionAverage> regionAverages(String month, String city, int limit);

    List<PriceTrend> priceTrends(String city, int months);

    List<DataQualitySummary> qualitySummaries(int limit);

    CompactionResult compact();
}
