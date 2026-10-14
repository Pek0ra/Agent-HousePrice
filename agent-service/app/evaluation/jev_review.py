"""Evaluate structured reviews from saved Jev reports without database calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from langchain_openai import ChatOpenAI

from app.agents.jev_router import INTENT_CRITERIA, SCOPE_CRITERIA
from app.agents.route_review import route_review_messages
from app.agents.routing_policy import decide_route
from app.config import settings
from app.schemas.chat import RouteReview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1, help="Maximum billable review calls")
    args = parser.parse_args()
    if args.limit < 1 or not settings.openai_api_key:
        parser.error("A positive limit and configured OPENAI_API_KEY are required")
    reports = [json.loads(path.read_text(encoding="utf-8-sig")) for path in args.reports]
    if any(not report.get("complete") for report in reports):
        parser.error("Input Jev reports must be complete")
    cases = [case for report in reports for case in report["cases"]]
    review_count = sum(case["review_reason"] is not None for case in cases)
    if args.limit < review_count:
        parser.error(f"This evaluation requires --limit {review_count} to cover all review cases")
    model = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key,
        base_url=settings.openai_base_url, temperature=0, timeout=30, max_retries=1)
    reviewer = model.with_structured_output(RouteReview, method="json_schema", include_raw=True)
    results = []
    for case in cases:
        reviewed = None
        error = None
        elapsed_ms = 0
        if case["review_reason"] is not None:
            proposed = {key: case[value] for key, value in (
                ("intent", "predicted_intent"), ("scope", "predicted_scope"),
                ("intent_confidence", "intent_confidence"), ("scope_confidence", "scope_confidence"),
                ("intent_probability", "intent_probability"), ("scope_probability", "scope_probability"),
                ("depends_probability", "depends_probability"), ("multiple_probability", "multiple_probability"),
                ("explicit_import", "explicit_import"),
                ("explicit_import_probability", "explicit_import_probability"),
            )}
            started = time.perf_counter()
            try:
                response = reviewer.invoke(route_review_messages(case["question"], None, proposed,
                    case["review_reason"], True))
                reviewed = response.get("parsed") if isinstance(response, dict) else response
                if (reviewed is None or reviewed.intent not in INTENT_CRITERIA or
                        reviewed.scope not in SCOPE_CRITERIA):
                    raise ValueError("Invalid structured review")
            except Exception:
                error = "review_unavailable"
            elapsed_ms = round((time.perf_counter() - started) * 1000)
        if error:
            final_intent, final_scope = "clarify", "none"
            final_source, reason = "none", error
        else:
            final_intent = reviewed.intent if reviewed is not None else case["predicted_intent"]
            final_scope = reviewed.scope if reviewed is not None else case["predicted_scope"]
            depends = reviewed.depends_on_previous if reviewed is not None else case["depends_probability"] >= 0.5
            multiple = reviewed.multiple_tasks if reviewed is not None else case["multiple_probability"] >= 0.5
            decision = decide_route(final_intent, final_scope, hive_available=True,
                multiple_tasks=multiple, has_history=False, depends_on_previous=depends,
                explicit_import=case["explicit_import"])
            final_intent, final_source, reason = decision.intent, decision.source, decision.reason
        results.append({
            "id": case["id"], "expected_intent": case["expected_intent"],
            "expected_source": case["expected_source"],
            "jev_intent": case["predicted_intent"], "jev_scope": case["predicted_scope"],
            "review_reason": case["review_reason"],
            "reviewed": reviewed.model_dump() if reviewed is not None else None,
            "review_error": error, "review_latency_ms": elapsed_ms,
            "final_intent": final_intent, "final_source": final_source,
            "final_reason": reason,
        })
    summary = {
        "evaluated": len(results), "review_calls": review_count,
        "review_failures": sum(item["review_error"] is not None for item in results),
        "final_source_correct": sum(item["final_source"] == item["expected_source"] for item in results),
        "final_route_correct": sum(item["final_source"] == item["expected_source"] and
                                   item["final_intent"] == item["expected_intent"] for item in results),
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
