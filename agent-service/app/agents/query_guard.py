"""Ground generated location predicates and scalar quality queries before execution."""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


QUALITY_SCALARS = {
    "无效面积": ("invalid_area_rows", "无效面积记录"),
    "无效价格": ("invalid_price_rows", "无效价格记录"),
    "缺失位置": ("missing_location_rows", "缺失位置记录"),
    "重复源记录": ("duplicate_source_rows", "重复源记录"),
    "有效行数": ("valid_rows", "有效记录"),
}


def quality_scalar(question: str, selected_tables: list[str]) -> tuple[str, str] | None:
    if selected_tables != ["v_agent_house_data_quality_summary"]:
        return None
    if not re.search(r"多少|几条|数量|行数", question):
        return None
    if re.search(r"大于|小于|超过|低于|至少|不超过|>\s*\d|<\s*\d", question):
        return None
    matches = [value for word, value in QUALITY_SCALARS.items() if word in question]
    return matches[0] if len(matches) == 1 else None


def ground_query(sql: str, *, districts: list[str], source: str,
                 selected_tables: list[str], question: str) -> str:
    """Canonicalize district literals; reject a query that silently drops the requested district."""
    quality = quality_scalar(question, selected_tables) if source == "hive" else None
    if quality:
        return f"SELECT {quality[0]} FROM v_agent_house_data_quality_summary"
    if not districts:
        return sql
    try:
        tree = sqlglot.parse_one(sql, read=source)
    except sqlglot.ParseError as exc:
        raise ValueError("SQL 解析失败，无法校验地区条件") from exc
    expected = set(districts)
    observed: list[str] = []
    changed = False

    def canonical(value: str) -> str:
        return next((name for name in expected if name == value or name.removesuffix("区") == value), value)

    for node in tree.walk():
        values: list[exp.Literal] = []
        if isinstance(node, exp.EQ) and isinstance(node.left, exp.Column) and node.left.name.lower() == "district":
            if isinstance(node.right, exp.Literal) and node.right.is_string:
                values = [node.right]
        elif isinstance(node, exp.In) and isinstance(node.this, exp.Column) and node.this.name.lower() == "district":
            values = [item for item in node.expressions if isinstance(item, exp.Literal) and item.is_string]
        for item in values:
            fixed = canonical(item.this)
            observed.append(fixed)
            if fixed != item.this:
                item.replace(exp.Literal.string(fixed))
                changed = True
    if set(observed) != expected:
        raise ValueError(f"SQL 地区条件与问题不一致：应为 {sorted(expected)}，实际为 {sorted(set(observed))}")
    return tree.sql(dialect=source) if changed else sql
