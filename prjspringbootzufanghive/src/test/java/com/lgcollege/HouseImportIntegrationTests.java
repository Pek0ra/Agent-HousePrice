package com.lgcollege;

import com.lgcollege.common.ApiCodes;
import com.lgcollege.importer.HdfsStorage;
import com.lgcollege.importer.HiveImportLoader;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;
import java.time.LocalDate;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Sql(scripts = "/schema-h2.sql", executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class HouseImportIntegrationTests {
    private static final String HEADER =
            "source_record_id,title,city,district,community,address,total_price,area," +
            "bedroom_count,living_room_count,layout,orientation,floor_description," +
            "floor_level,total_floors,decoration,surrounding_description,listing_date," +
            "data_source\r\n";

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private HdfsStorage hdfsStorage;

    @MockBean
    private HiveImportLoader hiveImportLoader;

    @Test
    void validCsvShouldCompleteHdfsAndHivePipeline() throws Exception {
        doNothing().when(hdfsStorage).upload(any(), anyString(), anyBoolean());
        doNothing().when(hiveImportLoader).load(anyLong(), any(), anyString());
        MockMultipartFile file = csvFile(
                HEADER +
                "CSV-001,测试房源,上海市,浦东新区,测试小区,示例路1号,300.00,60.00," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,REFINED,近地铁," +
                "2026-07-01,PUBLIC_DATASET\r\n");

        String response = mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.totalRows").value(1))
                .andExpect(jsonPath("$.data.successRows").value(1))
                .andExpect(jsonPath("$.data.failedRows").value(0))
                .andExpect(jsonPath("$.data.fileSha256").isNotEmpty())
                .andExpect(jsonPath("$.data.hdfsPath").isNotEmpty())
                .andReturn().getResponse().getContentAsString();

        long taskId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response).path("data").path("id").asLong();
        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"));

        verify(hdfsStorage).upload(
                any(), org.mockito.ArgumentMatchers.contains("task-" + taskId),
                org.mockito.ArgumentMatchers.eq(true));
        verify(hiveImportLoader).load(
                org.mockito.ArgumentMatchers.eq(taskId),
                any(LocalDate.class),
                org.mockito.ArgumentMatchers.contains("task-" + taskId));
    }

    @Test
    void invalidCsvShouldPersistFailedTaskAndSkipExternalSystems() throws Exception {
        MockMultipartFile file = csvFile(
                HEADER +
                "CSV-002,错误房源,,浦东新区,测试小区,示例路1号,-1,0," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,REFINED,近地铁," +
                "bad-date,PUBLIC_DATASET\r\n");

        String response = mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value(ApiCodes.IMPORT_FAILED))
                .andExpect(jsonPath("$.data.taskId").isNumber())
                .andReturn().getResponse().getContentAsString();

        long taskId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response).path("data").path("taskId").asLong();
        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("FAILED"))
                .andExpect(jsonPath("$.data.totalRows").value(1))
                .andExpect(jsonPath("$.data.failedRows").value(1))
                .andExpect(jsonPath("$.data.errorMessage").isNotEmpty())
                .andExpect(jsonPath("$.data.errorReportAvailable").value(true));

        mockMvc.perform(get("/api/house-imports/{id}/errors", taskId))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString("row_number,error_message")))
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString("city不能为空")));

        verifyNoInteractions(hdfsStorage, hiveImportLoader);
    }

    @Test
    void wrongHeaderAndFileTypeShouldBeRejected() throws Exception {
        MockMultipartFile wrongHeader = csvFile("city,total_price\r\n上海市,300\r\n");
        mockMvc.perform(multipart("/api/house-imports").file(wrongHeader))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value(ApiCodes.IMPORT_FAILED));

        MockMultipartFile textFile = new MockMultipartFile(
                "file", "houses.txt", "text/plain",
                "not csv".getBytes(StandardCharsets.UTF_8));
        mockMvc.perform(multipart("/api/house-imports").file(textFile))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.BUSINESS_ERROR));
    }

    @Test
    void hdfsFailureShouldRemainQueryableAndSkipHive() throws Exception {
        doThrow(new IllegalStateException("HDFS unavailable"))
                .doNothing()
                .when(hdfsStorage).upload(any(), anyString(), anyBoolean());
        MockMultipartFile file = csvFile(
                HEADER +
                "CSV-003,HDFS失败房源,上海市,浦东新区,测试小区,示例路1号,300.00,60.00," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,REFINED,近地铁," +
                "2026-07-01,PUBLIC_DATASET\r\n");

        String response = mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value(ApiCodes.IMPORT_FAILED))
                .andReturn().getResponse().getContentAsString();

        long taskId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response).path("data").path("taskId").asLong();
        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("FAILED"))
                .andExpect(jsonPath("$.data.totalRows").value(1))
                .andExpect(jsonPath("$.data.successRows").value(1))
                .andExpect(jsonPath("$.data.errorMessage").value("HDFS unavailable"));

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .post("/api/house-imports/{id}/retry", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.retryCount").value(1));
    }

    @Test
    void successfulHashShouldRejectDuplicateUpload() throws Exception {
        MockMultipartFile file = csvFile(
                HEADER +
                "CSV-004,防重房源,上海市,浦东新区,测试小区,示例路1号,300.00,60.00," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,REFINED,近地铁," +
                "2026-07-01,PUBLIC_DATASET\r\n");

        String first = mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        long firstTaskId = new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(first).path("data").path("id").asLong();

        mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(ApiCodes.DUPLICATE_IMPORT))
                .andExpect(jsonPath("$.data.existingTaskId").value(firstTaskId));
    }

    @Test
    void serviceFileSizeLimitShouldRejectOversizedCsv() throws Exception {
        byte[] oversized = new byte[1025];
        MockMultipartFile file = new MockMultipartFile(
                "file", "large.csv", "text/csv", oversized);

        mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(ApiCodes.BUSINESS_ERROR))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.containsString("超过业务限制")));
    }

    @Test
    void templateAndMissingTaskShouldHaveStableResponses() throws Exception {
        mockMvc.perform(get("/api/house-imports/template"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Content-Disposition",
                        org.hamcrest.Matchers.containsString(
                                "house_info_import_template.csv")))
                .andExpect(content().contentTypeCompatibleWith("text/csv"))
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString("source_record_id,title,city")));

        mockMvc.perform(get("/api/house-imports/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(ApiCodes.RESOURCE_NOT_FOUND));
    }

    private MockMultipartFile csvFile(String content) {
        return new MockMultipartFile(
                "file", "houses.csv", "text/csv",
                content.getBytes(StandardCharsets.UTF_8));
    }
}
