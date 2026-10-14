import json
from collections import Counter
from pathlib import Path

import pytest

from app.agents.jev_router import (
    INTENT_CRITERIA, SCOPE_CRITERIA, EXPLICIT_IMPORT_CRITERIA, JevRoutingClient, JevUnavailable,
    RouteSuggestion, parse_route_response,
)
from app.agents.routing_policy import decide_route, review_reason
from app.agents.conversation import validate_question_slots
from app.schemas.chat import QuestionSlots


def scope_for(intent, source):
    if source == "none": return "none"
    if source == "mysql": return "current_listing"
    return "import_quality" if intent == "data_quality" else "active_import"


def answer_payload(intent="aggregation", source="mysql", confidence=0.95,
                   depends=0.01, multiple=0.01):
    def choice(selected, options):
        rest = (1 - 0.98) / (len(options) - 1)
        return {"type": "choice", "choice": selected, "confidence": confidence,
                "probabilities": {key: 0.98 if key == selected else rest for key in options}}
    return {"model": "jev-1.13.0", "answers": {
        "intent": choice(intent, INTENT_CRITERIA),
        "scope": choice(scope_for(intent, source), SCOPE_CRITERIA),
        "explicit_import": choice("yes" if source == "hive" and intent != "data_quality" else "no", EXPLICIT_IMPORT_CRITERIA),
        "depends_on_previous": {"type": "noul", "noul": depends},
        "multiple_tasks": {"type": "noul", "noul": multiple},
    }, "usage": {"input_tokens": 20, "output_tokens": 12}}


@pytest.mark.parametrize("intent,source,table", [
    ("listing_search", "mysql", "v_agent_house_listing"),
    ("aggregation", "mysql", "v_agent_house_listing"),
    ("ranking", "mysql", "v_agent_district_summary"),
    ("comparison", "mysql", "v_agent_district_summary"),
    ("trend", "mysql", "v_agent_monthly_price_trend"),
    ("trend", "hive", "v_agent_house_info_analysis"),
    ("data_quality", "hive", "v_agent_house_data_quality_summary"),
])
def test_all_query_intents_have_fixed_views(intent, source, table):
    suggestion = parse_route_response(answer_payload(intent, source))
    assert suggestion.intent == intent and suggestion.requested_source == source
    assert review_reason(suggestion, threshold=0.7, noul_margin=0.15) is None
    decision = decide_route(intent, suggestion.scope, hive_available=True, multiple_tasks=False,
                            has_history=False, depends_on_previous=False)
    assert decision.tables == (table,) and decision.source == source


def test_non_query_and_hive_capability_policy():
    for intent in ("unsupported", "clarify"):
        decision = decide_route(intent, "none", hive_available=True, multiple_tasks=False,
                                has_history=False, depends_on_previous=False)
        assert decision.source == "none" and not decision.tables
    quality = decide_route("data_quality", "import_quality", hive_available=False, multiple_tasks=False,
                           has_history=False, depends_on_previous=False)
    assert quality.reason == "hive_required" and quality.needs_clarification
    trend = decide_route("trend", "active_import", hive_available=False, multiple_tasks=False,
                         has_history=False, depends_on_previous=False)
    assert trend.source == "none" and trend.reason == "hive_unavailable"
    historical_listing = decide_route("listing_search", "active_import", hive_available=False,
        multiple_tasks=False, has_history=False, depends_on_previous=False)
    assert historical_listing.source == "none" and historical_listing.needs_clarification


def test_dependency_multiple_tasks_and_conflict():
    assert decide_route("aggregation", "current_listing", hive_available=False, multiple_tasks=True,
                        has_history=False, depends_on_previous=False).reason == "multiple_tasks"
    assert decide_route("aggregation", "current_listing", hive_available=False, multiple_tasks=False,
                        has_history=False, depends_on_previous=True).reason == "missing_history"
    assert review_reason(parse_route_response(answer_payload("data_quality", "mysql")), threshold=0.7, noul_margin=0.15) == "intent_scope_conflict"
    assert review_reason(parse_route_response(answer_payload(confidence=0.4)), threshold=0.7, noul_margin=0.15) == "low_confidence"
    assert review_reason(parse_route_response(answer_payload(depends=0.5)), threshold=0.7, noul_margin=0.15) == "uncertain_boolean"
    assert review_reason(parse_route_response(answer_payload(depends=0.75)), threshold=0.7, noul_margin=0.15) == "positive_boolean_review"


def test_explicit_hive_requirement_cannot_be_routed_to_mysql():
    suggestion = parse_route_response(answer_payload("trend", "mysql"))
    suggestion.explicit_import = True
    suggestion.explicit_import_probability = 0.99
    assert review_reason(suggestion, threshold=0.7, noul_margin=0.15) == "explicit_import_conflict"
    decision = decide_route("trend", "current_listing", hive_available=True,
        multiple_tasks=False, has_history=False, depends_on_previous=False,
        explicit_import=True)
    assert decision.source == "none" and decision.needs_clarification


@pytest.mark.parametrize("change", [
    lambda p: p["answers"].pop("scope"),
    lambda p: p["answers"]["intent"].update(choice="invented"),
    lambda p: p["answers"]["scope"].update(probabilities={"current_listing": 1.0}),
    lambda p: p["answers"]["multiple_tasks"].update(noul=1.5),
])
def test_invalid_jev_response_is_rejected(change):
    payload = answer_payload()
    change(payload)
    with pytest.raises(JevUnavailable):
        parse_route_response(payload)


def test_http_client_sends_one_typed_request_and_no_sql(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, *_): return json.dumps(answer_payload()).encode()
    def fake_open(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()
    monkeypatch.setattr("app.agents.jev_router.urlopen", fake_open)
    client = JevRoutingClient("private-test-key", timeout_seconds=2)
    result = client.classify("上海房价多少？", {"cities": ["北京市"], "previous_answer_summary": "sensitive"}, False)
    body = json.loads(captured["request"].data)
    assert result.intent == "aggregation"
    assert body["model"] == "jev-latest"
    assert set(body["questions"]) == {"intent", "scope", "explicit_import", "depends_on_previous", "multiple_tasks"}
    assert "previous_answer_summary" not in str(body)
    assert "sql" not in body["state"] and "sql" not in body["questions"]
    assert captured["timeout"] == 2


def test_transport_timeout_is_redacted(monkeypatch):
    def fail(*_args, **_kwargs): raise TimeoutError("private-test-key")
    monkeypatch.setattr("app.agents.jev_router.urlopen", fail)
    with pytest.raises(JevUnavailable, match="Jev routing unavailable") as exc:
        JevRoutingClient("private-test-key").classify("房价？", None, False)
    assert "private-test-key" not in str(exc.value)


def test_annotated_dataset_route_policy_regression():
    path = Path(__file__).parents[2] / "agent-evaluation-dataset.jsonl"
    cases = [turn for line in path.read_text(encoding="utf-8").splitlines()
             for turn in json.loads(line)["turns"]]
    assert len(cases) == 97
    checked = 0
    source_confusion = Counter()
    table_matches = 0
    for turn in cases:
        expected = turn["expected"]
        decision = expected["decision"]
        if decision == "query":
            table = expected["tables"][0]
            intent = {
                "v_agent_house_listing": "listing_search",
                "v_agent_district_summary": "comparison",
                "v_agent_monthly_price_trend": "trend",
                "v_agent_house_info_analysis": "trend",
                "v_agent_house_data_quality_summary": "data_quality",
            }[table]
            route = decide_route(intent, scope_for(intent, expected["data_source"]), hive_available=True,
                multiple_tasks=False, has_history=True, depends_on_previous=False)
            assert route.source == expected["data_source"] and list(route.tables) == expected["tables"]
            checked += 1
            table_matches += 1
        elif decision in {"reject", "unsupported"}:
            route = decide_route("unsupported", "none", hive_available=True,
                multiple_tasks=False, has_history=False, depends_on_previous=False)
            assert route.source == expected["data_source"] and list(route.tables) == expected["tables"]
            checked += 1
            table_matches += 1
        else:
            assert decision == "clarify"
            route = decide_route("clarify", "none", hive_available=True,
                multiple_tasks=False, has_history=False, depends_on_previous=False)
            assert route.needs_clarification
            source_confusion[(expected["data_source"], route.source)] += 1
            table_matches += list(route.tables) == expected["tables"]
    assert checked == 86
    assert source_confusion == {("mysql", "none"): 9, ("hive", "none"): 2}
    assert table_matches == 95


def test_model_slots_are_normalized_and_range_checked():
    slots = validate_question_slots(QuestionSlots(cities=["上海"], districts=["浦东"],
        metric="monthly_rent", bedroom_count=3, start_month="2026-01"))
    assert slots["cities"] == ["上海市"] and slots["districts"] == ["浦东新区"]
    for invalid in (QuestionSlots(metric="made_up"), QuestionSlots(ranking_limit=101),
                    QuestionSlots(start_month="2026-13"), QuestionSlots(cities=["a' OR 1=1"])):
        with pytest.raises(ValueError):
            validate_question_slots(invalid)


_MANUAL_GOLD = [json.loads(line) for line in
    (Path(__file__).parent / "data" / "jev_intent_gold.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("sample", _MANUAL_GOLD, ids=lambda sample: sample["paraphrase_group"])
def test_manually_annotated_chinese_paraphrase_policy_with_mock_jev(sample):
    # Gold labels feed a mock response. This verifies policy coverage, not Jev accuracy.
    suggestion = parse_route_response(answer_payload(sample["intent"], sample["source"]))
    assert review_reason(suggestion, threshold=0.7, noul_margin=0.15) is None
    decision = decide_route(suggestion.intent, suggestion.scope, hive_available=True,
        multiple_tasks=False, has_history=False, depends_on_previous=False)
    assert decision.intent == sample["intent"]
    assert decision.source == sample["source"]
