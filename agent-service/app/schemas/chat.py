from typing import Any

from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


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


class ChatResponse(BaseModel):
    answer: str
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    chart: dict[str, Any] | None = None
    trace_id: str
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
