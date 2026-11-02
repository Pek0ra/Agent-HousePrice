from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.evaluation.reviewed20 import (
    GOLD, decimal_match, history_turns, load_gold, result_check, score_case,
    sql_semantics,
)


@pytest.fixture
def cases() -> dict:
    rows, _ = load_gold()
    return {r["case_id"]: r for r in rows}


def raw(answer="ok", rows=None, sql=None, details=None, prior=None, status=200):
    return {"history_responses": prior or [], "final": {"status": status, "duration_ms": 12,
            "request": {"message": "test", "thread_id": "thread-1"},
            "response": {"answer": answer, "rows": rows, "sql": sql, "thread_id": "thread-1", "details": details or {}}}}


def test_http_200_does_not_complete_task(cases):
    forbidden = cases["BLD11"]["must_not_include_parsed"][0]
    r = score_case(cases["BLD11"], raw(answer=forbidden))
    assert r["http_success"] is True
    assert r["task_completion"] == "needs_human_review"
    assert r["sql_executed"] is False
    assert r["failure_category"] == "business_error_candidate"
    assert r["answer_prohibited_literal_terms"] == [forbidden]


def test_zero_result_distinct_from_no_row(cases):
    sql = cases["BLD15"]["sql_parsed"]
    assert result_check(sql, {"rows": [[0]]})["status"] == "match"
    assert result_check(sql, {"rows": []})["status"] == "mismatch"
    assert result_check(sql, {})["status"] == "missing_rows"


@pytest.mark.parametrize("observed,expected", [
    ({"rows": [[0]]}, "match"),
    ({"rows": []}, "mismatch"),
    ({}, "missing_rows"),
    ({"rows": "0"}, "invalid_rows"),
    ({"rows": [[1]]}, "mismatch"),
])
def test_zero_value_score_boundary(cases, observed, expected):
    assert result_check(cases["BLD15"]["sql_parsed"], observed)["status"] == expected


@pytest.mark.parametrize("status,error,category", [
    (200, None, "business_error_candidate"),
    (422, None, "http_failure"),
    (503, None, "dependency_failure"),
    (None, "TimeoutError", "timeout"),
])
def test_http_status_does_not_override_business_check(cases, status, error, category):
    observation = raw(answer="错误答案", details={"data_source": "hive"}, status=status)
    observation["final"]["error"] = error
    result = score_case(cases["BLD11"], observation)
    assert result["http_success"] is (status == 200)
    assert result["source_check"] == "mismatch"
    assert result["failure_category"] == category
    assert result["task_completion"] == "needs_human_review"


def test_normalized_mysql_oracle_is_exact_to_cents(cases):
    assert decimal_match(83067.23, 83067.230325)
    assert not decimal_match(83067.23, 83067.26)
    r = score_case(cases["BLD16"], raw(rows=[["海淀区", 83067.230325]], sql="SELECT AVG(unit_price) FROM v_agent_house_listing", details={"successful_queries": 1}))
    assert r["status"] == "needs_human_review"
    assert r["sql_result"]["status"] == "match"


def test_district_in_mismatch_and_zero_excluding_filter(cases):
    expected = cases["BLD13"]["sql_parsed"]["sql"]
    bad = "SELECT district FROM v_agent_district_summary WHERE city='北京市' AND district IN ('朝阳','海淀') AND listing_type='SALE'"
    assert sql_semantics(expected, bad)["checks"]["district_in"] is False
    expected = cases["BLD15"]["sql_parsed"]["sql"]
    assert sql_semantics(expected, "SELECT invalid_area_rows FROM v_agent_house_data_quality_summary WHERE invalid_area_rows > 0")["checks"]["zero_including_filter"] is False


def test_policy_evidence_is_not_task_completion(cases):
    c = cases["BLD08"]
    version = c["acceptable_version_ids_parsed"][0]
    r = score_case(c, raw(answer="政策存在", details={"data_source": "policy", "route_suggestion": {"intent": "policy"},
                                   "policy_evidence": [{"version_id": version, "source_url": "https://example.org", "document_number": "565号", "clause_path": c["acceptable_clause_paths_parsed"][0]}]}))
    assert r["policy"]["version_match"]
    assert r["policy"]["clause_match"]
    assert r["answer_missing_literal_terms"]
    assert r["status"] == "needs_human_review"
    assert r["task_completion"] == "needs_human_review"


def test_jev_unavailable_is_not_wrong_intent(cases):
    r = score_case(cases["BLD01"], raw(details={"data_source": "policy", "route_reason": "jev_unavailable"}))
    assert r["jev_check"] == "unavailable"
    assert r["failure_category"] == "dependency_failure"


def test_nearby_jev_intent_label_does_not_fail_correct_sql_result(cases):
    c = cases["BLD13"]
    r = score_case(c, raw(rows=[["朝阳区", 156], ["海淀区", 154]],
                          sql=c["sql_parsed"]["sql"], details={"successful_queries": 1,
                          "data_source": "mysql", "route_suggestion": {"intent": "comparison"}}))
    assert r["jev_check"] == "mismatch"
    assert r["sql_result"]["status"] == "match"
    assert r["failure_category"] is None


def test_multiturn_thread_association(cases):
    assert len(history_turns(cases["BLD18"]["history"])) == 1
    prior = [{"response": {"thread_id": "thread-1"}}]
    assert score_case(cases["BLD18"], raw(prior=prior))["thread_check"] is True
    prior = [{"response": {"thread_id": "different"}}]
    assert score_case(cases["BLD18"], raw(prior=prior))["thread_check"] is False


def test_validator_rejects_duplicate_id_and_bad_json(tmp_path: Path):
    with GOLD.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader); fields = reader.fieldnames
    path = tmp_path / "gold.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows[:-1] + [rows[0]])
    with pytest.raises(ValueError, match="duplicate"):
        load_gold(path)
    rows[0]["must_include"] = "not json"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match="invalid must_include"):
        load_gold(path)
