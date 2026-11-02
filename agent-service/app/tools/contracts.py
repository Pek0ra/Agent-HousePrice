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


class PolicySearchInput(ToolInput):
    question: str = Field(min_length=1, max_length=2000)
    as_of: str | None = None
    published_by_date: bool = False
    topic: Literal["tax", "provident_fund", "purchase_restriction", "housing"] | None = None
    limit: int = Field(default=5, ge=1, le=10)


class PolicyReadInput(ToolInput):
    chunk_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class PolicyOutput(BaseModel):
    retrieved_at: str
    evidence: list[dict[str, Any]]
    limitations: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


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
    query_duration_ms: float | None = None


class ToolError(BaseModel):
    code: Literal["invalid_arguments", "unavailable", "unsafe_sql", "execution_failed"]
    message: str


class ToolResult(BaseModel):
    ok: bool
    data: MetricLookupOutput | SchemaOutput | QueryOutput | PolicyOutput | None = None
    error: ToolError | None = None
