"""Turn-local tool contracts. Inputs never contain connection or table choices."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LookupMetricInput(ToolInput):
    question: str = Field(min_length=1, max_length=2000)


class SchemaInput(ToolInput):
    pass


class QueryInput(ToolInput):
    sql: str = Field(min_length=1, max_length=20000)


class MetricDefinition(BaseModel):
    id: str
    title: str
    description: str
    status: str


class MetricLookupOutput(BaseModel):
    definitions: list[MetricDefinition]
    needs_clarification: bool
    clarification_question: str | None


class SchemaColumn(BaseModel):
    name: str
    type: str


class SchemaView(BaseModel):
    name: str
    description: str
    columns: list[SchemaColumn]


class SchemaOutput(BaseModel):
    source: Literal["mysql", "hive"]
    views: list[SchemaView]


class QueryOutput(BaseModel):
    source: Literal["mysql", "hive"]
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    is_empty: bool


class ToolError(BaseModel):
    code: Literal["invalid_arguments", "unavailable", "unsafe_sql", "execution_failed"]
    message: str


class ToolResult(BaseModel):
    ok: bool
    data: MetricLookupOutput | SchemaOutput | QueryOutput | None = None
    error: ToolError | None = None
