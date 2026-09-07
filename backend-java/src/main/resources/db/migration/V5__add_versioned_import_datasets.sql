SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE house_dataset (
    dataset_id          CHAR(36)      NOT NULL,
    import_task_id      BIGINT        NOT NULL,
    file_sha256         CHAR(64)      NOT NULL,
    status              VARCHAR(20)   NOT NULL DEFAULT 'STAGED',
    sale_rows           BIGINT        NOT NULL DEFAULT 0,
    rent_rows           BIGINT        NOT NULL DEFAULT 0,
    mysql_rows          BIGINT        NOT NULL DEFAULT 0,
    hive_rows           BIGINT        NOT NULL DEFAULT 0,
    activated_at        DATETIME      NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (dataset_id),
    UNIQUE KEY uk_house_dataset_task (import_task_id),
    KEY idx_house_dataset_status_created (status, created_at),
    CONSTRAINT chk_house_dataset_status CHECK (status IN ('STAGED','ACTIVE','ARCHIVED','FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='版本化房源数据集';

CREATE TABLE house_dataset_state (
    singleton_id       TINYINT      NOT NULL,
    active_dataset_id  CHAR(36)     NULL,
    updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (singleton_id),
    CONSTRAINT chk_house_dataset_state_singleton CHECK (singleton_id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='当前激活房源数据集指针';

INSERT INTO house_dataset_state(singleton_id, active_dataset_id)
VALUES (1, NULL)
ON DUPLICATE KEY UPDATE singleton_id = VALUES(singleton_id);

ALTER TABLE house_import_task
    ADD COLUMN dataset_id CHAR(36) NULL AFTER file_sha256,
    ADD COLUMN import_mode VARCHAR(20) NOT NULL DEFAULT 'REPLACE' AFTER dataset_id,
    ADD COLUMN valid_rows BIGINT NOT NULL DEFAULT 0 AFTER total_rows,
    ADD COLUMN mysql_rows BIGINT NOT NULL DEFAULT 0 AFTER failed_rows,
    ADD COLUMN hive_rows BIGINT NOT NULL DEFAULT 0 AFTER mysql_rows,
    ADD COLUMN hive_analysis_rows BIGINT NOT NULL DEFAULT 0 AFTER hive_rows,
    ADD COLUMN reconciliation_status VARCHAR(20) NULL AFTER hive_analysis_rows,
    ADD COLUMN previous_dataset_id CHAR(36) NULL AFTER reconciliation_status,
    ADD UNIQUE KEY uk_import_dataset_id (dataset_id),
    ADD CONSTRAINT chk_import_mode CHECK (import_mode IN ('REPLACE'));

ALTER TABLE house_info
    DROP INDEX uk_house_source_record,
    ADD COLUMN dataset_id CHAR(36) NULL AFTER import_task_id,
    ADD COLUMN dataset_scope VARCHAR(40)
        GENERATED ALWAYS AS (COALESCE(dataset_id, '__MANUAL__')) STORED,
    ADD UNIQUE KEY uk_house_dataset_source (dataset_scope, data_source, source_record_id),
    ADD KEY idx_house_dataset_active (dataset_id, deleted, listing_date);

ALTER TABLE rental_listing
    DROP INDEX uk_rental_source_record,
    ADD COLUMN address VARCHAR(255) NULL AFTER community,
    ADD COLUMN unit_price DECIMAL(12,2) NULL AFTER monthly_rent,
    ADD COLUMN orientation VARCHAR(30) NULL AFTER layout,
    ADD COLUMN floor_description VARCHAR(50) NULL AFTER orientation,
    ADD COLUMN floor_level VARCHAR(20) NULL AFTER floor_description,
    ADD COLUMN total_floors INT NULL AFTER floor_level,
    ADD COLUMN decoration VARCHAR(20) NULL AFTER total_floors,
    ADD COLUMN surrounding_description VARCHAR(500) NULL AFTER decoration,
    ADD COLUMN import_task_id BIGINT NULL AFTER data_source,
    ADD COLUMN dataset_id CHAR(36) NULL AFTER import_task_id,
    ADD COLUMN dataset_scope VARCHAR(40)
        GENERATED ALWAYS AS (COALESCE(dataset_id, '__MANUAL__')) STORED,
    ADD UNIQUE KEY uk_rental_dataset_source (dataset_scope, data_source, source_record_id),
    ADD KEY idx_rental_dataset_active (dataset_id, deleted, listing_date),
    ADD CONSTRAINT chk_rental_unit_price_empty CHECK (unit_price IS NULL),
    ADD CONSTRAINT chk_rental_total_floors CHECK (total_floors IS NULL OR total_floors > 0);

CREATE OR REPLACE VIEW v_agent_house_listing AS
SELECT 'SALE' AS listing_type, h.city, h.district, h.community,
       h.total_price, h.unit_price, CAST(NULL AS DECIMAL(12,2)) AS monthly_rent,
       h.area, h.bedroom_count, h.living_room_count, h.layout,
       h.listing_date, h.data_source
FROM house_info h
JOIN house_dataset_state s ON s.singleton_id = 1 AND s.active_dataset_id = h.dataset_id
WHERE h.deleted = 0
UNION ALL
SELECT 'RENT', r.city, r.district, r.community,
       CAST(NULL AS DECIMAL(12,2)), CAST(NULL AS DECIMAL(12,2)), r.monthly_rent,
       r.area, r.bedroom_count, r.living_room_count, r.layout,
       r.listing_date, r.data_source
FROM rental_listing r
JOIN house_dataset_state s ON s.singleton_id = 1 AND s.active_dataset_id = r.dataset_id
WHERE r.deleted = 0;

CREATE OR REPLACE VIEW v_agent_district_summary AS
SELECT listing_type, city, district, COUNT(*) AS listing_count,
       ROUND(AVG(total_price),2) avg_total_price, ROUND(MIN(total_price),2) min_total_price,
       ROUND(MAX(total_price),2) max_total_price, ROUND(AVG(unit_price),2) avg_unit_price,
       ROUND(MIN(unit_price),2) min_unit_price, ROUND(MAX(unit_price),2) max_unit_price,
       ROUND(AVG(monthly_rent),2) avg_monthly_rent,
       ROUND(MIN(monthly_rent),2) min_monthly_rent,
       ROUND(MAX(monthly_rent),2) max_monthly_rent
FROM v_agent_house_listing
GROUP BY listing_type, city, district;

CREATE OR REPLACE VIEW v_agent_monthly_price_trend AS
SELECT listing_type, city, district, DATE_FORMAT(listing_date, '%Y-%m') listing_month,
       COUNT(*) listing_count, ROUND(AVG(total_price),2) avg_total_price,
       ROUND(AVG(unit_price),2) avg_unit_price,
       ROUND(AVG(monthly_rent),2) avg_monthly_rent
FROM v_agent_house_listing
WHERE listing_date IS NOT NULL
GROUP BY listing_type, city, district, DATE_FORMAT(listing_date, '%Y-%m');

