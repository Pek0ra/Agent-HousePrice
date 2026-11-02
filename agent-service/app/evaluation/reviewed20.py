"""Reproducible, conservative evaluation of the reviewed 20-case CSV.

Only observations are automated. A human adjudication is a separate JSONL file.
This module deliberately has no service or application imports for offline replay.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "agent-service/evaluation/real-regression-2026-10-23/human_annotation_reviewed.csv"
OLD = ROOT / "agent-service/evaluation/real-regression-2026-10-23/new20_reviewed_2026-10-30.jsonl"
JSON_LISTS = ("acceptable_version_ids", "acceptable_clause_paths", "must_include", "must_not_include", "review_basis")
REQUIRED = ("case_id", "question", "history", "review_status", "should_answer", "expected_intent", "expected_source", "recommended_answer", "acceptable_range")
PENDING: dict[str, str] = {}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gold(path: Path = GOLD) -> tuple[list[dict], str]:
    if not path.is_file():
        raise ValueError(f"standard missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = set(REQUIRED + JSON_LISTS + ("sql_verification",)) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        rows = list(reader)
    ids = set()
    for line, row in enumerate(rows, 2):
        cid = row["case_id"].strip()
        if not all(row[k].strip() for k in REQUIRED):
            raise ValueError(f"line {line}: required field missing")
        if cid in ids:
            raise ValueError(f"duplicate case ID: {cid}")
        ids.add(cid)
        if row["should_answer"] not in {"true", "false"}:
            raise ValueError(f"{cid}: should_answer must be true/false")
        if row["expected_intent"] not in {"policy", "aggregation", "listing_search", "policy_listing"} or row["expected_source"] not in {"policy", "mysql", "hive"}:
            raise ValueError(f"{cid}: unknown intent/source")
        for key in JSON_LISTS:
            if not row[key]:
                if key in {"must_include", "must_not_include"}:
                    raise ValueError(f"{cid}: {key} must be a JSON list")
                row[key + "_parsed"] = []
                continue
            try:
                value = json.loads(row[key])
            except json.JSONDecodeError as exc:
                raise ValueError(f"{cid}: invalid {key}: {exc}") from exc
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"{cid}: {key} must be a string list")
            row[key + "_parsed"] = value
        if row["sql_verification"]:
            try:
                sql = json.loads(row["sql_verification"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"{cid}: invalid sql_verification: {exc}") from exc
            if not isinstance(sql, dict) or not all(k in sql for k in ("sql", "rows", "columns", "source")) or not isinstance(sql["rows"], list):
                raise ValueError(f"{cid}: incomplete sql_verification")
            if sql["source"] != row["expected_source"]:
                raise ValueError(f"{cid}: SQL source conflicts with expected_source")
            row["sql_parsed"] = sql
        else:
            row["sql_parsed"] = None
        # rag_retrieval and acceptable_range are prose in this reviewed CSV.
    if len(rows) != 20:
        raise ValueError(f"expected 20 reviewed cases; found {len(rows)}")
    return rows, digest(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def metadata(gold_hash: str, origin: str) -> dict:
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip())
    if origin.startswith(("http://", "https://")):
        parsed = urlsplit(origin)
        origin = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
    return {"created_at_utc": now(), "standard_sha256": gold_hash, "origin": origin,
            "git_commit": git or None, "working_tree_dirty": dirty,
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "public_service_config": {k: os.environ[k] for k in ("OPENAI_MODEL", "JEV_MODEL", "JEV_TIMEOUT_SECONDS", "AGENT_SERVICE_VERSION") if k in os.environ}}


def new_dir(base: Path, gold_hash: str) -> Path:
    path = base / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{gold_hash[:12]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def run_request(endpoint: str, message: str, thread_id: str | None, timeout: float) -> dict:
    payload = {"message": message}
    if thread_id:
        payload["thread_id"] = thread_id
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"request": payload, "status": None, "response": None, "error": type(exc).__name__, "duration_ms": round((time.perf_counter()-started)*1000)}
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = {"unparsed_body": raw}
    return {"request": payload, "status": status, "response": body, "error": None, "duration_ms": round((time.perf_counter()-started)*1000)}


def history_turns(history: str) -> list[str]:
    if history.strip() in {"无", "none", "None", ""}:
        return []
    return [part.strip() for part in history.removeprefix("上一问：").split("\n") if part.strip()]


def run_cases(cases: list[dict], endpoint: str, timeout: float, output: Path) -> None:
    with (output / "raw.jsonl").open("x", encoding="utf-8") as stream:
        for case in cases:
            prior, thread_id = [], None
            for message in history_turns(case["history"]):
                response = run_request(endpoint, message, thread_id, timeout)
                prior.append(response)
                thread_id = (response.get("response") or {}).get("thread_id") or thread_id
            final = run_request(endpoint, case["question"], thread_id, timeout)
            item = {"case_id": case["case_id"], "history": case["history"], "question": case["question"], "history_responses": prior, "final": final}
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"{case['case_id']} HTTP {final['status']}", flush=True)


def sql_semantics(expected: str, actual: str | None) -> dict:
    if not actual:
        return {"status": "missing", "checks": {}}
    checks = {}
    for key in ("city", "district", "listing_type"):
        pattern = rf"\b{key}\s*=\s*'([^']+)'"
        want = re.search(pattern, expected, re.I)
        got = re.search(pattern, actual, re.I)
        if want:
            checks[key] = bool(got and got.group(1) == want.group(1))
        in_pattern = rf"\b{key}\s+in\s*\(([^)]+)\)"
        wanted_in, got_in = re.search(in_pattern, expected, re.I), re.search(in_pattern, actual, re.I)
        if wanted_in:
            values = lambda match: set(re.findall(r"'([^']+)'", match.group(1))) if match else set()
            checks[key + "_in"] = values(wanted_in) == values(got_in)
    # Compare explicit ordering/limit; SQL projection and aliases may differ.
    for key, pattern in (("order_by", r"\border\s+by\s+(\w+)\s+(asc|desc)"), ("limit", r"\blimit\s+(\d+)")):
        want, got = re.search(pattern, expected, re.I), re.search(pattern, actual, re.I)
        if want:
            checks[key] = bool(got and tuple(x.lower() for x in got.groups()) == tuple(x.lower() for x in want.groups()))
    if "invalid_area_rows" in expected.lower() and "invalid_area_rows" in actual.lower():
        checks["zero_including_filter"] = not bool(re.search(r"\binvalid_area_rows\s*>\s*0", actual, re.I))
    return {"status": "match" if all(checks.values()) else "mismatch", "checks": checks}


def decimal_match(want: object, got: object) -> bool:
    try:
        a, b = Decimal(str(want)), Decimal(str(got))
    except (InvalidOperation, ValueError):
        return str(want).strip() == str(got).strip()
    # Oracle values are expressed to cents. No tolerance is invented after seeing results.
    return a.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == b.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def result_check(sql: dict | None, response: dict) -> dict:
    if not sql:
        return {"status": "not_applicable"}
    rows = response.get("rows")
    if rows is None:
        return {"status": "missing_rows"}
    if not isinstance(rows, list):
        return {"status": "invalid_rows"}
    wanted, actual = sql["rows"], rows
    if len(wanted) != len(actual):
        return {"status": "mismatch", "expected_rows": len(wanted), "actual_rows": len(actual)}
    # A scalar query returning [[0]] is distinct from no result row [].
    def ordered_values(w: list, a: list) -> bool:
        remaining = iter(a)
        return all(any(decimal_match(value, observed) for observed in remaining) for value in w)
    values_match = all(ordered_values(w, a) for w, a in zip(wanted, actual))
    partial = not values_match and all(any(decimal_match(w[-1], observed) for observed in a) for w, a in zip(wanted, actual) if w and a)
    return {"status": "match" if values_match else "projection_review" if partial else "mismatch", "expected_rows": len(wanted), "actual_rows": len(actual), "expected": wanted, "actual": actual, "precision": "decimal cents; half-up; zero extra tolerance"}


def score_case(case: dict, raw: dict, adjudication: dict | None = None) -> dict:
    final = raw.get("final") or {}; body = final.get("response") or {}; details = body.get("details") or {}
    answer = body.get("answer") or ""; evidence = details.get("policy_evidence") or []
    suggestion = details.get("route_suggestion") or {}
    sql = case["sql_parsed"]
    results = result_check(sql, body)
    versions = case["acceptable_version_ids_parsed"]
    clauses = case["acceptable_clause_paths_parsed"]
    policy = {"status": "not_applicable" if not versions else "needs_human_review", "version_match": bool(versions and any(e.get("version_id") in versions for e in evidence)),
              "clause_match": bool(clauses and any(e.get("clause_path") in clauses for e in evidence)),
              "source_present": any(bool(e.get("source_url")) for e in evidence),
              "document_number_present": any(bool(e.get("document_number")) for e in evidence),
              "evidence_count": len(evidence), "version_ids": sorted({e.get("version_id") for e in evidence if e.get("version_id")})}
    prior = raw.get("history_responses") or []
    requested_thread = (final.get("request") or {}).get("thread_id")
    prior_thread = ((prior[-1].get("response") or {}).get("thread_id") if prior else None)
    thread_ok = None if not prior else bool(prior_thread and requested_thread == prior_thread and body.get("thread_id") == prior_thread)
    missing = [x for x in case["must_include_parsed"] if x not in answer]
    prohibited = [x for x in case["must_not_include_parsed"] if x in answer]
    http_ok = final.get("status") == 200
    sql_executed = bool(details.get("successful_queries")) if sql else None
    semantics = sql_semantics(sql["sql"], body.get("sql")) if sql else {"status": "not_applicable", "checks": {}}
    if not suggestion:
        jev = "unavailable"
    else:
        jev = "match" if suggestion.get("intent") == case["expected_intent"] else "mismatch"
    source = "match" if details.get("data_source") == case["expected_source"] else "mismatch"
    safety_refusal = bool(re.search(r"(安全|权限|违规).{0,12}(拒绝|无法|不能)", answer))
    if not http_ok:
        failure = "timeout" if final.get("error") in {"TimeoutError", "Timeout"} else "dependency_failure" if final.get("status") in {502, 503, 504} or final.get("error") else "http_failure"
    elif details.get("route_reason") in {"review_unavailable", "jev_unavailable"}:
        failure = "dependency_failure"
    elif safety_refusal:
        failure = "safety_refusal"
    elif any(s == "mismatch" for s in (source, semantics["status"], results["status"])) or sql and not sql_executed or prohibited or thread_ok is False:
        failure = "business_error_candidate"
    else:
        failure = None
    decision = adjudication.get("decision") if adjudication else None
    status = "oracle_pending" if case["case_id"] in PENDING else "adjudicated" if decision else "needs_human_review"
    return {"case_id": case["case_id"], "status": status, "oracle_issue": PENDING.get(case["case_id"]),
            "http_success": http_ok, "http_status": final.get("status"), "duration_ms": final.get("duration_ms"),
            "task_completion": decision or "needs_human_review", "failure_category": failure,
            "jev_intent": suggestion.get("intent"), "jev_check": jev, "data_source": details.get("data_source"), "source_check": source,
            "sql_executed": sql_executed, "sql_semantics": semantics, "sql_result": results,
            "policy": policy, "answer_missing_literal_terms": missing, "answer_prohibited_literal_terms": prohibited,
            "answer_fact_check": "needs_human_review", "thread_check": thread_ok, "used_history": details.get("used_history"),
            "inherited_fields": details.get("inherited_fields"), "overridden_fields": details.get("overridden_fields"),
            "trace_id": body.get("trace_id"), "thread_id": body.get("thread_id"), "route_reason": details.get("route_reason"),
            "sql": body.get("sql"), "rows": body.get("rows"), "policy_evidence": evidence,
            "answer": answer, "adjudication": adjudication}


def adjudications(path: Path | None) -> dict:
    if not path:
        return {}
    result = {}
    for row in read_jsonl(path):
        if row.get("decision") not in {"pass", "partial", "fail"} or not all(row.get(k) for k in ("case_id", "reviewer", "reviewed_at", "reason")):
            raise ValueError("adjudication needs case_id, pass/partial/fail, reviewer, reviewed_at, reason")
        if row["case_id"] in result:
            raise ValueError(f"duplicate adjudication: {row['case_id']}")
        result[row["case_id"]] = row
    return result


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered)-1)*p
    lo = int(index); hi = min(lo+1, len(ordered)-1)
    return round(ordered[lo] + (ordered[hi]-ordered[lo])*(index-lo), 1)


def score_run(cases: list[dict], raw_path: Path, output: Path, adjudication_path: Path | None = None) -> dict:
    raw = read_jsonl(raw_path)
    by_id = {r["case_id"]: r for r in raw}
    if len(raw) != len(cases) or set(by_id) != {c["case_id"] for c in cases}:
        raise ValueError("raw response IDs must match the complete 20-case standard")
    for case in cases:
        item = by_id[case["case_id"]]
        if item.get("question") != case["question"] or item.get("history") != case["history"]:
            raise ValueError(f"{case['case_id']}: raw question/history differs from standard")
    decisions = adjudications(adjudication_path)
    if set(decisions) - set(by_id):
        raise ValueError("adjudication contains unknown case ID")
    scored = [score_case(c, by_id[c["case_id"]], decisions.get(c["case_id"])) for c in cases]
    with (output / "scored.jsonl").open("x", encoding="utf-8") as stream:
        for row in scored:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    durations = [r["duration_ms"] for r in scored if isinstance(r["duration_ms"], (int, float))]
    def count(key: str, value: object) -> int:
        return sum(r[key] == value for r in scored)
    summary = {"cases": len(scored), "completed_at_utc": now(), "http_success": count("http_success", True),
               "task_completion": {v: count("task_completion", v) for v in ("pass", "partial", "fail", "needs_human_review")},
               "jev_match": count("jev_check", "match"), "jev_unavailable": count("jev_check", "unavailable"),
               "source_match": count("source_check", "match"),
               "sql_executed": count("sql_executed", True), "sql_expected": sum(c["sql_parsed"] is not None for c in cases),
               "sql_result_match": sum(r["sql_result"]["status"] == "match" for r in scored),
               "policy_version_match": sum(r["policy"]["version_match"] for r in scored),
               "policy_clause_match": sum(r["policy"]["clause_match"] for r in scored),
               "literal_terms_missing_cases": sum(bool(r["answer_missing_literal_terms"]) for r in scored),
               "prohibited_literal_cases": sum(bool(r["answer_prohibited_literal_terms"]) for r in scored),
               "thread_match": count("thread_check", True), "thread_mismatch": count("thread_check", False),
               "failure_categories": {v: count("failure_category", v) for v in ("dependency_failure", "timeout", "http_failure", "business_error_candidate", "safety_refusal")},
               "p50_ms": percentile(durations, .5), "p95_ms": percentile(durations, .95),
               "latency_note": "Serial case execution; not a concurrent load test", "oracle_pending": list(PENDING)}
    write_json(output / "summary.json", summary)
    with (output / "cases.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        fields = ["case_id", "status", "task_completion", "http_success", "jev_check", "source_check", "sql_executed", "sql_result", "thread_check", "failure_category", "duration_ms", "trace_id"]
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in scored:
            writer.writerow({k: row[k]["status"] if k == "sql_result" else row.get(k) for k in fields})
    return summary


def report(output: Path) -> None:
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    meta = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    rows = read_jsonl(output / "scored.jsonl")
    lines = ["# Agent reviewed 20 evaluation", "", f"Started: {meta['created_at_utc']}  ", f"Completed: {summary['completed_at_utc']}  ", f"Code: {meta['git_commit']} (dirty={meta['working_tree_dirty']})  ", f"Standard SHA-256: `{meta['standard_sha256']}`  ", f"Origin: {meta['origin']}  ", f"Environment: {json.dumps(meta['environment'], ensure_ascii=False)}  ", f"Public config: {json.dumps(meta['public_service_config'], ensure_ascii=False)}", "", "## Separate metrics", ""]
    for key, value in summary.items():
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
    lines += ["", "## Per case", "", "| ID | HTTP | Task | Jev | Source | SQL executed | SQL result | Policy version/clause | Thread | Review |", "|---|---:|---|---|---|---|---|---|---|---|"]
    for r in rows:
        policy = r["policy"]
        lines.append(f"| {r['case_id']} | {r['http_status']} | {r['task_completion']} | {r['jev_check']} | {r['source_check']} | {r['sql_executed']} | {r['sql_result']['status']} | {policy['version_match']}/{policy['clause_match']} | {r['thread_check']} | {r['status']} |")
    lines += ["", "## Review evidence by case", ""]
    for r in rows:
        lines.append(f"### {r['case_id']}")
        lines.append("")
        lines.append(f"- Failure category: {r['failure_category'] or 'none observed'}; trace: {r['trace_id']}; route: {r['route_reason']}.")
        lines.append(f"- SQL semantics: {json.dumps(r['sql_semantics'], ensure_ascii=False)}; result: {r['sql_result']['status']}.")
        lines.append(f"- Answer literal gaps: {json.dumps(r['answer_missing_literal_terms'], ensure_ascii=False)}; prohibited hits: {json.dumps(r['answer_prohibited_literal_terms'], ensure_ascii=False)}.")
        lines.append(f"- Policy evidence: {r['policy']['evidence_count']} items; version IDs: {json.dumps(r['policy']['version_ids'], ensure_ascii=False)}; source present: {r['policy']['source_present']}; document number present: {r['policy']['document_number_present']}.")
        lines.append("")
    lines += ["## Pending oracle and human review", ""]
    for cid, issue in PENDING.items():
        lines.append(f"- {cid}: {issue}")
    lines += ["", "Literal answer checks are evidence only. Policy presence and HTTP 200 do not prove task completion. See scored.jsonl for requests, SQL, rows, route and policy evidence in raw.jsonl and scored.jsonl. Human decisions belong in a separate JSONL file."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare(old: Path, new: Path, output: Path) -> None:
    old_meta = json.loads((old / "metadata.json").read_text(encoding="utf-8"))
    new_meta = json.loads((new / "metadata.json").read_text(encoding="utf-8"))
    if old_meta["standard_sha256"] != new_meta["standard_sha256"]:
        raise ValueError("comparison standard hashes differ")
    a, b = ({r["case_id"]: r for r in read_jsonl(p / "scored.jsonl")} for p in (old, new))
    if set(a) != set(b):
        raise ValueError("comparison case IDs differ")
    failures = lambda r: bool(r["failure_category"] or r["answer_prohibited_literal_terms"] or r["thread_check"] is False)
    result = {"old": str(old), "new": str(new), "new_failures": [], "fixed": [], "still_failing": [], "latency_change_ms": {}, "case_differences": {}}
    for cid in sorted(a):
        before, after = failures(a[cid]), failures(b[cid])
        if after and not before: result["new_failures"].append(cid)
        if before and not after: result["fixed"].append(cid)
        if before and after: result["still_failing"].append(cid)
        result["latency_change_ms"][cid] = (b[cid]["duration_ms"] or 0) - (a[cid]["duration_ms"] or 0)
        result["case_differences"][cid] = {"old_failure_category": a[cid]["failure_category"], "new_failure_category": b[cid]["failure_category"],
                                             "old_task_completion": a[cid]["task_completion"], "new_task_completion": b[cid]["task_completion"],
                                             "old_sql_result": a[cid]["sql_result"]["status"], "new_sql_result": b[cid]["sql_result"]["status"],
                                             "old_jev": a[cid]["jev_check"], "new_jev": b[cid]["jev_check"]}
    write_json(output, result)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("validate", "run", "score", "report", "compare", "all"))
    p.add_argument("--gold", type=Path, default=GOLD); p.add_argument("--raw", type=Path)
    p.add_argument("--output-root", type=Path, default=ROOT / "agent-service/evaluation/runs")
    p.add_argument("--output", type=Path); p.add_argument("--old", type=Path); p.add_argument("--new", type=Path)
    p.add_argument("--adjudications", type=Path)
    p.add_argument("--endpoint", default="http://127.0.0.1:8000/api/v1/chat")
    p.add_argument("--timeout", type=float, default=90)
    args = p.parse_args(argv)
    try:
        cases, gold_hash = load_gold(args.gold)
        if args.command == "validate":
            print(json.dumps({"cases": len(cases), "standard_sha256": gold_hash, "oracle_pending": PENDING}, ensure_ascii=False)); return 0
        if args.command == "compare":
            if not args.old or not args.new or not args.output: p.error("compare requires --old --new --output")
            compare(args.old, args.new, args.output); return 0
        if args.command == "report":
            if not args.output: p.error("report requires --output directory")
            report(args.output); return 0
        if args.command == "score" and not args.raw: p.error("score requires --raw")
        output = args.output or new_dir(args.output_root, gold_hash)
        if args.output:
            output.mkdir(parents=True, exist_ok=False)
        origin = str(args.raw) if args.command == "score" else args.endpoint
        write_json(output / "metadata.json", metadata(gold_hash, origin))
        if args.command in {"run", "all"}:
            run_cases(cases, args.endpoint, args.timeout, output)
        if args.command in {"score", "all"}:
            score_run(cases, args.raw or output / "raw.jsonl", output, args.adjudications)
            report(output)
        print(output.resolve()); return 0
    except (ValueError, OSError) as exc:
        print(f"evaluation error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
