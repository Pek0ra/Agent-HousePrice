package com.lgcollege.controller;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.CompactionResult;
import com.lgcollege.dto.analytics.DataQualitySummary;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import com.lgcollege.service.HouseAnalyticsService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@ConditionalOnProperty(
        prefix = "app.big-data", name = "enabled",
        havingValue = "true", matchIfMissing = false)
@RequestMapping("/api/analytics")
public class HouseAnalyticsController {
    private final HouseAnalyticsService analyticsService;

    public HouseAnalyticsController(HouseAnalyticsService analyticsService) {
        this.analyticsService = analyticsService;
    }

    @GetMapping("/overview")
    public ApiResponse<AnalyticsOverview> overview(
            @RequestParam(required = false) String month,
            @RequestParam(required = false) String city) {
        return ApiResponse.success(analyticsService.overview(month, city));
    }

    @GetMapping("/regions")
    public ApiResponse<List<RegionAverage>> regions(
            @RequestParam(required = false) String month,
            @RequestParam(required = false) String city,
            @RequestParam(defaultValue = "10") int limit) {
        return ApiResponse.success(
                analyticsService.regionAverages(month, city, limit));
    }

    @GetMapping("/price-trends")
    public ApiResponse<List<PriceTrend>> priceTrends(
            @RequestParam(required = false) String city,
            @RequestParam(defaultValue = "12") int months) {
        return ApiResponse.success(analyticsService.priceTrends(city, months));
    }

    @GetMapping("/quality")
    public ApiResponse<List<DataQualitySummary>> quality(
            @RequestParam(defaultValue = "10") int limit) {
        return ApiResponse.success(analyticsService.qualitySummaries(limit));
    }

    @PostMapping("/maintenance/compact")
    public ApiResponse<CompactionResult> compact() {
        return ApiResponse.success(analyticsService.compact());
    }
}
