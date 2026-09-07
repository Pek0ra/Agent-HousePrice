from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.mysql_agent import (
    AgentCheckpointError,
    AgentNotConfiguredError,
    AgentQueryError,
    MysqlNaturalLanguageAgent,
)
from app.api.dependencies import get_mysql_agent
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/v1/capabilities", tags=["system"])
def capabilities() -> dict:
    return {
        "mysql": True,
        "hive": settings.big_data_enabled,
        "model_configured": bool(settings.openai_api_key),
        "model": settings.openai_model,
    }


@router.post("/api/v1/chat", response_model=ChatResponse, tags=["agent"])
def chat(
    request: ChatRequest,
    agent: MysqlNaturalLanguageAgent = Depends(get_mysql_agent),
) -> ChatResponse:
    try:
        return agent.ask(request.message, request.thread_id)
    except AgentCheckpointError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
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
