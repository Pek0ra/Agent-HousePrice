SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS rental_listing (
    id                BIGINT         NOT NULL AUTO_INCREMENT COMMENT '出租房主键',
    source_record_id  VARCHAR(100)   NOT NULL COMMENT '数据源中的原始记录编号',
    title             VARCHAR(200)   NULL COMMENT '出租房标题',
    city              VARCHAR(50)    NOT NULL COMMENT '城市标准名称',
    district          VARCHAR(50)    NOT NULL COMMENT '行政区标准名称',
    community         VARCHAR(100)   NOT NULL COMMENT '小区名称',
    monthly_rent      DECIMAL(12, 2) NOT NULL COMMENT '月租金，单位：元/月',
    area              DECIMAL(10, 2) NOT NULL COMMENT '建筑面积，单位：平方米',
    bedroom_count     INT            NULL COMMENT '卧室数量',
    living_room_count INT            NULL COMMENT '客厅数量',
    layout            VARCHAR(50)    NULL COMMENT '标准化户型描述',
    listing_date      DATE           NOT NULL COMMENT '挂牌日期',
    data_source       VARCHAR(50)    NOT NULL COMMENT '数据来源编码',
    created_at        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted           TINYINT        NOT NULL DEFAULT 0 COMMENT '逻辑删除：0正常，1删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_rental_source_record (data_source, source_record_id),
    KEY idx_rental_region (city, district, community, deleted),
    KEY idx_rental_monthly_rent (monthly_rent),
    KEY idx_rental_listing_date (listing_date),
    CONSTRAINT chk_rental_monthly_rent CHECK (monthly_rent > 0),
    CONSTRAINT chk_rental_area CHECK (area > 0),
    CONSTRAINT chk_rental_deleted CHECK (deleted IN (0, 1))
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  COMMENT = '出租房挂牌数据表';

INSERT INTO rental_listing (
    source_record_id, title, city, district, community, monthly_rent, area,
    bedroom_count, living_room_count, layout, listing_date, data_source
) VALUES
    ('AGENT-RENT-001', '浦东三室一厅一月样本', '上海市', '浦东新区', '世纪花园', 8000.00, 92.00, 3, 1, '3室1厅', '2026-01-15', 'AGENT_SAMPLE'),
    ('AGENT-RENT-002', '浦东三室一厅二月样本', '上海市', '浦东新区', '张江家园', 8500.00, 96.00, 3, 1, '3室1厅', '2026-02-15', 'AGENT_SAMPLE'),
    ('AGENT-RENT-003', '浦东三室一厅三月样本', '上海市', '浦东新区', '金桥新城', 9000.00, 98.00, 3, 1, '3室1厅', '2026-03-15', 'AGENT_SAMPLE'),
    ('AGENT-RENT-004', '浦东两室一厅样本', '上海市', '浦东新区', '碧云社区', 6800.00, 72.00, 2, 1, '2室1厅', '2026-03-20', 'AGENT_SAMPLE'),
    ('AGENT-RENT-005', '徐汇两室一厅样本', '上海市', '徐汇区', '徐家汇花园', 7600.00, 70.00, 2, 1, '2室1厅', '2026-03-10', 'AGENT_SAMPLE'),
    ('AGENT-RENT-006', '南山两室一厅样本A', '深圳市', '南山区', '科技园社区', 9000.00, 68.00, 2, 1, '2室1厅', '2026-01-12', 'AGENT_SAMPLE'),
    ('AGENT-RENT-007', '南山两室一厅样本B', '深圳市', '南山区', '后海社区', 10000.00, 75.00, 2, 1, '2室1厅', '2026-02-12', 'AGENT_SAMPLE'),
    ('AGENT-RENT-008', '福田两室一厅样本A', '深圳市', '福田区', '香蜜湖社区', 8000.00, 66.00, 2, 1, '2室1厅', '2026-01-18', 'AGENT_SAMPLE'),
    ('AGENT-RENT-009', '福田两室一厅样本B', '深圳市', '福田区', '中心区社区', 8500.00, 70.00, 2, 1, '2室1厅', '2026-02-18', 'AGENT_SAMPLE'),
    ('AGENT-RENT-010', '朝阳一室一厅样本', '北京市', '朝阳区', '望京社区', 6200.00, 48.00, 1, 1, '1室1厅', '2026-01-08', 'AGENT_SAMPLE'),
    ('AGENT-RENT-011', '海淀一室一厅样本', '北京市', '海淀区', '中关村社区', 6800.00, 46.00, 1, 1, '1室1厅', '2026-02-08', 'AGENT_SAMPLE'),
    ('AGENT-RENT-012', '天河两室一厅样本', '广州市', '天河区', '珠江新城社区', 5800.00, 65.00, 2, 1, '2室1厅', '2026-03-08', 'AGENT_SAMPLE')
AS new
ON DUPLICATE KEY UPDATE
    title = new.title,
    city = new.city,
    district = new.district,
    community = new.community,
    monthly_rent = new.monthly_rent,
    area = new.area,
    bedroom_count = new.bedroom_count,
    living_room_count = new.living_room_count,
    layout = new.layout,
    listing_date = new.listing_date;

INSERT INTO house_info (
    source_record_id, title, city, district, community, total_price, unit_price,
    area, bedroom_count, living_room_count, layout, listing_date, data_source
) VALUES
    ('AGENT-SALE-001', '北京东城挂牌样本', '北京市', '东城区', '东城社区', 720.00, 120000.00, 60.00, 2, 1, '2室1厅', '2026-01-05', 'AGENT_SAMPLE'),
    ('AGENT-SALE-002', '北京西城挂牌样本', '北京市', '西城区', '西城社区', 780.00, 130000.00, 60.00, 2, 1, '2室1厅', '2026-01-10', 'AGENT_SAMPLE'),
    ('AGENT-SALE-003', '北京海淀挂牌样本', '北京市', '海淀区', '海淀社区', 880.00, 110000.00, 80.00, 3, 1, '3室1厅', '2026-02-05', 'AGENT_SAMPLE'),
    ('AGENT-SALE-004', '北京朝阳挂牌样本', '北京市', '朝阳区', '朝阳社区', 720.00, 90000.00, 80.00, 3, 1, '3室1厅', '2026-02-10', 'AGENT_SAMPLE'),
    ('AGENT-SALE-005', '北京丰台挂牌样本', '北京市', '丰台区', '丰台社区', 560.00, 70000.00, 80.00, 3, 1, '3室1厅', '2026-03-05', 'AGENT_SAMPLE'),
    ('AGENT-SALE-006', '北京石景山挂牌样本', '北京市', '石景山区', '石景山社区', 480.00, 60000.00, 80.00, 3, 1, '3室1厅', '2026-03-10', 'AGENT_SAMPLE'),
    ('AGENT-SALE-007', '北京通州挂牌样本', '北京市', '通州区', '通州社区', 400.00, 50000.00, 80.00, 3, 1, '3室1厅', '2026-03-15', 'AGENT_SAMPLE')
AS new
ON DUPLICATE KEY UPDATE
    title = new.title,
    city = new.city,
    district = new.district,
    community = new.community,
    total_price = new.total_price,
    unit_price = new.unit_price,
    area = new.area,
    bedroom_count = new.bedroom_count,
    living_room_count = new.living_room_count,
    layout = new.layout,
    listing_date = new.listing_date;

CREATE OR REPLACE VIEW agent_house_info AS
SELECT city, district, community, total_price, unit_price, area,
       bedroom_count, living_room_count, layout, orientation, floor_level,
       total_floors, decoration, listing_date, data_source
FROM house_info
WHERE deleted = 0;

CREATE OR REPLACE VIEW agent_rental_listing AS
SELECT city, district, community, monthly_rent, area, bedroom_count,
       living_room_count, layout, listing_date, data_source
FROM rental_listing
WHERE deleted = 0;
