# 城析：房价智能问数与分析平台

这是一个面向城市房源数据的自然语言问数项目。用户不需要编写 SQL，只需用中文提出“上海浦东三室一厅的平均房价是多少？”或“北京各区平均房价最高的五个区是哪几个？”等问题，系统便会理解查询意图、选择合适的数据源、生成并校验只读 SQL，并以结论、明细表格和图表的形式返回结果。

项目的初衷不是简单地让大模型“直接连库”，而是探索一条可解释、可审计、可控制的智能问数路径：业务指标由知识库约束，模型生成的 SQL 经过 AST 安全校验，数据库账号遵循最小权限原则，每次查询均带有执行信息和审计记录。同时，项目兼顾日常业务查询和离线分析两类场景，可在轻量的 MySQL 模式与包含 HDFS/Hive 的大数据模式之间切换。

## 主要功能

- 中文自然语言问数，返回数据结论、SQL、结果表格和 ECharts 图表。
- 自动识别问题意图，并根据问题选择 MySQL 实时业务视图或 Hive 离线分析视图。
- 基于 Markdown 业务知识库的轻量 RAG，统一房价、租金、趋势、性价比等指标口径。
- 房源 CRUD、分页筛选、区域统计和价格趋势等 Java REST API。
- SALE/RENT 混合 CSV 校验、导入、任务查询、失败重试和历史数据集回滚。
- 版本化数据集：新数据通过 MySQL/Hive 对账后才切换为活动版本。
- SQLGlot AST 校验、白名单视图、查询限行、执行超时、有限修复及独立审计账号。
- React 问数工作台，保留最近 30 条浏览器本地会话，并展示数据源、耗时、选表、重试次数和 trace ID。
- Docker Compose 一键运行核心服务，并可按需启用 HDFS/Hive。

## 系统架构

```text
浏览器
  │
  ▼
React + Nginx（统一入口）
  ├── /api/agent/* ──► FastAPI + LangGraph Agent
  │                       ├── 业务语义 RAG
  │                       ├── SQL 生成与 SQLGlot 校验
  │                       ├── MySQL 只读视图
  │                       └── Hive 分析视图（bigdata 模式）
  │
  └── /api/java/*  ──► Spring Boot + MyBatis
                          ├── 房源管理与实时统计 ──► MySQL
                          └── CSV 导入编排 ──► MySQL / HDFS / Hive
```

| 组件 | 技术栈 | 主要职责 |
| --- | --- | --- |
| `frontend/` | React 19、TypeScript、Vite、ECharts、Nginx | 问数交互、表格/图表展示、执行详情和统一反向代理 |
| `agent-service/` | Python 3.11+、FastAPI、LangGraph、LangChain、SQLGlot | 意图识别、RAG、选源、SQL 生成/修复、安全校验、答案生成与审计 |
| `backend-java/` | Java 17、Spring Boot 2.7、MyBatis、Flyway | 房源业务 API、MySQL 统计、CSV 导入编排及 Hive 分析 API |
| MySQL 8 | 业务存储 | 房源、租赁、导入任务、数据集状态、Agent 只读视图和审计记录 |
| HDFS / Hive 3.1 | 可选分析层 | 规范化文件存储、历史明细、聚合分析和数据质量统计 |
| Docker Compose | 容器编排 | 管理服务依赖、健康检查、网络和持久化卷 |

## 目录结构

```text
Agent-HousePrice/
├── frontend/                    # React 问数工作台与 Nginx 配置
├── agent-service/               # Python Agent、RAG 知识库及 pytest 测试
│   ├── app/agents/              # LangGraph 工作流、Prompt 与状态定义
│   ├── app/database/            # MySQL、Hive 和审计访问层
│   ├── app/rag/knowledge/       # 版本化业务指标文档
│   └── app/security/            # SQL AST 安全校验
├── backend-java/                # Spring Boot 业务服务
│   ├── src/main/java/           # Controller、Service、Mapper、导入管线
│   ├── src/main/resources/db/   # Flyway 数据库迁移
│   └── sql/hive/                # Hive 表与视图定义
├── infra/                       # MySQL、Hadoop、Hive 初始化与安全脚本
├── data/house_listings.csv      # 可直接导入的示例数据
├── docker-compose.yml           # 核心及 bigdata 服务编排
├── agent-evaluation-dataset.jsonl
└── AGENT_EVALUATION.md          # Agent 评测口径与数据快照说明
```

## 环境要求

推荐直接使用 Docker 启动。完整的大数据模式需要为 Docker Desktop 分配更多内存。

- Docker Desktop 或 Docker Engine，支持 Docker Compose v2。
- 可用的 OpenAI API Key，或兼容 OpenAI Chat Completions 接口的服务地址和模型名。没有模型配置时健康检查仍可用，但智能问数接口会返回 `503`。
- 如需脱离容器调试：Java 17、Python 3.11～3.14、Node.js 20+。
- Windows 示例命令使用 PowerShell；Linux/macOS 可替换为等价命令。

## 配置环境

在仓库根目录复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

至少修改以下配置，不要将真实密码或 API Key 提交到 Git：

```ini
MYSQL_PASSWORD=设置一个MySQL_root密码
AGENT_MYSQL_PASSWORD=设置一个Agent只读账号密码
AGENT_AUDIT_MYSQL_PASSWORD=设置一个Agent审计账号密码
IMPORT_MYSQL_PASSWORD=设置一个导入账号密码

OPENAI_API_KEY=你的模型密钥
OPENAI_MODEL=gpt-4.1-mini
# 使用兼容服务时填写；使用 OpenAI 官方接口时留空
OPENAI_BASE_URL=
```

常用配置说明：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FRONTEND_PORT` | `80` | Web 工作台宿主机端口 |
| `MYSQL_PORT` | 示例文件为 `3307` | MySQL 暴露到宿主机的端口 |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Agent 使用的模型名 |
| `SQL_MAX_ROWS` | `100` | Agent 查询最大返回行数 |
| `SQL_EXECUTION_TIMEOUT_MS` | `5000` | MySQL 查询超时毫秒数 |
| `SQL_MAX_REPAIR_ATTEMPTS` | `1` | SQL 生成失败后的最大修复次数，程序上限为 2 |
| `SPRING_PROFILES_ACTIVE` | `local` | Java 运行模式：`local` 或 `bigdata` |
| `BIG_DATA_ENABLED` | `false` | 是否启用 HDFS/Hive 路由和相关 Bean |
| `JAVA_MAVEN_PROFILE` | `local` | Java 镜像构建时是否打包 Hive/Hadoop 依赖 |

`SPRING_PROFILES_ACTIVE`、`BIG_DATA_ENABLED` 和 `JAVA_MAVEN_PROFILE` 应保持一致：核心模式分别使用 `local`、`false`、`local`；大数据模式分别使用 `bigdata`、`true`、`bigdata`。

## 使用 Docker 启动

### 核心模式（推荐首次使用）

核心模式启动 MySQL、数据库权限初始化、Java 后端、Python Agent、React/Nginx 前端，不启动 HDFS/Hive：

```powershell
docker compose up --build -d
docker compose ps -a
```

首次构建需要下载镜像和依赖。待 `mysql`、`java-backend`、`python-agent`、`frontend` 均为 `healthy` 后，打开：

- Web 问数工作台：<http://localhost>（修改过 `FRONTEND_PORT` 时使用对应端口）
- Java 健康检查：<http://localhost:9900/actuator/health>
- Python Agent 健康检查：<http://localhost:8000/health>
- FastAPI 接口文档：<http://localhost:8000/docs>

`mysql-agent-security` 显示 `Exited (0)` 是正常状态：它是一次性权限配置任务，不是常驻服务。

查看日志或停止服务：

```powershell
docker compose logs -f --tail=100 java-backend python-agent frontend
docker compose down
```

普通 `docker compose down` 会保留数据卷。只有明确需要清空 MySQL、Java、HDFS 和 Hive 的本地开发数据时才执行 `docker compose down -v`；该操作不可恢复。

### 大数据模式

大数据模式会额外启动 NameNode、DataNode、Hive Metastore 和 HiveServer2。根目录脚本会设置一致的 Java/Hive 配置、启动容器并等待 Hive 初始化：

```powershell
.\infra\bigdata\start-bigdata.ps1
```

也可以手动配置 `.env`：

```ini
JAVA_MAVEN_PROFILE=bigdata
SPRING_PROFILES_ACTIVE=bigdata
BIG_DATA_ENABLED=true
```

然后运行：

```powershell
docker compose --profile bigdata up --build -d
docker compose wait hive-init
docker compose --profile bigdata ps -a
```

大数据模式额外开放 NameNode Web UI `9870`、HiveServer2 JDBC `10001` 和 HiveServer2 Web UI `10002`。Hive 初始化任务 `hive-init` 成功完成后显示 `Exited (0)`，同样属于正常状态。

## 项目使用方法

### 1. 在网页中自然语言问数

打开 Web 工作台，在输入框直接提问。Enter 发送，Shift + Enter 换行。适合的问题包括：

- `上海浦东三室一厅的平均房价是多少？`
- `北京各区平均房价最高的五个区是哪几个？`
- `对比深圳南山区和福田区的平均租金。`
- `上海历史房价月度趋势如何？`（历史分析建议使用 bigdata 模式）
- `哪个区性价比最高？`（指标口径不明确时，Agent 会先请求澄清）

页面中可以核验最终结论、查询结果、图表、生成的 SQL、数据源、选中的表/视图、执行耗时、修复次数和 trace ID。最近 30 条会话只保存在当前浏览器的 `localStorage`，不是服务端会话。

### 2. 直接调用 Agent API

通过 Nginx 统一入口调用：

```powershell
$body = @{ message = '北京各区平均房价最高的五个区是哪几个？' } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost/api/agent/chat `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 12
```

也可直接请求 `POST http://localhost:8000/api/v1/chat`。典型响应包含：

```json
{
  "answer": "根据当前挂牌样本……",
  "sql": "SELECT ...",
  "columns": ["district", "avg_unit_price"],
  "rows": [["示例区", 50000.0]],
  "chart": null,
  "trace_id": "...",
  "details": {
    "data_source": "mysql",
    "duration_ms": 860,
    "selected_tables": ["v_agent_district_summary"],
    "retrieved_metrics": [],
    "row_count": 1,
    "retry_count": 0
  }
}
```

### 3. 使用 Java 业务接口

容器内的 Nginx 将 `/api/java/*` 转发为 Java 服务的 `/api/*`。常用接口如下：

| 方法 | 统一入口 | 功能 |
| --- | --- | --- |
| `GET` | `/api/java/system/capabilities` | 查看当前 local/bigdata 能力 |
| `GET` | `/api/java/houses?page=1&size=10` | 分页查询房源 |
| `POST` | `/api/java/houses` | 新增房源 |
| `GET/PUT/DELETE` | `/api/java/houses/{id}` | 查询、修改或删除单条房源 |
| `GET` | `/api/java/statistics/overview` | MySQL 实时统计概览 |
| `GET` | `/api/java/statistics/regions` | MySQL 区域均值 |
| `GET` | `/api/java/statistics/price-trends` | MySQL 价格趋势 |
| `GET` | `/api/java/analytics/*` | Hive 概览、区域、趋势和质量分析，仅 bigdata 模式 |

Java 业务接口统一返回 `{ "code": 0, "message": "success", "data": ... }`；非零 `code` 表示业务错误。

### 4. 导入示例 CSV（bigdata 模式）

CSV 导入接口仅在 bigdata 模式启用。示例文件 `data/house_listings.csv` 同时包含 SALE 和 RENT 数据：

```powershell
$result = curl.exe --silent --show-error --fail-with-body `
  -F "file=@data/house_listings.csv;type=text/csv" `
  http://localhost:9900/api/house-imports

$taskId = ($result | ConvertFrom-Json).data.id
Invoke-RestMethod "http://localhost:9900/api/house-imports/$taskId" | ConvertTo-Json -Depth 8
```

其他导入接口：

- `GET /api/house-imports/template`：下载 UTF-8 CSV 模板。
- `GET /api/house-imports/{id}`：查询任务状态和对账结果。
- `GET /api/house-imports/{id}/errors`：下载错误行报告。
- `POST /api/house-imports/{id}/retry`：幂等重试外部系统失败的任务。
- `POST /api/house-imports/{id}/activate`：回滚并激活一个已成功对账的历史数据集。

导入状态依次经过 `PENDING → VALIDATING → LOADING_MYSQL → UPLOADING_HDFS → LOADING_HIVE → COMPACTING_HIVE → VERIFYING → ACTIVATING → SUCCESS`。只有 CSV 有效行数、MySQL 行数和 Hive 明细/分析行数全部一致时，新数据集才会成为活动版本。重复上传完全相同的文件会返回 `409`，避免重复数据。

## 本地开发启动

Docker 模式最能还原完整依赖。本地运行适合在 IDE 中调试单个服务，通常仍建议先通过容器启动 MySQL。

### Java 服务

`.env.example` 默认将容器 MySQL 暴露到宿主机 `3307`，因此本地 Java 的 JDBC 地址也要使用该端口：

```powershell
docker compose up -d mysql

$env:MYSQL_URL = 'jdbc:mysql://localhost:3307/house_price?useUnicode=true&characterEncoding=UTF-8&connectionCollation=utf8mb4_0900_ai_ci&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true'
$env:MYSQL_USERNAME = 'root'
$env:MYSQL_PASSWORD = '与根目录.env一致的密码'
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:BIG_DATA_ENABLED = 'false'

Set-Location backend-java
.\mvnw.cmd spring-boot:run
```

Java 不会自动读取根目录 `.env`，在 IntelliJ IDEA 中调试时需将这些变量加入 Run Configuration。大数据模式需同时使用 Maven 的 `bigdata` profile：`.\mvnw.cmd -Pbigdata spring-boot:run`。

### Python Agent

```powershell
Set-Location agent-service
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

编辑 `agent-service/.env`，将 `MYSQL_PORT` 设置为宿主机实际映射端口（根目录示例为 `3307`），并填写 `house_agent_ro`、`house_agent_audit` 对应密码和模型配置。上述数据库账号由 Compose 的 `mysql-agent-security` 初始化任务创建。

### 前端

```powershell
Set-Location frontend
npm install
npm run dev
```

开发服务器默认由 Vite 启动；其代理目标定义在 `frontend/vite.config.ts`。生产容器由 Nginx 提供静态资源和同源 API 转发。

## 分层设计与实现思路

### 展示与接入层

React 工作台负责问题输入、会话历史、答案表格和图表展示；它不直接持有数据库信息。Nginx 作为浏览器唯一入口，将 Java 和 Agent 请求分别转发到内部容器，减少跨域配置并隔离内部服务地址。前端还把 SQL 和执行详情显式展示出来，使自然语言答案可追溯而不是黑盒输出。

### Agent 编排层

`agent-service/app/agents/mysql_agent.py` 使用 LangGraph 将问数过程拆成可控节点：

```text
意图识别 → 数据源选择 → 问题结构化 → 业务知识检索
        → 查询计划 → SQL 生成 → AST 校验 → 执行
        → 结果检查 → 必要时有限修复 → 答案/图表生成 → 审计
```

对于危险请求、不支持的问题或缺少关键口径的问题，工作流会拒绝或澄清，而不是强行生成 SQL。成功响应同时返回原始查询结果与执行元数据，方便前端展示、问题定位和离线评测。

### 业务语义 RAG 层

业务定义存放在 `agent-service/app/rag/knowledge/*.md`，每个文档包含关键词、状态、澄清方式和指标定义。检索器以确定性规则选取最相关文档，将业务口径注入 SQL 生成上下文。例如“总价”“单价”“月租金”“月度趋势”和“性价比”各自有独立定义。这样可以通过 Git 审查和版本管理业务知识，也能在指标含义模糊时主动澄清。

### SQL 与数据库安全层

安全边界不依赖 Prompt 自觉，而由多层机制共同约束：

1. Agent 只能访问白名单视图；MySQL 账号 `house_agent_ro` 仅拥有这些视图的 `SELECT` 权限。
2. SQLGlot 将 SQL 解析成 AST，拒绝非单条查询、DML/DDL、越权表、跨库限定名、`SELECT *` 和危险节点。
3. 校验器强制最大行数，数据库会话设置执行超时，SQL 只允许有限次数修复。
4. `house_agent_audit` 账号只允许向审计表写入，和业务只读账号相互隔离。
5. 每次请求记录问题、SQL、状态、结果行数、耗时、修复次数、错误摘要和 trace ID。

MySQL Agent 主要使用 `v_agent_house_listing`、`v_agent_district_summary` 和 `v_agent_monthly_price_trend`；Hive Agent 仅使用当前活动数据集对应的分析和质量视图。

### Java 业务与导入层

Spring Boot 采用 Controller → Service → Mapper/Repository 分层。MyBatis 负责 MySQL 业务读写，Flyway 负责数据库结构、视图与种子数据的版本迁移。`local` profile 只创建 MySQL 相关组件；`bigdata` profile 才注册 Hive/HDFS 数据源、分析接口和 CSV 导入管线，因此核心开发不必承担庞大的 Hadoop 依赖和资源开销。

CSV 导入采用“先暂存、后核验、最后切换”的思路。Java 完成格式和业务规则校验后，将同一份规范化数据写入 MySQL、HDFS 和 Hive，再比较各层行数；全部一致才原子性切换活动 `dataset_id`。旧版本继续保留，可以回滚，同时 Agent 视图始终只暴露活动版本。

### 数据存储与分析层

MySQL 服务实时 CRUD、分页筛选和轻量聚合，适合当前活动房源查询。HDFS 保存按数据集版本组织的规范化 CSV，Hive 保存历史明细、分析表和质量汇总，适合跨月趋势与较重的离线分析。Agent 根据意图选择数据源，使实时性与分析能力不必由同一个存储系统承担。

### 配置与基础设施层

Docker Compose 通过健康检查控制启动顺序，通过命名卷持久化 MySQL、Java 运行数据、HDFS 和 Hive Metastore。数据库迁移由 Flyway 管理；已有迁移文件不应修改，结构变化应新增更高版本的迁移。密码和模型密钥仅通过环境变量注入。

## 测试与验证

### 自动化测试

Python 测试覆盖 Agent 工作流分支、RAG 召回、SQL 安全边界、图表配置、审计以及 MySQL/Hive 路由：

```powershell
Set-Location agent-service
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Java 测试基于 H2 和测试夹具，覆盖应用启动、房源 CRUD、统计、CSV 校验、导入状态机和分析接口：

```powershell
Set-Location backend-java
.\mvnw.cmd test
# 同时编译/测试 Hive 相关代码
.\mvnw.cmd -Pbigdata test
```

前端通过 TypeScript 编译和生产构建验证类型及资源打包：

```powershell
Set-Location frontend
npm install
npm run build
```

Compose 配置可在启动前验证：

```powershell
docker compose config --quiet
docker compose --profile bigdata config --quiet
```

### 集成验证

核心模式至少检查以下内容：

```powershell
Invoke-RestMethod http://localhost:9900/actuator/health
Invoke-RestMethod http://localhost:9900/api/system/capabilities | ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:9900/api/statistics/overview | ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:8000/health
Invoke-WebRequest http://localhost/health -UseBasicParsing
```

预期 Java 状态为 `UP`、Agent 状态为 `ok`，能力接口显示 `mode=local` 和 `bigDataEnabled=false`。大数据模式还应验证 HDFS 存活节点、Hive 表、CSV 导入后的 MySQL/Hive 行数对账、Agent 的 Hive 路由，以及只读账号无法访问原始表或执行写语句。

### Agent 评测

根目录 `agent-evaluation-dataset.jsonl` 提供覆盖查询、澄清、数据源路由和安全攻击等场景的评测集。评测时应固定 `data/house_listings.csv` 数据快照，记录每条请求的原始响应，并考察 SQL 可执行性、结果正确性、答案忠实度、数据源选择、危险请求拒绝、延迟、模型调用和回归情况。详细字段和判定标准见 [AGENT_EVALUATION.md](./AGENT_EVALUATION.md)。

## 进一步阅读

- [Agent Prompt 与业务口径设计](./agent-service/docs/prompt-design.md)
- [房源字段字典](./backend-java/docs/house-info-field-dictionary.md)
- [Agent 评测说明](./AGENT_EVALUATION.md)
