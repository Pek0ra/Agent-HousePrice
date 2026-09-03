from __future__ import annotations

from typing import Any, Literal, TypedDict

Intent = Literal[
    "listing_search",
    "aggregation",
    "ranking",
    "comparison",
    "trend",
    "unsafe_request",
    "unsupported",
]
DataSource = Literal["mysql", "hive", "none"]


class ValidationResult(TypedDict):
    valid: bool
    normalized_sql: str | None
    error: str | None


class QueryResult(TypedDict):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    is_empty: bool


class AgentWorkflowState(TypedDict, total=False):
    question: str
    trace_id: str
    data_source: DataSource
    intent: Intent
    selected_tables: list[str]
    retrieved_context: str
    retrieved_document_ids: list[str]
    structured_question: dict[str, Any]
    query_plan: dict[str, Any]
    generated_sql: str
    validation_result: ValidationResult
    query_result: QueryResult
    retry_count: int
    final_answer: str
    chart_config: dict[str, Any] | None
    needs_clarification: bool
    clarification_question: str | None
    error: str
