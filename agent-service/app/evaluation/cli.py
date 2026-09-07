from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.evaluation.baseline import load_baseline
from app.evaluation.client import AgentClient
from app.evaluation.loader import DatasetError, load_cases, sha256_file
from app.evaluation.pricing import estimate_cost, load_pricing
from app.evaluation.reporter import write_reports
from app.evaluation.scorers import score


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="通过 HTTP 独立运行房价 Agent 确定性评测")
    result.add_argument("--dataset", type=Path, required=True); result.add_argument("--base-url", default="http://localhost:8000/api/v1/chat")
    result.add_argument("--output-dir", type=Path, default=Path("evaluation-results")); result.add_argument("--run-id")
    result.add_argument("--baseline", type=Path); result.add_argument("--groups", nargs="*"); result.add_argument("--case-ids", nargs="*")
    result.add_argument("--timeout", type=float, default=60); result.add_argument("--concurrency", type=int, default=1)
    result.add_argument("--pricing-file", type=Path); result.add_argument("--fail-on-regression", action="store_true"); result.add_argument("--max-cases", type=int)
    return result


def _run_case(case, url: str, timeout: float, pricing: dict | None) -> tuple[list[dict], list[dict]]:
    client = AgentClient(url, timeout); thread_id = None; raw_items = []; scored_items = []
    try:
        for index, turn in enumerate(case.turns, 1):
            if turn.expected.get("new_thread"): thread_id = None
            status, elapsed, body, raw_body = client.ask(turn.question, thread_id)
            if body and body.get("thread_id"): thread_id = body["thread_id"]
            raw = {"case_id": case.id, "group": case.group, "turn_index": index, "question": turn.question, "expected": turn.expected, "http_status": status, "response_time_ms": round(elapsed, 2), "body": body, "raw_body": raw_body, "error": None}
            metrics = score(body, status, turn.expected, estimate_cost((body or {}).get("details") or {}, pricing))
            raw_items.append(raw); scored_items.append({**raw, "metrics": metrics, "passed": metrics["passed"]})
    except Exception as exc:
        index = len(raw_items) + 1; turn = case.turns[index - 1]
        raw = {"case_id": case.id, "group": case.group, "turn_index": index, "question": turn.question, "expected": turn.expected, "http_status": None, "response_time_ms": 0, "body": None, "raw_body": "", "error": str(exc)}
        metrics = score(None, None, turn.expected, None); raw_items.append(raw); scored_items.append({**raw, "metrics": metrics, "passed": False})
    finally: client.close()
    return raw_items, scored_items


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.concurrency < 1 or args.max_cases is not None and args.max_cases < 1: print("参数必须为正数", file=sys.stderr); return 2
    try:
        cases = load_cases(args.dataset, set(args.groups or []) or None, set(args.case_ids or []) or None)
        if args.max_cases: cases = cases[:args.max_cases]
        snapshot_hashes = {case.snapshot_sha256.lower() for case in cases}; snapshot_ids = {case.snapshot_id for case in cases}
        csv_path = args.dataset.parent / "data" / "house_listings.csv"
        if not csv_path.is_file() or snapshot_hashes != {sha256_file(csv_path)}: raise DatasetError("CSV 数据快照 SHA-256 与评测集不匹配")
        client = AgentClient(args.base_url, args.timeout)
        try:
            client.health()
            capabilities = client.capabilities()
            if not capabilities.get("mysql"): raise RuntimeError("MySQL 能力不可用")
            requires_hive = any(turn.expected.get("data_source") == "hive" for case in cases for turn in case.turns)
            if requires_hive and not capabilities.get("hive"): raise RuntimeError("选中的用例需要 Hive，但服务未启用 Hive")
            client.verify_snapshot_count(5000)
        finally: client.close()
        pricing = load_pricing(args.pricing_file); baseline = load_baseline(args.baseline)
    except (DatasetError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"预检失败：{exc}", file=sys.stderr); return 2
    raw_all = []; scored_all = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_run_case, case, args.base_url, args.timeout, pricing) for case in cases]
        for future in as_completed(futures):
            raw, scored = future.result(); raw_all.extend(raw); scored_all.extend(scored)
    scored_all.sort(key=lambda item: ([case.id for case in cases].index(item["case_id"]), item["turn_index"])); raw_all.sort(key=lambda item: ([case.id for case in cases].index(item["case_id"]), item["turn_index"]))
    for item in scored_all:
        item["regressed"] = baseline.get((item["case_id"], item["turn_index"]), False) and not item["passed"]
        item["metrics"]["regression"] = item["regressed"]
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    try: git_commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or None
    except OSError: git_commit = None
    try: summary = write_reports(args.output_dir / run_id, raw_all, scored_all, {"run_id": run_id, "snapshot_id": sorted(snapshot_ids), "snapshot_sha256": sorted(snapshot_hashes), "model": settings.openai_model, "prompt_version": "langgraph-v2", "git_commit": git_commit})
    except FileExistsError: print(f"输出目录已存在：{args.output_dir / run_id}", file=sys.stderr); return 2
    print(f"报告：{(args.output_dir / run_id / 'report.md').resolve()}")
    regression = bool(summary["regressions"]); failed = summary["passed_turns"] != summary["total_turns"]
    return 1 if failed or (args.fail_on_regression and regression) else 0
