package com.lgcollege;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.lgcollege.common.ApiCodes;
import com.lgcollege.common.PageResult;
import com.lgcollege.dto.house.HouseInfoRequest;
import com.lgcollege.dto.house.HouseQuery;
import com.lgcollege.entity.mysql.HouseInfo;
import com.lgcollege.service.HouseInfoService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Sql(scripts = "/schema-h2.sql", executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class HouseInfoCrudIntegrationTests {

    @Autowired
    private HouseInfoService houseInfoService;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void serviceShouldCompleteCrudAndCalculateUnitPrice() {
        HouseInfo created = houseInfoService.create(buildRequest(
                "S-001", "阳光花园", "500.00", "100.00"));

        assertThat(created.getId()).isNotNull();
        assertThat(created.getUnitPrice()).isEqualByComparingTo("50000.00");
        assertThat(houseInfoService.findById(created.getId())).isNotNull();

        HouseInfoRequest updateRequest = buildRequest(
                "S-001", "阳光花园", "600.00", "100.00");
        HouseInfo updated = houseInfoService.update(created.getId(), updateRequest);

        assertThat(updated.getTotalPrice()).isEqualByComparingTo("600.00");
        assertThat(updated.getUnitPrice()).isEqualByComparingTo("60000.00");
        assertThat(houseInfoService.delete(created.getId())).isTrue();
        assertThat(houseInfoService.findById(created.getId())).isNull();
        assertThat(houseInfoService.delete(created.getId())).isFalse();
    }

    @Test
    void serviceShouldFilterAndPageWithStableStructure() {
        houseInfoService.create(buildRequest("S-001", "阳光花园", "500.00", "100.00"));
        houseInfoService.create(buildRequest("S-002", "滨江小区", "300.00", "60.00"));

        HouseQuery query = new HouseQuery();
        query.setCommunity("阳光花园");
        query.setMinUnitPrice(new BigDecimal("45000"));
        query.setMaxUnitPrice(new BigDecimal("55000"));
        query.setPage(1);
        query.setPageSize(10);

        PageResult<HouseInfo> result = houseInfoService.findPage(query);

        assertThat(result.getTotal()).isEqualTo(1);
        assertThat(result.getTotalPages()).isEqualTo(1);
        assertThat(result.getRecords()).extracting(HouseInfo::getCommunity)
                .containsExactly("阳光花园");
    }

    @Test
    void restApiShouldExposeCreateReadUpdateDelete() throws Exception {
        String createJson = objectMapper.writeValueAsString(
                buildRequest("API-001", "接口小区", "400.00", "80.00"));

        String responseBody = mockMvc.perform(post("/api/houses")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createJson))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.message").value("success"))
                .andExpect(jsonPath("$.data.unitPrice").value(50000.00))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode response = objectMapper.readTree(responseBody);
        long id = response.path("data").path("id").asLong();

        mockMvc.perform(get("/api/houses/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.data.community").value("接口小区"));

        String updateJson = objectMapper.writeValueAsString(
                buildRequest("API-001", "接口小区", "480.00", "80.00"));
        mockMvc.perform(put("/api/houses/{id}", id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(updateJson))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.unitPrice").value(60000.00));

        mockMvc.perform(delete("/api/houses/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.data").doesNotExist());
        mockMvc.perform(get("/api/houses/{id}", id))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(ApiCodes.RESOURCE_NOT_FOUND));
    }

    @Test
    void restApiShouldRejectInvalidRequestWithFieldErrors() throws Exception {
        String invalidJson = "{"
                + "\"city\":\"\","
                + "\"district\":\"浦东新区\","
                + "\"community\":\"测试小区\","
                + "\"totalPrice\":-1,"
                + "\"area\":0"
                + "}";

        mockMvc.perform(post("/api/houses")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(invalidJson))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.VALIDATION_ERROR))
                .andExpect(jsonPath("$.message").value("请求参数校验失败"))
                .andExpect(jsonPath("$.data.city").value("城市不能为空"))
                .andExpect(jsonPath("$.data.totalPrice").value("总价必须大于0"))
                .andExpect(jsonPath("$.data.area").value("面积必须大于0"));
    }

    @Test
    void restApiShouldReturnConflictForDuplicateSourceRecord() throws Exception {
        String requestJson = objectMapper.writeValueAsString(
                buildRequest("DUPLICATE-001", "重复小区", "300.00", "60.00"));

        mockMvc.perform(post("/api/houses")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/houses")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(ApiCodes.DUPLICATE_RESOURCE))
                .andExpect(jsonPath("$.message").value("数据已存在，请勿重复提交"));
    }

    @Test
    void restApiShouldValidatePathQueryAndMalformedJson() throws Exception {
        mockMvc.perform(get("/api/houses/0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.VALIDATION_ERROR));

        mockMvc.perform(get("/api/houses")
                        .param("page", "0")
                        .param("pageSize", "101"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.VALIDATION_ERROR))
                .andExpect(jsonPath("$.data.page").value("页码必须大于0"))
                .andExpect(jsonPath("$.data.pageSize").value("每页数量不能超过100"));

        mockMvc.perform(post("/api/houses")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid-json}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.MALFORMED_REQUEST));
    }

    private HouseInfoRequest buildRequest(
            String sourceRecordId,
            String community,
            String totalPrice,
            String area) {
        HouseInfoRequest request = new HouseInfoRequest();
        request.setSourceRecordId(sourceRecordId);
        request.setTitle(community + "房源");
        request.setCity("上海市");
        request.setDistrict("浦东新区");
        request.setCommunity(community);
        request.setAddress("示例路1号");
        request.setTotalPrice(new BigDecimal(totalPrice));
        request.setArea(new BigDecimal(area));
        request.setBedroomCount(3);
        request.setLivingRoomCount(2);
        request.setLayout("3室2厅");
        request.setOrientation("MULTIPLE");
        request.setFloorDescription("中楼层/共18层");
        request.setFloorLevel("MIDDLE");
        request.setTotalFloors(18);
        request.setDecoration("REFINED");
        request.setDataSource("PUBLIC_DATASET");
        return request;
    }
}
