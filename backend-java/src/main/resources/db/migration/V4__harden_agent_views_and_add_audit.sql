SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS agent_query_audit (
    id             BIGINT        NOT NULL AUTO_INCREMENT COMMENT '审计记录主键',
    trace_id       CHAR(36)      NOT NULL COMMENT '单次问数链路编号',
    question       VARCHAR(2000) NOT NULL COMMENT '用户原始问题',
    generated_sql  TEXT          NULL COMMENT '最终生成或被拒绝的SQL',
    status         VARCHAR(30)   NOT NULL COMMENT 'SUCCESS/NO_DATA/CLARIFICATION/REJECTED/FAILED',
    result_rows    INT           NOT NULL DEFAULT 0 COMMENT '返回结果行数',
    repair_count   INT           NOT NULL DEFAULT 0 COMMENT '模型修正SQL次数',
    duration_ms    BIGINT        NOT NULL DEFAULT 0 COMMENT '总处理耗时，毫秒',
    error_summary  VARCHAR(1000) NULL COMMENT '失败摘要',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_audit_trace (trace_id),
    KEY idx_agent_audit_created (created_at),
    KEY idx_agent_audit_status_created (status, created_at)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  COMMENT = 'Agent自然语言问数审计记录';

CREATE OR REPLACE VIEW v_agent_house_listing AS
SELECT 'SALE' AS listing_type, city, district, community,
       total_price, unit_price, CAST(NULL AS DECIMAL(12, 2)) AS monthly_rent,
       area, bedroom_count, living_room_count, layout, listing_date, data_source
FROM house_info
WHERE deleted = 0
UNION ALL
SELECT 'RENT' AS listing_type, city, district, community,
       CAST(NULL AS DECIMAL(12, 2)) AS total_price,
       CAST(NULL AS DECIMAL(12, 2)) AS unit_price,
       monthly_rent, area, bedroom_count, living_room_count, layout,
       listing_date, data_source
FROM rental_listing
WHERE deleted = 0;

CREATE OR REPLACE VIEW v_agent_district_summary AS
SELECT 'SALE' AS listing_type, city, district, COUNT(*) AS listing_count,
       ROUND(AVG(total_price), 2) AS avg_total_price,
       ROUND(MIN(total_price), 2) AS min_total_price,
       ROUND(MAX(total_price), 2) AS max_total_price,
       ROUND(AVG(unit_price), 2) AS avg_unit_price,
       ROUND(MIN(unit_price), 2) AS min_unit_price,
       ROUND(MAX(unit_price), 2) AS max_unit_price,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_monthly_rent,
       CAST(NULL AS DECIMAL(12, 2)) AS min_monthly_rent,
       CAST(NULL AS DECIMAL(12, 2)) AS max_monthly_rent
FROM house_info
WHERE deleted = 0
GROUP BY city, district
UNION ALL
SELECT 'RENT' AS listing_type, city, district, COUNT(*) AS listing_count,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_total_price,
       CAST(NULL AS DECIMAL(12, 2)) AS min_total_price,
       CAST(NULL AS DECIMAL(12, 2)) AS max_total_price,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_unit_price,
       CAST(NULL AS DECIMAL(12, 2)) AS min_unit_price,
       CAST(NULL AS DECIMAL(12, 2)) AS max_unit_price,
       ROUND(AVG(monthly_rent), 2) AS avg_monthly_rent,
       ROUND(MIN(monthly_rent), 2) AS min_monthly_rent,
       ROUND(MAX(monthly_rent), 2) AS max_monthly_rent
FROM rental_listing
WHERE deleted = 0
GROUP BY city, district;

CREATE OR REPLACE VIEW v_agent_monthly_price_trend AS
SELECT 'SALE' AS listing_type, city, district,
       DATE_FORMAT(listing_date, '%Y-%m') AS listing_month,
       COUNT(*) AS listing_count,
       ROUND(AVG(total_price), 2) AS avg_total_price,
       ROUND(AVG(unit_price), 2) AS avg_unit_price,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_monthly_rent
FROM house_info
WHERE deleted = 0 AND listing_date IS NOT NULL
GROUP BY city, district, DATE_FORMAT(listing_date, '%Y-%m')
UNION ALL
SELECT 'RENT' AS listing_type, city, district,
       DATE_FORMAT(listing_date, '%Y-%m') AS listing_month,
       COUNT(*) AS listing_count,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_total_price,
       CAST(NULL AS DECIMAL(12, 2)) AS avg_unit_price,
       ROUND(AVG(monthly_rent), 2) AS avg_monthly_rent
FROM rental_listing
WHERE deleted = 0
GROUP BY city, district, DATE_FORMAT(listing_date, '%Y-%m');

DROP VIEW IF EXISTS agent_house_info;
DROP VIEW IF EXISTS agent_rental_listing;
