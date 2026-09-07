$ErrorActionPreference = 'Stop'

$env:JAVA_MAVEN_PROFILE = 'bigdata'
$env:SPRING_PROFILES_ACTIVE = 'bigdata'
$env:BIG_DATA_ENABLED = 'true'

docker compose --profile bigdata up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "bigdata Compose startup failed (exit code: $LASTEXITCODE)"
}

docker compose wait hive-init
if ($LASTEXITCODE -ne 0) {
    throw "Hive initialization failed (exit code: $LASTEXITCODE)"
}

docker compose --profile bigdata ps -a
