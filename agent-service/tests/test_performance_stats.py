import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("performance_stats", Path(__file__).parents[1] / "performance" / "stats.py")
stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stats)


def test_percentiles_linear_interpolation():
    assert stats.percentile([10, 20, 30, 40], 50) == 25
    assert stats.percentile([10, 20, 30, 40], 95) == 38.5
    assert stats.percentile([], 95) is None


def test_warmup_excluded_and_small_sample():
    rows = [{"phase": "warmup", "duration_ms": 9999, "category": "http_error", "spans": {}},
            {"phase": "sample", "duration_ms": 10, "category": "success", "spans": {}}]
    summary = stats.summarize(rows, 5)
    assert summary["n"] == 1 and summary["p95_ms"] == 10
    assert summary["http_error_rate"] == 0
    assert summary["p95_note"] == "样本不足、仅供观察"


def test_error_classes_and_safe_degradation():
    case = {"expected_source": "mysql", "assertions": {"successful_queries": 1}}
    assert stats.classify(None, None, "timeout", case) == "timeout"
    assert stats.classify(429, {}, None, case) == "rate_or_quota"
    assert stats.classify(200, {"trace_id": "x", "answer": "稍后重试", "details":
        {"route_reason": "jev_unavailable", "data_source": "none", "successful_queries": 0}}, None, case) == "safe_degradation"
    assert stats.classify(200, {"trace_id": "x", "answer": "ok", "details":
        {"data_source": "policy", "successful_queries": 0}}, None, case) == "business_failure"


def test_fault_phase_split():
    rows = [{"phase": "baseline"}, {"phase": "timeout"}, {"phase": "timeout"}, {"phase": "recovery"}]
    assert {key: len(value) for key, value in stats.split_fault_phases(rows).items()} == {"baseline": 1, "timeout": 2, "recovery": 1}


def test_stub_choice_matches_current_jev_parser():
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1] / "performance"))
    from jev_stub import choice
    from app.agents.jev_router import INTENT_CRITERIA, SCOPE_CRITERIA, EXPLICIT_IMPORT_CRITERIA, parse_route_response
    answer = parse_route_response({"answers": {
        "intent": choice(list(INTENT_CRITERIA), "aggregation"),
        "scope": choice(list(SCOPE_CRITERIA), "current_listing"),
        "explicit_import": choice(list(EXPLICIT_IMPORT_CRITERIA), "no"),
        "depends_on_previous": {"type": "noul", "noul": 0},
        "multiple_tasks": {"type": "noul", "noul": 0}}})
    assert answer.requested_source == "mysql"
