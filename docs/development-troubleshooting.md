# 开发问题复盘与解决方案

本文记录“城析：房价智能问数与分析平台”从原始 Spring Boot/Hive 项目演进为 MySQL、Java、Python Agent、HDFS/Hive 和 React 前端一体化项目时遇到的主要问题。重点不是罗列报错，而是说明问题为什么出现、如何定位、最终采用了什么方案，以及哪些风险仍需继续处理。

## 1. 复盘方法

排查过程中始终把问题拆成四层：

1. **配置层**：环境变量、端口、Compose profile 是否符合预期。
2. **基础设施层**：容器是否真正健康，数据卷和初始化任务是否可重复使用。
3. **数据层**：源 CSV、MySQL、HDFS、Hive 和活动视图的数据是否一致。
4. **应用层**：Java、Agent、前端是否使用了正确的数据源、Schema 和业务口径。

仅看到进程启动或端口开放不算验收完成。最终判断通常需要同时检查健康状态、日志、数据库内容、接口响应和重复启动行为。

## 2. 问题状态总览

| 问题 | 根因摘要 | 当前状态 |
| --- | --- | --- |
| `Duplicate column name 'error_report_path'` | 建表脚本与增量脚本重复维护同一字段 | 已修复 |
| MySQL 中文注释显示乱码 | SQL 文件、客户端会话和连接编码没有形成完整 UTF-8 链路 | 已修复 |
| MySQL 容器显示 `health: starting` | 容器已启动不等于数据库已就绪 | 已通过 healthcheck 和依赖条件处理 |
| Java 在没有 Hive 时可能启动失败 | Hive Bean 和接口没有按运行模式隔离 | 已修复 |
| 手工 SQL 与 Flyway/Docker 初始化职责重叠 | 多套脚本缺少唯一迁移入口 | 已迁移为 Flyway 主导 |
| 宿主机 3306 端口冲突 | 本机已有 MySQL 占用默认端口 | 已支持映射到 3307 |
| CSV 写入 MySQL/Hive 后可能出现不一致 | 只检查总数无法发现分类或月份错位 | 已增加版本化、分组对账和原子激活 |
| Hive Metastore 重启后重复初始化失败 | Derby 实际目录未持久化，且官方入口无条件初始化 | 已修复 |
| Hive Metastore 无法写数据卷 | Docker 卷属主为 root，Hive 进程为 UID 1000 | 已修复 |
| Schema 初始化与运行中的 Derby 锁冲突 | 一次性初始化任务重复打开在线 Derby | 已修复 |
| Java 健康检查提示 `Database mydb does not exist` | Java 启动早于 Hive 业务库初始化 | 已通过可恢复连接和启动脚本等待处理 |
| Agent 请求 Hive 返回 500 | Agent 白名单字段与真实 Hive 视图字段不一致 | 已修复并增加回归测试 |
| Agent 重建后错误路由到 MySQL | 新 PowerShell 进程丢失临时 bigdata 环境变量 | 已通过统一启动脚本规避 |
| “房价”偶发生成租金 SQL | SQL 安全校验没有验证业务语义与结构化意图一致 | 已定位，语义校验待实施 |
| “系统能力”按钮返回 502 | 页面按钮指向 API 代理路径而不是页面地址 | 已修复为双向页面导航 |

## 3. MySQL 脚本重复执行与字段冲突

### 3.1 现象

手工依次执行旧 SQL 文件时出现：

```text
ERROR 1060 (42S21): Duplicate column name 'error_report_path'
```

### 3.2 根因

`error_report_path` 已在建表脚本中存在，后续“可靠性增强”脚本又执行了一次 `ADD COLUMN`。这类问题通常来自：

- 完整建表脚本和增量升级脚本同时被当作初始化脚本执行；
- 脚本没有版本记录，不知道某次变更是否已经应用；
- 修改了旧脚本后，又保留了针对旧结构的补丁脚本。

### 3.3 解决方案

- 将当前完整结构收敛到 Flyway 迁移目录 `backend-java/src/main/resources/db/migration/`。
- 已存在的历史迁移不再反复修改，通过新版本迁移追加变化。
- Docker 的 `infra/mysql/init/` 只负责创建数据库和设置基础字符集，业务表演进交给 Flyway。
- 在全新 MySQL 8 环境中从空库执行全部迁移，确认不会重复创建字段。

### 3.4 解决思路

问题的关键不只是让某条 SQL “不报错”，而是建立唯一的数据库版本来源。否则即使给某次 `ALTER TABLE` 加条件，下一次结构调整仍可能产生同类冲突。

## 4. 中文注释乱码

### 4.1 现象

`SHOW CREATE TABLE` 曾显示：

```text
COMMENT='CSV鍒癏DFS/Hive瀵煎叆浠诲姟'
```

正确内容应为“CSV到HDFS/Hive导入任务”。

### 4.2 根因

`utf8mb4` 表字符集只能保证数据库如何保存字符，不能自动修复已经按错误编码读取的 SQL 文本。完整链路包含：

```text
SQL 文件编码 → MySQL 客户端读取编码 → 会话字符集 → 数据库/表字符集 → 查询终端显示编码
```

任何一环把 UTF-8 字节按 GBK/ANSI 解释，写入数据库的就已经是乱码文本。

### 4.3 解决方案

- SQL、Java、Python 和前端源码统一保存为 UTF-8。
- MySQL 初始化及 Flyway 脚本显式执行：

  ```sql
  SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
  ```

- 数据库和表统一使用 `utf8mb4_0900_ai_ci`。
- JDBC URL 增加 `useUnicode=true`、`characterEncoding=UTF-8` 和 `connectionCollation=utf8mb4_0900_ai_ci`。
- 命令行验证使用 `mysql --default-character-set=utf8mb4`。
- Windows PowerShell 5 发送中文 JSON 时显式转换为 UTF-8 字节。
- PowerShell 启动脚本的异常提示改用 ASCII，避免无 BOM UTF-8 脚本被旧版 PowerShell 按系统代码页读取。

### 4.4 验证

在隔离 MySQL 8 和 Compose MySQL 中检查到：

```text
TABLE_COLLATION = utf8mb4_0900_ai_ci
TABLE_COMMENT   = 版本化房源数据集
```

## 5. 容器启动与真正就绪的差异

### 5.1 现象

`docker compose up -d mysql` 返回成功，但 `docker compose ps` 显示：

```text
Up ... (health: starting)
```

### 5.2 根因

Docker 的 `running` 只表示容器主进程存在，不代表 MySQL 已完成恢复、初始化并可以接受连接。Java 如果仅依赖容器启动顺序，仍可能在数据库就绪前连接失败。

### 5.3 解决方案

- MySQL 增加真实连接型 healthcheck。
- Java 使用 `depends_on: condition: service_healthy` 等待 MySQL。
- 一次性安全账号初始化任务也等待 MySQL 健康，并等待 Flyway 创建完所需对象。
- 验收时等待 `healthy`，不能把 `health: starting` 当作最终成功。

## 6. local 与 bigdata 模式没有完全隔离

### 6.1 风险

早期项目默认创建 Hive/HDFS 相关 Bean。没有虚拟机、HiveServer2 或 HDFS 时，Spring Boot 可能因为连接失败而无法启动，导致 MySQL CRUD 也不可用。

### 6.2 解决方案

- 明确两种运行模式：
  - `local`：仅 MySQL；
  - `bigdata`：MySQL + HDFS + Hive。
- 使用 `SPRING_PROFILES_ACTIVE` 和 `BIG_DATA_ENABLED` 条件化创建 Hive/HDFS Bean。
- local 模式不注册 Hive 分析和 CSV 导入接口，能力接口明确返回当前模式。
- Maven 同样区分 local/bigdata 依赖，避免 local 包携带庞大的 Hadoop/Hive 依赖。
- 前端根据能力信息隐藏不可用的大数据操作。

### 6.3 思路

“捕获 Hive 连接异常”只能缓解症状；更可靠的边界是在功能关闭时根本不创建相关 Bean、不注册相关接口。

## 7. Compose 端口冲突

### 7.1 现象

完整环境启动时 Docker 报错：

```text
ports are not available: listen tcp 0.0.0.0:3306: bind ...
```

### 7.2 根因

宿主机已有 MySQL 使用 3306。容器内部端口和宿主机映射端口是两个概念，不需要为了避免冲突修改所有服务的数据库地址。

### 7.3 解决方案

- 宿主机映射改为 `MYSQL_PORT=3307`。
- 容器间仍使用 `mysql:3306`。
- 宿主机直接运行 Java/Python 时使用 `localhost:3307`。
- 启动脚本支持在当前 PowerShell 会话中覆盖：

  ```powershell
  $env:MYSQL_PORT = '3307'
  .\infra\bigdata\start-bigdata.ps1
  ```

这种方案只改变边界端口，不改变容器网络内稳定的服务发现地址。

## 8. CSV 双写一致性不足

### 8.1 风险

同一份 CSV 需要写入 MySQL、HDFS 和 Hive。任一阶段失败，都可能产生以下状态：

- MySQL 已更新，Hive 仍是旧数据；
- HDFS 文件存在，但 Hive 分区没有加载；
- 总行数相同，但 SALE/RENT、城市或月份分布不同；
- 新数据失败后覆盖了原本可用的数据。

### 8.2 解决方案

- 每次导入生成独立 `dataset_id`，新版本先处于暂存状态。
- CSV 只规范化一次，同一规范化结果写入 MySQL、HDFS 和 Hive。
- 流程固化为：

  ```text
  VALIDATING
    → LOADING_MYSQL
    → UPLOADING_HDFS
    → LOADING_HIVE
    → COMPACTING_HIVE
    → VERIFYING
    → ACTIVATING
  ```

- 对账不仅检查总行数，还检查 `listing_type + city + month` 的分组计数。
- 只有 MySQL/Hive 全部一致时，才同时切换活动数据集指针。
- 失败时保留旧活动版本；成功历史版本可以重新激活回滚。
- 使用文件 SHA-256 防止相同成功文件重复导入，重复请求返回 HTTP 409。

### 8.3 思路

MySQL 和 Hive 之间无法直接使用一个普通本地事务，因此采用“版本暂存 + 对账 + 原子切换可见性”的发布模型。用户只能看到已验证通过的版本，从而把跨系统最终一致性问题隔离在发布之前。

## 9. Hive Metastore 持久化与初始化问题

这一部分连续暴露了三个相互关联的问题。

### 9.1 Derby 数据目录没有真正持久化

#### 现象

Metastore 重启后反复执行初始化并报错：

```text
FUNCTION 'NUCLEUS_ASCII' already exists
Schema initialization failed
```

#### 根因

Compose 把卷挂载到 `/opt/hive/data`，但 Derby 默认使用相对路径 `metastore_db`，实际写到了 `/opt/hive/metastore_db`。看似配置了持久化卷，真正的元数据却留在容器可写层中。

#### 修复

在 `hive-site.xml` 中显式设置：

```xml
<name>javax.jdo.option.ConnectionURL</name>
<value>jdbc:derby:;databaseName=/opt/hive/data/metastore_db;create=true</value>
```

这样 Derby 文件和声明的命名卷指向同一目录。

### 9.2 Hive 用户没有卷写权限

#### 现象

修正路径后出现：

```text
Failed to create database '/opt/hive/data/metastore_db'
Permission denied
```

#### 根因

Docker 新卷默认归 root 所有，而 `apache/hive:3.1.3` 默认以 UID/GID 1000 的 `hive` 用户运行。

#### 修复

增加一次性 `hive-metastore-volume-init` 服务，以 root 身份只执行：

```text
chown -R 1000:1000 /opt/hive/data
```

长期运行的 Metastore 仍保持非 root，避免为了方便而扩大运行权限。

### 9.3 初始化任务与在线 Derby 争用文件锁

#### 现象

首次启动成功后再次执行相同 Compose 命令，`schema-init` 因 Derby 已被在线 Metastore 占用而失败。

#### 根因

一次性 Compose 服务会在后续 `up` 中再次运行。如果它直接执行 `schematool -info`，就会与正在运行的 Derby 进程竞争数据库文件锁。

#### 修复

- 增加 `.schema-initialized` 成功标记。
- 如果标记存在，初始化任务立即成功退出。
- 如果 Metastore 已在线，则不再打开 Derby，只补写标记并退出。
- 只有“没有标记且服务未在线”的新卷才运行 `schematool`。
- Metastore 设置 `IS_RESUME=true`，避免官方入口再次无条件初始化。

### 9.4 验证方式

验证不止执行首次启动，还执行了：

1. 完整导入 20 行数据；
2. 强制重建 Metastore；
3. 再次执行同一启动脚本；
4. 检查 Metastore/HiveServer2 均 healthy；
5. 确认 Hive 活动视图仍为 20 行，质量统计仍为 8 SALE、12 RENT。

## 10. Java 启动早于 Hive 数据库初始化

### 10.1 现象

Java 健康检查曾输出：

```text
Database mydb does not exist
```

### 10.2 根因

HiveServer2 端口已经可连接，但 `hive-init` 尚未创建 `mydb` 和业务表。端口健康与业务 Schema 就绪是不同层次的状态。

### 10.3 解决方案

- Java 的 Hive 连接池允许后续重新建立连接，不因一次早期失败导致进程退出。
- `start-bigdata.ps1` 在 Compose 启动后执行 `docker compose wait hive-init`。
- `hive-init` 非 0 退出时，启动脚本整体失败；成功返回代表业务库初始化已完成。
- 验收继续检查 Java `/actuator/health`，而不是只看 HiveServer2 端口。

### 10.4 权衡

Java 服务不能静态依赖 bigdata profile 中才存在的服务，否则 core 模式无法启动。因此选择“应用可恢复 + bigdata 启动脚本等待最终初始化”的组合，而不是让 Java 永久依赖 Hive 初始化容器。

## 11. Agent Hive Schema 与真实视图不一致

### 11.1 现象

历史趋势问数请求返回 HTTP 500：

```text
Hive table v_agent_house_info_analysis is missing expected columns: ['import_task_id']
```

### 11.2 根因

Hive 分析视图实际字段为 `source_import_task_id`，Agent 白名单写成了 `import_task_id`。两者含义接近，但名称不相同。Agent 在生成 SQL 前执行 Schema 自检，因此主动拒绝了不一致结构。

### 11.3 解决方案

- 将 Agent 白名单改为 `source_import_task_id`。
- 修正同一文件中的中文业务描述。
- 新增回归测试，明确分析视图必须包含 `source_import_task_id`，不能退回错误名称。
- 重建 Python 镜像后，用真实 Hive 请求验证历史趋势查询。

### 11.4 思路

这里不应该删除 Schema 自检来“让接口先跑起来”。自检拦截了模型基于错误 Schema 生成 SQL，是正确的保护机制；应该修正契约来源，并用测试锁定契约。

## 12. PowerShell 环境变量作用域导致模式错误

### 12.1 现象

Agent 容器健康，但“历史租金趋势”被路由到 MySQL，而不是 Hive。

### 12.2 根因

`$env:BIG_DATA_ENABLED='true'` 只在当前 PowerShell 进程及其子进程有效。后续使用新的终端/执行进程单独重建 Python 容器时没有重新设置变量，Compose 使用默认值 `false`，于是 Agent 按 local 模式运行。

### 12.3 解决方案

- 大数据环境统一通过 `infra/bigdata/start-bigdata.ps1` 启动。
- 脚本同时设置：

  ```text
  JAVA_MAVEN_PROFILE=bigdata
  SPRING_PROFILES_ACTIVE=bigdata
  BIG_DATA_ENABLED=true
  ```

- 如果手工运行 Compose，则在根 `.env` 中持久配置这三个值并保持一致。
- 验证 `/api/system/capabilities` 返回 `mode=bigdata`，再测试 Agent 路由。

## 13. “房价”被生成成“租金”SQL

### 13.1 现象

问题：

```text
上海市浦东新区3室2厅平均房价
```

模型却生成：

```sql
SELECT ROUND(AVG(monthly_rent), 2)
FROM v_agent_house_listing
WHERE city = '上海市'
  AND district = '浦东新区'
  AND bedroom_count = 3
  AND living_room_count = 2
  AND listing_type = 'RENT'
LIMIT 20;
```

于是错误回答“当前数据中未找到符合条件的房源”。

### 13.2 数据核查

- 对应 CSV 与当前活动数据集 SHA-256 一致，说明文件已经导入。
- `SYN-SALE-001819` 在 `house_info` 中存在，未删除，类型为 SALE。
- 当前活动视图内共有 47 条上海市浦东新区 3 室 2 厅出售挂牌，0 条相同条件的出租挂牌。
- 正确平均挂牌单价约为 `92763.12 元/平方米`。

因此原始数据没有问题，错误发生在 SQL 业务语义层。

### 13.3 为什么已有 Prompt 仍会出错

当前确定性结构化节点已经把：

```text
房价 → metric=unit_price, listing_type=SALE
```

Prompt 也明确要求房价使用 `unit_price`。但 SQL 最终仍由概率模型生成，模型可能偶发忽略上游约束。现有 SQLGlot 校验关注的是：

- 是否为单条 SELECT；
- 是否访问白名单视图；
- 是否包含危险语句；
- 是否限制结果行数。

错误 SQL 虽然业务含义错误，但在安全层面依然是合法的只读白名单查询，所以能够通过 AST 校验。

### 13.4 推荐的后续修复（尚未实施）

增加独立的“业务语义校验”，在 SQL 安全校验之后、执行之前比较结构化意图和 AST：

| 结构化指标 | 必须使用 | 必须过滤 |
| --- | --- | --- |
| `unit_price` | `unit_price` / `avg_unit_price` | `listing_type='SALE'` |
| `total_price` | `total_price` / `avg_total_price` | `listing_type='SALE'` |
| `monthly_rent` | `monthly_rent` / `avg_monthly_rent` | `listing_type='RENT'` |

不一致时不执行 SQL，而是带着明确错误原因触发最多一次修正。更稳定的方案是由程序确定指标列和挂牌类型，只让模型补充维度、筛选和排序。

这个问题目前是已确认的待办，不能仅依靠继续加强 Prompt 来宣称解决。

## 14. 前端“系统能力”按钮返回 502

### 14.1 现象

智能问数页顶部的“系统能力”按钮点击后显示 502。

### 14.2 根因

按钮指向 `/api/java/system/capabilities`。这是 Nginx 代理的 JSON API 路径，不是房价分析页面入口；代理异常时用户直接看到 502，而且按钮文案也不能说明目的地。

### 14.3 解决方案

- 按钮改名为“房价数据分析中心”。
- 明确跳转到 `http://localhost:9900/`。
- 使用深色背景、阴影、箭头及 hover/focus 样式提高可见性。
- Java 分析页顶部增加“返回智能问数中心”按钮，跳转到 `http://localhost/`。

## 16. 连续问数被拆成多条历史并可能串线

旧前端把每一轮问答都保存为一个 `Conversation`，并用单独的全局 localStorage 键保存 `thread_id`。所以第二问会新增左侧记录；切换历史或刷新时，全局线程还可能与当前显示的记录不一致。

修复后，`Conversation` 拥有自己的 `threadId` 和 `turns[]`；异步结果使用 `conversationId + turnId` 精确回写，并拒绝不匹配的线程。localStorage 升级为 v2，旧记录按 `response.thread_id` 合并，无线程记录单独保留。失败重试更新原 turn，每条最近会话增加删除按钮；上限是 30 个会话、每个 50 轮。

删除浏览器历史只移除本地展示，不会立即删除服务端 SQLite checkpoint；后端按自己的保留策略管理线程状态。
- 重建前端和 Java 镜像，从实际容器返回的 HTML/JS 验证文案与目标 URL，并确认两端 HTTP 200。

## 15. 调试过程中容易误判的现象

### 15.1 Agent 容器健康但前端问数返回 502

Python Agent 重建后直连 `localhost:8000` 正常，但 Nginx 仍可能把 `python-agent` 服务名缓存为重建前的容器 IP，日志表现为 `connect() failed (113: Host is unreachable)`。因此“容器 healthy”与“统一入口代理可达”需要分别验证。

前端 Nginx 已配置 Docker 内置 DNS `127.0.0.11`，并通过变量形式的 `proxy_pass` 在请求时重新解析 `python-agent` 和 `java-backend`。这样上游容器被替换后不需要依赖手工重启 Nginx。验收同时检查直连 Agent 和 `http://localhost/api/agent/chat`，不能只检查健康端点。

### 15.2 PowerShell 中文管道查询为空

诊断数据时，PowerShell 5 管道可能用非 UTF-8 编码把中文 SQL 传给 MySQL，导致中文条件无法匹配，但不会一定报语法错误。最终使用 UTF-8 客户端设置、十六进制 UTF-8 字面量或应用连接复核，避免把终端编码问题误判为数据缺失。

### 15.3 Compose 一次性任务显示 Exited

`hdfs-init`、`hive-metastore-volume-init`、`hive-metastore-schema-init`、`hive-init` 显示 `Exited (0)` 表示成功完成。只有非 0 退出码才是失败。

### 15.4 修改 `.env` 不会自动改变已有 MySQL root 密码

MySQL 官方镜像只在空数据卷首次初始化时使用 `MYSQL_ROOT_PASSWORD`。已有卷修改 `.env` 不会自动改库内密码。普通重启应沿用原密码；需要修改账号时显式执行账号变更流程，不能把删除数据卷当作常规修复手段。

## 16. 最终验证基线

阶段性完整验收得到以下结果：

- Java bigdata profile：29 个测试通过。
- Python Agent：32 个测试通过；仅有第三方 Starlette 弃用警告。
- Compose core/bigdata 配置解析成功。
- Flyway V0–V6 状态全部成功。
- 完整 Compose 可在已有卷上重复启动。
- MySQL、Java、Python、前端、NameNode、DataNode、Metastore、HiveServer2 均达到 healthy。
- 第一版 20 行统一样例的导入结果：MySQL 20、Hive detail 20、Hive analysis 20，8 SALE、12 RENT，对账 MATCHED。
- HDFS 中存在对应规范化文件。
- 相同文件重复上传返回 HTTP 409。
- Metastore 重建后 Hive 数据仍存在。
- 历史租金趋势问题能够路由到 Hive 并返回结果。
- 两个前端页面可以双向跳转。

随后用于更完整演示的 5000 行合成 CSV 也已导入并激活，其中 SALE/RENT 各 2500 行。排查“浦东新区 3 室 2 厅平均房价”时再次核对了本地 CSV SHA-256 与活动数据集记录，两者一致。这里保留 20 行结果是为了记录当时从空环境完成全链路验收的基线，不代表当前活动集仍只有 20 行。

## 17. 可复用的工程经验

1. **初始化脚本必须可重复运行。** 首次成功不代表重启、重建或已有卷场景也成功。
2. **健康检查必须对应真实依赖。** 端口开放、进程运行和业务 Schema 可用是三个不同状态。
3. **跨数据源发布应先对账再切换。** 不要让用户直接看到半完成的新版本。
4. **安全正确不等于业务正确。** AST 能阻止 DROP，却不能判断“房价”是否被错误写成“租金”。
5. **Prompt 是软约束，程序校验是硬约束。** 可确定的指标映射、权限和重试次数应由代码控制。
6. **容器内外地址必须分开理解。** 宿主机可以用 3307，容器间仍应使用服务名和 3306。
7. **数据问题要沿血缘逐层核对。** CSV、原始表、活动指针、Agent 视图和生成 SQL 必须分别验证。
8. **错误修复要补回归测试或启动验收。** 否则修复往往只覆盖当次环境，无法防止复发。
