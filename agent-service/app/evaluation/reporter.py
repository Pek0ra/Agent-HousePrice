from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values: return None
    ordered = sorted(values); index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return round(ordered[index], 2)


def write_reports(run_dir: Path, raw: list[dict], scored: list[dict], metadata: dict[str, Any]) -> dict:
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "raw-results.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in raw), encoding="utf-8")
    (run_dir / "scored-results.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in scored), encoding="utf-8")
    groups: dict[str, list[bool]] = defaultdict(list)
    for item in scored: groups[item["group"]].append(item["passed"])
    durations = [item["response_time_ms"] for item in scored]
    token = lambda name: sum(item.get("metrics", {}).get(name) or 0 for item in scored)
    priced = [item["metrics"].get("estimated_cost_usd") for item in scored]
    summary = {
        **metadata, "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len({item["case_id"] for item in scored}), "total_turns": len(scored),
        "passed_turns": sum(item["passed"] for item in scored),
        "group_pass_rates": {name: round(sum(values) / len(values), 4) for name, values in groups.items()},
        "metric_pass_rates": {name: round(sum(bool(item["metrics"].get(name)) for item in scored) / len(scored), 4) for name in ["sql_executable", "result_correct", "answer_grounded", "data_source_correct", "selected_tables_correct", "dangerous_sql_rejected", "used_history_correct"]},
        "response_time_ms": {"average": round(statistics.mean(durations), 2), "p50": _percentile(durations, .5), "p95": _percentile(durations, .95)},
        "model_calls": token("model_calls"), "prompt_tokens": token("prompt_tokens"), "completion_tokens": token("completion_tokens"), "total_tokens": token("total_tokens"),
        "estimated_cost_usd": round(sum(value for value in priced if value is not None), 8) if priced and all(value is not None for value in priced) else None,
        "regressions": [{"case_id": i["case_id"], "turn_index": i["turn_index"]} for i in scored if i.get("regressed")],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [f"# Agent 评测报告：{metadata['run_id']}", "", f"- 用例：{summary['total_cases']}，轮次：{summary['total_turns']}", f"- 通过：{summary['passed_turns']}/{summary['total_turns']}", f"- 延迟：平均 {summary['response_time_ms']['average']} ms，P50 {summary['response_time_ms']['p50']} ms，P95 {summary['response_time_ms']['p95']} ms", f"- 模型调用：{summary['model_calls']}，Token：{summary['total_tokens']}", f"- 估算费用：{summary['estimated_cost_usd'] if summary['estimated_cost_usd'] is not None else '未配置价格，无法估算'}", "", "## 分组通过率", ""]
    report += [f"- {name}: {rate:.1%}" for name, rate in summary["group_pass_rates"].items()]
    report += ["", "## 回归" , "", *(f"- {item['case_id']} / turn {item['turn_index']}" for item in summary["regressions"])] if summary["regressions"] else ["", "## 回归", "", "无。"]
    (run_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary
