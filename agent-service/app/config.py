import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _cors_origins() -> tuple[str, ...]:
    raw_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:9900,http://127.0.0.1:9900",
    )
    return tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL") or None
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_database: str = os.getenv("MYSQL_DATABASE", "house_price")
    mysql_username: str = os.getenv("MYSQL_USERNAME", "house_agent_ro")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "house_agent_change_me")
    audit_mysql_username: str = os.getenv("AUDIT_MYSQL_USERNAME", "house_agent_audit")
    audit_mysql_password: str = os.getenv(
        "AUDIT_MYSQL_PASSWORD", "house_agent_audit_change_me"
    )
    sql_max_rows: int = int(os.getenv("SQL_MAX_ROWS", "100"))
    sql_execution_timeout_ms: int = int(os.getenv("SQL_EXECUTION_TIMEOUT_MS", "5000"))
    sql_max_repair_attempts: int = min(
        2, max(0, int(os.getenv("SQL_MAX_REPAIR_ATTEMPTS", "1")))
    )
    cors_origins: tuple[str, ...] = _cors_origins()


settings = Settings()
