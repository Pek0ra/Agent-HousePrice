CREATE EXTERNAL TABLE IF NOT EXISTS house_info_raw (
    source_record_id        STRING,
    title                   STRING,
    city                    STRING,
    district                STRING,
    community               STRING,
    address                 STRING,
    total_price             STRING,
    area                    STRING,
    bedroom_count           STRING,
    living_room_count       STRING,
    layout                  STRING,
    orientation             STRING,
    floor_description       STRING,
    floor_level             STRING,
    total_floors            STRING,
    decoration              STRING,
    surrounding_description STRING,
    listing_date            STRING,
    data_source             STRING
)
PARTITIONED BY (import_task_id BIGINT)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
    "separatorChar" = ",",
    "quoteChar" = "\"",
    "escapeChar" = "\\"
)
STORED AS TEXTFILE
TBLPROPERTIES ("skip.header.line.count" = "1");

CREATE TABLE IF NOT EXISTS house_info_detail (
    source_record_id        STRING,
    title                   STRING,
    city                    STRING,
    district                STRING,
    community               STRING,
    address                 STRING,
    total_price             DECIMAL(12, 2),
    unit_price              DECIMAL(12, 2),
    area                    DECIMAL(10, 2),
    bedroom_count           INT,
    living_room_count       INT,
    layout                  STRING,
    orientation             STRING,
    floor_description       STRING,
    floor_level             STRING,
    total_floors            INT,
    decoration              STRING,
    surrounding_description STRING,
    listing_date            DATE,
    data_source             STRING
)
PARTITIONED BY (import_date STRING, import_task_id BIGINT)
STORED AS ORC
TBLPROPERTIES (
    "orc.compress" = "SNAPPY"
);
