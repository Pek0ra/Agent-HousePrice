import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.mysql_agent import (
    AgentCheckpointError, AgentDependencyError, AgentNotConfiguredError, AgentQueryError,
)
from app.api.dependencies import get_mysql_agent
from app.schemas.chat import ChatResponse


class FakeAgent:
    def ask(self, question: str, thread_id: str | None = None) -> ChatResponse:
        return ChatResponse(
            answer="浦东新区三室一厅挂牌房源平均月租金约为 8500 元/月。",
            sql=(
                "SELECT ROUND(AVG(monthly_rent), 2) AS avg_monthly_rent "
                "FROM v_agent_house_listing WHERE city = '上海市' "
                "AND district = '浦东新区' AND bedroom_count = 3 "
                "AND living_room_count = 1 LIMIT 100"
            ),
            columns=["avg_monthly_rent"],
            rows=[[8500.0]],
            chart=None,
            trace_id="test-trace-id",
            thread_id=thread_id or "generated-thread-id",
        )

def test_health(api_client: TestClient) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.json() == {"status": "ok"}


def test_chat_returns_query_result_contract(api_client: TestClient, override_agent) -> None:
    override_agent(FakeAgent())
    response = api_client.post(
        "/api/v1/chat", json={"message": "上海浦东三室一厅的平均租金是多少？"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["avg_monthly_rent"]
    assert body["rows"] == [[8500.0]]
    assert body["chart"] is None
    assert body["trace_id"] == "test-trace-id"
    assert body["thread_id"] == "generated-thread-id"
    assert body["details"]["data_source"] == "none"
    assert body["details"]["duration_ms"] == 0
    assert body["sql"].startswith("SELECT")
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert "浦东新区三室一厅" in response.content.decode("utf-8")


def test_chat_rejects_an_empty_message(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/chat", json={"message": ""})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json; charset=utf-8"


def test_chat_continues_the_supplied_thread(api_client: TestClient, override_agent) -> None:
    override_agent(FakeAgent())
    response = api_client.post(
        "/api/v1/chat",
        json={"message": "那深圳南山区呢？", "thread_id": "thread_123"},
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == "thread_123"


@pytest.mark.parametrize("thread_id", ["../checkpoint.db", "a/b", "x" * 65, "-leading", "space id", "中文", ""])
def test_chat_rejects_unsafe_thread_ids(api_client: TestClient, thread_id: str) -> None:
    response = api_client.post(
        "/api/v1/chat", json={"message": "查询上海房价", "thread_id": thread_id}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("error,status", [
    (AgentCheckpointError("会话状态暂时无法读取或保存，请稍后重试。"), 503),
    (AgentDependencyError("依赖不可用"), 503),
    (AgentNotConfiguredError("配置缺失"), 503),
    (AgentQueryError("查询无效"), 422),
])
def test_agent_errors_are_safe_http_responses(
    api_client: TestClient, override_agent, error: Exception, status: int,
) -> None:
    class BrokenAgent:
        def ask(self, question: str, thread_id: str | None = None) -> ChatResponse:
            raise error

    override_agent(BrokenAgent())
    response = api_client.post("/api/v1/chat", json={"message": "查询上海房价"})

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}
    assert "Traceback" not in response.text


def test_agent_override_is_isolated(api_app: FastAPI) -> None:
    assert get_mysql_agent not in api_app.dependency_overrides
