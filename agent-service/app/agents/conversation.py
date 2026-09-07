from __future__ import annotations

import re
from typing import Any

from app.schemas.chat import ContextResolution

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
DISTRICT_CITIES = {
    "浦东新区": "上海市",
    "南山区": "深圳市",
    "福田区": "深圳市",
}
CN_NUMBER = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

CONTEXT_FIELDS = (
    "cities",
    "districts",
    "listing_type",
    "metric",
    "bedroom_count",
    "living_room_count",
    "start_month",
    "end_month",
    "ranking_limit",
    "intent",
)

DEPENDENCY_PATTERN = re.compile(
    r"(^\s*(那|那么|再|继续|同样|然后)|只看|改成|换成|上述|这些|刚才|上一(?:条|轮)|按之前|照旧|也呢|呢[？?]?$)"
)


def _number(value: str) -> int:
    return int(value) if value.isdigit() else CN_NUMBER[value]


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def extract_explicit_slots(question: str) -> dict[str, Any]:
    cities = [canonical for alias, canonical in CITY_ALIASES.items() if alias in question]
    districts = [
        canonical for alias, canonical in DISTRICT_ALIASES.items() if alias in question
    ]
    slots: dict[str, Any] = {}
    if cities:
        slots["cities"] = _ordered_unique(cities)
    if districts:
        slots["districts"] = _ordered_unique(districts)

    if re.search(r"(月租金|租金|出租|租赁)", question):
        slots.update(metric="monthly_rent", listing_type="RENT")
    elif "总价" in question:
        slots.update(metric="total_price", listing_type="SALE")
    elif re.search(r"(房价|挂牌单价|单价|均价)", question):
        slots.update(metric="unit_price", listing_type="SALE")
    elif re.search(r"(数量|多少套|几套)", question):
        slots["metric"] = "listing_count"
    elif re.search(r"(出售|售房|在售)", question):
        slots.update(metric="listing", listing_type="SALE")
    elif re.search(r"(房源|房子|住宅)", question):
        slots["metric"] = "listing"

    room_match = re.search(
        r"([\d一二两三四五六七八九])室([\d一二两三四五六七八九])厅", question
    )
    if room_match:
        slots["bedroom_count"] = _number(room_match.group(1))
        slots["living_room_count"] = _number(room_match.group(2))

    months = re.findall(r"((?:19|20)\d{2})[-年/.](0?[1-9]|1[0-2])(?:月)?", question)
    if months:
        normalized_months = [f"{year}-{int(month):02d}" for year, month in months]
        slots["start_month"] = normalized_months[0]
        slots["end_month"] = normalized_months[-1]

    rank_match = re.search(r"(?:top\s*|前)(\d+|[一二两三四五六七八九])", question, re.I)
    if rank_match:
        slots["ranking_limit"] = _number(rank_match.group(1))

    if re.search(r"(趋势|走势|月度|每月|按月|变化)", question):
        slots["intent"] = "trend"
    elif re.search(r"(对比|比较|相比|之间|哪个.{0,4}(更高|更低|更贵|便宜|好))", question):
        slots["intent"] = "comparison"
    elif re.search(r"(排名|排行|top\s*\d*|前[\d一二两三四五六七八九十]+)", question, re.I):
        slots["intent"] = "ranking"
    elif re.search(r"(平均|均价|最高|最低|最大|最小|多少|数量|房价|租金|性价比|划算)", question):
        slots["intent"] = "aggregation"
    elif re.search(r"(列出|哪些|查询|查看|房源)", question):
        slots["intent"] = "listing_search"
    return slots


def normalize_question(question: str) -> str:
    normalized = question
    for alias, canonical in {**CITY_ALIASES, **DISTRICT_ALIASES}.items():
        if alias in normalized and canonical not in normalized:
            normalized = normalized.replace(alias, canonical)
    return normalized


def _new_context() -> dict[str, Any]:
    return {
        "cities": [],
        "districts": [],
        "listing_type": None,
        "metric": None,
        "bedroom_count": None,
        "living_room_count": None,
        "start_month": None,
        "end_month": None,
        "ranking_limit": None,
        "intent": None,
        "pending_clarification": None,
        "previous_question": None,
        "previous_answer_summary": None,
    }


def _is_complete_new_question(question: str, slots: dict[str, Any]) -> bool:
    has_location = bool(slots.get("cities") or slots.get("districts"))
    has_subject = bool(
        slots.get("metric")
        or slots.get("listing_type")
        or re.search(r"(房源|房价|租金|住宅|数据质量|hive)", question, re.I)
    )
    return has_location and has_subject and not DEPENDENCY_PATTERN.search(question)


def _render_standalone(context: dict[str, Any]) -> str:
    locations = [*context.get("cities", []), *context.get("districts", [])]
    location_text = "、".join(_ordered_unique(locations))
    listing_text = {"RENT": "出租房", "SALE": "出售房"}.get(
        context.get("listing_type"), "房源"
    )
    metric_text = {
        "monthly_rent": "平均月租金",
        "unit_price": "平均挂牌单价",
        "total_price": "平均挂牌总价",
        "listing_count": "挂牌数量",
        "listing": "房源",
    }.get(context.get("metric"), "房源数据")
    room_text = ""
    if context.get("bedroom_count") is not None:
        room_text = f"，户型为{context['bedroom_count']}室"
        if context.get("living_room_count") is not None:
            room_text += f"{context['living_room_count']}厅"
    time_text = ""
    if context.get("start_month"):
        time_text = f"，从{context['start_month']}"
        if context.get("end_month"):
            time_text += f"到{context['end_month']}"
    intent = context.get("intent")
    if intent == "comparison":
        return f"比较{location_text or '指定地区'}{listing_text}的{metric_text}{room_text}{time_text}。"
    if intent == "ranking":
        limit = context.get("ranking_limit") or 5
        return f"查询{location_text}{listing_text}{metric_text}排名前{limit}名{room_text}{time_text}。"
    if intent == "trend":
        return f"查询{location_text}{listing_text}{metric_text}的月度趋势{room_text}{time_text}。"
    if intent == "listing_search" or context.get("metric") == "listing":
        return f"列出{location_text}{listing_text}{room_text}{time_text}。"
    return f"查询{location_text}{listing_text}的{metric_text}{room_text}{time_text}。"


def resolve_conversation_context(
    question: str,
    previous_context: dict[str, Any] | None,
    *,
    unsafe: bool = False,
) -> tuple[ContextResolution, dict[str, Any]]:
    old = {**_new_context(), **(previous_context or {})}
    explicit = extract_explicit_slots(question)
    has_history = bool(old.get("previous_question") or old.get("pending_clarification"))
    complete_new = _is_complete_new_question(question, explicit)
    dependent_marker = bool(DEPENDENCY_PATTERN.search(question))
    depends = bool(has_history and not unsafe and (dependent_marker or old.get("pending_clarification")))

    if unsafe:
        resolution = ContextResolution(
            depends_on_history=False,
            standalone_question=question,
            inherited_fields=[],
            overridden_fields=[],
            unresolved_reference=False,
            clarification_question=None,
        )
        return resolution, old

    if complete_new:
        depends = False

    if not has_history or not depends:
        merged = _new_context()
    else:
        merged = dict(old)

    inherited: list[str] = []
    overridden: list[str] = []

    if depends:
        for field in CONTEXT_FIELDS:
            if field not in explicit and old.get(field) not in (None, [], ""):
                inherited.append(field)

    if "cities" in explicit:
        if depends and old.get("cities") != explicit["cities"]:
            overridden.append("cities")
        merged["cities"] = explicit["cities"]
        # A new city replaces the old geographic scope, including its districts.
        if depends and old.get("districts") and not explicit.get("districts"):
            overridden.append("districts")
        new_districts = explicit.get("districts", [])
        if depends and old.get("districts") != new_districts:
            overridden.append("districts")
        merged["districts"] = new_districts
    elif "districts" in explicit:
        if depends and old.get("districts") != explicit["districts"]:
            overridden.append("districts")
        merged["districts"] = explicit["districts"]
        inferred = _ordered_unique(
            [DISTRICT_CITIES[item] for item in explicit["districts"] if item in DISTRICT_CITIES]
        )
        if inferred and not merged.get("cities"):
            merged["cities"] = inferred

    for field, value in explicit.items():
        if field in {"cities", "districts"}:
            continue
        if depends and old.get(field) not in (None, [], "") and old.get(field) != value:
            overridden.append(field)
        merged[field] = value

    if re.search(r"(不限区域|所有区域|取消区域限制)", question):
        if depends and merged.get("districts"):
            overridden.append("districts")
        merged["districts"] = []
    if re.search(r"(不限户型|所有户型|取消户型限制)", question):
        for field in ("bedroom_count", "living_room_count"):
            if depends and merged.get(field) is not None:
                overridden.append(field)
            merged[field] = None
    if re.search(r"(不限时间|全部月份|取消时间限制)", question):
        for field in ("start_month", "end_month"):
            if depends and merged.get(field) is not None:
                overridden.append(field)
            merged[field] = None

    # Metric and listing type are one business unit; never retain a contradictory pair.
    if merged.get("metric") == "monthly_rent":
        merged["listing_type"] = "RENT"
    elif merged.get("metric") in {"unit_price", "total_price"}:
        merged["listing_type"] = "SALE"

    unresolved = bool(
        has_history
        and dependent_marker
        and not explicit
        and re.search(r"(这个|那个|这些|上述|那里|那边)", question)
    )
    clarification = "你想沿用上一轮的哪些条件，并修改什么内容？" if unresolved else None
    standalone = normalize_question(question) if not depends else _render_standalone(merged)
    resolution = ContextResolution(
        depends_on_history=depends,
        standalone_question=standalone,
        inherited_fields=_ordered_unique(inherited),
        overridden_fields=_ordered_unique(overridden),
        unresolved_reference=unresolved,
        clarification_question=clarification,
    )
    return resolution, merged


def trim_messages(
    messages: list[dict[str, str]], *, max_messages: int, max_chars: int
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(messages[-max_messages:]):
        content = str(message.get("content", ""))[:1000]
        if selected and used + len(content) > max_chars:
            break
        selected.append({"role": str(message.get("role", "user")), "content": content})
        used += len(content)
    return list(reversed(selected))
