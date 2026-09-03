from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.mysql_agent import (
    AgentNotConfiguredError,
    AgentQueryError,
    MysqlNaturalLanguageAgent,
)
from app.api.dependencies import get_mysql_agent
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/api/v1/chat", response_model=ChatResponse, tags=["agent"])
def chat(
    request: ChatRequest,
    agent: MysqlNaturalLanguageAgent = Depends(get_mysql_agent),
) -> ChatResponse:
    try:
        return agent.ask(request.message)
    except AgentNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AgentQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
