import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


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
    typesafe_api_key: str | None = os.getenv("TYPESAFE_API_KEY") or None
    jev_model: str = os.getenv("JEV_MODEL", "jev-latest")
    jev_timeout_seconds: float = float(os.getenv("JEV_TIMEOUT_SECONDS", "5"))
    jev_confidence_threshold: float = float(os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.7"))
    jev_noul_margin: float = float(os.getenv("JEV_NOUL_MARGIN", "0.15"))
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
    tool_max_model_calls: int = int(os.getenv("TOOL_MAX_MODEL_CALLS", "6"))
    model_max_calls_per_turn: int = int(os.getenv("MODEL_MAX_CALLS_PER_TURN", "8"))
    tool_max_calls: int = int(os.getenv("TOOL_MAX_CALLS", "8"))
    tool_max_successful_queries: int = 1
    checkpoint_db_path: str = os.getenv(
        "CHECKPOINT_DB_PATH", "data/checkpoints/agent_checkpoints.sqlite"
    )
    conversation_history_max_messages: int = min(
        10, max(2, int(os.getenv("CONVERSATION_HISTORY_MAX_MESSAGES", "8")))
    )
    conversation_history_max_chars: int = min(
        12000, max(1000, int(os.getenv("CONVERSATION_HISTORY_MAX_CHARS", "6000")))
    )
    big_data_enabled: bool = _env_bool("BIG_DATA_ENABLED")
    hive_host: str = os.getenv("HIVE_HOST", "127.0.0.1")
    hive_port: int = int(os.getenv("HIVE_PORT", "10001"))
    hive_database: str = os.getenv("HIVE_DATABASE", "mydb")
    hive_username: str = os.getenv("HIVE_USERNAME", "hive")
    hive_auth: str = os.getenv("HIVE_AUTH", "NONE")
    cors_origins: tuple[str, ...] = _cors_origins()


settings = Settings()
