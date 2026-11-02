"""Capability-scoped tools; no model invocation or persistent state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.database.hive import HIVE_ALLOWED_COLUMNS, HIVE_TABLE_DESCRIPTIONS
from app.database.mysql import ALLOWED_COLUMNS, TABLE_DESCRIPTIONS
from app.rag.retriever import MarkdownBusinessKnowledgeRetriever
from app.security.sql_validator import SqlValidator, UnsafeSqlError
from app.tools.contracts import (
    LookupMetricInput, MetricDefinition, MetricLookupOutput, QueryInput, QueryOutput,
    SchemaColumn, SchemaInput, SchemaOutput, SchemaView, ToolError, ToolInput, ToolResult,
    PolicySearchInput, PolicyReadInput, PolicyOutput,
)

Source = Literal["mysql", "hive", "policy"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    input_model: type[ToolInput]
    output_model: type[BaseModel]
    _handler: Callable[[ToolInput], BaseModel]

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            parsed = self.input_model.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, error=ToolError(code="invalid_arguments", message="工具参数无效，请按输入结构重试。"))
        try:
            return ToolResult(ok=True, data=self._handler(parsed))
        except UnsafeSqlError:
            return ToolResult(ok=False, error=ToolError(code="unsafe_sql", message="SQL 仅能读取本轮允许的视图；请检查语句、表名和 LIMIT。"))
        except Exception:
            return ToolResult(ok=False, error=ToolError(code="execution_failed", message="工具执行失败，请检查查询后重试。"))


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def get(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        definition = self.get(name)
        if definition is None:
            return ToolResult(ok=False, error=ToolError(code="unavailable", message="本轮不可使用该工具。"))
        return definition.invoke(arguments)

    def as_langchain_tools(self) -> list[Any]:
        """Expose only this registry's Pydantic schemas to bind_tools."""
        from langchain_core.tools import StructuredTool

        descriptions = {
            "lookup_metric_definition": "查询业务指标定义与歧义状态。参数为当前问题。",
            "get_mysql_schema": "查看本轮允许的 MySQL Agent 视图及列。无参数。",
            "get_hive_schema": "查看本轮允许的 Hive Agent 视图及列。无参数。",
            "query_mysql_readonly": "执行受控 MySQL 只读 SQL；只能访问本轮视图。",
            "query_hive_readonly": "执行受控 Hive 只读 SQL；只能访问本轮视图。",
            "search_policy": "检索经机器检查的北京政策条款，返回原文及来源。",
            "read_policy_clause": "按检索得到的 chunk_id 读取政策条款。",
        }
        return [
            StructuredTool.from_function(
                func=lambda _name=name, **kwargs: self.invoke(_name, kwargs).model_dump_json(),
                name=name,
                description=descriptions[name],
                args_schema=definition.input_model,
            )
            for name, definition in self._definitions.items()
        ]


def build_tool_registry(
    *,
    settings: Settings,
    selected_tables: set[str],
    source: Source,
    mysql_database: Any,
    hive_database: Any | None = None,
    retriever: MarkdownBusinessKnowledgeRetriever | None = None,
    policy_store: Any | None = None,
) -> ToolRegistry:
    """Build once per turn from trusted routing state, never from tool arguments."""
    if source not in ("mysql", "hive", "policy"):
        raise ValueError("Unsupported data source")
    if source == "policy":
        if selected_tables:
            raise ValueError("Policy tools cannot select SQL views")
        if policy_store is None:
            from app.rag.policy_store import PolicyStore
            policy_store = PolicyStore(settings.policy_qdrant_location)
        def search(value: ToolInput) -> PolicyOutput:
            assert isinstance(value, PolicySearchInput)
            return PolicyOutput.model_validate(policy_store.search(value.question, as_of=value.as_of,
                published_by_date=value.published_by_date, topic=value.topic, limit=value.limit))
        def read(value: ToolInput) -> PolicyOutput:
            assert isinstance(value, PolicyReadInput)
            point = policy_store.client.retrieve("beijing_policy_v1", ids=[value.chunk_id], with_payload=True)
            evidence = [p.payload for p in point if p.payload["review_status"] == "machine_checked"]
            from datetime import datetime, timezone
            return PolicyOutput(retrieved_at=datetime.now(timezone.utc).isoformat(), evidence=evidence,
                limitations=["条款不存在或尚未人工核对"] if not evidence else [])
        return ToolRegistry([ToolDefinition("search_policy", PolicySearchInput, PolicyOutput, search),
                             ToolDefinition("read_policy_clause", PolicyReadInput, PolicyOutput, read)])
    if settings.sql_max_rows < 1:
        raise ValueError("SQL row limit must be positive")
    if source == "hive" and (not settings.big_data_enabled or hive_database is None):
        raise ValueError("Hive is unavailable")
    allowed = HIVE_ALLOWED_COLUMNS if source == "hive" else ALLOWED_COLUMNS
    database = hive_database if source == "hive" else mysql_database
    if not selected_tables or not selected_tables <= allowed.keys():
        raise ValueError("Invalid turn table selection")
    if not selected_tables <= database.allowed_tables:
        raise ValueError("Selected views are unavailable")
    selected = frozenset(selected_tables)
    knowledge = retriever or MarkdownBusinessKnowledgeRetriever()

    def lookup(value: ToolInput) -> MetricLookupOutput:
        assert isinstance(value, LookupMetricInput)
        result = knowledge.retrieve(value.question)
        return MetricLookupOutput(
            definitions=[MetricDefinition(id=doc.document_id, title=doc.title, description=doc.content, status=doc.status) for doc in result.documents],
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
        )

    def schema(_: ToolInput) -> SchemaOutput:
        # The adapter verifies actual columns; only the selected subset is exposed.
        raw = database.describe_allowed_schema()
        sections = {part.split("\n", 1)[0].removeprefix("TABLE "): part for part in raw.split("\n\n")}
        descriptions = HIVE_TABLE_DESCRIPTIONS if source == "hive" else TABLE_DESCRIPTIONS
        views = []
        for name in sorted(selected):
            section = sections.get(name)
            if section is None:
                raise RuntimeError("Selected schema unavailable")
            column_line = next((line.removeprefix("COLUMNS: ") for line in section.splitlines() if line.startswith("COLUMNS: ")), None)
            if column_line is None:
                raise RuntimeError("Selected schema unavailable")
            names = "|".join(re.escape(column) for column in allowed[name])
            parts = re.split(rf", (?=(?:{names}) )", column_line)
            actual = dict(part.strip().split(" ", 1) for part in parts)
            views.append(SchemaView(
                name=name, description=descriptions[name],
                columns=[SchemaColumn(name=column, type=actual[column]) for column in allowed[name]],
            ))
        return SchemaOutput(source=source, views=views)

    def query(value: ToolInput) -> QueryOutput:
        assert isinstance(value, QueryInput)
        normalized = SqlValidator(set(selected), max_rows=settings.sql_max_rows, dialect=source).validate_and_normalize(value.sql)
        query_started = time.perf_counter()
        columns, rows = database.execute_read_only(normalized)
        query_duration_ms = round((time.perf_counter() - query_started) * 1000, 3)
        # Bound even a misbehaving adapter before handing rows to a caller.
        def json_value(cell: Any) -> Any:
            if isinstance(cell, Decimal):
                return float(cell)
            if isinstance(cell, (date, datetime)):
                return cell.isoformat()
            return cell
        bounded = [[json_value(cell) for cell in row] for row in rows[: settings.sql_max_rows]]
        return QueryOutput(source=source, sql=normalized, columns=list(columns), rows=bounded,
                           query_duration_ms=query_duration_ms,
                           row_count=len(bounded), is_empty=not bounded or all(all(cell is None for cell in row) for row in bounded))

    definitions = [ToolDefinition("lookup_metric_definition", LookupMetricInput, MetricLookupOutput, lookup)]
    definitions.append(ToolDefinition(f"get_{source}_schema", SchemaInput, SchemaOutput, schema))
    definitions.append(ToolDefinition(f"query_{source}_readonly", QueryInput, QueryOutput, query))
    return ToolRegistry(definitions)
