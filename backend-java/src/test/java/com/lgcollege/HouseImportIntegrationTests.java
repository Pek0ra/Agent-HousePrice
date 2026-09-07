package com.lgcollege;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lgcollege.common.ApiCodes;
import com.lgcollege.importer.HdfsStorage;
import com.lgcollege.importer.HiveImportLoader;
import com.lgcollege.importer.MysqlDatasetWriter;
import org.junit.jupiter.api.BeforeEach;
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
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
            "source_record_id,listing_type,title,city,district,community,address,total_price," +
            "unit_price,monthly_rent,area,bedroom_count,living_room_count,layout,orientation," +
            "floor_description,floor_level,total_floors,decoration,surrounding_description," +
            "listing_date,data_source\r\n";

    @Autowired private MockMvc mockMvc;
    @MockBean private HdfsStorage hdfsStorage;
    @MockBean private HiveImportLoader hiveLoader;
    @MockBean private MysqlDatasetWriter mysqlWriter;

    @BeforeEach
    void configureWriters() {
        when(mysqlWriter.currentDatasetId()).thenReturn(null);
        when(mysqlWriter.counts(anyString())).thenReturn(new MysqlDatasetWriter.DatasetCounts(1, 0));
        when(hiveLoader.counts(anyString())).thenReturn(new HiveImportLoader.HiveDatasetCounts(1, 1, 1, 0));
        when(mysqlWriter.groupedCounts(anyString())).thenReturn(Map.of("SALE|上海市|2026-07", 1L));
        when(hiveLoader.groupedCounts(anyString())).thenReturn(Map.of("SALE|上海市|2026-07", 1L));
        doNothing().when(hdfsStorage).upload(any(), anyString(), anyBoolean());
        doNothing().when(hiveLoader).load(anyLong(), anyString(), anyString());
    }

    @Test
    void validCsvStagesReconcilesAndActivatesOneDataset() throws Exception {
        String response = mockMvc.perform(multipart("/api/house-imports").file(csvFile(HEADER + validSale("CSV-001"))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value(ApiCodes.SUCCESS))
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.reconciliationStatus").value("MATCHED"))
                .andExpect(jsonPath("$.data.mysqlRows").value(1))
                .andExpect(jsonPath("$.data.hiveRows").value(1))
                .andExpect(jsonPath("$.data.datasetId").isNotEmpty())
                .andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("id").asLong();
        String datasetId = new ObjectMapper().readTree(response).path("data").path("datasetId").asText();

        verify(mysqlWriter).stage(org.mockito.ArgumentMatchers.eq(datasetId),
                org.mockito.ArgumentMatchers.eq(taskId), anyString(), any());
        verify(hdfsStorage).upload(any(), org.mockito.ArgumentMatchers.endsWith("/house_listings.csv"),
                org.mockito.ArgumentMatchers.eq(true));
        verify(hiveLoader).load(taskId, datasetId, "/data/house/normalized/" + datasetId);
        verify(hiveLoader).activate(datasetId);
        verify(mysqlWriter).activate(datasetId);
    }

    @Test
    void rentCsvIsWrittenToBothStores() throws Exception {
        when(mysqlWriter.counts(anyString())).thenReturn(new MysqlDatasetWriter.DatasetCounts(0, 1));
        when(hiveLoader.counts(anyString())).thenReturn(new HiveImportLoader.HiveDatasetCounts(1, 1, 0, 1));
        when(mysqlWriter.groupedCounts(anyString())).thenReturn(Map.of("RENT|深圳市|2026-02", 1L));
        when(hiveLoader.groupedCounts(anyString())).thenReturn(Map.of("RENT|深圳市|2026-02", 1L));
        String rent = "CSV-RENT,RENT,中文出租,深圳市,南山区,测试小区,,,,9000,68,2,1,2室1厅," +
                ",,,,,,2026-02-01,TEST\r\n";
        mockMvc.perform(multipart("/api/house-imports").file(csvFile("\uFEFF" + HEADER + rent)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.mysqlRows").value(1));
    }

    @Test
    void mixedCsvRequiresSaleRentCountsToMatch() throws Exception {
        when(mysqlWriter.counts(anyString())).thenReturn(new MysqlDatasetWriter.DatasetCounts(1, 1));
        when(hiveLoader.counts(anyString())).thenReturn(new HiveImportLoader.HiveDatasetCounts(2, 2, 1, 1));
        when(mysqlWriter.groupedCounts(anyString())).thenReturn(Map.of(
                "SALE|上海市|2026-07", 1L, "RENT|深圳市|2026-02", 1L));
        when(hiveLoader.groupedCounts(anyString())).thenReturn(Map.of(
                "SALE|上海市|2026-07", 1L, "RENT|深圳市|2026-02", 1L));
        String rent = "CSV-R,RENT,出租,深圳市,福田区,测试小区,,,,8000,66,2,1,2室1厅," +
                ",,,,,,2026-02-01,TEST\r\n";
        mockMvc.perform(multipart("/api/house-imports").file(csvFile(HEADER + validSale("CSV-S") + rent)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.validRows").value(2))
                .andExpect(jsonPath("$.data.reconciliationStatus").value("MATCHED"));
    }

    @Test
    void invalidCsvPersistsFailureAndDoesNotTouchExternalStores() throws Exception {
        String bad = "CSV-002,SALE,错误房源,,浦东新区,测试小区,示例路1号,-1,,,0," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,精装,近地铁,bad-date,PUBLIC_DATASET\r\n";
        String response = mockMvc.perform(multipart("/api/house-imports").file(csvFile(HEADER + bad)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value(ApiCodes.IMPORT_FAILED))
                .andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("taskId").asLong();

        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("FAILED"))
                .andExpect(jsonPath("$.data.failureStage").value("VALIDATING"))
                .andExpect(jsonPath("$.data.errorReportAvailable").value(true));
        verifyNoInteractions(hdfsStorage, hiveLoader);
        verify(mysqlWriter, never()).stage(anyString(), anyLong(), anyString(), any());
    }

    @Test
    void hdfsFailureKeepsOldDatasetAndCanRetryIdempotently() throws Exception {
        doThrow(new IllegalStateException("HDFS unavailable")).doNothing()
                .when(hdfsStorage).upload(any(), anyString(), anyBoolean());
        String response = mockMvc.perform(multipart("/api/house-imports").file(csvFile(HEADER + validSale("CSV-003"))))
                .andExpect(status().isUnprocessableEntity()).andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("taskId").asLong();

        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("FAILED"))
                .andExpect(jsonPath("$.data.mysqlRows").value(1))
                .andExpect(jsonPath("$.data.hiveRows").value(0));
        verify(hiveLoader, never()).activate(anyString());
        verify(mysqlWriter, never()).activate(anyString());

        mockMvc.perform(post("/api/house-imports/{id}/retry", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"))
                .andExpect(jsonPath("$.data.retryCount").value(1));
    }

    @Test
    void hiveFailureDoesNotExposeStagedMysqlRowsAndCanRetry() throws Exception {
        doThrow(new IllegalStateException("Hive unavailable")).doNothing()
                .when(hiveLoader).load(anyLong(), anyString(), anyString());
        String response = mockMvc.perform(multipart("/api/house-imports")
                        .file(csvFile(HEADER + validSale("CSV-HIVE-FAIL"))))
                .andExpect(status().isUnprocessableEntity()).andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("taskId").asLong();

        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.failureStage").value("LOADING_HIVE"))
                .andExpect(jsonPath("$.data.mysqlRows").value(1));
        verify(hiveLoader, never()).activate(anyString());
        verify(mysqlWriter, never()).activate(anyString());

        mockMvc.perform(post("/api/house-imports/{id}/retry", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("SUCCESS"));
    }

    @Test
    void mysqlStageFailureDoesNotCallHdfsHiveOrActivation() throws Exception {
        doThrow(new IllegalStateException("MySQL writer unavailable"))
                .when(mysqlWriter).stage(anyString(), anyLong(), anyString(), any());
        String response = mockMvc.perform(multipart("/api/house-imports")
                        .file(csvFile(HEADER + validSale("CSV-MYSQL-FAIL"))))
                .andExpect(status().isUnprocessableEntity()).andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("taskId").asLong();

        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.failureStage").value("LOADING_MYSQL"));
        verifyNoInteractions(hdfsStorage, hiveLoader);
        verify(mysqlWriter, never()).activate(anyString());
    }

    @Test
    void groupedReconciliationMismatchPreventsActivation() throws Exception {
        when(hiveLoader.groupedCounts(anyString())).thenReturn(Map.of());
        String response = mockMvc.perform(multipart("/api/house-imports")
                        .file(csvFile(HEADER + validSale("CSV-GROUP-MISMATCH"))))
                .andExpect(status().isUnprocessableEntity()).andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(response).path("data").path("taskId").asLong();
        mockMvc.perform(get("/api/house-imports/{id}", taskId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.failureStage").value("VERIFYING"))
                .andExpect(jsonPath("$.data.reconciliationStatus").value("FAILED"));
        verify(hiveLoader, never()).activate(anyString());
        verify(mysqlWriter, never()).activate(anyString());
    }

    @Test
    void duplicateSuccessfulFileIsRejected() throws Exception {
        MockMultipartFile file = csvFile(HEADER + validSale("CSV-004"));
        String first = mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        long taskId = new ObjectMapper().readTree(first).path("data").path("id").asLong();
        mockMvc.perform(multipart("/api/house-imports").file(file))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.data.existingTaskId").value(taskId));
    }

    @Test
    void templateUsesUnifiedSchemaAndMissingTaskIs404() throws Exception {
        mockMvc.perform(get("/api/house-imports/template"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("house_listings_import_template.csv")))
                .andExpect(content().string(org.hamcrest.Matchers.containsString(
                        "source_record_id,listing_type,title")));
        mockMvc.perform(get("/api/house-imports/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(ApiCodes.RESOURCE_NOT_FOUND));
    }

    private MockMultipartFile csvFile(String content) {
        return new MockMultipartFile("file", "houses.csv", "text/csv", content.getBytes(StandardCharsets.UTF_8));
    }

    private String validSale(String id) {
        return id + ",SALE,测试房源,上海市,浦东新区,测试小区,示例路1号,300.00,50000,,60.00," +
                "2,1,2室1厅,SOUTH,中楼层,MIDDLE,18,精装,近地铁,2026-07-01,PUBLIC_DATASET\r\n";
    }
}
