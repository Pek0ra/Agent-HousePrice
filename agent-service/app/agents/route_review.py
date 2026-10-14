"""Shared prompt for the one-shot structured review of uncertain Jev routes."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.jev_router import INTENT_CRITERIA, SCOPE_CRITERIA


def route_review_messages(
    question: str, previous: dict[str, Any] | None, proposed: dict[str, Any],
    reason: str, hive_available: bool,
) -> list[SystemMessage | HumanMessage]:
    return [
        SystemMessage(
            "对当前房产问数请求做一次结构化路由复核。intent 只能为 " + ", ".join(INTENT_CRITERIA) +
            "，规则：" + json.dumps(INTENT_CRITERIA, ensure_ascii=False) +
            "。scope 只能为 " + ", ".join(SCOPE_CRITERIA) +
            "，规则：" + json.dumps(SCOPE_CRITERIA, ensure_ascii=False) +
            "。scope 表示用户要求的数据集，不因 Hive 不可用而改成 MySQL。"
            "只有两个独立查询才算多个任务；同一查询的多个字段或指标不算。"
            "只有必须继承上一轮条件才算依赖上文；当前激活数据集不是上文。"
            "明确指定 Hive/导入数据时不能选 current_listing。"
            "不得生成 SQL。Hive 可用：" + str(hive_available)
        ),
        HumanMessage(json.dumps({
            "question": question,
            "previous": {key: (previous or {}).get(key) for key in ("cities", "districts", "metric", "intent")},
            "jev_suggestion": proposed,
            "review_reason": reason,
        }, ensure_ascii=False)),
    ]
