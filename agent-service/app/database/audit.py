from __future__ import annotations

import json
import logging

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine

from app.config import Settings

logger = logging.getLogger("agent.audit")
logger.setLevel(logging.INFO)


class MysqlAuditRepository:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(
            URL.create(
                drivername="mysql+pymysql",
                username=settings.audit_mysql_username,
                password=settings.audit_mysql_password,
                host=settings.mysql_host,
                port=settings.mysql_port,
                database=settings.mysql_database,
                query={"charset": "utf8mb4"},
            ),
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    def record(
        self,
        *,
        trace_id: str,
        question: str,
        generated_sql: str | None,
        status: str,
        result_rows: int,
        repair_count: int,
        duration_ms: int,
        error_summary: str | None,
        thread_id: str | None,
        used_history: bool,
        inherited_fields: list[str],
        overridden_fields: list[str],
        context_resolution_duration_ms: int,
        model_calls: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> None:
        values = {
            "trace_id": trace_id,
            "question": question[:2000],
            "generated_sql": generated_sql,
            "status": status[:30],
            "result_rows": result_rows,
            "repair_count": repair_count,
            "duration_ms": duration_ms,
            "error_summary": error_summary[:1000] if error_summary else None,
            "thread_id": thread_id,
            "used_history": used_history,
            "inherited_fields": json.dumps(inherited_fields, ensure_ascii=False),
            "overridden_fields": json.dumps(overridden_fields, ensure_ascii=False),
            "context_resolution_duration_ms": context_resolution_duration_ms,
            "model_calls": model_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO agent_query_audit "
                    "(trace_id, question, generated_sql, status, result_rows, "
                    "repair_count, duration_ms, error_summary, thread_id, used_history, "
                    "inherited_fields, overridden_fields, context_resolution_duration_ms, "
                    "model_calls, prompt_tokens, completion_tokens, total_tokens) "
                    "VALUES (:trace_id, :question, :generated_sql, :status, "
                    ":result_rows, :repair_count, :duration_ms, :error_summary, "
                    ":thread_id, :used_history, :inherited_fields, :overridden_fields, "
                    ":context_resolution_duration_ms, :model_calls, :prompt_tokens, "
                    ":completion_tokens, :total_tokens)"
                ),
                values,
            )
        logger.info(
            "agent_query_audit trace_id=%s thread_id=%s status=%s rows=%s used_history=%s",
            trace_id,
            thread_id,
            status,
            result_rows,
            used_history,
        )
