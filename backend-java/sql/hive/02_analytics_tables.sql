-- Upgrade an existing detail table created before SNAPPY was configured.
ALTER TABLE house_info_detail SET TBLPROPERTIES ("orc.compress" = "SNAPPY");

-- DWS analysis layer: task-level detail files are compacted into month partitions.
CREATE TABLE IF NOT EXISTS house_info_analysis (
    source_record_id        STRING,
    title                   STRING,
    city                    STRING,
    district                STRING,
    community               STRING,
    total_price             DECIMAL(12, 2),
    unit_price              DECIMAL(12, 2),
    area                    DECIMAL(10, 2),
    bedroom_count           INT,
    living_room_count       INT,
    layout                  STRING,
    orientation             STRING,
    floor_level             STRING,
    total_floors            INT,
    decoration              STRING,
    listing_date            DATE,
    data_source             STRING,
    source_import_task_id   BIGINT
)
PARTITIONED BY (listing_month STRING)
STORED AS ORC
TBLPROPERTIES (
    "orc.compress" = "SNAPPY"
);

-- DQ summary: one overwrite-safe partition for each import task.
CREATE TABLE IF NOT EXISTS house_data_quality_summary (
    total_rows               BIGINT,
    valid_rows               BIGINT,
    missing_location_rows    BIGINT,
    invalid_price_rows       BIGINT,
    invalid_area_rows        BIGINT,
    duplicate_source_rows    BIGINT,
    quality_score            DECIMAL(5, 2)
)
PARTITIONED BY (import_date STRING, import_task_id BIGINT)
STORED AS ORC
TBLPROPERTIES (
    "orc.compress" = "SNAPPY"
);

-- Recommended session settings for ORC output and small-file merging.
SET hive.exec.compress.output=true;
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.merge.mapfiles=true;
SET hive.merge.mapredfiles=true;
SET hive.merge.tezfiles=true;
SET hive.merge.size.per.task=268435456;
SET hive.merge.smallfiles.avgsize=16777216;
