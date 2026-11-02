from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.conversation import (
    extract_explicit_slots,
    rent_basis_choice,
    resolve_conversation_context,
    trim_messages,
    validate_question_slots,
)
from app.agents.query_guard import ground_query, quality_scalar
from app.agents.jev_router import JevRoutingClient, JevUnavailable, RouteSuggestion, INTENT_CRITERIA, SCOPE_CRITERIA
from app.agents.routing_policy import decide_route, inherit_followup_route, review_reason
from app.agents.route_review import route_review_messages
from app.agents.prompts import (
    TOOL_CALLING_SYSTEM_PROMPT,
)
from app.agents.workflow_state import AgentWorkflowState
from app.config import Settings
from app.database.audit import MysqlAuditRepository
from app.mcp_client import TurnMcpClient
from app.rag.retriever import MarkdownBusinessKnowledgeRetriever
from app.rag.policy_scope import explicit_policy_cities, policy_query_date
from app.schemas.chat import ChatResponse, ExecutionDetails, QuestionSlots, RouteReview

logger = logging.getLogger(__name__)

UNSAFE_PATTERN = re.compile(
    r"(忽略.{0,12}(规则|指令|限制)|删除|清空|销毁|修改|写入|"
    r"\b(delete|drop|truncate|alter|insert|update|create|grant|revoke)\b)",
    re.IGNORECASE,
)
THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class AgentNotConfiguredError(RuntimeError):
    pass


class AgentQueryError(RuntimeError):
    pass


class AgentDependencyError(AgentQueryError):
    pass


class AgentCheckpointError(RuntimeError):
    pass


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class MysqlNaturalLanguageAgent:
    """Controlled, checkpointed LangGraph workflow for read-only housing queries."""

    def __init__(
        self,
        settings: Settings,
        database: Any | None = None,
        model: ChatOpenAI | None = None,
        audit_repository: MysqlAuditRepository | None = None,
        knowledge_retriever: MarkdownBusinessKnowledgeRetriever | None = None,
        hive_database: Any | None = None,
        checkpointer: Any | None = None,
        jev_client: JevRoutingClient | None = None,
        mcp_client_factory: Any | None = None,
    ) -> None:
        if not 0 <= settings.jev_confidence_threshold <= 1 or not 0 <= settings.jev_noul_margin < 0.5:
            raise ValueError("Invalid Jev routing thresholds")
        if settings.jev_timeout_seconds <= 0:
            raise ValueError("Jev timeout must be positive")
        if (settings.tool_max_model_calls < 1 or settings.model_max_calls_per_turn < 1
                or settings.tool_max_calls < 1 or settings.tool_max_successful_queries != 1):
            raise ValueError("Invalid tool loop limits")
        self._settings = settings
        self._mcp_client_factory = mcp_client_factory or (lambda source, tables: TurnMcpClient(settings, source, tables))
        self._model = model
        self._audit_repository = audit_repository or MysqlAuditRepository(settings)
        self._knowledge_retriever = knowledge_retriever or MarkdownBusinessKnowledgeRetriever()
        self._jev_client = jev_client or (JevRoutingClient(settings.typesafe_api_key, model=settings.jev_model,
            timeout_seconds=settings.jev_timeout_seconds, endpoint=settings.jev_endpoint) if settings.typesafe_api_key else None)
        self._hive_available = settings.big_data_enabled
        self._checkpoint_connection: sqlite3.Connection | None = None
        self._checkpointer = checkpointer or self._create_checkpointer(
            settings.checkpoint_db_path
        )
        self._graph = self._build_graph()

    def _create_checkpointer(self, database_path: str) -> SqliteSaver:
        try:
            if database_path != ":memory:":
                path = Path(database_path).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                connection_target = str(path)
            else:
                connection_target = database_path
            connection = sqlite3.connect(connection_target, check_same_thread=False)
            connection.execute("PRAGMA busy_timeout=5000")
            if database_path != ":memory:":
                connection.execute("PRAGMA journal_mode=WAL")
            serde = JsonPlusSerializer(allowed_msgpack_modules=())
            saver = SqliteSaver(connection, serde=serde)
            saver.setup()
            self._checkpoint_connection = connection
            return saver
        except (OSError, sqlite3.DatabaseError) as exc:
            raise AgentCheckpointError(
                "会话存储不可用，请检查 CHECKPOINT_DB_PATH 指向的 SQLite 文件及目录权限。"
            ) from exc

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

    @staticmethod
    def _usage_from_raw(raw: Any) -> tuple[int, int, int] | None:
        metadata = getattr(raw, "usage_metadata", None) or {}
        if metadata:
            prompt = metadata.get("input_tokens", metadata.get("prompt_tokens"))
            completion = metadata.get("output_tokens", metadata.get("completion_tokens"))
            total = metadata.get("total_tokens")
            if prompt is not None and completion is not None:
                return int(prompt), int(completion), int(total if total is not None else prompt + completion)
        token_usage = (getattr(raw, "response_metadata", None) or {}).get("token_usage", {})
        if token_usage:
            prompt = token_usage.get("prompt_tokens")
            completion = token_usage.get("completion_tokens")
            if prompt is not None and completion is not None:
                return int(prompt), int(completion), int(token_usage.get("total_tokens", prompt + completion))
        return None

    def _invoke_structured(self, state: AgentWorkflowState, schema: Any, messages: list[Any]) -> tuple[Any, dict[str, Any]]:
        if state.get("model_usage", {}).get("model_calls", 0) >= self._settings.model_max_calls_per_turn:
            raise AgentQueryError("本轮模型调用已达上限。")
        model_started = time.perf_counter()
        output = self._get_model().with_structured_output(schema, method="json_schema", include_raw=True).invoke(messages)
        parsed = output.get("parsed") if isinstance(output, dict) and "parsed" in output else output
        raw = output.get("raw") if isinstance(output, dict) else None
        previous = state.get("model_usage", {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        usage = {**previous, "model_calls": int(previous.get("model_calls", 0)) + 1}
        usage["timings"] = [*previous.get("timings", []), {"purpose": schema.__name__,
            "duration_ms": round((time.perf_counter() - model_started) * 1000, 3)}]
        tokens = self._usage_from_raw(raw)
        usage["timings"][-1].update(prompt_tokens=tokens[0] if tokens else None,
                                     completion_tokens=tokens[1] if tokens else None,
                                     total_tokens=tokens[2] if tokens else None)
        if tokens is None or previous.get("prompt_tokens") is None:
            usage.update(prompt_tokens=None, completion_tokens=None, total_tokens=None)
        else:
            usage.update(
                prompt_tokens=int(previous["prompt_tokens"]) + tokens[0],
                completion_tokens=int(previous["completion_tokens"]) + tokens[1],
                total_tokens=int(previous["total_tokens"]) + tokens[2],
            )
        return parsed, usage

    # 1. Reset turn-scoped fields while preserving compact thread memory.
    def _prepare_turn(self, state: AgentWorkflowState) -> AgentWorkflowState:
        messages = trim_messages(
            state.get("messages", []),
            max_messages=self._settings.conversation_history_max_messages,
            max_chars=self._settings.conversation_history_max_chars,
        )
        current_question = state["current_question"].strip()
        return {
            "messages": messages,
            "current_question": current_question,
            "resolved_question": current_question,
            "raw_unsafe_detected": bool(UNSAFE_PATTERN.search(current_question)),
            "data_source": "none",
            "requested_scope": "none",
            "intent": "unsupported",
            "selected_tables": [],
            "retrieved_context": "",
            "retrieved_document_ids": [],
            "retrieved_metrics": [],
            "structured_question": {},
            "query_plan": {},
            "generated_sql": "",
            "validation_result": {
                "valid": False,
                "normalized_sql": None,
                "error": None,
            },
            "query_result": None,
            "retry_count": 0,
            "final_answer": "",
            "chart_config": None,
            "needs_clarification": False,
            "metric_basis_ambiguity": False,
            "clarification_question": None,
            "error": "",
            "context_resolution": {},
            "context_resolution_duration_ms": 0,
            "model_usage": {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "timings": []},
            "route_suggestion": {}, "route_reason": "", "route_reviewed": False,
            "route_duration_ms": 0, "allowed_tools": [],
            "jev_duration_ms": None, "qdrant_duration_ms": None, "rerank_duration_ms": None,
            "jev_error_category": None,
            "query_durations": [],
            "tool_transcript": None, "pending_tool_calls": None,
            "proposed_answer": None, "tool_model_calls": 0,
            "tool_call_count": 0, "successful_queries": 0,
            "policy_evidence": [], "policy_limitations": [],
            "policy_tool_calls": [], "dependency_unavailable": False,
        }

    # 2. Resolve references against structured, bounded thread context.
    def _resolve_context(self, state: AgentWorkflowState) -> AgentWorkflowState:
        # History is applied after Jev's dependency judgment and validated slot extraction.
        return {"resolved_question": state["current_question"]}

    # 3. Jev proposes a bounded route; a single structured model review handles uncertainty.
    def _recognize_intent(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state.get("raw_unsafe_detected"):
            return {"intent": "unsafe_request", "requested_scope": "none", "data_source": "none", "route_reason": "unsafe_request"}
        started = time.perf_counter()
        suggestion: RouteSuggestion | None = None
        reason = "jev_unconfigured"
        jev_error_category = None
        hive_available = self._hive_available
        if self._jev_client is not None:
            try:
                jev_started = time.perf_counter()
                suggestion = self._jev_client.classify(state["current_question"], state.get("conversation_context"), hive_available)
                reason = review_reason(suggestion, threshold=self._settings.jev_confidence_threshold,
                                       noul_margin=self._settings.jev_noul_margin) or "accepted"
            except JevUnavailable as exc:
                reason = "jev_unavailable"
                jev_error_category = exc.category
            except Exception:
                reason = "jev_unavailable"
        jev_duration_ms = round((time.perf_counter() - jev_started) * 1000, 3) if self._jev_client is not None else None
        if reason in {"jev_unavailable", "jev_unconfigured"}:
            return {"intent": "clarify", "requested_scope": "none", "data_source": "none",
                    "needs_clarification": True,
                    "clarification_question": "意图识别服务暂不可用，无法安全选择数据源，请稍后重试。",
                    "route_reason": reason, "jev_duration_ms": jev_duration_ms,
                    "jev_error_category": jev_error_category,
                    "route_duration_ms": int((time.perf_counter() - started) * 1000)}
        proposed = suggestion.model_dump() if suggestion else {}
        if reason != "accepted":
            try:
                reviewed, usage = self._invoke_structured(state, RouteReview,
                    route_review_messages(state["current_question"], state.get("conversation_context"),
                                          proposed, reason, hive_available))
                if reviewed.intent not in INTENT_CRITERIA or reviewed.scope not in SCOPE_CRITERIA:
                    raise ValueError("Invalid route review")
                reviewed_scope = reviewed.scope
                if reviewed.intent == "policy_listing" and reviewed_scope == "policy" and suggestion.scope in {
                    "current_listing", "active_import"
                }:
                    reviewed_scope = suggestion.scope
                intent, scope, depends = inherit_followup_route(state["current_question"],
                    state.get("conversation_context"), reviewed.intent, reviewed_scope, reviewed.depends_on_previous)
                return {"intent": intent, "requested_scope": scope, "data_source": "none",
                        "route_suggestion": {**proposed, "depends_on_previous": depends,
                                             "multiple_tasks": reviewed.multiple_tasks},
                        "route_reason": f"{reason}:scope_reconciled" if reviewed_scope != reviewed.scope
                                        else f"{reason}:history_inherited" if intent != reviewed.intent or scope != reviewed.scope else reason,
                        "route_reviewed": True, "model_usage": usage, "jev_duration_ms": jev_duration_ms,
                        "route_duration_ms": int((time.perf_counter() - started) * 1000), "jev_duration_ms": jev_duration_ms}
            except Exception as exc:
                logger.warning("route_review_failed error_type=%s", type(exc).__name__)
                return {"intent": "clarify", "requested_scope": "none", "data_source": "none", "needs_clarification": True,
                        "clarification_question": "请明确要查询的房源指标和范围。", "route_suggestion": proposed,
                        "route_reason": f"{reason}_review_failed", "route_reviewed": True,
                        "route_duration_ms": int((time.perf_counter() - started) * 1000)}
        intent, scope, depends = inherit_followup_route(state["current_question"],
            state.get("conversation_context"), suggestion.intent, suggestion.scope, suggestion.depends_probability >= 0.5)
        return {"intent": intent, "requested_scope": scope, "data_source": "none",
                "route_suggestion": {**proposed, "depends_on_previous": depends,
                                     "multiple_tasks": suggestion.multiple_probability >= 0.5},
                "route_reason": "history_inherited" if intent != suggestion.intent or scope != suggestion.scope else "accepted",
                "route_duration_ms": int((time.perf_counter() - started) * 1000), "jev_duration_ms": jev_duration_ms}

    # 4. Capability policy, never a regex or a model authorization decision.
    def _select_data_source(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state["intent"] == "unsafe_request" or state.get("needs_clarification"):
            return {"data_source": "none", "selected_tables": []}
        route = state.get("route_suggestion", {})
        decision = decide_route(state["intent"], state["requested_scope"],
            hive_available=self._hive_available,
            multiple_tasks=bool(route.get("multiple_tasks")),
            has_history=bool(state.get("conversation_context", {}).get("previous_question")),
            depends_on_previous=bool(route.get("depends_on_previous")),
            explicit_import=bool(route.get("explicit_import")),
            row_granularity=state.get("structured_question", {}).get("row_granularity"))
        tables = list(decision.tables)
        if decision.source == "mysql" and decision.intent in {"ranking", "comparison"} and state.get("structured_question", {}).get("bedroom_count") is not None:
            tables = ["v_agent_house_listing"]
        allowed_tools = []
        if decision.source in {"mysql", "hive"} and tables:
            allowed_tools = list(self._mcp_client_factory(decision.source, set(tables)).names)
        elif decision.source == "policy":
            allowed_tools = list(self._mcp_client_factory("policy", set()).names)
        return {"intent": decision.intent, "data_source": decision.source,
                "selected_tables": tables, "needs_clarification": decision.needs_clarification,
                "clarification_question": decision.clarification_question,
                "allowed_tools": allowed_tools,
                "route_reason": decision.reason if decision.reason != "accepted" else state.get("route_reason", "accepted")}

    # 5. Materialize inherited slots before prompting the model.
    def _structure_question(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state["intent"] in {"unsafe_request", "unsupported", "clarify", "policy"} or state.get("needs_clarification"):
            return {"structured_question": {}}
        try:
            slots, usage = self._invoke_structured(state, QuestionSlots, [
                SystemMessage("只提取当前问题明确给出的城市、区县、挂牌类型、指标、户型、月份和排名数量，输出 QuestionSlots。"
                              "不得推断缺失值。listing_type 只能是 SALE、RENT 或 null；出售为 SALE、出租为 RENT。"
                              "metric 只能为 listing、listing_count、unit_price、total_price、monthly_rent；"
                              "问房源条数用 listing_count，问租金才用 monthly_rent。"
                              "跨区比较月租时，metric_basis 只能为 district_average、district_listing_max 或 ambiguous。"
                              "只说哪个区月租最高而未说明平均还是区内单套最高时，必须用 ambiguous；不得自行选择。"
                              "明确说平均月租用 district_average，明确说单套最贵月租用 district_listing_max。"
                              "row_granularity 只能为 listing、district 或 null；要求单条房源/社区明细用 listing，区域汇总用 district。"
                              "月份格式 YYYY-MM。取消条件时设置 clear_* 标志。不得决定意图、数据源或 SQL。"),
                HumanMessage(state["current_question"]),
            ])
            if slots is None:
                raise ValueError("Structured slot response was empty")
            explicit = validate_question_slots(slots)
            grounded = extract_explicit_slots(state["current_question"])
            prior_pending = bool(state.get("conversation_context", {}).get("pending_metric_choice"))
            selected_basis = rent_basis_choice(state["current_question"]) if prior_pending else None
            if selected_basis:
                explicit["metric_basis"] = selected_basis
            elif grounded.get("metric_basis"):
                explicit["metric_basis"] = grounded["metric_basis"]
            for field in ("bedroom_count", "living_room_count", "start_month", "end_month"):
                if field not in grounded:
                    explicit.pop(field, None)
            if "ranking_limit" not in grounded:
                explicit.pop("ranking_limit", None)
                if re.search(r"(哪个区|哪一个区).{0,12}(最高|最贵)|(?:最高|最贵).{0,12}(哪个区|哪一个区)|(?:最高|最贵)的区", state["current_question"]):
                    explicit["ranking_limit"] = 1
            stated_granularity = grounded.get("row_granularity")
            if stated_granularity == "listing":
                explicit["row_granularity"] = "listing"
            if explicit.get("row_granularity") is None:
                explicit.pop("row_granularity", None)
            started = time.perf_counter()
            route = state.get("route_suggestion", {})
            resolution, context = resolve_conversation_context(
                state["current_question"], state.get("conversation_context"),
                explicit_slots=explicit, depends_on_history=bool(route.get("depends_on_previous")),
            )
            if slots.clear_districts:
                context["districts"] = []
            if slots.clear_layout:
                context["bedroom_count"] = context["living_room_count"] = None
            if slots.clear_months:
                context["start_month"] = context["end_month"] = None
            context["intent"] = state["intent"]
            district_rent_comparison = (
                state["intent"] in {"ranking", "comparison", "aggregation"}
                and context.get("listing_type") == "RENT"
                and context.get("metric") == "monthly_rent"
                and ("区" in state["current_question"] or prior_pending)
                and ("最高" in state["current_question"] or "最贵" in state["current_question"]
                     or prior_pending)
            )
            if district_rent_comparison:
                context["intent"] = "ranking"
            if district_rent_comparison and not grounded.get("metric_basis") and not selected_basis:
                context["metric_basis"] = "ambiguous"
            if district_rent_comparison and context.get("metric_basis") not in {
                "district_average", "district_listing_max"
            }:
                context["metric_basis"] = "ambiguous"
                return {"resolved_question": resolution.standalone_question,
                        "conversation_context": context,
                        "context_resolution": resolution.model_dump(),
                        "structured_question": context,
                        "intent": "ranking",
                        "needs_clarification": True,
                        "metric_basis_ambiguity": True,
                        "clarification_question": "你想比较各区的平均月租，还是比较各区单套房源的最高月租？"}
            structured = {**context, "normalized_question": resolution.standalone_question,
                          "metric": context.get("metric") or "listing"}
            return {"resolved_question": resolution.standalone_question,
                    "conversation_context": context, "context_resolution": resolution.model_dump(),
                    "intent": context["intent"],
                    "context_resolution_duration_ms": int((time.perf_counter() - started) * 1000),
                    "structured_question": structured, "model_usage": usage,
                    "needs_clarification": resolution.unresolved_reference,
                    "metric_basis_ambiguity": False,
                    "clarification_question": resolution.clarification_question}
        except Exception as exc:
            logger.exception("Question slot extraction failed")
            raise AgentNotConfiguredError("问题条件解析暂不可用，无法可靠执行查询；请稍后重试。") from exc

    # 6. Retrieve safe schema and relevant business semantics from Markdown RAG.
    def _retrieve_context(self, state: AgentWorkflowState) -> AgentWorkflowState:
        tools = self._turn_tools(state)
        schema_result = tools.invoke(f"get_{state['data_source']}_schema", {})
        metric_result = tools.invoke("lookup_metric_definition", {"question": state["resolved_question"]})
        if not schema_result.ok or not metric_result.ok:
            raise AgentDependencyError("查询依赖服务暂不可用，请稍后重试。")
        schema = schema_result.data
        retrieval = metric_result.data
        rendered_schema = "\n\n".join(
            f"TABLE {view.name}\nDESCRIPTION: {view.description}\nCOLUMNS: " +
            ", ".join(f"{column.name} {column.type}" for column in view.columns)
            for view in schema.views
        )
        metric_context = "\n\n".join(
            f"METRIC {definition.id} ({definition.title})\n{definition.description}"
            for definition in retrieval.definitions
        ) or "未检索到额外业务指标定义；不得自行创造指标口径。"
        policy_question = state["current_question"]
        previous_policy = state.get("conversation_context", {}).get("policy_question")
        if (state["intent"] == "policy_listing" and state.get("context_resolution", {}).get("depends_on_history")
                and previous_policy):
            prior_clause = re.split(r"结合|同时查|并查", previous_policy, maxsplit=1)[-1]
            current_parts = re.split(r"结合|沿用上一问的", state["current_question"], maxsplit=1)
            policy_question = f"{prior_clause} {current_parts[-1] if len(current_parts) > 1 else ''}"
        policy = self._search_policy(policy_question, trace_id=state["trace_id"]) if state["intent"] == "policy_listing" else None
        return {
            "retrieved_context": f"{rendered_schema}\n\n检索到的业务口径：\n{metric_context}",
            "policy_evidence": policy["evidence"] if policy else [],
            "policy_limitations": policy["limitations"] if policy else [],
            "policy_tool_calls": policy["tool_calls"] if policy else [],
            "qdrant_duration_ms": policy.get("timings_ms", {}).get("qdrant") if policy else None,
            "rerank_duration_ms": policy.get("timings_ms", {}).get("rerank") if policy else None,
            "retrieved_document_ids": [definition.id for definition in retrieval.definitions],
            "retrieved_metrics": [
                {
                    "id": definition.id,
                    "title": definition.title,
                    "description": definition.description,
                }
                for definition in retrieval.definitions
            ],
            "needs_clarification": state.get("needs_clarification", False)
            or retrieval.needs_clarification,
            "clarification_question": state.get("clarification_question")
            or retrieval.clarification_question,
        }

    def _search_policy(self, question: str, *, trace_id: str) -> dict[str, Any]:
        cities = explicit_policy_cities(question)
        other = sorted(city for city in cities if city != "北京市")
        if other:
            return {"evidence": [], "limitations": [f"当前政策语料仅覆盖北京市，不包含{'、'.join(other)}；不能用北京条款回答其他城市政策。"],
                    "tool_calls": [{"tool": "search_policy", "status": "scope_rejected", "duration_ms": 0, "trace_id": trace_id}]}
        as_of, published_by_date = policy_query_date(question)
        started = time.perf_counter()
        try:
            result = self._mcp_client_factory("policy", set()).invoke("search_policy",
                {"question": question, "as_of": as_of, "published_by_date": published_by_date, "limit": 5})
            if result.ok and result.data is not None:
                return {**result.data.model_dump(mode="json"),
                        "tool_calls": [{"tool": "search_policy", "status": "ok", "duration_ms": int((time.perf_counter() - started) * 1000), "trace_id": trace_id}]}
        except Exception:
            logger.exception("policy_mcp_unavailable")
        return {"evidence": [], "limitations": ["政策 MCP 或 Qdrant 暂不可用，无法核对政策结论"],
                "tool_calls": [{"tool": "search_policy", "status": "failed", "duration_ms": int((time.perf_counter() - started) * 1000), "trace_id": trace_id}]}

    def _policy_answer(self, state: AgentWorkflowState) -> AgentWorkflowState:
        from app.rag.policy_conclusions import direct_policy_conclusion
        result = self._search_policy(state["resolved_question"], trace_id=state["trace_id"])
        rendered = self._render_policy_evidence(result["evidence"], result["limitations"])
        question = state["resolved_question"]
        evidence = result["evidence"]
        conclusion = direct_policy_conclusion(question, evidence)
        if conclusion:
            rendered = conclusion + "\n\n" + rendered
        if "360" in question and ("能否" in question or "引用" in question) and any(
            item.get("version_id") == "bj-housing-2025-360" and "五环外" in item.get("content", "")
            and "不限套数" in item.get("content", "") for item in evidence
        ):
            rendered = ("可以引用京建发〔2025〕360号中符合条件家庭五环外购房不限套数的条款；"
                        "但完整的现行限购结论还需核对后续政策和个人条件。\n\n" + rendered)
        elif "565" in question and "引用" in question and any(
            item.get("version_id") == "bj-housing-2025-565-bulletin" and "25%" in item.get("content", "")
            for item in evidence
        ):
            rendered = ("可以引用京建发〔2025〕565号第四条，二套住房公积金贷款最低首付款比例不低于25%；"
                        "25%是政策底线，具体贷款审批和后续操作口径仍需核对。\n\n" + rendered)
        return {"policy_evidence": result["evidence"], "policy_limitations": result["limitations"],
                "qdrant_duration_ms": result.get("timings_ms", {}).get("qdrant"),
                "rerank_duration_ms": result.get("timings_ms", {}).get("rerank"),
                "policy_tool_calls": result["tool_calls"],
                "final_answer": rendered,
                "chart_config": None}

    @staticmethod
    def _render_policy_evidence(evidence: list[dict[str, Any]], limitations: list[str]) -> str:
        if not evidence:
            return "现有已审核政策中未找到足够依据，暂不能判断适用资格或优惠金额。" + "；".join(limitations)
        parts = ["政策原文（按相关度列出，适用资格需结合个人条件核对）："]
        for item in evidence[:3]:
            number = item.get("document_number") or "无文号公告"
            parts.append(f"{item['content']}\n出处：{number}，{item['clause_path']}，{item['source_url']}")
        notices = list(dict.fromkeys(item.get("file_enactment_text") for item in evidence[:3]
                                     if item.get("file_enactment_text")))
        if notices:
            parts.append("文件级施行与冲突说明：" + "；".join(notices))
        parts.append("根据已知条件的推断：仅能确定上述条款文字，不能据此断定个人资格或最终额度。")
        parts.append("缺少的用户条件：户籍、住房套数、购房日期、购房区域、公积金缴存及既有贷款情况（按具体条款核对）。")
        if limitations:
            parts.append("核对限制：" + "；".join(limitations))
        if any(item.get("effective_check") != "machine_checked" for item in evidence):
            parts.append("生效时间存在待核对的推导或未知项，不据此认定当前有效。")
        if len({item.get("version_id") for item in evidence}) > 1:
            parts.append("检索到不同版本；覆盖关系须按条款、区域和适用日期核对，不按文件发布时间直接取最新。")
        return "\n\n".join(parts)

    # 7. Deterministic table selection keeps raw schema away from the model.
    @staticmethod
    def _build_query_plan(state: AgentWorkflowState) -> AgentWorkflowState:
        intent = state["intent"]
        structured = state["structured_question"]
        tables = state["selected_tables"]
        plan = {
            "intent": intent,
            "data_source": state["data_source"],
            "selected_tables": tables,
            "question": structured,
            "constraints": ["read_only", "whitelist_only", "limit_100"],
            "allowed_tools": state.get("allowed_tools", []),
        }
        return {"selected_tables": tables, "query_plan": plan}

    def _turn_tools(self, state: AgentWorkflowState):
        return self._mcp_client_factory(state["data_source"], set(state["selected_tables"]))

    def _call_tool_model(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if (state.get("tool_model_calls", 0) >= self._settings.tool_max_model_calls
                or state.get("model_usage", {}).get("model_calls", 0) >= self._settings.model_max_calls_per_turn):
            return {"error": "模型工具调用已达上限。"}
        registry = self._turn_tools(state)
        transcript = state.get("tool_transcript") or [
            SystemMessage(TOOL_CALLING_SYSTEM_PROMPT.format(
                query_plan=json.dumps(state["query_plan"], ensure_ascii=False),
                context=state["retrieved_context"],
            )),
            HumanMessage(state["structured_question"]["normalized_question"]),
        ]
        model = self._get_model()
        if not hasattr(model, "bind_tools"):
            raise AgentNotConfiguredError("当前生成式模型不支持工具调用。")
        discovered_tools = registry.as_langchain_tools()
        try:
            bound = model.bind_tools(discovered_tools)
            model_started = time.perf_counter()
            reply = bound.invoke(transcript)
        except Exception as exc:
            raise AgentNotConfiguredError("当前模型服务的工具调用不可用，请检查 bind_tools 兼容性。") from exc
        if not isinstance(reply, AIMessage) or getattr(reply, "invalid_tool_calls", None):
            raise AgentNotConfiguredError("模型服务未返回可解析的工具调用结果。")
        if not reply.tool_calls and state.get("query_result") is None:
            content = reply.content.strip() if isinstance(reply.content, str) else ""
            if not (len(content) <= 200 and (content.endswith(("？", "?")) or content.startswith(("请明确", "请补充")))):
                raise AgentNotConfiguredError("模型未发出查询工具调用，无法确认 function calling 兼容性。")
        usage = self._usage_after_message(state, reply)
        purpose = ("sql_repair" if state.get("retry_count", 0) else
                   "answer_synthesis" if state.get("successful_queries", 0) else "sql_generation")
        usage["timings"] = [*usage.get("timings", []), {"purpose": purpose,
            "duration_ms": round((time.perf_counter() - model_started) * 1000, 3)}]
        call_tokens = self._usage_from_raw(reply)
        usage["timings"][-1].update(prompt_tokens=call_tokens[0] if call_tokens else None,
                                     completion_tokens=call_tokens[1] if call_tokens else None,
                                     total_tokens=call_tokens[2] if call_tokens else None)
        return {
            "tool_transcript": [*transcript, reply],
            "pending_tool_calls": list(reply.tool_calls),
            "proposed_answer": reply.content if isinstance(reply.content, str) else "",
            "tool_model_calls": state.get("tool_model_calls", 0) + 1,
            "model_usage": usage,
            "error": "",
        }

    def _usage_after_message(self, state: AgentWorkflowState, reply: AIMessage) -> dict[str, Any]:
        previous = state.get("model_usage", {"model_calls": 0, "prompt_tokens": 0,
                                              "completion_tokens": 0, "total_tokens": 0})
        usage = {**previous, "model_calls": int(previous.get("model_calls", 0)) + 1}
        tokens = self._usage_from_raw(reply)
        if tokens is None or previous.get("prompt_tokens") is None:
            usage.update(prompt_tokens=None, completion_tokens=None, total_tokens=None)
        else:
            usage.update(prompt_tokens=int(previous["prompt_tokens"]) + tokens[0],
                         completion_tokens=int(previous["completion_tokens"]) + tokens[1],
                         total_tokens=int(previous["total_tokens"]) + tokens[2])
        return usage

    def _execute_tool_calls(self, state: AgentWorkflowState) -> AgentWorkflowState:
        registry = self._turn_tools(state)
        transcript = list(state.get("tool_transcript") or [])
        count = state.get("tool_call_count", 0)
        repairs = state.get("retry_count", 0)
        successful = state.get("successful_queries", 0)
        query_result = state.get("query_result")
        generated_sql = state.get("generated_sql", "")
        query_durations = list(state.get("query_durations", []))
        error = ""
        dependency_unavailable = False
        for call in state.get("pending_tool_calls") or []:
            if count >= self._settings.tool_max_calls:
                error = "工具调用次数已达上限。"
                break
            name, args, call_id = call.get("name"), call.get("args"), call.get("id")
            if not isinstance(name, str) or not isinstance(args, dict) or not isinstance(call_id, str) or not call_id:
                error = "模型返回的工具调用格式无效。"
                break
            count += 1
            is_query = name in {"query_mysql_readonly", "query_hive_readonly"}
            basis = state.get("structured_question", {}).get("metric_basis")
            if (name == "query_mysql_readonly" and successful == 0
                    and state.get("intent") == "ranking"
                    and state.get("selected_tables") == ["v_agent_district_summary"]
                    and basis in {"district_average", "district_listing_max"}):
                details = state["structured_question"]
                cities = details.get("cities") or []
                if len(cities) == 1 and details.get("listing_type") == "RENT":
                    column = "avg_monthly_rent" if basis == "district_average" else "max_monthly_rent"
                    limit = min(int(details.get("ranking_limit") or 1), 100)
                    args = {"sql": (f"SELECT district, {column} FROM v_agent_district_summary "
                                    f"WHERE city = '{cities[0]}' AND listing_type = 'RENT' "
                                    f"ORDER BY {column} DESC LIMIT {limit}")}
            validation_error = None
            if is_query and isinstance(args.get("sql"), str):
                try:
                    args = {**args, "sql": ground_query(
                        args["sql"], districts=state.get("structured_question", {}).get("districts") or [],
                        source=state["data_source"], selected_tables=state.get("selected_tables") or [],
                        question=state["current_question"])}
                except ValueError as exc:
                    validation_error = str(exc)
            if is_query and successful == 0 and isinstance(args.get("sql"), str):
                generated_sql = args["sql"][:20000]
            if validation_error:
                from app.tools.contracts import ToolError, ToolResult
                result = ToolResult(ok=False, error=ToolError(code="invalid_arguments", message=validation_error))
            elif is_query and successful >= self._settings.tool_max_successful_queries:
                from app.tools.contracts import ToolError, ToolResult
                result = ToolResult(ok=False, error=ToolError(code="unavailable", message="本轮查询已完成，不可再次查询。"))
            else:
                result = registry.invoke(name, args)
            transcript.append(ToolMessage(content=result.model_dump_json(), tool_call_id=call_id, name=name))
            if is_query and result.ok:
                data = result.data
                if data.query_duration_ms is not None:
                    query_durations.append({"source": state["data_source"], "duration_ms": data.query_duration_ms})
                rows = [[_json_value(value) for value in row] for row in data.rows]
                query_result = {"columns": data.columns, "rows": rows,
                                "row_count": len(rows), "is_empty": data.is_empty}
                generated_sql = data.sql
                successful += 1
            elif is_query and not result.ok and successful == 0:
                if result.error and result.error.code == "execution_failed":
                    error = "查询依赖服务暂不可用，请稍后重试。"
                    dependency_unavailable = True
                    break
                if repairs >= self._settings.sql_max_repair_attempts:
                    error = result.error.message
                    break
                repairs += 1
        return {"tool_transcript": transcript, "pending_tool_calls": None, "query_durations": query_durations,
                "tool_call_count": count, "retry_count": repairs,
                "successful_queries": successful, "query_result": query_result,
                "generated_sql": generated_sql, "error": error,
                "dependency_unavailable": dependency_unavailable}

    @staticmethod
    def _route_after_tool_model(state: AgentWorkflowState) -> str:
        if state.get("error"):
            return "failed"
        if state.get("pending_tool_calls"):
            return "execute"
        if state.get("query_result") is not None:
            return "answer"
        return "clarify"

    @staticmethod
    def _route_after_tool_execution(state: AgentWorkflowState) -> str:
        return "failed" if state.get("error") else "continue"

    # Ground final text in the successful tool result.
    def _generate_answer(self, state: AgentWorkflowState) -> AgentWorkflowState:
        if state["intent"] == "unsafe_request":
            return {"final_answer": "该请求包含写入或绕过安全规则的意图。我只能帮你查询房源和统计数据。", "chart_config": None}
        if state["intent"] == "unsupported":
            return {"final_answer": "当前只支持房源、区域均价、租金对比和价格趋势等问数需求。请说明想查询的城市和指标。", "chart_config": None}
        if state.get("needs_clarification"):
            return {"final_answer": state.get("clarification_question") or "请补充查询条件。", "chart_config": None}

        result = state.get("query_result")
        if result is None:
            proposed = (state.get("proposed_answer") or "").strip()
            question = proposed if len(proposed) <= 200 and (proposed.endswith(("？", "?")) or proposed.startswith(("请明确", "请补充"))) else "请明确查询指标和范围。"
            return {"needs_clarification": True,
                    "clarification_question": question,
                    "final_answer": question, "chart_config": None}
        if result["is_empty"]:
            if state["intent"] == "policy_listing":
                return {"final_answer": self._render_policy_evidence(state.get("policy_evidence", []), state.get("policy_limitations", [])) + "\n\n项目房源样本未找到符合条件的数据；CSV 导入样本为合成数据。", "chart_config": None}
            return {"final_answer": "当前数据中未找到符合条件的房源。", "chart_config": None}
        quality = quality_scalar(state["current_question"], state.get("selected_tables") or [])
        if quality and result["columns"] == [quality[0]] and len(result["rows"]) == 1:
            value = result["rows"][0][0]
            if value is not None:
                return {"final_answer": f"当前激活导入批次的{quality[1]} {value} 条；这是项目合成 CSV 的质量统计。",
                        "chart_config": None}
        answer = (state.get("proposed_answer") or "").strip()
        if not answer:
            return {"needs_clarification": True, "clarification_question": "请重新描述查询需求。",
                    "final_answer": "请重新描述查询需求。", "chart_config": None}
        if state["intent"] == "policy_listing":
            answer = (self._render_policy_evidence(state.get("policy_evidence", []), state.get("policy_limitations", [])) +
                      "\n\n项目房源样本（项目 CSV 为合成数据，仅作项目数据证据，不代表真实市场挂牌）：" +
                      json.dumps({"columns": result["columns"], "rows": result["rows"]}, ensure_ascii=False))
        return {"final_answer": answer, "chart_config": self._build_chart_config(state)}

    # 14. Persist only compact messages and structured slots, never rows in history.
    def _persist_context(self, state: AgentWorkflowState) -> AgentWorkflowState:
        context = dict(state.get("conversation_context", {}))
        if state["intent"] not in {"unsafe_request", "unsupported"} and state.get("route_reason") != "missing_history":
            context.update(
                pending_clarification=(
                    state.get("clarification_question")
                    if state.get("needs_clarification")
                    else None
                ),
                pending_metric_choice=bool(state.get("metric_basis_ambiguity")),
                previous_question=state["current_question"][:1000],
                previous_answer_summary=state["final_answer"][:1000],
                intent=state["intent"],
                requested_scope=state.get("requested_scope"),
            )
            if state["intent"] == "policy_listing":
                context["policy_question"] = (
                    context.get("policy_question") if state.get("context_resolution", {}).get("depends_on_history")
                    and context.get("policy_question") else state["current_question"][:1000]
                )
        messages = [
            *state.get("messages", []),
            {"role": "user", "content": state["current_question"][:1000]},
            {"role": "assistant", "content": state["final_answer"][:1000]},
        ]
        return {
            "conversation_context": context,
            "previous_structured_question": state.get("structured_question", {}),
            "pending_question": (
                state["resolved_question"] if state.get("needs_clarification") else None
            ),
            "messages": trim_messages(
                messages,
                max_messages=self._settings.conversation_history_max_messages,
                max_chars=self._settings.conversation_history_max_chars,
            ),
        }

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
        if state["data_source"] == "policy":
            return "policy"
        return "finish" if state["data_source"] == "none" else "continue"

    @staticmethod
    def _route_after_retrieval(state: AgentWorkflowState) -> str:
        return "clarify" if state.get("needs_clarification") else "continue"

    def _build_graph(self):
        graph = StateGraph(AgentWorkflowState)
        graph.add_node("prepare_turn", self._prepare_turn)
        graph.add_node("resolve_context", self._resolve_context)
        graph.add_node("recognize_intent", self._recognize_intent)
        graph.add_node("select_data_source", self._select_data_source)
        graph.add_node("structure_question", self._structure_question)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("build_query_plan", self._build_query_plan)
        graph.add_node("call_tool_model", self._call_tool_model)
        graph.add_node("execute_tool_calls", self._execute_tool_calls)
        graph.add_node("generate_answer", self._generate_answer)
        graph.add_node("policy_answer", self._policy_answer)
        graph.add_node("persist_context", self._persist_context)

        graph.add_edge(START, "prepare_turn")
        graph.add_edge("prepare_turn", "resolve_context")
        graph.add_edge("resolve_context", "recognize_intent")
        graph.add_edge("recognize_intent", "structure_question")
        graph.add_edge("structure_question", "select_data_source")
        graph.add_conditional_edges("select_data_source", self._route_after_source, {"finish": "generate_answer", "continue": "build_query_plan", "policy": "policy_answer"})
        graph.add_edge("policy_answer", "persist_context")
        graph.add_edge("build_query_plan", "retrieve_context")
        graph.add_conditional_edges(
            "retrieve_context",
            self._route_after_retrieval,
            {"clarify": "generate_answer", "continue": "call_tool_model"},
        )
        graph.add_conditional_edges("call_tool_model", self._route_after_tool_model,
            {"execute": "execute_tool_calls", "answer": "generate_answer",
             "clarify": "generate_answer", "failed": END})
        graph.add_conditional_edges("execute_tool_calls", self._route_after_tool_execution,
            {"continue": "call_tool_model", "failed": END})
        graph.add_edge("generate_answer", "persist_context")
        graph.add_edge("persist_context", END)
        return graph.compile(checkpointer=self._checkpointer)

    def ask(self, question: str, thread_id: str | None = None) -> ChatResponse:
        conversation_id = thread_id or str(uuid4())
        if not THREAD_ID_PATTERN.fullmatch(conversation_id):
            raise ValueError(
                "thread_id 只能包含字母、数字、下划线或连字符，且长度不能超过 64。"
            )
        trace_id = str(uuid4())
        started = time.perf_counter()
        final_state: AgentWorkflowState = {}
        audit_status = "FAILED"
        error_summary: str | None = None
        try:
            config = {"configurable": {"thread_id": conversation_id}}
            final_state = self._graph.invoke(
                {
                    "current_question": question,
                    "thread_id": conversation_id,
                    "trace_id": trace_id,
                },
                config=config,
            )
            intent = final_state["intent"]
            if intent == "unsafe_request":
                audit_status = "REJECTED"
            elif intent == "unsupported" or final_state.get("needs_clarification"):
                audit_status = "CLARIFICATION"
            elif final_state.get("error"):
                validation = final_state.get("validation_result")
                audit_status = "REJECTED" if validation and not validation["valid"] else "FAILED"
                error_summary = final_state["error"]
                if final_state.get("dependency_unavailable"):
                    raise AgentDependencyError(error_summary)
                raise AgentQueryError(error_summary)
            else:
                audit_status = "NO_DATA" if final_state.get("query_result") and final_state["query_result"]["is_empty"] else "SUCCESS"

            result = final_state.get("query_result")
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ChatResponse(
                answer=final_state["final_answer"],
                sql=final_state.get("generated_sql") or None,
                columns=result["columns"] if result else [],
                rows=result["rows"] if result else [],
                chart=final_state.get("chart_config"),
                trace_id=trace_id,
                thread_id=conversation_id,
                details=ExecutionDetails(
                    data_source=final_state.get("data_source", "none"),
                    duration_ms=duration_ms,
                    selected_tables=final_state.get("selected_tables", []),
                    retrieved_metrics=final_state.get("retrieved_metrics", []),
                    row_count=result["row_count"] if result else 0,
                    retry_count=final_state.get("retry_count", 0),
                    used_history=bool(
                        final_state.get("context_resolution", {}).get(
                            "depends_on_history", False
                        )
                    ),
                    inherited_fields=final_state.get("context_resolution", {}).get(
                        "inherited_fields", []
                    ),
                    overridden_fields=final_state.get("context_resolution", {}).get(
                        "overridden_fields", []
                    ),
                    context_resolution_duration_ms=final_state.get(
                        "context_resolution_duration_ms", 0
                    ),
                    route_suggestion={key: final_state.get("route_suggestion", {}).get(key) for key in
                        ("intent", "scope", "intent_confidence", "scope_confidence", "intent_probability", "scope_probability", "depends_probability", "multiple_probability", "explicit_import", "explicit_import_probability")
                        if key in final_state.get("route_suggestion", {})} or None,
                    route_reason=final_state.get("route_reason") or None,
                    route_reviewed=bool(final_state.get("route_reviewed")),
                    route_duration_ms=final_state.get("route_duration_ms", 0),
                    jev_duration_ms=final_state.get("jev_duration_ms"),
                    llm_calls=final_state.get("model_usage", {}).get("timings", []),
                    llm_duration_ms=round(sum(item["duration_ms"] for item in final_state.get("model_usage", {}).get("timings", [])), 3) if final_state.get("model_usage", {}).get("timings") else None,
                    qdrant_duration_ms=final_state.get("qdrant_duration_ms"),
                    rerank_duration_ms=final_state.get("rerank_duration_ms"),
                    mysql_duration_ms=next((item["duration_ms"] for item in final_state.get("query_durations", []) if item["source"] == "mysql"), None),
                    hive_duration_ms=next((item["duration_ms"] for item in final_state.get("query_durations", []) if item["source"] == "hive"), None),
                    error_category=final_state.get("jev_error_category") or ("jev_unconfigured" if final_state.get("route_reason") == "jev_unconfigured" else None),
                    allowed_tools=final_state.get("allowed_tools", []),
                    tool_model_calls=final_state.get("tool_model_calls", 0),
                    tool_call_count=final_state.get("tool_call_count", 0),
                    successful_queries=final_state.get("successful_queries", 0),
                    policy_evidence=final_state.get("policy_evidence", []),
                    policy_limitations=final_state.get("policy_limitations", []),
                    policy_tool_calls=final_state.get("policy_tool_calls", []),
                    policy_tool_call_count=len(final_state.get("policy_tool_calls", [])),
                    **final_state.get("model_usage", {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
                ),
            )
        except (OSError, sqlite3.DatabaseError) as exc:
            error_summary = "checkpoint storage failure"
            raise AgentCheckpointError(
                "会话状态暂时无法读取或保存，请稍后重试或新建会话。"
            ) from exc
        except Exception as exc:
            if error_summary is None:
                error_summary = str(exc)
            exc.trace_id = trace_id
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
                "thread_id": conversation_id,
                "used_history": bool(
                    final_state.get("context_resolution", {}).get(
                        "depends_on_history", False
                    )
                ),
                "inherited_fields": final_state.get("context_resolution", {}).get(
                    "inherited_fields", []
                ),
                "overridden_fields": final_state.get("context_resolution", {}).get(
                    "overridden_fields", []
                ),
                "context_resolution_duration_ms": final_state.get(
                    "context_resolution_duration_ms", 0
                ),
                **final_state.get("model_usage", {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            }
            try:
                self._audit_repository.record(**audit_values)
            except Exception:
                logger.exception("audit_write_failed fallback_audit=%s", json.dumps(audit_values, ensure_ascii=False, default=str))

    def get_conversation_state(self, thread_id: str) -> AgentWorkflowState:
        """Return a checkpoint snapshot for diagnostics without exposing it via HTTP."""
        if not THREAD_ID_PATTERN.fullmatch(thread_id):
            raise ValueError("thread_id 格式无效。")
        try:
            snapshot = self._graph.get_state(
                {"configurable": {"thread_id": thread_id}}
            )
            return dict(snapshot.values)
        except (OSError, sqlite3.DatabaseError) as exc:
            raise AgentCheckpointError("会话状态暂时无法读取。") from exc
