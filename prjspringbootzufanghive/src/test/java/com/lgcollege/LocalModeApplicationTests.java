package com.lgcollege;

import com.lgcollege.common.ApiCodes;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles({"test", "local"})
class LocalModeApplicationTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void mysqlBackedHouseApiShouldRemainAvailableWithoutBigDataServices() throws Exception {
        mockMvc.perform(get("/api/houses"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS));
    }

    @Test
    void hiveAnalyticsApiShouldNotBeRegisteredInLocalMode() throws Exception {
        mockMvc.perform(get("/api/analytics/overview"))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/house-imports/1"))
                .andExpect(status().isNotFound());
    }

    @Test
    void capabilitiesShouldReportLocalMode() throws Exception {
        mockMvc.perform(get("/api/system/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.data.mode").value("local"))
                .andExpect(jsonPath("$.data.mysqlEnabled").value(true))
                .andExpect(jsonPath("$.data.bigDataEnabled").value(false));
    }

    @Test
    void actuatorHealthShouldRemainUpWithoutHive() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
