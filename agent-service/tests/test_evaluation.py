import json
from pathlib import Path

import pytest

from app.evaluation.baseline import load_baseline
from app.evaluation.loader import DatasetError, load_cases
from app.evaluation.pricing import estimate_cost
from app.evaluation.scorers import score


def test_loader_reads_multiturn_v2_dataset(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"schema_version": "2.0", "id": "CTX", "group": "连续对话", "snapshot_id": "s", "snapshot_sha256": "a", "turns": [{"question": "第一问", "expected": {}}, {"question": "第二问", "expected": {"used_history": True}}]}, ensure_ascii=False), encoding="utf-8")
    cases = load_cases(path)
    assert len(cases) == 1 and len(cases[0].turns) == 2


def test_loader_rejects_old_schema(tmp_path: Path) -> None:
    path = tmp_path / "old.jsonl"; path.write_text('{"id":"old"}', encoding="utf-8")
    with pytest.raises(DatasetError): load_cases(path)


def test_structured_scorer_checks_rows_source_tables_and_history() -> None:
    expected = {"decision": "query", "sql_should_execute": True, "data_source": "mysql", "tables": ["v"], "used_history": True, "inherited_fields": ["metric"], "assertions": {"row_count": 1, "ordered_values": [{"row": 0, "column": 0, "value": 12.5}]}}
    body = {"sql": "SELECT AVG(x) FROM v", "rows": [[12.5]], "columns": ["avg"], "answer": "12.5", "details": {"data_source": "mysql", "selected_tables": ["v"], "used_history": True, "inherited_fields": ["metric"]}}
    assert score(body, 200, expected, None)["passed"] is True


def test_pricing_returns_null_when_usage_or_price_is_missing() -> None:
    assert estimate_cost({}, {"input_usd_per_million": 1, "output_usd_per_million": 2}) is None
    assert estimate_cost({"prompt_tokens": 10, "completion_tokens": 5}, None) is None


def test_baseline_is_keyed_by_case_and_turn(tmp_path: Path) -> None:
    path = tmp_path / "scored.jsonl"; path.write_text('{"case_id":"A","turn_index":2,"passed":true}\n', encoding="utf-8")
    assert load_baseline(path) == {("A", 2): True}
