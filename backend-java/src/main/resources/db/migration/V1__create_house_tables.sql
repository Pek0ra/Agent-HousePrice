SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS house_info (
    id                      BIGINT         NOT NULL AUTO_INCREMENT COMMENT '系统主键',
    source_record_id        VARCHAR(100)   NULL COMMENT '数据源中的原始记录编号',
    title                   VARCHAR(200)   NULL COMMENT '房源标题',
    city                    VARCHAR(50)    NOT NULL COMMENT '城市标准名称',
    district                VARCHAR(50)    NOT NULL COMMENT '行政区标准名称',
    community               VARCHAR(100)   NOT NULL COMMENT '小区名称',
    address                 VARCHAR(255)   NULL COMMENT '详细地址',
    total_price             DECIMAL(12, 2) NOT NULL COMMENT '总价，单位：万元',
    unit_price              DECIMAL(12, 2) NOT NULL COMMENT '单价，单位：元/平方米',
    area                    DECIMAL(10, 2) NOT NULL COMMENT '建筑面积，单位：平方米',
    bedroom_count           INT            NULL COMMENT '卧室数量',
    living_room_count       INT            NULL COMMENT '客厅数量',
    layout                  VARCHAR(50)    NULL COMMENT '标准化户型描述',
    orientation             VARCHAR(30)    NULL COMMENT '朝向标准编码',
    floor_description       VARCHAR(50)    NULL COMMENT '楼层原始/标准化描述',
    floor_level             VARCHAR(20)    NULL COMMENT 'LOW/MIDDLE/HIGH/UNKNOWN',
    total_floors            INT            NULL COMMENT '总楼层数',
    decoration              VARCHAR(20)    NULL COMMENT '装修标准编码',
    surrounding_description VARCHAR(500)   NULL COMMENT '周边环境描述',
    listing_date            DATE           NULL COMMENT '挂牌日期',
    data_source             VARCHAR(50)    NOT NULL COMMENT '数据来源编码',
    import_task_id          BIGINT         NULL COMMENT '导入任务编号',
    created_at              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted                 TINYINT         NOT NULL DEFAULT 0 COMMENT '逻辑删除：0正常，1删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_house_source_record (data_source, source_record_id),
    KEY idx_house_region (city, district, community, deleted),
    KEY idx_house_unit_price (unit_price),
    KEY idx_house_total_price (total_price),
    KEY idx_house_area (area),
    KEY idx_house_listing_date (listing_date),
    KEY idx_house_deleted_id (deleted, id),
    CONSTRAINT chk_house_total_price CHECK (total_price > 0),
    CONSTRAINT chk_house_unit_price CHECK (unit_price > 0),
    CONSTRAINT chk_house_area CHECK (area > 0),
    CONSTRAINT chk_house_bedroom_count CHECK (bedroom_count IS NULL OR bedroom_count >= 0),
    CONSTRAINT chk_house_living_room_count CHECK (living_room_count IS NULL OR living_room_count >= 0),
    CONSTRAINT chk_house_total_floors CHECK (total_floors IS NULL OR total_floors > 0),
    CONSTRAINT chk_house_deleted CHECK (deleted IN (0, 1))
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  COMMENT = '二手房房源业务表';

CREATE TABLE IF NOT EXISTS house_import_task (
    id                BIGINT        NOT NULL AUTO_INCREMENT COMMENT '导入任务主键',
    original_filename VARCHAR(255)  NOT NULL COMMENT '用户上传的原始文件名',
    file_size         BIGINT        NOT NULL COMMENT '文件大小，单位：字节',
    file_sha256       CHAR(64)      NULL COMMENT '文件SHA-256摘要',
    status            VARCHAR(30)   NOT NULL COMMENT '任务状态',
    total_rows        BIGINT        NOT NULL DEFAULT 0 COMMENT 'CSV数据总行数，不含表头',
    success_rows      BIGINT        NOT NULL DEFAULT 0 COMMENT '校验成功行数',
    failed_rows       BIGINT        NOT NULL DEFAULT 0 COMMENT '校验失败行数',
    hdfs_path         VARCHAR(500)  NULL COMMENT 'HDFS文件完整路径',
    error_report_path VARCHAR(500)  NULL COMMENT '错误行报告的内部保存路径',
    failure_stage     VARCHAR(30)   NULL COMMENT '最近一次失败所处阶段',
    retry_count       INT           NOT NULL DEFAULT 0 COMMENT '已重试次数',
    staging_path      VARCHAR(500)  NULL COMMENT '失败重试使用的内部暂存路径',
    error_message     VARCHAR(1000) NULL COMMENT '失败摘要',
    started_at        DATETIME      NULL COMMENT '任务开始时间',
    finished_at       DATETIME      NULL COMMENT '任务结束时间',
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    successful_sha256 CHAR(64)
        GENERATED ALWAYS AS (
            CASE WHEN status = 'SUCCESS' THEN file_sha256 ELSE NULL END
        ) STORED COMMENT '仅成功任务参与防重复的生成列',
    PRIMARY KEY (id),
    UNIQUE KEY uk_import_success_sha256 (successful_sha256),
    KEY idx_import_task_status_created (status, created_at),
    KEY idx_import_task_sha256 (file_sha256),
    CONSTRAINT chk_import_task_rows CHECK (
        total_rows >= 0
        AND success_rows >= 0
        AND failed_rows >= 0
        AND retry_count >= 0
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  COMMENT = 'CSV到HDFS/Hive导入任务';
