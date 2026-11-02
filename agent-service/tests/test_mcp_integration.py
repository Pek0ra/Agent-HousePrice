import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api.dependencies import get_mysql_agent
from app.config import Settings
from app.main import create_app
from app.mcp_client import McpUnavailableError, TurnMcpClient
from app.agents.mysql_agent import MysqlNaturalLanguageAgent
from tests.test_function_calling import Audit, StaticJev, ToolModel, call


def client(**kwargs):
    return TurnMcpClient(Settings(**{"mcp_server_module": "tests.mcp_fixture_server", **kwargs}),
        "mysql", {"v_agent_house_listing"})


def test_process_mcp_list_and_call():
    tools = client()
    assert tools.names == ("lookup_metric_definition", "get_mysql_schema", "query_mysql_readonly")
    assert tools.invoke("lookup_metric_definition", {"question": "上海房价"}).ok
    schema = tools.invoke("get_mysql_schema", {})
    assert schema.ok and [view.name for view in schema.data.views] == ["v_agent_house_listing"]
    query = tools.invoke("query_mysql_readonly", {"sql": "SELECT unit_price FROM v_agent_house_listing"})
    assert query.ok and query.data.rows == [[12345]]


def test_mcp_rejects_forgery_and_unsafe_sql():
    tools = client(sql_max_rows=2)
    for name, args, code in [
        ("query_hive_readonly", {"sql": "SELECT city FROM v_agent_house_info_analysis"}, "unavailable"),
        ("query_mysql_readonly", {"sql": "SELECT unit_price FROM other_table"}, "unsafe_sql"),
        ("query_mysql_readonly", {"sql": "DELETE FROM v_agent_house_listing"}, "unsafe_sql"),
        ("query_mysql_readonly", {"sql": "SELECT unit_price FROM v_agent_house_listing", "source": "hive"}, "invalid_arguments"),
        ("get_mysql_schema", {"allowed_tables": ["other_table"]}, "invalid_arguments"),
    ]:
        result = tools.invoke(name, args)
        assert not result.ok and result.error.code == code
    query = tools.invoke("query_mysql_readonly", {"sql": "SELECT unit_price FROM v_agent_house_listing LIMIT 500"})
    assert query.ok and query.data.rows == [[1], [2]] and "LIMIT 2" in query.data.sql
    hive = TurnMcpClient(Settings(big_data_enabled=False, mcp_server_module="tests.mcp_fixture_server"),
        "hive", {"v_agent_house_info_analysis"})
    with pytest.raises(McpUnavailableError):
        _ = hive.names


def test_enabled_hive_exposes_only_hive_tools():
    hive = TurnMcpClient(Settings(big_data_enabled=True, mcp_server_module="tests.mcp_fixture_server"),
        "hive", {"v_agent_house_info_analysis"})
    assert hive.names == ("lookup_metric_definition", "get_hive_schema", "query_hive_readonly")
    assert hive.invoke("get_hive_schema", {}).ok
    assert hive.invoke("query_hive_readonly",
        {"sql": "SELECT unit_price FROM v_agent_house_info_analysis"}).data.rows == [[8800]]
    assert hive.invoke("query_mysql_readonly",
        {"sql": "SELECT unit_price FROM v_agent_house_listing"}).error.code == "unavailable"


def test_mcp_server_stopped_is_explicit():
    tools = client(mcp_server_module="tests.missing_server")
    with pytest.raises(McpUnavailableError, match="MCP Server 不可用"):
        _ = tools.names


def test_chat_api_reports_mcp_outage(tmp_path):
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"),
        mcp_server_module="tests.missing_server")
    agent = MysqlNaturalLanguageAgent(settings, model=ToolModel([]),
        audit_repository=Audit(), jev_client=StaticJev())
    app = create_app()
    app.dependency_overrides[get_mysql_agent] = lambda: agent
    response = TestClient(app).post("/api/v1/chat", json={"message": "上海房价是多少？"})
    assert response.status_code == 503
    assert "MCP Server 不可用" in response.json()["detail"]


def test_chat_api_uses_mcp_and_preserves_response(tmp_path):
    model = ToolModel([
        call("query_mysql_readonly", {"sql": "SELECT unit_price FROM v_agent_house_listing"}),
        AIMessage(content="上海挂牌单价为 12345 元。"),
    ])
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"),
        mcp_server_module="tests.mcp_fixture_server")
    agent = MysqlNaturalLanguageAgent(settings, model=model, audit_repository=Audit(), jev_client=StaticJev())
    app = create_app()
    app.dependency_overrides[get_mysql_agent] = lambda: agent
    response = TestClient(app).post("/api/v1/chat", json={"message": "上海房价是多少？"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] == [[12345]]
    assert body["details"]["successful_queries"] == 1
    assert body["details"]["allowed_tools"] == ["lookup_metric_definition", "get_mysql_schema", "query_mysql_readonly"]
    assert body["answer"] and body["columns"] == ["unit_price"]


def test_chat_api_preserves_chart(tmp_path):
    model = ToolModel([
        call("query_mysql_readonly", {"sql": "SELECT listing_month, avg_unit_price FROM v_agent_monthly_price_trend"}),
        AIMessage(content="上海挂牌单价逐月上升。"),
    ])
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"),
        mcp_server_module="tests.mcp_fixture_server")
    agent = MysqlNaturalLanguageAgent(settings, model=model, audit_repository=Audit(),
        jev_client=StaticJev("trend", "current_listing"))
    app = create_app()
    app.dependency_overrides[get_mysql_agent] = lambda: agent
    response = TestClient(app).post("/api/v1/chat", json={"message": "上海房价月度趋势如何？"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["rows"]) == 2 and body["chart"]["type"] == "line"


def test_chat_mcp_rejects_second_successful_query(tmp_path):
    sql = "SELECT unit_price FROM v_agent_house_listing"
    model = ToolModel([call("query_mysql_readonly", {"sql": sql}, 1),
        call("query_mysql_readonly", {"sql": sql}, 2),
        AIMessage(content="上海挂牌单价为 12345 元。")])
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"),
        mcp_server_module="tests.mcp_fixture_server")
    agent = MysqlNaturalLanguageAgent(settings, model=model, audit_repository=Audit(), jev_client=StaticJev())
    app = create_app()
    app.dependency_overrides[get_mysql_agent] = lambda: agent
    response = TestClient(app).post("/api/v1/chat", json={"message": "上海房价是多少？"})
    assert response.status_code == 200, response.text
    assert response.json()["details"]["successful_queries"] == 1
    tool_messages = [message for message in model.seen[-1] if message.type == "tool"]
    assert tool_messages[-1].content.find('"unavailable"') >= 0
