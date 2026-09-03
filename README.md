# 一线城市房价智能问数 Agent

项目的 Java 服务位于 `backend-java/`。MySQL 和 Java 后端均可通过 Docker Compose 运行；开发时仍可只启动 MySQL，并直接在 IDE 中调试 Java。Hive、HDFS 和 Python Agent 将在后续阶段接入。

## 1. 配置环境变量

复制根目录的 `.env.example` 为 `.env`，并修改 `MYSQL_PASSWORD`：

```powershell
Copy-Item .env.example .env
```

Docker Compose 会自动读取根目录 `.env` 中的 `MYSQL_PASSWORD` 和 `MYSQL_PORT`。

Java 不会自动读取 `.env` 文件。请在 IntelliJ IDEA 的 Run Configuration 中添加以下环境变量，或者在启动 Java 的同一个 PowerShell 窗口中设置：

```powershell
$env:MYSQL_URL = 'jdbc:mysql://localhost:3306/house_price?useUnicode=true&characterEncoding=UTF-8&connectionCollation=utf8mb4_0900_ai_ci&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true'
$env:MYSQL_USERNAME = 'root'
$env:MYSQL_PASSWORD = '替换为.env中的密码'
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:BIG_DATA_ENABLED = 'false'
```

## 2. Java 运行模式

| Profile | MySQL | Hive/HDFS | 用途 |
| --- | --- | --- | --- |
| `local` | 启用 | 禁用 | 默认本地开发模式，无需虚拟机 |
| `bigdata` | 启用 | 启用 | Hadoop/Hive 环境可用时使用 |

没有指定 profile 时默认使用 `local`。切换到大数据模式时设置：

```powershell
$env:SPRING_PROFILES_ACTIVE = 'bigdata'
$env:BIG_DATA_ENABLED = 'true'
```

bigdata 模式还需要配置 `HIVE_URL`、`HDFS_WEB_URL` 等环境变量。local 模式不会创建 Hive/HDFS Bean，也不会注册 Hive 分析和 CSV 导入接口。

Maven 同样区分依赖模式：`local`（默认）不会打包庞大的 Hive/Hadoop 依赖；需要运行 bigdata 模式时使用 `.\mvnw.cmd -Pbigdata package`。Docker 构建对应使用 `.env` 中的 `JAVA_MAVEN_PROFILE=local` 或 `bigdata`，该值应与 `SPRING_PROFILES_ACTIVE` 保持一致。

## 3. 启动 MySQL

在仓库根目录执行：

```powershell
docker compose up -d mysql
docker compose ps
```

首次创建数据卷时，`infra/mysql/init/01_database.sql` 会创建 UTF-8 的 `house_price` 数据库。表结构和初始化数据由 Java 启动时的 Flyway 自动管理：

1. `db/migration/V1__create_house_tables.sql`：创建业务表。
2. `db/migration/V2__seed_sample_house.sql`：写入示例房源。

旧数据库首次接入 Flyway 时会自动建立 baseline 0，然后执行现有迁移；后续数据库变更请新增更高版本的迁移文件，不要修改已经应用的迁移。

初始化脚本只会在数据卷为空时执行。普通的 `docker compose down` 不会删除数据；如需在开发环境中从头验证初始化，可执行 `docker compose down -v`，然后再次启动。`down -v` 会永久删除当前 Compose MySQL 数据卷中的所有数据，请勿用于需要保留数据的环境。

## 4. 启动 Java

设置上述环境变量后：

```powershell
Set-Location backend-java
.\mvnw.cmd package -DskipTests
java -jar target\prjspringboothive-ver1.0.jar
```

启动成功后可检查：

```powershell
Invoke-RestMethod http://localhost:9900/actuator/health
Invoke-RestMethod http://localhost:9900/api/system/capabilities
Invoke-RestMethod http://localhost:9900/api/statistics/overview
```

业务 API 统一返回数值业务码：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

### 阶段 2：两轮验证

第一轮验证自动化测试及 local 模式配置，不要求本机存在 Hive/HDFS：

```powershell
Set-Location backend-java
.\mvnw.cmd test
Set-Location ..
```

预期 Maven 显示 `BUILD SUCCESS`，当前测试数为 21，失败数为 0。

第二轮使用宿主机 Java 连接 Docker MySQL。先执行前文“启动 MySQL”和“启动 Java”的命令，然后另开 PowerShell：

```powershell
$health = Invoke-RestMethod http://localhost:9900/actuator/health
$caps = Invoke-RestMethod http://localhost:9900/api/system/capabilities
$stats = Invoke-RestMethod http://localhost:9900/api/statistics/overview

$health.status
$caps | ConvertTo-Json -Depth 5
$stats | ConvertTo-Json -Depth 5

try {
    Invoke-WebRequest http://localhost:9900/api/analytics/overview -UseBasicParsing
} catch {
    $_.Exception.Response.StatusCode.value__
}
```

预期分别看到：健康状态 `UP`、`mode` 为 `local`、`bigDataEnabled` 为 `false`、统计接口业务码为 `0`，Hive 分析接口状态码为 `404`。

## 5. 使用 Docker Compose 启动完整后端

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 java-backend
```

Compose 中的 Java 使用 `jdbc:mysql://mysql:3306/house_price` 访问 MySQL，不使用宿主机的 `localhost`。`java-backend` 会等 MySQL healthcheck 通过后再启动。MySQL 数据保存在 `agent-house-price-mysql-data`，Java 的运行数据目录保存在 `agent-house-price-java-data`；Java 日志写到标准输出，并由 Docker 的 `json-file` 驱动轮转。

### 阶段 3：两轮验证

第一轮检查配置、测试并单独构建镜像：

```powershell
docker compose config --quiet
Set-Location backend-java
.\mvnw.cmd test
Set-Location ..
docker compose build java-backend
```

所有命令都应以退出码 0 完成，测试应显示 `BUILD SUCCESS`。

第二轮模拟日常完整启动，不删除已有数据库数据：

```powershell
docker compose down
docker compose up --build -d
docker compose ps

$health = Invoke-RestMethod http://localhost:9900/actuator/health
$caps = Invoke-RestMethod http://localhost:9900/api/system/capabilities
$houses = Invoke-RestMethod 'http://localhost:9900/api/houses?page=1&size=10'
$stats = Invoke-RestMethod http://localhost:9900/api/statistics/overview

$health.status
$caps | ConvertTo-Json -Depth 5
$houses | ConvertTo-Json -Depth 5
$stats | ConvertTo-Json -Depth 5
curl.exe -s 'http://localhost:9900/api/houses?page=1&size=1'
docker compose logs --tail=100 java-backend
```

预期两个容器最终均为 `healthy`，健康状态为 `UP`，三个业务接口的 `code` 均为 `0`，`curl.exe` 输出中的房源中文正常，日志中出现 Java 启动成功及 Flyway schema 已为最新版本的信息。Windows PowerShell 5 的 `ConvertTo-Json` 可能错误解码没有 charset 参数的 JSON；中文验收以 `curl.exe` 或 Workbench 的原始显示为准。验证后可执行 `docker compose down` 停止服务；不要加 `-v`，否则会删除数据库和 Java 数据卷。

## 6. Workbench 验收

使用 `localhost:3306`、用户 `root` 和 `.env` 中的密码连接，然后执行：

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';

SELECT schema_name, default_character_set_name, default_collation_name
FROM information_schema.schemata
WHERE schema_name = 'house_price';

USE house_price;
SHOW TABLES;
SHOW CREATE TABLE house_info;
SHOW CREATE TABLE house_import_task;
SELECT installed_rank, version, description, success
FROM flyway_schema_history
ORDER BY installed_rank;

SELECT source_record_id, title, city, district, community, address
FROM house_info
WHERE source_record_id = 'SAMPLE-001';
```

预期字符集为 `utf8mb4`、排序规则为 `utf8mb4_0900_ai_ci`，表注释和示例数据中的中文应正常显示。

如果 Windows 的 `mysql.exe` 命令行显示 `CSV鍒癏DFS...`，但 Workbench 显示正常，通常是终端显示编码而不是数据库存储错误。可使用以下方式连接：

```powershell
mysql --default-character-set=utf8mb4 -h 127.0.0.1 -P 3306 -uroot -p
```

进入客户端后可执行 `SET NAMES utf8mb4;`。PowerShell 仍显示异常时，先执行 `chcp 65001`，或直接使用 Workbench 验证。
