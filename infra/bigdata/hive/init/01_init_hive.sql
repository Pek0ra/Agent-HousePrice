CREATE DATABASE IF NOT EXISTS mydb LOCATION 'hdfs:///user/hive/warehouse/mydb.db';
USE mydb;

CREATE EXTERNAL TABLE IF NOT EXISTS house_info_raw (
  source_record_id STRING, listing_type STRING, title STRING, city STRING,
  district STRING, community STRING, address STRING, total_price STRING,
  unit_price STRING, monthly_rent STRING, area STRING, bedroom_count STRING,
  living_room_count STRING, layout STRING, orientation STRING,
  floor_description STRING, floor_level STRING, total_floors STRING,
  decoration STRING, surrounding_description STRING, listing_date STRING,
  data_source STRING
)
PARTITIONED BY (dataset_id STRING, import_task_id BIGINT)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES ('separatorChar'=',','quoteChar'='"','escapeChar'='\\')
STORED AS TEXTFILE LOCATION 'hdfs:///data/house/normalized'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE TABLE IF NOT EXISTS house_info_detail (
  source_record_id STRING, listing_type STRING, title STRING, city STRING,
  district STRING, community STRING, address STRING, total_price DECIMAL(12,2),
  unit_price DECIMAL(12,2), monthly_rent DECIMAL(12,2), area DECIMAL(10,2),
  bedroom_count INT, living_room_count INT, layout STRING, orientation STRING,
  floor_description STRING, floor_level STRING, total_floors INT, decoration STRING,
  surrounding_description STRING, listing_date DATE, data_source STRING,
  source_import_task_id BIGINT
)
PARTITIONED BY (dataset_id STRING) STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS house_info_analysis (
  source_record_id STRING, listing_type STRING, title STRING, city STRING,
  district STRING, community STRING, total_price DECIMAL(12,2),
  unit_price DECIMAL(12,2), monthly_rent DECIMAL(12,2), area DECIMAL(10,2),
  bedroom_count INT, living_room_count INT, layout STRING, orientation STRING,
  floor_level STRING, total_floors INT, decoration STRING, listing_date DATE,
  data_source STRING, source_import_task_id BIGINT
)
PARTITIONED BY (dataset_id STRING, listing_month STRING) STORED AS ORC
TBLPROPERTIES ('orc.compress'='SNAPPY');

CREATE TABLE IF NOT EXISTS house_data_quality_summary (
  total_rows BIGINT, valid_rows BIGINT, sale_rows BIGINT, rent_rows BIGINT,
  missing_location_rows BIGINT, invalid_price_rows BIGINT, invalid_area_rows BIGINT,
  duplicate_source_rows BIGINT, quality_score DECIMAL(5,2)
)
PARTITIONED BY (dataset_id STRING, import_task_id BIGINT) STORED AS ORC;

CREATE TABLE IF NOT EXISTS house_active_dataset (
  dataset_id STRING, activated_at TIMESTAMP
) STORED AS ORC;

CREATE OR REPLACE VIEW v_agent_house_info_analysis AS
SELECT a.* FROM house_info_analysis a
JOIN house_active_dataset d ON a.dataset_id = d.dataset_id;

CREATE OR REPLACE VIEW v_agent_house_data_quality_summary AS
SELECT q.* FROM house_data_quality_summary q
JOIN house_active_dataset d ON q.dataset_id = d.dataset_id;
