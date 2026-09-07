---
id: import_data_quality
title: 房源 CSV 导入质量口径
keywords: 数据质量,质量分,导入任务,缺失,非法,重复,Hive
requires_clarification: false
---

Hive 数据质量查询使用 `v_agent_house_data_quality_summary`，该视图只暴露当前已激活数据集。`total_rows` 是 CSV 数据行数，`valid_rows` 是规范化成功行数，`sale_rows` 和 `rent_rows` 分别是出售与出租数量。`missing_location_rows`、`invalid_price_rows`、`invalid_area_rows`、`duplicate_source_rows` 表示对应错误数，`quality_score` 为 0 到 100。失败或未激活的数据集不得参与当前质量结论。
