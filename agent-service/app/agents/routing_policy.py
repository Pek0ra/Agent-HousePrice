"""Deterministic permission and table policy for a Jev suggestion."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.agents.jev_router import RouteSuggestion, ScopeChoice, SCOPE_SOURCE
from app.agents.conversation import DEPENDENCY_PATTERN, rent_basis_choice


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    source: str
    tables: tuple[str, ...]
    reason: str
    needs_clarification: bool = False
    clarification_question: str | None = None


def inherit_followup_route(question: str, previous: dict[str, Any] | None,
                           intent: str, scope: str, depends: bool) -> tuple[str, str, bool]:
    """Continue a known task when the user explicitly refers to that task.

    Jev still identifies a new task; this only repairs anaphora against a
    previously routed, structured turn. It never grants new SQL permissions.
    """
    old = previous or {}
    old_intent, old_scope = old.get("intent"), old.get("requested_scope")
    if old.get("pending_metric_choice") and rent_basis_choice(question) and old_intent and old_scope:
        return old_intent, old_scope, True
    if not old.get("previous_question") or not old_intent or not (depends or DEPENDENCY_PATTERN.search(question)):
        return intent, scope, depends
    depends = True
    if old_intent == "policy_listing" and (intent in {"policy", "comparison", "clarify", "policy_listing"}):
        return "policy_listing", old_scope or "current_listing", depends
    if intent == "clarify" and old_intent not in {"unsupported", "unsafe_request", "clarify"}:
        return old_intent, old_scope or scope, depends
    if scope == "none" and old_scope in {"current_listing", "active_import", "import_quality"}:
        return intent, old_scope, depends
    if old_scope == "active_import" and scope == "current_listing" and not re.search(
        r"项目房源|MySQL|mysql|当前挂牌", question):
        return intent, "active_import", depends
    return intent, scope, depends


def review_reason(suggestion: RouteSuggestion, *, threshold: float, noul_margin: float) -> str | None:
    if min(suggestion.intent_confidence, suggestion.scope_confidence,
           suggestion.intent_probability, suggestion.scope_probability) < threshold:
        return "low_confidence"
    if abs(suggestion.depends_probability - 0.5) < noul_margin or abs(suggestion.multiple_probability - 0.5) < noul_margin:
        return "uncertain_boolean"
    if suggestion.intent not in {"unsupported", "clarify"} and any(
        0.5 <= probability < 0.85 for probability in
        (suggestion.depends_probability, suggestion.multiple_probability)
    ):
        return "positive_boolean_review"
    if suggestion.intent == "policy" and suggestion.scope != "policy":
        return "intent_scope_conflict"
    if suggestion.intent == "policy_listing" and suggestion.scope not in {"current_listing", "active_import"}:
        return "intent_scope_conflict"
    if suggestion.intent in {"unsupported", "clarify"} and suggestion.scope != "none":
        return "intent_scope_conflict"
    if suggestion.intent not in {"unsupported", "clarify"} and suggestion.scope == "none":
        return "intent_scope_conflict"
    if (suggestion.intent == "data_quality") != (suggestion.scope == "import_quality"):
        return "intent_scope_conflict"
    if suggestion.explicit_import and suggestion.scope == "current_listing":
        return "explicit_import_conflict"
    return None


def decide_route(intent: str, scope: ScopeChoice, *, hive_available: bool,
                 multiple_tasks: bool, has_history: bool, depends_on_previous: bool,
                 explicit_import: bool = False, row_granularity: str | None = None) -> RouteDecision:
    if intent == "policy":
        return RouteDecision("policy", "policy", (), "accepted") if scope == "policy" else RouteDecision("clarify", "none", (), "scope_conflict", True, "请明确需要查询的政策。")
    if intent == "policy_listing":
        if explicit_import and scope != "active_import":
            return RouteDecision("clarify", "none", (), "explicit_import_conflict", True, "明确指定 CSV 导入数据时需要选择 Hive 数据源。")
        if scope == "current_listing":
            return RouteDecision("policy_listing", "mysql", ("v_agent_house_listing",), "accepted")
        if scope == "active_import" and hive_available:
            return RouteDecision("policy_listing", "hive", ("v_agent_house_info_analysis",), "accepted")
        return RouteDecision("clarify", "none", (), "hive_required" if scope == "active_import" else "scope_conflict", True, "CSV 导入数据组合查询需要启用 Hive；请明确数据来源。")
    if multiple_tasks:
        return RouteDecision("clarify", "none", (), "multiple_tasks", True, "请先选择其中一个查询任务。")
    if depends_on_previous and not has_history:
        return RouteDecision("clarify", "none", (), "missing_history", True, "请补充要沿用的查询条件。")
    if intent == "unsupported":
        return RouteDecision("unsupported", "none", (), "unsupported")
    if intent == "clarify":
        return RouteDecision("clarify", "none", (), "ambiguous_intent", True, "请明确要查询的房源指标或分析任务。")
    if intent == "data_quality":
        if not hive_available:
            return RouteDecision("clarify", "none", (), "hive_required", True, "数据质量查询需要 Hive；当前未启用，请启用后重试。")
        if scope != "import_quality":
            return RouteDecision("clarify", "none", (), "scope_conflict", True, "请确认要查询导入数据质量。")
        return RouteDecision(intent, "hive", ("v_agent_house_data_quality_summary",), "accepted")
    if scope == "import_quality":
        return RouteDecision("clarify", "none", (), "scope_conflict", True, "请明确要查询导入质量还是房源统计。")
    if scope == "none":
        return RouteDecision("clarify", "none", (), "scope_conflict", True, "请明确查询范围与指标。")
    if explicit_import and scope == "current_listing":
        return RouteDecision("clarify", "none", (), "explicit_import_conflict", True, "请确认是否查询 Hive 导入数据集。")
    source = SCOPE_SOURCE[scope]
    if source == "hive" and not hive_available:
        return RouteDecision("clarify", "none", (), "hive_unavailable", True, "该导入数据查询需要 Hive；当前未启用。")
    if source == "hive":
        return RouteDecision(intent, source, ("v_agent_house_info_analysis",), "accepted")
    if intent == "trend":
        table = "v_agent_monthly_price_trend"
    elif intent in {"ranking", "comparison"} and row_granularity != "listing":
        table = "v_agent_district_summary"
    else:
        table = "v_agent_house_listing"
    return RouteDecision(intent, "mysql", (table,), "accepted")
