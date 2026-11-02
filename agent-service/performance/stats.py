"""Deterministic reporting of compact Locust records; never imputes missing spans."""
from __future__ import annotations

import math
from collections import defaultdict


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percent / 100
    low = math.floor(rank)
    return round(ordered[low] + (ordered[math.ceil(rank)] - ordered[low]) * (rank - low), 3)


def sampled(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("phase") == "sample"]


def classify(status: int | None, body: dict | None, error: str | None, case: dict) -> str:
    if error:
        return "timeout" if error == "timeout" else "network_failure"
    if status != 200:
        message = str(body).lower() if body else ""
        if status == 429 or any(term in message for term in ("quota", "rate_limit", "rate limit", "限流", "额度")):
            return "rate_or_quota"
        return "http_error"
    if not isinstance(body, dict) or not body.get("trace_id") or not isinstance(body.get("details"), dict):
        return "business_failure"
    details = body["details"]
    if details.get("route_reason") in {"jev_unavailable", "jev_unconfigured"}:
        return "safe_degradation" if details.get("data_source") == "none" and details.get("successful_queries", 0) == 0 and body.get("answer") else "business_failure"
    if case.get("expected_source") != details.get("data_source"):
        return "business_failure"
    checks = case.get("assertions", {})
    answer = str(body.get("answer") or "")
    if any(term not in answer for term in checks.get("answer_all", [])):
        return "business_failure"
    if checks.get("answer_any") and not any(term in answer for term in checks["answer_any"]):
        return "business_failure"
    if len(body.get("rows") or []) < checks.get("row_count_min", 0):
        return "business_failure"
    if len(details.get("policy_evidence") or []) < checks.get("evidence_min", 0):
        return "business_failure"
    if details.get("successful_queries") != checks.get("successful_queries", details.get("successful_queries")):
        return "business_failure"
    return "success"


def summarize(records: list[dict], sample_seconds: float, min_p95_samples: int = 100) -> dict:
    rows = sampled(records)
    latencies = [r["duration_ms"] for r in rows if isinstance(r.get("duration_ms"), (int, float))]
    count = len(rows)
    classes = defaultdict(int)
    for row in rows:
        classes[row["category"]] += 1
    spans = {}
    fields = ("jev_duration_ms", "route_duration_ms", "llm_duration_ms", "qdrant_duration_ms",
              "rerank_duration_ms", "mysql_duration_ms", "hive_duration_ms", "policy_tool_duration_ms", "duration_ms")
    for field in fields:
        values = [r["spans"][field] for r in rows if isinstance(r.get("spans", {}).get(field), (int, float))]
        spans[field] = {"n": len(values), "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95)}
    return {"n": count, "peak_inflight": max((r.get("inflight", 0) for r in records), default=0),
            "p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95),
            "max_ms": max(latencies, default=None), "throughput_rps": round(count / sample_seconds, 3) if sample_seconds > 0 else None,
            "http_error_rate": classes["http_error"] / count if count else None,
            "network_failure_rate": classes["network_failure"] / count if count else None,
            "timeout_rate": (classes["timeout"] + sum(r.get("error_category") == "jev_timeout" for r in rows)) / count if count else None,
            "client_timeout_rate": classes["timeout"] / count if count else None,
            "business_failure_rate": classes["business_failure"] / count if count else None,
            "rate_or_quota": classes["rate_or_quota"] + sum(r.get("error_category") == "jev_rate_or_quota" for r in rows),
            "classes": dict(classes), "spans": spans,
            "p95_note": "样本不足、仅供观察" if count < min_p95_samples else ""}


def split_fault_phases(records: list[dict]) -> dict[str, list[dict]]:
    phases = defaultdict(list)
    for row in records:
        phases[row["phase"]].append(row)
    return dict(phases)
