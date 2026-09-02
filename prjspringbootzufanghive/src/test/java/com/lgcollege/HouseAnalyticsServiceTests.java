package com.lgcollege;

import com.lgcollege.analytics.HouseAnalyticsRepository;
import com.lgcollege.service.impl.HouseAnalyticsServiceImpl;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class HouseAnalyticsServiceTests {
    private final HouseAnalyticsServiceImpl service =
            new HouseAnalyticsServiceImpl(mock(HouseAnalyticsRepository.class));

    @Test
    void shouldRejectInvalidMonthAndUnsafeLimitsBeforeHiveQuery() {
        assertThatThrownBy(() -> service.overview("2026-13", null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("month必须使用yyyy-MM格式");

        assertThatThrownBy(() -> service.regionAverages(null, null, 51))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("limit必须在");

        assertThatThrownBy(() -> service.priceTrends(null, 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("months必须在");
    }
}
