"""The model emits actual LangChain tool_calls; Python executes scoped tools."""

import json
import sqlite3

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agents.jev_router import RouteSuggestion
from app.agents.mysql_agent import AgentNotConfiguredError, AgentQueryError, MysqlNaturalLanguageAgent
from app.config import Settings
from app.database.hive import HIVE_ALLOWED_COLUMNS
from app.database.mysql import ALLOWED_COLUMNS
from app.schemas.chat import QuestionSlots


SQL = "SELECT unit_price FROM v_agent_house_listing"
ROW_MARKER = "ROW_SENTINEL_9bb13fa4"


def call(name, args=None, number=1):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": f"call_{number}"}])


class StaticJev:
    def __init__(self, intent="aggregation", scope="current_listing"):
        self.intent, self.scope = intent, scope

    def classify(self, question, previous, hive_available):
        return RouteSuggestion(intent=self.intent, scope=self.scope,
            intent_confidence=0.99, scope_confidence=0.99,
            intent_probability=0.99, scope_probability=0.99,
            depends_probability=0.01, multiple_probability=0.01)


class Database:
    def __init__(self, mapping=ALLOWED_COLUMNS, rows=None):
        self.allowed_tables = set(mapping)
        self.mapping = mapping
        self.rows = rows if rows is not None else [[ROW_MARKER]]
        self.executed = []

    def describe_allowed_schema(self):
        return "\n\n".join(f"TABLE {table}\nDESCRIPTION: test\nCOLUMNS: " +
            ", ".join(f"{column} DECIMAL" for column in columns)
            for table, columns in self.mapping.items())

    def execute_read_only(self, sql):
        self.executed.append(sql)
        return ["unit_price"], self.rows


class ToolModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.mode = None
        self.bound_names = []
        self.seen = []

    def with_structured_output(self, schema, **kwargs):
        self.mode = "slots"
        return self

    def bind_tools(self, tools, **kwargs):
        self.mode = "tools"
        self.bound_names.append(tuple(tool.name for tool in tools))
        return self

    def invoke(self, messages):
        if self.mode == "slots":
            return QuestionSlots(cities=["上海"], metric="unit_price", listing_type="SALE")
        self.seen.append(messages)
        return self.replies.pop(0)


class Audit:
    def __init__(self): self.records = []
    def record(self, **values): self.records.append(values)


def agent(tmp_path, replies, *, database=None, hive=None, jev=None, **limits):
    model = ToolModel(replies)
    audit = Audit()
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"),
                        big_data_enabled=hive is not None, **limits)
    instance = MysqlNaturalLanguageAgent(settings, database=database or Database(),
        hive_database=hive, model=model, audit_repository=audit, jev_client=jev or StaticJev())
    return instance, model, audit


def test_real_tool_call_flow_and_checkpoint_omits_rows(tmp_path):
    db = Database()
    model_replies = [
        call("lookup_metric_definition", {"question": "上海房价是多少？"}, 1),
        call("get_mysql_schema", {}, 2),
        call("query_mysql_readonly", {"sql": SQL}, 3),
        AIMessage(content="上海挂牌单价查询完成，结果来自挂牌样本。"),
    ]
    service, model, audit = agent(tmp_path, model_replies, database=db)
    response = service.ask("上海房价是多少？", "tool-thread")

    assert model.bound_names and all(names == (
        "lookup_metric_definition", "get_mysql_schema", "query_mysql_readonly")
        for names in model.bound_names)
    assert db.executed == [response.sql]
    assert response.rows == [[ROW_MARKER]]
    assert response.answer == "上海挂牌单价查询完成，结果来自挂牌样本。"
    assert response.details.model_calls == 5  # slot extraction plus four bound calls
    assert audit.records[0]["status"] == "SUCCESS"
    tool_results = [message for message in model.seen[-1] if isinstance(message, ToolMessage)]
    assert len(tool_results) == 3
    assert json.loads(tool_results[-1].content)["data"]["rows"] == [[ROW_MARKER]]
    checkpoint = service.get_conversation_state("tool-thread")
    assert "query_result" not in checkpoint
    assert "tool_transcript" not in checkpoint
    assert "pending_tool_calls" not in checkpoint
    assert ROW_MARKER.encode() not in (tmp_path / "checkpoint.sqlite").read_bytes()


def test_model_without_tool_call_cannot_invent_answer(tmp_path):
    db = Database()
    service, _, audit = agent(tmp_path, [AIMessage(content="房价是99999元。")], database=db)
    with pytest.raises(AgentNotConfiguredError, match="function calling"):
        service.ask("上海房价是多少？")
    assert db.executed == [] and audit.records[0]["status"] == "FAILED"


def test_model_may_ask_clarification_without_tool(tmp_path):
    service, _, audit = agent(tmp_path, [AIMessage(content="请明确要查询哪个城市？")])
    response = service.ask("上海房价是多少？")
    assert response.sql is None and response.answer.endswith("？")
    assert audit.records[0]["status"] == "CLARIFICATION"


@pytest.mark.parametrize("bad_call", [
    call("delete_all_houses", {}, 1),
    call("query_hive_readonly", {"sql": "SELECT city FROM v_agent_house_info_analysis"}, 1),
    call("query_mysql_readonly", {"sql": SQL, "database": "other"}, 1),
])
def test_unavailable_cross_source_and_invalid_arguments_return_error_to_model(tmp_path, bad_call):
    db = Database()
    service, model, _ = agent(tmp_path, [bad_call, call("query_mysql_readonly", {"sql": SQL}, 2),
        AIMessage(content="已根据挂牌样本回答。")], database=db)
    response = service.ask("上海房价是多少？")
    first_result = next(message for message in model.seen[1] if isinstance(message, ToolMessage))
    assert json.loads(first_result.content)["ok"] is False
    assert db.executed == [response.sql]
    assert response.details.allowed_tools == ["lookup_metric_definition", "get_mysql_schema", "query_mysql_readonly"]


def test_hive_route_binds_only_hive_tools(tmp_path):
    hive = Database(HIVE_ALLOWED_COLUMNS, rows=[[77]])
    service, model, _ = agent(tmp_path, [
        call("query_hive_readonly", {"sql": "SELECT unit_price FROM v_agent_house_info_analysis"}),
        AIMessage(content="历史挂牌样本为77。")], hive=hive,
        jev=StaticJev("trend", "active_import"))
    response = service.ask("上海导入数据集历史房价趋势如何？")
    assert response.details.data_source == "hive"
    assert model.bound_names[0] == ("lookup_metric_definition", "get_hive_schema", "query_hive_readonly")
    assert response.sql == hive.executed[0]


def test_query_failure_is_repaired_and_revalidated(tmp_path):
    db = Database()
    service, model, audit = agent(tmp_path, [
        call("query_mysql_readonly", {"sql": "DELETE FROM v_agent_house_listing"}, 1),
        call("query_mysql_readonly", {"sql": SQL}, 2),
        AIMessage(content="挂牌样本查询完成。")], database=db)
    response = service.ask("上海房价是多少？")
    assert response.details.retry_count == 1
    assert db.executed == [response.sql]
    assert audit.records[0]["repair_count"] == 1
    first_result = next(message for message in model.seen[1] if isinstance(message, ToolMessage))
    assert json.loads(first_result.content)["error"]["code"] == "unsafe_sql"


def test_model_and_tool_loop_limits_exit(tmp_path):
    service, _, _ = agent(tmp_path, [call("get_mysql_schema", {}, 1),
        call("get_mysql_schema", {}, 2)], tool_max_model_calls=2)
    with pytest.raises(AgentQueryError, match="上限"):
        service.ask("上海房价是多少？")
    service, _, _ = agent(tmp_path / "other", [call("get_mysql_schema", {}, 1),
        call("get_mysql_schema", {}, 2)], tool_max_calls=1)
    with pytest.raises(AgentQueryError, match="上限"):
        service.ask("上海房价是多少？")


def test_successful_query_cannot_be_executed_twice(tmp_path):
    db = Database()
    service, model, _ = agent(tmp_path, [
        call("query_mysql_readonly", {"sql": SQL}, 1),
        call("query_mysql_readonly", {"sql": SQL}, 2),
        AIMessage(content="挂牌样本查询完成。")], database=db)
    response = service.ask("上海房价是多少？")
    assert response.details.successful_queries == 1
    assert len(db.executed) == 1
    errors = [json.loads(message.content) for message in model.seen[-1] if isinstance(message, ToolMessage)]
    assert errors[-1]["error"]["code"] == "unavailable"


def test_bind_tools_incompatibility_is_explicit(tmp_path):
    class NoToolsModel(ToolModel):
        bind_tools = None
    model = NoToolsModel([])
    settings = Settings(openai_api_key="test", checkpoint_db_path=str(tmp_path / "checkpoint.sqlite"))
    service = MysqlNaturalLanguageAgent(settings, database=Database(), model=model,
        audit_repository=Audit(), jev_client=StaticJev())
    with pytest.raises(AgentNotConfiguredError, match="工具调用"):
        service.ask("上海房价是多少？")
