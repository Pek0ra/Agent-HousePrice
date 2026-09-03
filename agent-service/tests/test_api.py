from fastapi.testclient import TestClient

from app.api.dependencies import get_mysql_agent
from app.main import app
from app.schemas.chat import ChatResponse


class FakeAgent:
    def ask(self, question: str) -> ChatResponse:
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
        )

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.json() == {"status": "ok"}


def test_chat_returns_query_result_contract() -> None:
    app.dependency_overrides[get_mysql_agent] = lambda: FakeAgent()
    try:
        response = client.post(
            "/api/v1/chat", json={"message": "上海浦东三室一厅的平均租金是多少？"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["avg_monthly_rent"]
    assert body["rows"] == [[8500.0]]
    assert body["chart"] is None
    assert body["trace_id"] == "test-trace-id"
    assert body["details"]["data_source"] == "none"
    assert body["details"]["duration_ms"] == 0
    assert body["sql"].startswith("SELECT")
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert "浦东新区三室一厅" in response.content.decode("utf-8")


def test_chat_rejects_an_empty_message() -> None:
    response = client.post("/api/v1/chat", json={"message": ""})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json; charset=utf-8"
