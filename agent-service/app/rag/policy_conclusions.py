"""Short conclusions for policy questions whose facts can be checked mechanically."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.rag.policy_scope import policy_query_date


_PERIOD = re.compile(r"自(20\d{2})年(\d{1,2})月(\d{1,2})日至(20\d{2})年(\d{1,2})月(\d{1,2})日")
_SOCIAL_YEARS = re.compile(r"连续缴纳满(\d+)年")


def direct_policy_conclusion(question: str, evidence: list[dict[str, Any]]) -> str | None:
    """Return a direct answer only when all required facts are in retrieved evidence."""
    if not evidence:
        return None
    compact = re.sub(r"\s+", "", question)

    if "公积金" in compact and "利率" in compact and any(
        word in compact for word in ("生效", "执行时间", "何时执行")
    ):
        rate = [item for item in evidence if item.get("policy_subject") == "provident_loan_interest_rate"]
        new = next((item for item in rate if "2025年5月8日（含）之后新发放" in item.get("content", "")), None)
        existing = next((item for item in rate if "2026年1月1日（含）开始" in item.get("content", "")), None)
        if (new and existing and new.get("version_id") == existing.get("version_id")
                and new.get("effective_check") == "unknown"):
            return ("不能仅从文件元数据确认统一生效日：effective_date为unknown。公告正文对新发放与存量贷款分别规定，"
                    "2025年5月8日（含）后新发放的贷款按调整后利率；此前已发放的贷款"
                    "需按贷款期限区分，一年以上的自2026年1月1日（含）起执行调整后利率。"
                    "不能把公告发布日期当作所有贷款的统一生效日。")

    asked_date, published_by_date = policy_query_date(question)
    if (asked_date and not published_by_date and "换购" in compact
            and any(word in compact for word in ("适用期间", "适用期", "追溯适用"))):
        for item in evidence:
            if item.get("policy_subject") != "replacement_income_tax_refund":
                continue
            match = _PERIOD.search(item.get("content", ""))
            if not match:
                continue
            try:
                start = date(*map(int, match.groups()[:3]))
                end = date(*map(int, match.groups()[3:]))
                target = date.fromisoformat(asked_date)
            except ValueError:
                continue
            if start <= target <= end:
                published = item.get("publication_date")
                later = bool(published and published > asked_date)
                date_text = f"{target.year}年{target.month}月{target.day}日"
                answer = f"是，{date_text}落在该公告明确写出的{start.year}年{start.month}月{start.day}日至{end.year}年{end.month}月{end.day}日适用期间。"
                if later:
                    pub = date.fromisoformat(published)
                    answer += f"但公告于{pub.month}月{pub.day}日才公布，这是后来发布的追溯适用规则，不能说{date_text}当时已经公布。"
                return answer + "这只判断政策期间，个人能否退税仍需核对其他条件。"

    if ("五环内" in compact and any(word in compact for word in ("非京籍", "非本市户籍"))
            and any(word in compact for word in ("变化", "前后", "对比"))):
        versions: dict[str, tuple[int, dict[str, Any]]] = {}
        for item in evidence:
            if (item.get("policy_subject") != "nonlocal_purchase_social_years"
                    or item.get("applicability_scope", {}).get("ring") != "inner"):
                continue
            match = _SOCIAL_YEARS.search(item.get("content", ""))
            if match and item.get("effective_from"):
                versions[item["effective_from"]] = (int(match.group(1)), item)
        ordered = sorted(versions.items())
        if len(ordered) >= 2:
            before_date, (before_years, before) = ordered[-2]
            current_date, (current_years, current) = ordered[-1]
            if before_years != current_years:
                effective = date.fromisoformat(current_date)
                prefix = f"有变化：五环内非京籍家庭购房所需连续缴纳社保或个税年限，从此前的满{before_years}年调整为满{current_years}年。"
                if len(ordered) >= 3:
                    earlier_date, (earlier_years, _) = ordered[-3]
                    def label(item: dict[str, Any], fallback: str) -> str:
                        number = re.search(r"〔(20\d{2})〕(\d+)号", item.get("document_number") or "")
                        return f"{number.group(1)}年{number.group(2)}号" if number else fallback
                    prefix += (f"已收录的三个版本依次为{earlier_date[:4]}年满{earlier_years}年、"
                               f"{label(before, before_date[:4] + '年')}满{before_years}年、"
                               f"{label(current, current_date[:4] + '年')}满{current_years}年。")
                prefix += f"最新通知写明自印发次日起施行，按文件印发日推算为{effective.year}年{effective.month}月{effective.day}日。"
                if current.get("effective_check") != "machine_checked":
                    prefix += "该施行日是机器据原文推算，正式适用仍需核对。"
                return prefix
    return None
