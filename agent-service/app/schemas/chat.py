from typing import Any

from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Safe conversation identifier returned by an earlier response.",
    )


class ContextResolution(BaseModel):
    depends_on_history: bool
    standalone_question: str
    inherited_fields: list[str] = Field(default_factory=list)
    overridden_fields: list[str] = Field(default_factory=list)
    unresolved_reference: bool = False
    clarification_question: str | None = None


class RetrievedMetric(BaseModel):
    id: str
    title: str
    description: str


class ExecutionDetails(BaseModel):
    data_source: str = "none"
    duration_ms: int = 0
    selected_tables: list[str] = Field(default_factory=list)
    retrieved_metrics: list[RetrievedMetric] = Field(default_factory=list)
    row_count: int = 0
    retry_count: int = 0
    used_history: bool = False
    inherited_fields: list[str] = Field(default_factory=list)
    overridden_fields: list[str] = Field(default_factory=list)
    context_resolution_duration_ms: int = 0
    model_calls: int = 0
    prompt_tokens: int | None = 0
    completion_tokens: int | None = 0
    total_tokens: int | None = 0
    route_suggestion: dict[str, Any] | None = None
    route_reason: str | None = None
    route_reviewed: bool = False
    route_duration_ms: int = 0
    allowed_tools: list[str] = Field(default_factory=list)
    tool_model_calls: int = 0
    tool_call_count: int = 0
    successful_queries: int = 0


class QuestionSlots(BaseModel):
    """Only explicit filters from the current user question; omitted means inherit if dependent."""
    cities: list[str] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    listing_type: str | None = None
    metric: str | None = None
    bedroom_count: int | None = None
    living_room_count: int | None = None
    start_month: str | None = None
    end_month: str | None = None
    ranking_limit: int | None = None
    clear_districts: bool = False
    clear_layout: bool = False
    clear_months: bool = False


class RouteReview(BaseModel):
    intent: str
    scope: str
    depends_on_previous: bool
    multiple_tasks: bool


class ChatResponse(BaseModel):
    answer: str
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    chart: dict[str, Any] | None = None
    trace_id: str
    thread_id: str
    details: ExecutionDetails = Field(default_factory=ExecutionDetails)


class QueryPlan(BaseModel):
    needs_clarification: bool = Field(
        description="Whether answering safely requires more information from the user."
    )
    clarification_question: str | None = Field(
        default=None,
        description="A concise Chinese follow-up question when clarification is required.",
    )
    sql: str | None = Field(
        default=None,
        description="One read-only SELECT statement in the selected SQL dialect, or null when clarification is required.",
    )


class AnswerDraft(BaseModel):
    answer: str = Field(description="A concise Chinese answer grounded only in query results.")
