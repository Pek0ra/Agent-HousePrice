from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agents.prompts import (
    ANSWER_SYSTEM_PROMPT,
    SQL_GENERATION_SYSTEM_PROMPT,
    SQL_REPAIR_SYSTEM_PROMPT,
)
from app.agents.workflow_state import AgentWorkflowState, Intent
from app.config import Settings
from app.database.audit import MysqlAuditRepository
from app.database.mysql import MysqlQueryDatabase
from app.rag.retriever import MarkdownBusinessKnowledgeRetriever
from app.schemas.chat import AnswerDraft, ChatResponse, QueryPlan
from app.security.sql_validator import SqlValidator

logger = logging.getLogger(__name__)

UNSAFE_PATTERN = re.compile(
    r"(忽略.{0,12}(规则|指令|限制)|删除|清空|销毁|修改|写入|"
    r"\b(delete|drop|truncate|alter|insert|update|create|grant|revoke)\b)",
    re.IGNORECASE,
)
HOUSING_PATTERN = re.compile(
    r"(房|租金|房价|挂牌|小区|行政区|均价|单价|总价|趋势|成交|性价比|划算)"
)

CITY_ALIASES = {
    "北京": "北京市",
    "上海": "上海市",
    "广州": "广州市",
    "深圳": "深圳市",
}
DISTRICT_ALIASES = {
    "浦东": "浦东新区",
    "南山": "南山区",
    "福田": "福田区",
}
CN_NUMBER = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


class AgentNotConfiguredError(RuntimeError):
    pass


class AgentQueryError(RuntimeError):
    pass


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _number(value: str) -> int:
    return int(value) if value.isdigit() else CN_NUMBER[value]


class MysqlNaturalLanguageAgent:
    """Single controlled LangGraph workflow for read-only housing queries."""

    def __init__(
        self,
        settings: Settings,
        database: MysqlQueryDatabase | None = None,
        model: ChatOpenAI | None = None,
        audit_repository: MysqlAuditRepository | None = None,
        knowledge_retriever: MarkdownBusinessKnowledgeRetriever | None = None,
        hive_database: Any | None = None,
    ) -> None:
        self._settings = settings
        self._database = database or MysqlQueryDatabase(settings)
        self._model = model
        self._audit_repository = audit_repository or MysqlAuditRepository(settings)
        self._knowledge_retriever = knowledge_retriever or MarkdownBusinessKnowledgeRetriever()
        if hive_database is not None:
            self._hive_database = hive_database
        elif settings.big_data_enabled:
            from app.database.hive import HiveQueryDatabase

            self._hive_database = HiveQueryDatabase(settings)
        else:
            self._hive_database = None
        self._graph = self._build_graph()

    @property
    def workflow_nodes(self) -> tuple[str, ...]:
        return tuple(
            name for name in self._graph.get_graph().nodes
            if name not in {"__start__", "__end__"}
        )

    def workflow_mermaid(self) -> str:
        return self._graph.get_graph().draw_mermaid()

    def _get_model(self) -> ChatOpenAI:
        if self._model is not None:
            return self._model
        if not self._settings.openai_api_key:
            raise AgentNotConfiguredError("未配置 OPENAI_API_KEY，暂时无法生成自然语言查询。")
        self._model = ChatOpenAI(
            model=self._settings.openai_model,
            api_key=self._settings.openai_api_key,
            base_url=self._settings.openai_base_url,
            temperature=0,
            timeout=30,
            max_retries=1,
        )
        return self._model

    # 1. Intent recognition: deterministic routing, not an authorization layer.
    def _recognize_intent(self, state: AgentWorkflowState) -> AgentWorkflowState:
        question = state["question"].strip()
        if UNSAFE_PATTERN.search(question):
            intent: Intent = "unsafe_request"
        elif not HOUSING_PATTERN.search(question):
            intent = "unsupported"
        elif re.search(r"(趋势|走势|月度|每月|按月|变化)", question):
            intent = "trend"
        elif re.search(r"(对比|比较|相比|之间)", question):
            intent = "comparison"
        elif re.search(r"(排名|排行|top\s*\d*|前[\d一二三四五六七八九十]+|最高的[\d一二三四五])", question, re.I):
            intent = "ranking"
        elif re.search(r"(平均|均价|最高|最低|最大|最小|多少|数量|房价|租金|性价比|划算)", question):
            intent = "aggregation"
        else:
            intent = "listing_search"
        return {"intent": intent}

    # 2. Deterministic data-source selection keeps routing outside the model.
    def _select_data_source(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state["intent"] in {"unsafe_request", "unsupported"}:
            return {"data_source": "none", "selected_tables": []}
        question = state["question"]
        hive_query = "租金" not in question and (
            state["intent"] == "trend"
            or bool(re.search(r"(历史|离线|批量|全量|数仓|hive)", question, re.I))
        )
        if self._settings.big_data_enabled and self._hive_database is not None and hive_query:
            return {"data_source": "hive"}
        return {"data_source": "mysql"}

    # 3. Normalize common entities before prompting the model.
    @staticmethod
    def _structure_question(state: AgentWorkflowState) -> AgentWorkflowState:
        question = state["question"]
        normalized = question
        cities: list[str] = []
        districts: list[str] = []
        for alias, canonical in CITY_ALIASES.items():
            if alias in question:
                cities.append(canonical)
                if canonical not in normalized:
                    normalized = normalized.replace(alias, canonical)
        for alias, canonical in DISTRICT_ALIASES.items():
            if alias in question:
                districts.append(canonical)
                if canonical not in normalized:
                    normalized = normalized.replace(alias, canonical)

        room_match = re.search(r"([\d一二两三四五六七八九])室([\d一二两三四五六七八九])厅", question)
        metric = "listing"
        listing_type: str | None = None
        if "租金" in question or "出租" in question:
            metric, listing_type = "monthly_rent", "RENT"
        elif "总价" in question:
            metric, listing_type = "total_price", "SALE"
        elif any(word in question for word in ("房价", "均价", "单价")):
            metric, listing_type = "unit_price", "SALE"
        elif any(word in question for word in ("数量", "多少套", "几套")):
            metric = "listing_count"

        structured: dict[str, Any] = {
            "normalized_question": normalized,
            "cities": list(dict.fromkeys(cities)),
            "districts": list(dict.fromkeys(districts)),
            "metric": metric,
            "listing_type": listing_type,
        }
        if room_match:
            structured["bedroom_count"] = _number(room_match.group(1))
            structured["living_room_count"] = _number(room_match.group(2))
        return {"structured_question": structured}

    # 4. Retrieve safe schema and relevant business semantics from Markdown RAG.
    def _retrieve_context(self, state: AgentWorkflowState) -> AgentWorkflowState:
        database = self._hive_database if state["data_source"] == "hive" else self._database
        if database is None:
            raise RuntimeError("已选择 Hive，但 Hive 查询工具未配置")
        schema = database.describe_allowed_schema()
        retrieval = self._knowledge_retriever.retrieve(state["question"])
        return {
            "retrieved_context": f"{schema}\n\n检索到的业务口径：\n{retrieval.context}",
            "retrieved_document_ids": retrieval.document_ids,
            "needs_clarification": retrieval.needs_clarification,
            "clarification_question": retrieval.clarification_question,
        }

    # 5. Deterministic table selection keeps raw schema away from the model.
    @staticmethod
    def _build_query_plan(state: AgentWorkflowState) -> AgentWorkflowState:
        intent = state["intent"]
        structured = state["structured_question"]
        if state["data_source"] == "hive":
            tables = ["house_info_analysis"]
        elif intent == "trend":
            tables = ["v_agent_monthly_price_trend"]
        elif intent in {"ranking", "comparison"} and "bedroom_count" not in structured:
            tables = ["v_agent_district_summary"]
        else:
            tables = ["v_agent_house_listing"]
        plan = {
            "intent": intent,
            "data_source": state["data_source"],
            "selected_tables": tables,
            "question": structured,
            "constraints": ["read_only", "whitelist_only", "limit_100"],
        }
        return {"selected_tables": tables, "query_plan": plan}

    # 6. Generate SQL from the explicit upstream plan.
    def _generate_sql(self, state: AgentWorkflowState) -> AgentWorkflowState:
        generator = self._get_model().with_structured_output(QueryPlan, method="json_schema")
        plan = generator.invoke([
            SystemMessage(SQL_GENERATION_SYSTEM_PROMPT.format(
                dialect_name="Hive" if state["data_source"] == "hive" else "MySQL",
                query_plan=json.dumps(state["query_plan"], ensure_ascii=False),
                context=state["retrieved_context"],
            )),
            HumanMessage(state["structured_question"]["normalized_question"]),
        ])
        return {
            "generated_sql": plan.sql or "",
            "needs_clarification": plan.needs_clarification,
            "clarification_question": plan.clarification_question,
            "validation_result": {"valid": False, "normalized_sql": None, "error": None},
            "error": "",
        }

    # 7. Validate SQL with SQLGlot.
    def _validate_sql(self, state: AgentWorkflowState) -> AgentWorkflowState:
        candidate = state.get("generated_sql", "")
        if not candidate:
            error = "模型没有生成 SQL"
            return {"validation_result": {"valid": False, "normalized_sql": None, "error": error}, "error": error}
        try:
            plan_validator = SqlValidator(
                set(state["selected_tables"]),
                max_rows=self._settings.sql_max_rows,
                dialect="hive" if state["data_source"] == "hive" else "mysql",
            )
            normalized = plan_validator.validate_and_normalize(candidate)
            return {
                "generated_sql": normalized,
                "validation_result": {"valid": True, "normalized_sql": normalized, "error": None},
                "error": "",
            }
        except ValueError as exc:
            error = str(exc)
            return {"validation_result": {"valid": False, "normalized_sql": None, "error": error}, "error": error}

    # 8. Execute the read-only query.
    def _execute_query(self, state: AgentWorkflowState) -> AgentWorkflowState:
        try:
            database = self._hive_database if state["data_source"] == "hive" else self._database
            if database is None:
                raise RuntimeError("Hive 查询工具未配置")
            columns, rows = database.execute_read_only(state["generated_sql"])
            normalized_rows = [[_json_value(value) for value in row] for row in rows]
            return {
                "query_result": {"columns": columns, "rows": normalized_rows, "row_count": len(normalized_rows), "is_empty": False},
                "error": "",
            }
        except Exception as exc:
            return {"error": f"数据库执行失败：{exc}"}

    # 9. Inspect the result before answer generation.
    @staticmethod
    def _check_result(state: AgentWorkflowState) -> AgentWorkflowState:
        result = state["query_result"]
        rows = result["rows"]
        is_empty = not rows or all(all(value is None for value in row) for row in rows)
        return {"query_result": {**result, "is_empty": is_empty}}

    # 10. Repair SQL with a bounded retry count.
    def _retry_query(self, state: AgentWorkflowState) -> AgentWorkflowState:
        repair_model = self._get_model().with_structured_output(QueryPlan, method="json_schema")
        repair_request = {
            "question": state["question"],
            "query_plan": state["query_plan"],
            "previous_sql": state.get("generated_sql"),
            "error": state["error"],
        }
        repaired = repair_model.invoke([
            SystemMessage(SQL_REPAIR_SYSTEM_PROMPT.format(
                dialect_name="Hive" if state["data_source"] == "hive" else "MySQL",
                context=state["retrieved_context"],
            )),
            HumanMessage(json.dumps(repair_request, ensure_ascii=False)),
        ])
        return {
            "generated_sql": repaired.sql or "",
            "needs_clarification": repaired.needs_clarification,
            "clarification_question": repaired.clarification_question,
            "retry_count": state.get("retry_count", 0) + 1,
            "error": "",
        }

    # 11. Generate a grounded answer and deterministic chart configuration.
    def _generate_answer(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state["intent"] == "unsafe_request":
            return {"final_answer": "该请求包含写入或绕过安全规则的意图。我只能帮你查询房源和统计数据。", "chart_config": None}
        if state["intent"] == "unsupported":
            return {"final_answer": "当前只支持房源、区域均价、租金对比和价格趋势等问数需求。请说明想查询的城市和指标。", "chart_config": None}
        if state.get("needs_clarification"):
            return {"final_answer": state.get("clarification_question") or "请补充查询条件。", "chart_config": None}

        result = state["query_result"]
        if result["is_empty"]:
            return {"final_answer": "当前数据中未找到符合条件的房源。", "chart_config": None}

        answer_model = self._get_model().with_structured_output(AnswerDraft, method="json_schema")
        payload = {"question": state["question"], "sql": state["generated_sql"], "columns": result["columns"], "rows": result["rows"]}
        draft = answer_model.invoke([
            SystemMessage(ANSWER_SYSTEM_PROMPT),
            HumanMessage(json.dumps(payload, ensure_ascii=False, default=str)),
        ])
        return {"final_answer": draft.answer, "chart_config": self._build_chart_config(state)}

    @staticmethod
    def _build_chart_config(state: AgentWorkflowState) -> dict[str, Any] | None:
        if state["intent"] not in {"ranking", "comparison", "trend"}:
            return None
        result = state["query_result"]
        if len(result["rows"]) < 2:
            return None
        columns, sample = result["columns"], result["rows"][0]
        numeric_fields = [name for name, value in zip(columns, sample) if isinstance(value, (int, float)) and not isinstance(value, bool)]
        category_fields = [name for name in columns if name not in numeric_fields]
        if not numeric_fields or not category_fields:
            return None
        metric = state["structured_question"].get("metric")
        metric_label = {
            "monthly_rent": "月租金",
            "unit_price": "挂牌单价",
            "total_price": "挂牌总价",
            "listing_count": "挂牌数量",
        }.get(metric, "房源数据")
        intent_label = {
            "trend": "趋势",
            "ranking": "排名",
            "comparison": "对比",
        }[state["intent"]]
        return {
            "type": "line" if state["intent"] == "trend" else "bar",
            "title": f"{metric_label}{intent_label}",
            "x_field": category_fields[-1],
            "y_fields": numeric_fields,
        }

    @staticmethod
    def _route_after_source(state: AgentWorkflowState) -> str:
        return "finish" if state["data_source"] == "none" else "continue"

    @staticmethod
    def _route_after_retrieval(state: AgentWorkflowState) -> str:
        return "clarify" if state.get("needs_clarification") else "continue"

    @staticmethod
    def _route_after_generation(state: AgentWorkflowState) -> str:
        return "clarify" if state.get("needs_clarification") else "validate"

    def _route_after_validation(self, state: AgentWorkflowState) -> str:
        if state["validation_result"]["valid"]:
            return "execute"
        return "retry" if state.get("retry_count", 0) < self._settings.sql_max_repair_attempts else "failed"

    def _route_after_execution(self, state: AgentWorkflowState) -> str:
        if not state.get("error"):
            return "check"
        return "retry" if state.get("retry_count", 0) < self._settings.sql_max_repair_attempts else "failed"

    def _build_graph(self):
        graph = StateGraph(AgentWorkflowState)
        graph.add_node("recognize_intent", self._recognize_intent)
        graph.add_node("select_data_source", self._select_data_source)
        graph.add_node("structure_question", self._structure_question)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("build_query_plan", self._build_query_plan)
        graph.add_node("generate_sql", self._generate_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_query", self._execute_query)
        graph.add_node("check_result", self._check_result)
        graph.add_node("retry_query", self._retry_query)
        graph.add_node("generate_answer", self._generate_answer)

        graph.add_edge(START, "recognize_intent")
        graph.add_edge("recognize_intent", "select_data_source")
        graph.add_conditional_edges("select_data_source", self._route_after_source, {"finish": "generate_answer", "continue": "structure_question"})
        graph.add_edge("structure_question", "retrieve_context")
        graph.add_conditional_edges(
            "retrieve_context",
            self._route_after_retrieval,
            {"clarify": "generate_answer", "continue": "build_query_plan"},
        )
        graph.add_edge("build_query_plan", "generate_sql")
        graph.add_conditional_edges("generate_sql", self._route_after_generation, {"clarify": "generate_answer", "validate": "validate_sql"})
        graph.add_conditional_edges("validate_sql", self._route_after_validation, {"execute": "execute_query", "retry": "retry_query", "failed": END})
        graph.add_conditional_edges("execute_query", self._route_after_execution, {"check": "check_result", "retry": "retry_query", "failed": END})
        graph.add_edge("check_result", "generate_answer")
        graph.add_conditional_edges(
            "retry_query",
            self._route_after_generation,
            {"clarify": "generate_answer", "validate": "validate_sql"},
        )
        graph.add_edge("generate_answer", END)
        return graph.compile()

    def ask(self, question: str) -> ChatResponse:
        trace_id = str(uuid4())
        started = time.perf_counter()
        final_state: AgentWorkflowState = {}
        audit_status = "FAILED"
        error_summary: str | None = None
        try:
            final_state = self._graph.invoke({"question": question, "trace_id": trace_id, "retry_count": 0, "error": ""})
            intent = final_state["intent"]
            if intent == "unsafe_request":
                audit_status = "REJECTED"
            elif intent == "unsupported" or final_state.get("needs_clarification"):
                audit_status = "CLARIFICATION"
            elif final_state.get("error"):
                validation = final_state.get("validation_result")
                audit_status = "REJECTED" if validation and not validation["valid"] else "FAILED"
                error_summary = final_state["error"]
                raise AgentQueryError(error_summary)
            else:
                audit_status = "NO_DATA" if final_state["query_result"]["is_empty"] else "SUCCESS"

            result = final_state.get("query_result")
            return ChatResponse(
                answer=final_state["final_answer"],
                sql=final_state.get("generated_sql") or None,
                columns=result["columns"] if result else [],
                rows=result["rows"] if result else [],
                chart=final_state.get("chart_config"),
                trace_id=trace_id,
            )
        except Exception as exc:
            if error_summary is None:
                error_summary = str(exc)
            raise
        finally:
            result = final_state.get("query_result")
            audit_values = {
                "trace_id": trace_id,
                "question": question,
                "generated_sql": final_state.get("generated_sql") or None,
                "status": audit_status,
                "result_rows": result["row_count"] if result else 0,
                "repair_count": final_state.get("retry_count", 0),
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "error_summary": error_summary,
            }
            try:
                self._audit_repository.record(**audit_values)
            except Exception:
                logger.exception("audit_write_failed fallback_audit=%s", json.dumps(audit_values, ensure_ascii=False, default=str))
