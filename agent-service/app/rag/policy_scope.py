"""Bound the policy corpus by explicit geography and question time semantics."""

from __future__ import annotations

import re

# The corpus has Beijing-scoped indexing. An explicit different city must never
# silently inherit that scope. This list covers municipalities and major cities;
# the explicit 市 suffix catches other named cities without matching 市场/本市.
_CITY_NAMES = (
    "北京", "天津", "上海", "重庆", "广州", "深圳", "杭州", "南京", "苏州", "成都",
    "武汉", "西安", "郑州", "长沙", "合肥", "济南", "青岛", "厦门", "福州", "宁波",
    "无锡", "东莞", "佛山", "珠海", "沈阳", "大连", "哈尔滨", "昆明", "南宁", "廊坊",
    "南昌", "石家庄", "太原", "兰州", "贵阳", "海口", "呼和浩特", "乌鲁木齐",
)
_NAMED_CITY = re.compile(r"([\u4e00-\u9fff]{2,6})市(?=的|购|住|房|限|公|政|今|明|去|2|，|。|？|\?|$)")
_DAY = re.compile(r"(?<!\d)(20\d{2})\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})\s*日?")


def explicit_policy_cities(question: str) -> set[str]:
    found = {f"{name}市" for name in _CITY_NAMES if name in question}
    for raw in _NAMED_CITY.findall(question):
        if raw not in {"本", "该"}:
            name = next((known for known in sorted(_CITY_NAMES, key=len, reverse=True) if raw.endswith(known)), raw)
            found.add(f"{name}市")
    return found


def policy_query_date(question: str) -> tuple[str | None, bool]:
    """Return a requested date and whether the user asks what was public then."""
    compact = re.sub(r"\s+", "", question)
    published_by_date = bool(re.search(r"当时(已经|已|能)(公布|发布|查到|获知)|截至当日(已经|已)?(公布|发布)|当日(已经|已)(公布|发布)|当时可获知", compact))
    match = _DAY.search(compact)
    if match:
        from datetime import date
        try:
            return date(*map(int, match.groups())).isoformat(), published_by_date
        except ValueError:
            return None, published_by_date
    # A year alone specifies the beginning of a future eligibility year only
    # when the question actually asks whether a benefit still applies then.
    year = re.search(r"(?<!\d)(20\d{2})年", compact)
    if year and re.search(r"还|仍|届时|当年|该年|那年|适用|能享受", compact):
        return f"{year.group(1)}-01-01", published_by_date
    return None, published_by_date
