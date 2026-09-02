package com.lgcollege;

import com.lgcollege.dto.analytics.AnalyticsOverview;
import com.lgcollege.dto.analytics.CompactionResult;
import com.lgcollege.dto.analytics.DataQualitySummary;
import com.lgcollege.dto.analytics.PriceTrend;
import com.lgcollege.dto.analytics.RegionAverage;
import com.lgcollege.service.HouseAnalyticsService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Collections;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class HouseAnalyticsControllerTests {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private HouseAnalyticsService analyticsService;

    @Test
    void analyticsEndpointsShouldReturnStableDashboardContract() throws Exception {
        when(analyticsService.overview("2026-07", "上海市"))
                .thenReturn(new AnalyticsOverview(
                        120, 1, 3,
                        new BigDecimal("420.50"),
                        new BigDecimal("61234.56"),
                        new BigDecimal("82.30"),
                        LocalDate.of(2026, 7, 20)));
        when(analyticsService.regionAverages("2026-07", "上海市", 10))
                .thenReturn(Collections.singletonList(new RegionAverage(
                        "上海市", "浦东新区", 80,
                        new BigDecimal("500.00"),
                        new BigDecimal("68000.00"),
                        new BigDecimal("78.00"))));
        when(analyticsService.priceTrends("上海市", 12))
                .thenReturn(Collections.singletonList(new PriceTrend(
                        "2026-07", 120,
                        new BigDecimal("420.50"),
                        new BigDecimal("61234.56"))));
        when(analyticsService.qualitySummaries(10))
                .thenReturn(Collections.singletonList(new DataQualitySummary(
                        "2026-07-26", 15, 100, 98,
                        1, 0, 0, 1, new BigDecimal("98.00"))));

        mockMvc.perform(get("/api/analytics/overview")
                        .param("month", "2026-07")
                        .param("city", "上海市"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.listingCount").value(120))
                .andExpect(jsonPath("$.data.averageUnitPrice").value(61234.56));

        mockMvc.perform(get("/api/analytics/regions")
                        .param("month", "2026-07")
                        .param("city", "上海市"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].district").value("浦东新区"));

        mockMvc.perform(get("/api/analytics/price-trends")
                        .param("city", "上海市"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].month").value("2026-07"));

        mockMvc.perform(get("/api/analytics/quality"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].qualityScore").value(98.00));
    }

    @Test
    void compactionEndpointShouldReturnMaintenanceResult() throws Exception {
        when(analyticsService.compact())
                .thenReturn(new CompactionResult(
                        "SUCCESS", 1350, "house_info_analysis"));

        mockMvc.perform(post("/api/analytics/maintenance/compact"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.targetTable")
                        .value("house_info_analysis"));
    }
}
