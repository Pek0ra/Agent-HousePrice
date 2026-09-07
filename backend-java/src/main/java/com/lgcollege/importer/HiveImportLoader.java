package com.lgcollege.importer;

import java.util.Map;

public interface HiveImportLoader {
    void load(Long taskId, String datasetId, String hdfsDirectory);
    HiveDatasetCounts counts(String datasetId);

    Map<String, Long> groupedCounts(String datasetId);
    void activate(String datasetId);
    void restore(String datasetId);

    record HiveDatasetCounts(long detailRows, long analysisRows, long saleRows, long rentRows) { }
}
