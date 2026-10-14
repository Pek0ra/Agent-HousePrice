"""Deterministic permission and table policy for a Jev suggestion."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.jev_router import RouteSuggestion, ScopeChoice, SCOPE_SOURCE


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    source: str
    tables: tuple[str, ...]
    reason: str
    needs_clarification: bool = False
    clarification_question: str | None = None


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
                 explicit_import: bool = False) -> RouteDecision:
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
    elif intent in {"ranking", "comparison"}:
        table = "v_agent_district_summary"
    else:
        table = "v_agent_house_listing"
    return RouteDecision(intent, "mysql", (table,), "accepted")
