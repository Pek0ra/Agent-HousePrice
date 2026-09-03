package com.lgcollege.service;

import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;

import java.util.List;

public interface HouseStatisticsService {
    AnalyticsOverview overview(String month, String city);

    List<RegionAverage> regionAverages(String month, String city, int limit);

    List<PriceTrend> priceTrends(String city, int months);
}
