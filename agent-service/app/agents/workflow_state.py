from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.channels import UntrackedValue

Intent = Literal[
    "listing_search",
    "aggregation",
    "ranking",
    "comparison",
    "trend",
    "data_quality",
    "policy",
    "policy_listing",
    "clarify",
    "unsafe_request",
    "unsupported",
]
DataSource = Literal["mysql", "hive", "policy", "none"]
RequestedScope = Literal["current_listing", "active_import", "import_quality", "policy", "none"]


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
    # Thread-scoped fields persisted by the LangGraph checkpointer.
    thread_id: str
    messages: list[dict[str, str]]
    conversation_context: dict[str, Any]
    previous_structured_question: dict[str, Any]
    pending_question: str | None

    # Turn-scoped fields. prepare_turn must reset every field in this section.
    current_question: str
    resolved_question: str
    trace_id: str
    data_source: DataSource
    requested_scope: RequestedScope
    intent: Intent
    selected_tables: list[str]
    retrieved_context: str
    retrieved_document_ids: list[str]
    retrieved_metrics: list[dict[str, str]]
    structured_question: dict[str, Any]
    query_plan: dict[str, Any]
    generated_sql: str
    validation_result: ValidationResult
    query_result: Annotated[QueryResult | None, UntrackedValue]
    retry_count: int
    final_answer: str
    chart_config: dict[str, Any] | None
    needs_clarification: bool
    metric_basis_ambiguity: bool
    clarification_question: str | None
    error: str
    raw_unsafe_detected: bool
    context_resolution: dict[str, Any]
    context_resolution_duration_ms: int
    model_usage: dict[str, Any]
    route_suggestion: dict[str, Any]
    route_reason: str
    route_reviewed: bool
    route_duration_ms: int
    jev_duration_ms: float | None
    jev_error_category: str | None
    qdrant_duration_ms: float | None
    rerank_duration_ms: float | None
    query_durations: list[dict[str, Any]]
    allowed_tools: list[str]
    tool_transcript: Annotated[list[Any] | None, UntrackedValue]
    pending_tool_calls: Annotated[list[dict[str, Any]] | None, UntrackedValue]
    proposed_answer: Annotated[str | None, UntrackedValue]
    tool_model_calls: int
    tool_call_count: int
    successful_queries: int
    policy_evidence: list[dict[str, Any]]
    policy_limitations: list[str]
    policy_tool_calls: list[dict[str, Any]]
    dependency_unavailable: bool
