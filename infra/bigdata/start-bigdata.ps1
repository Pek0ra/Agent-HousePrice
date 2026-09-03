$ErrorActionPreference = 'Stop'

$env:JAVA_MAVEN_PROFILE = 'bigdata'
$env:SPRING_PROFILES_ACTIVE = 'bigdata'
$env:BIG_DATA_ENABLED = 'true'

docker compose --profile bigdata up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "bigdata Compose 启动失败，退出码：$LASTEXITCODE"
}

docker compose --profile bigdata ps -a
