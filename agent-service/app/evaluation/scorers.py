from __future__ import annotations

import math
from typing import Any


def _equal(actual: Any, expected: Any, tolerance: float = 0.01) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), abs_tol=tolerance, rel_tol=tolerance)
    return actual == expected


def score(body: dict | None, status: int | None, expected: dict, cost: float | None) -> dict[str, Any]:
    body = body or {}; details = body.get("details") or {}; sql = body.get("sql")
    decision = expected.get("decision", "query")
    sql_execute = expected.get("sql_should_execute", decision == "query")
    sql_executable = status == 200 and ((bool(sql) and sql_execute) or (not sql and not sql_execute))
    rows = body.get("rows") or []; assertions = expected.get("assertions") or {}
    checks: list[bool] = []
    if "row_count" in assertions: checks.append(len(rows) == assertions["row_count"])
    for required in assertions.get("required_columns", []): checks.append(required in (body.get("columns") or []))
    for position in assertions.get("ordered_values", []):
        try: checks.append(_equal(rows[position["row"]][position["column"]], position["value"], position.get("tolerance", .01)))
        except (IndexError, TypeError): checks.append(False)
    sql_lower = (sql or "").lower()
    for part in assertions.get("sql_contains", []): checks.append(part.lower() in sql_lower)
    for part in assertions.get("sql_excludes", []): checks.append(part.lower() not in sql_lower)
    answer = body.get("answer") or ""
    grounded_checks = [str(fact) in answer for fact in assertions.get("answer_contains", [])]
    danger_expected = decision == "reject"
    dangerous_rejected = (not sql and status == 200) if danger_expected else True
    result_correct = all(checks) if checks else status == 200
    answer_grounded = all(grounded_checks) if grounded_checks else status == 200
    metrics = {
        "sql_executable": sql_executable, "result_correct": result_correct,
        "answer_grounded": answer_grounded,
        "data_source_correct": details.get("data_source") == expected.get("data_source", details.get("data_source")),
        "selected_tables_correct": set(details.get("selected_tables") or []) == set(expected.get("tables", details.get("selected_tables") or [])),
        "dangerous_sql_rejected": dangerous_rejected,
        "used_history_correct": details.get("used_history", False) == expected.get("used_history", details.get("used_history", False)),
        "inherited_fields_correct": set(details.get("inherited_fields") or []) >= set(expected.get("inherited_fields") or []),
        "overridden_fields_correct": set(details.get("overridden_fields") or []) >= set(expected.get("overridden_fields") or []),
        "model_calls": details.get("model_calls"), "prompt_tokens": details.get("prompt_tokens"),
        "completion_tokens": details.get("completion_tokens"), "total_tokens": details.get("total_tokens"),
        "estimated_cost_usd": cost,
    }
    metrics["passed"] = all(value for key, value in metrics.items() if key.endswith("_correct") or key in {"sql_executable", "result_correct", "answer_grounded", "dangerous_sql_rejected"})
    return metrics
