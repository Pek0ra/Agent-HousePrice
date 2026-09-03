CREATE DATABASE IF NOT EXISTS mydb
LOCATION 'hdfs:///user/hive/warehouse/mydb.db';

USE mydb;

CREATE EXTERNAL TABLE IF NOT EXISTS house_info_raw (
    source_record_id STRING,
    title STRING,
    city STRING,
    district STRING,
    community STRING,
    address STRING,
    total_price STRING,
    area STRING,
    bedroom_count STRING,
    living_room_count STRING,
    layout STRING,
    orientation STRING,
    floor_description STRING,
    floor_level STRING,
    total_floors STRING,
    decoration STRING,
    surrounding_description STRING,
    listing_date STRING,
    data_source STRING
)
PARTITIONED BY (import_task_id BIGINT)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
    'separatorChar'=',',
    'quoteChar'='"',
    'escapeChar'='\\'
)
STORED AS TEXTFILE
LOCATION 'hdfs:///data/house/raw'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE TABLE IF NOT EXISTS house_info_detail (
    source_record_id STRING,
    title STRING,
    city STRING,
    district STRING,
    community STRING,
    address STRING,
    total_price DECIMAL(12,2),
    unit_price DECIMAL(12,2),
    area DECIMAL(10,2),
    bedroom_count INT,
    living_room_count INT,
    layout STRING,
    orientation STRING,
    floor_description STRING,
    floor_level STRING,
    total_floors INT,
    decoration STRING,
    surrounding_description STRING,
    listing_date DATE,
    data_source STRING
)
PARTITIONED BY (import_date STRING, import_task_id BIGINT)
STORED AS ORC;

CREATE TABLE IF NOT EXISTS house_info_analysis (
    source_record_id STRING,
    title STRING,
    city STRING,
    district STRING,
    community STRING,
    total_price DECIMAL(12,2),
    unit_price DECIMAL(12,2),
    area DECIMAL(10,2),
    bedroom_count INT,
    living_room_count INT,
    layout STRING,
    orientation STRING,
    floor_level STRING,
    total_floors INT,
    decoration STRING,
    listing_date DATE,
    data_source STRING,
    import_task_id BIGINT
)
PARTITIONED BY (listing_month STRING)
STORED AS ORC;

CREATE TABLE IF NOT EXISTS house_data_quality_summary (
    total_rows BIGINT,
    valid_rows BIGINT,
    missing_location_rows BIGINT,
    invalid_price_rows BIGINT,
    invalid_area_rows BIGINT,
    duplicate_source_rows BIGINT,
    quality_score DECIMAL(5,2)
)
PARTITIONED BY (import_date STRING, import_task_id BIGINT)
STORED AS ORC;

INSERT OVERWRITE TABLE house_info_analysis PARTITION (listing_month)
VALUES
    ('HIVE-001','北京东城离线样本','北京市','东城区','东城社区',720.00,120000.00,60.00,2,1,'2室1厅','南北','中层',18,'精装',CAST('2026-01-05' AS DATE),'HIVE_SAMPLE',1,'2026-01'),
    ('HIVE-002','北京西城离线样本','北京市','西城区','西城社区',780.00,130000.00,60.00,2,1,'2室1厅','南北','中层',18,'精装',CAST('2026-01-10' AS DATE),'HIVE_SAMPLE',1,'2026-01'),
    ('HIVE-003','北京海淀离线样本','北京市','海淀区','海淀社区',880.00,110000.00,80.00,3,1,'3室1厅','南','高层',24,'精装',CAST('2026-02-05' AS DATE),'HIVE_SAMPLE',1,'2026-02'),
    ('HIVE-004','北京朝阳离线样本','北京市','朝阳区','朝阳社区',720.00,90000.00,80.00,3,1,'3室1厅','南','中层',20,'简装',CAST('2026-02-10' AS DATE),'HIVE_SAMPLE',1,'2026-02'),
    ('HIVE-005','上海浦东一月样本','上海市','浦东新区','世纪花园',600.00,65000.00,92.00,3,1,'3室1厅','南北','中层',18,'精装',CAST('2026-01-15' AS DATE),'HIVE_SAMPLE',1,'2026-01'),
    ('HIVE-006','上海浦东二月样本','上海市','浦东新区','张江家园',640.00,67000.00,96.00,3,1,'3室1厅','南北','高层',24,'精装',CAST('2026-02-15' AS DATE),'HIVE_SAMPLE',1,'2026-02'),
    ('HIVE-007','上海浦东三月样本','上海市','浦东新区','金桥新城',686.00,70000.00,98.00,3,1,'3室1厅','南','中层',20,'精装',CAST('2026-03-15' AS DATE),'HIVE_SAMPLE',1,'2026-03');
