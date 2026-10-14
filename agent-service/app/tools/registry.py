"""Capability-scoped tools; no model invocation or persistent state."""

from __future__ import annotations

from dataclasses import dataclass
import re
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
)

Source = Literal["mysql", "hive"]


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
) -> ToolRegistry:
    """Build once per turn from trusted routing state, never from tool arguments."""
    if source not in ("mysql", "hive"):
        raise ValueError("Unsupported data source")
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
        columns, rows = database.execute_read_only(normalized)
        # Bound even a misbehaving adapter before handing rows to a caller.
        bounded = [list(row) for row in rows[: settings.sql_max_rows]]
        return QueryOutput(source=source, sql=normalized, columns=list(columns), rows=bounded,
                           row_count=len(bounded), is_empty=not bounded or all(all(cell is None for cell in row) for row in bounded))

    definitions = [ToolDefinition("lookup_metric_definition", LookupMetricInput, MetricLookupOutput, lookup)]
    definitions.append(ToolDefinition(f"get_{source}_schema", SchemaInput, SchemaOutput, schema))
    definitions.append(ToolDefinition(f"query_{source}_readonly", QueryInput, QueryOutput, query))
    return ToolRegistry(definitions)
