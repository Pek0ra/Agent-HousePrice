# HouseInfo 字段字典

## 1. 文档目的

本文档是房价数据分析与管理系统的数据模型合同。后续 Java 实体、DTO、MySQL 表、Hive 表、CSV 清洗脚本、接口文档和前端字段必须以本字典为准。

当前主业务口径确定为：**二手房售价管理与分析**。旧 `Zufang` 模型属于租房原型，不能把含义不明确的租金字段直接迁移为二手房单价或总价。

## 2. 统一规范

### 2.1 命名

- Java 使用小驼峰，例如 `unitPrice`。
- MySQL、Hive 和 CSV 使用小写蛇形，例如 `unit_price`。
- 不使用 `index`、`type`、`source` 等含义模糊或容易与关键字混淆的字段名。
- Java 数据库实体统一命名为 `HouseInfo`，MySQL 表统一命名为 `house_info`。

### 2.2 单位与精度

- `totalPrice`：万元，保留 2 位小数。
- `unitPrice`：元/平方米，保留 2 位小数。
- `area`：平方米，保留 2 位小数。
- 时间统一使用北京时间业务语义，接口输出使用 ISO-8601 格式。
- 价格在 Java 中使用 `BigDecimal`，禁止使用 `String`、`float` 或 `double` 表示业务金额。

### 2.3 价格一致性

`totalPrice` 和 `area` 是核心输入字段，`unitPrice` 按下式计算：

```text
unitPrice = totalPrice × 10000 ÷ area
```

计算时保留 2 位小数，舍入方式为 `HALF_UP`。导入文件如果同时提供单价，应与计算值比较；偏差超过 1% 时进入异常记录，不能静默覆盖。

## 3. HouseInfo 主字段

| 序号 | 业务含义 | Java 字段 | Java 类型 | MySQL 字段与类型 | Hive 字段与类型 | 必填 | 规则与用途 |
|---:|---|---|---|---|---|:---:|---|
| 1 | 系统主键 | `id` | `Long` | `id BIGINT` | `id BIGINT` | 是 | MySQL 自增生成；不使用数据文件行号作为主键 |
| 2 | 外部记录编号 | `sourceRecordId` | `String` | `source_record_id VARCHAR(100)` | `source_record_id STRING` | 否 | 保存数据源原编号；与数据来源组合用于去重 |
| 3 | 房源标题 | `title` | `String` | `title VARCHAR(200)` | `title STRING` | 否 | 去除首尾空格；最长 200 字符 |
| 4 | 城市 | `city` | `String` | `city VARCHAR(50)` | `city STRING` | 是 | 标准行政区名称，例如“上海市” |
| 5 | 行政区 | `district` | `String` | `district VARCHAR(50)` | `district STRING` | 是 | 例如“浦东新区”；用于区域筛选和统计 |
| 6 | 小区名称 | `community` | `String` | `community VARCHAR(100)` | `community STRING` | 是 | 去除首尾空格并统一别名；用于小区聚合 |
| 7 | 详细地址 | `address` | `String` | `address VARCHAR(255)` | `address STRING` | 否 | 不承担行政区统计职责 |
| 8 | 房屋总价 | `totalPrice` | `BigDecimal` | `total_price DECIMAL(12,2)` | `total_price DECIMAL(12,2)` | 是 | 单位：万元；必须大于 0 |
| 9 | 单位面积价格 | `unitPrice` | `BigDecimal` | `unit_price DECIMAL(12,2)` | `unit_price DECIMAL(12,2)` | 是 | 单位：元/平方米；由总价和面积计算或校验 |
| 10 | 建筑面积 | `area` | `BigDecimal` | `area DECIMAL(10,2)` | `area DECIMAL(10,2)` | 是 | 单位：平方米；必须大于 0 |
| 11 | 卧室数 | `bedroomCount` | `Integer` | `bedroom_count INT` | `bedroom_count INT` | 否 | 必须大于等于 0；无法解析时为空 |
| 12 | 客厅数 | `livingRoomCount` | `Integer` | `living_room_count INT` | `living_room_count INT` | 否 | 必须大于等于 0；无法解析时为空 |
| 13 | 户型原始描述 | `layout` | `String` | `layout VARCHAR(50)` | `layout STRING` | 否 | 例如“3室2厅”；保留标准化后的可读文本 |
| 14 | 朝向 | `orientation` | `String` | `orientation VARCHAR(30)` | `orientation STRING` | 否 | 使用本文定义的朝向编码 |
| 15 | 楼层原始描述 | `floorDescription` | `String` | `floor_description VARCHAR(50)` | `floor_description STRING` | 否 | 例如“中楼层/共18层”；用于追溯原信息 |
| 16 | 楼层级别 | `floorLevel` | `String` | `floor_level VARCHAR(20)` | `floor_level STRING` | 否 | 使用 `LOW/MIDDLE/HIGH/UNKNOWN` |
| 17 | 总楼层数 | `totalFloors` | `Integer` | `total_floors INT` | `total_floors INT` | 否 | 必须大于 0；从楼层描述中解析 |
| 18 | 装修情况 | `decoration` | `String` | `decoration VARCHAR(20)` | `decoration STRING` | 否 | 使用本文定义的装修编码 |
| 19 | 周边环境描述 | `surroundingDescription` | `String` | `surrounding_description VARCHAR(500)` | `surrounding_description STRING` | 否 | 说明性文本，不直接作为核心聚合维度 |
| 20 | 挂牌日期 | `listingDate` | `LocalDate` | `listing_date DATE` | `listing_date DATE` | 否 | 只有存在真实日期时才用于趋势分析 |
| 21 | 数据来源 | `dataSource` | `String` | `data_source VARCHAR(50)` | `data_source STRING` | 是 | 例如 `PUBLIC_DATASET`、`MANUAL_IMPORT`、`MANUAL_ENTRY` |
| 22 | 导入任务编号 | `importTaskId` | `Long` | `import_task_id BIGINT` | `import_task_id BIGINT` | 否 | CSV 导入时关联任务；人工录入可为空 |
| 23 | 创建时间 | `createdAt` | `LocalDateTime` | `created_at DATETIME` | `created_at TIMESTAMP` | 是 | 由后端或数据库生成 |
| 24 | 更新时间 | `updatedAt` | `LocalDateTime` | `updated_at DATETIME` | `updated_at TIMESTAMP` | 是 | 每次修改时更新 |
| 25 | 逻辑删除标记 | `deleted` | `Boolean` | `deleted TINYINT(1)` | `deleted BOOLEAN` | 是 | `false/0` 正常，`true/1` 已删除；默认未删除 |

## 4. 枚举字典

数据库暂时使用字符串编码，不使用 MySQL `ENUM`。这样可以避免枚举变更必须修改表结构，也能让 MySQL、Hive、CSV 和 Java 使用相同编码。Java 层后续使用枚举类限制合法值。

### 4.1 楼层级别 `floorLevel`

| 编码 | 中文显示 | 清洗示例 |
|---|---|---|
| `LOW` | 低楼层 | 低楼层、底层、低区 |
| `MIDDLE` | 中楼层 | 中楼层、中层、中区 |
| `HIGH` | 高楼层 | 高楼层、高层、高区 |
| `UNKNOWN` | 未知 | 空值或无法识别 |

### 4.2 装修情况 `decoration`

| 编码 | 中文显示 | 清洗示例 |
|---|---|---|
| `ROUGH` | 毛坯 | 毛坯、未装修 |
| `SIMPLE` | 简装 | 简装、简单装修 |
| `REFINED` | 精装 | 精装、精装修 |
| `LUXURY` | 豪装 | 豪华装修、豪装 |
| `OTHER` | 其他 | 有效但未归入标准类别 |
| `UNKNOWN` | 未知 | 空值或无法识别 |

### 4.3 朝向 `orientation`

| 编码 | 中文显示 |
|---|---|
| `EAST` | 东 |
| `SOUTH` | 南 |
| `WEST` | 西 |
| `NORTH` | 北 |
| `SOUTHEAST` | 东南 |
| `SOUTHWEST` | 西南 |
| `NORTHEAST` | 东北 |
| `NORTHWEST` | 西北 |
| `MULTIPLE` | 多朝向 |
| `UNKNOWN` | 未知 |

包含两个以上不能归一为单一标准朝向的描述，例如“南北通透”，统一为 `MULTIPLE`，同时可在清洗错误或原始数据中保留原值以便追溯。

### 4.4 数据来源 `dataSource`

| 编码 | 含义 |
|---|---|
| `PUBLIC_DATASET` | 公开数据集 |
| `MANUAL_IMPORT` | 管理员上传文件 |
| `MANUAL_ENTRY` | 后台人工录入 |

## 5. 数据质量和校验规则

### 5.1 必须拒绝的记录

- 城市、行政区或小区名称为空。
- 总价或面积无法转换为数值。
- 总价小于等于 0。
- 面积小于等于 0。
- 计算出的单价小于等于 0。
- 同一数据来源下，外部记录编号重复且内容冲突。
- 文件单价与计算单价偏差超过 1%。

### 5.2 可以保留但需要标准化的记录

- 标题、地址、朝向、装修、楼层或挂牌日期为空。
- 户型无法拆分为卧室数和客厅数，此时保留 `layout`，数量字段置空。
- 枚举字段无法识别时转换为 `UNKNOWN`，并计入质量报告。

### 5.3 去重业务键

优先使用：

```text
data_source + source_record_id
```

如果数据源没有原始编号，使用以下字段生成内容指纹：

```text
city + district + community + address + area + total_price + listing_date
```

内容指纹用于导入幂等和重复检测，不替代 MySQL 自增主键 `id`。

## 6. 旧 Zufang 字段迁移矩阵

| 旧字段 | 旧含义 | 新字段 | 迁移策略 |
|---|---|---|---|
| `zid` | 租房记录编号 | `sourceRecordId` | 转为字符串并标记旧数据来源；不能作为新表自增主键 |
| `title` | 房源标题 | `title` | 清理乱码和首尾空格后迁移 |
| `xqname` | 小区名称 | `community` | 标准化小区名称后迁移 |
| `address` | 地址 | `address` | 清理后迁移；不能据此盲目推断城市和行政区 |
| `huanjing` | 周边环境 | `surroundingDescription` | 作为描述文本迁移 |
| `jiage` | 含义不明确的价格字符串 | 无法直接迁移 | 必须先确认是月租、总价还是单价；禁止直接写入 `totalPrice` 或 `unitPrice` |
| `louceng` | 楼层描述 | `floorDescription` | 保留原描述，再尝试解析 `floorLevel` 和 `totalFloors` |
| `mianji` | 面积 | `area` | 转为 `BigDecimal`，校验大于 0 |
| `shi` | 室 | `bedroomCount` | 校验非负后迁移 |
| `ting` | 厅 | `livingRoomCount` | 校验非负后迁移 |

旧模型没有提供以下二手房核心信息：

- `city`
- `district`
- `totalPrice`
- `unitPrice`
- `orientation`
- `decoration`
- `listingDate`

因此旧租房记录不能直接作为新的二手房分析明细。建议保留旧表作为原型数据或导入暂存数据，待获得字段含义明确的二手房样例 CSV 后再进入 `house_info`。

## 7. 各层对象边界

后续不应让一个 `HouseInfo` 对象承担所有职责：

- `HouseInfo`：映射 MySQL 房源记录。
- `CreateHouseDTO`：接收新增参数，不包含 `id`、审计字段和删除标记。
- `UpdateHouseDTO`：接收允许修改的字段。
- `HouseQueryDTO`：接收区域、价格、面积、户型、朝向、装修和分页条件。
- `HouseDetailVO`：向前端返回房源详情和中文枚举显示值。
- Hive 分析结果 VO：只返回统计维度、指标值和排序信息。

## 8. 后续实现验收清单

- [ ] Java 实体字段名称、类型与本字典一致。
- [ ] MySQL DDL 字段、精度、默认值与本字典一致。
- [ ] Hive DDL 字段名称和数值类型与本字典一致。
- [ ] CSV 清洗输出列名与 Hive 字段一致。
- [ ] API 文档明确展示价格和面积单位。
- [ ] 单价计算统一使用 `BigDecimal` 和 `HALF_UP`。
- [ ] 枚举非法值在接口层被拒绝，在清洗层被归一或记录。
- [ ] 旧 `jiage` 未经语义确认不得迁移。
- [ ] 趋势接口只有在 `listingDate` 存在真实数据时才能实现。
