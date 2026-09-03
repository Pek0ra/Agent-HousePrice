DROP TABLE IF EXISTS house_info;
DROP TABLE IF EXISTS house_import_task;

CREATE TABLE house_info (
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_record_id        VARCHAR(100),
    title                   VARCHAR(200),
    city                    VARCHAR(50) NOT NULL,
    district                VARCHAR(50) NOT NULL,
    community               VARCHAR(100) NOT NULL,
    address                 VARCHAR(255),
    total_price             DECIMAL(12, 2) NOT NULL,
    unit_price              DECIMAL(12, 2) NOT NULL,
    area                    DECIMAL(10, 2) NOT NULL,
    bedroom_count           INT,
    living_room_count       INT,
    layout                  VARCHAR(50),
    orientation             VARCHAR(30),
    floor_description       VARCHAR(50),
    floor_level             VARCHAR(20),
    total_floors            INT,
    decoration              VARCHAR(20),
    surrounding_description VARCHAR(500),
    listing_date            DATE,
    data_source             VARCHAR(50) NOT NULL,
    import_task_id          BIGINT,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted                 TINYINT NOT NULL DEFAULT 0,
    CONSTRAINT uk_house_source_record UNIQUE (data_source, source_record_id)
);

CREATE TABLE house_import_task (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    original_filename VARCHAR(255) NOT NULL,
    file_size         BIGINT NOT NULL,
    file_sha256       CHAR(64),
    status            VARCHAR(30) NOT NULL,
    total_rows        BIGINT NOT NULL DEFAULT 0,
    success_rows      BIGINT NOT NULL DEFAULT 0,
    failed_rows       BIGINT NOT NULL DEFAULT 0,
    hdfs_path         VARCHAR(500),
    error_report_path VARCHAR(500),
    failure_stage     VARCHAR(30),
    retry_count       INT NOT NULL DEFAULT 0,
    staging_path      VARCHAR(500),
    error_message     VARCHAR(1000),
    started_at        TIMESTAMP,
    finished_at       TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    successful_sha256 CHAR(64) GENERATED ALWAYS AS (
        CASE WHEN status = 'SUCCESS' THEN file_sha256 ELSE NULL END
    ),
    CONSTRAINT uk_import_success_sha256 UNIQUE (successful_sha256)
);
