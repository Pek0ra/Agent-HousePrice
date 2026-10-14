"""Opt-in, small live Jev routing probe over manually labeled Chinese questions.

Run: python -m app.evaluation.jev_routing --limit 1
Increase --limit deliberately; each item makes one billable request.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import time

from app.agents.jev_router import JevRoutingClient, JevUnavailable
from app.agents.routing_policy import decide_route, review_reason
from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in live Jev routing probe")
    parser.add_argument("--limit", type=int, default=1, help="Maximum billable calls (default: 1)")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many selected rows when resuming a partial probe")
    parser.add_argument("--timeout-seconds", type=float, default=None, help="Per-call timeout override for this probe")
    parser.add_argument("--dataset", choices=("legacy", "160"), default="legacy")
    parser.add_argument("--split", choices=("all", "dev", "test"), default="all")
    parser.add_argument("--id", action="append", dest="ids", help="Evaluate only this case ID; repeat to select more")
    args = parser.parse_args()
    if not settings.typesafe_api_key:
        print("No TYPESAFE_API_KEY: live Jev Chinese accuracy unverified.")
        return
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.offset < 0 or (args.timeout_seconds is not None and args.timeout_seconds <= 0):
        parser.error("Invalid offset or timeout")
    name = "jev_routing_160.jsonl" if args.dataset == "160" else "jev_intent_gold.jsonl"
    path = Path(__file__).parents[2] / "tests" / "data" / name
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if args.split != "all":
        samples = [sample for sample in samples if sample.get("split") == args.split]
    if args.ids:
        selected = set(args.ids)
        samples = [sample for sample in samples if sample.get("id") in selected]
        unknown = selected - {sample["id"] for sample in samples}
        if unknown:
            parser.error(f"Unknown case IDs for selected dataset/split: {', '.join(sorted(unknown))}")
    if not samples or args.offset >= len(samples):
        parser.error("No samples match the requested dataset and split")
    client = JevRoutingClient(settings.typesafe_api_key, model=settings.jev_model,
                              timeout_seconds=args.timeout_seconds or settings.jev_timeout_seconds)
    totals = Counter()
    correct = Counter()
    confusion = defaultdict(Counter)
    source_confusion = defaultdict(Counter)
    latency = []
    source_correct = 0
    scope_correct = 0
    final_source_correct = 0
    final_route_correct = 0
    reviewed = 0
    cases = []
    call_errors = 0
    selected_samples = samples[args.offset:args.offset + args.limit]
    for sample in selected_samples:
        started = time.perf_counter()
        try:
            route = client.classify(sample["question"], sample.get("previous"), sample.get("hive_available", True))
        except JevUnavailable:
            call_errors += 1
            break
        latency.append((time.perf_counter() - started) * 1000)
        expected = sample["intent"]
        totals[expected] += 1
        correct[expected] += route.intent == expected
        predicted_source = route.requested_source
        expected_scope = ("import_quality" if expected == "data_quality" else
                          "active_import" if sample["source"] == "hive" else
                          "current_listing" if sample["source"] == "mysql" else "none")
        source_correct += predicted_source == sample["source"]
        scope_correct += route.scope == expected_scope
        source_confusion[sample["source"]][predicted_source] += 1
        confusion[expected][route.intent] += 1
        reason = review_reason(route, threshold=settings.jev_confidence_threshold,
                               noul_margin=settings.jev_noul_margin)
        reviewed += reason is not None
        decision = decide_route(route.intent, route.scope,
            hive_available=sample.get("hive_available", True),
            multiple_tasks=route.multiple_probability >= 0.5,
            has_history=bool((sample.get("previous") or {}).get("previous_question")),
            depends_on_previous=route.depends_probability >= 0.5,
            explicit_import=route.explicit_import)
        final_source_correct += decision.source == sample["source"]
        final_route_correct += decision.source == sample["source"] and decision.intent == expected
        cases.append({
            "id": sample.get("id"), "question": sample["question"],
            "expected_intent": expected, "predicted_intent": route.intent,
            "expected_scope": expected_scope, "predicted_scope": route.scope,
            "expected_source": sample["source"], "predicted_source": predicted_source,
            "scope_probability": route.scope_probability,
            "scope_confidence": route.scope_confidence,
            "intent_probability": route.intent_probability,
            "intent_confidence": route.intent_confidence,
            "depends_probability": route.depends_probability,
            "multiple_probability": route.multiple_probability,
            "explicit_import": route.explicit_import,
            "explicit_import_probability": route.explicit_import_probability,
            "review_reason": reason, "policy_source_without_review": decision.source,
            "policy_reason_without_review": decision.reason,
            "latency_ms": round(latency[-1], 1),
        })
    print(json.dumps({
        "evaluated": len(latency), "selected": len(selected_samples),
        "complete": len(latency) == len(selected_samples), "call_errors": call_errors,
        "offset": args.offset, "total_gold": len(samples),
        "intent_accuracy_by_class": {name: {"correct": correct[name], "total": count,
            "accuracy": correct[name] / count} for name, count in totals.items()},
        "source_accuracy": source_correct / len(latency) if latency else None,
        "scope_accuracy": scope_correct / len(latency) if latency else None,
        "source_confusion": {name: dict(values) for name, values in source_confusion.items()},
        "policy_source_accuracy_without_review": final_source_correct / len(latency) if latency else None,
        "policy_route_accuracy_without_review": final_route_correct / len(latency) if latency else None,
        "review_triggered": reviewed,
        "confusion": {name: dict(values) for name, values in confusion.items()},
        "latency_ms_median": statistics.median(latency) if latency else None,
        "latency_ms_max": max(latency) if latency else None,
        "latency_ms_p95": sorted(latency)[max(0, int((len(latency) - 1) * 0.95))] if latency else None,
        "cases": cases,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
