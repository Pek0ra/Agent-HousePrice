package com.lgcollege.controller;

import com.lgcollege.common.ApiResponse;
import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import com.lgcollege.service.HouseStatisticsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/statistics")
public class HouseStatisticsController {
    private final HouseStatisticsService statisticsService;

    public HouseStatisticsController(HouseStatisticsService statisticsService) {
        this.statisticsService = statisticsService;
    }

    @GetMapping("/overview")
    public ApiResponse<AnalyticsOverview> overview(
            @RequestParam(required = false) String month,
            @RequestParam(required = false) String city) {
        return ApiResponse.success(statisticsService.overview(month, city));
    }

    @GetMapping("/regions")
    public ApiResponse<List<RegionAverage>> regions(
            @RequestParam(required = false) String month,
            @RequestParam(required = false) String city,
            @RequestParam(defaultValue = "10") int limit) {
        return ApiResponse.success(statisticsService.regionAverages(month, city, limit));
    }

    @GetMapping("/price-trends")
    public ApiResponse<List<PriceTrend>> priceTrends(
            @RequestParam(required = false) String city,
            @RequestParam(defaultValue = "12") int months) {
        return ApiResponse.success(statisticsService.priceTrends(city, months));
    }
}
