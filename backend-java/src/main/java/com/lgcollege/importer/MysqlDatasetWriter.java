package com.lgcollege.importer;

import java.util.List;
import java.util.Map;

public interface MysqlDatasetWriter {
    String currentDatasetId();
    void stage(String datasetId, long taskId, String sha256, List<NormalizedHouseListing> rows);
    DatasetCounts counts(String datasetId);

    void recordHiveCounts(String datasetId, long hiveRows);

    Map<String, Long> groupedCounts(String datasetId);
    void activate(String datasetId);
    void restore(String datasetId);
    void markFailed(String datasetId);

    record DatasetCounts(long saleRows, long rentRows) {
        public long totalRows() { return saleRows + rentRows; }
    }
}
