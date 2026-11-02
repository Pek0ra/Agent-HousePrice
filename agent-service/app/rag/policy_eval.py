"""Small manually reviewed retrieval set; no model fine tuning is performed."""
from __future__ import annotations

import json
from pathlib import Path

from app.rag.policy_index import COLLECTION
from app.rag.policy_store import PolicyStore


def main():
    cases = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / "tests/data/policy_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    store = PolicyStore()
    results = {"dense_baseline": [], "hybrid_reranked": []}
    for case in cases:
        query = case["question"]
        vector = store._vector([query])[0]
        dense = store.client.query_points(COLLECTION, query=vector, limit=20, with_payload=True).points
        baseline = [p.payload for p in dense if p.payload["review_status"] == "machine_checked" and
                    (not case.get("as_of") or p.payload["publication_date"] <= case["as_of"] and
                     (not p.payload["effective_from"] or p.payload["effective_from"] <= case["as_of"]))][:5]
        optimized = store.search(query, as_of=case.get("as_of"), limit=5)["evidence"]
        for name, evidence in (("dense_baseline", baseline), ("hybrid_reranked", optimized)):
            gold = case["gold_version"]
            hits = [item["version_id"] == gold and case["gold_text"] in item["content"] for item in evidence] if gold else []
            results[name].append({"question": query, "kind": case["kind"], "hit_at_1": bool(hits[:1] and hits[0]),
                                  "hit_at_5": any(hits), "refused": not evidence, "gold": gold,
                                  "future_version_error": any(case.get("as_of") and (item["publication_date"] > case["as_of"] or
                                      item["effective_from"] and item["effective_from"] > case["as_of"]) for item in evidence),
                                  "top": evidence[0]["version_id"] if evidence else None})
    report = {}
    for name, rows in results.items():
        answerable = [r for r in rows if r["gold"]]
        no_answer = [r for r in rows if not r["gold"]]
        report[name] = {"recall_at_1": sum(r["hit_at_1"] for r in answerable) / len(answerable),
                        "recall_at_5": sum(r["hit_at_5"] for r in answerable) / len(answerable),
                        "citation_correct_at_1": sum(r["hit_at_1"] for r in answerable) / len(answerable),
                        "no_answer_refusal": sum(r["refused"] for r in no_answer) / len(no_answer),
                        "future_version_errors": sum(r["future_version_error"] for r in rows),
                        "failures": [r for r in rows if (r["gold"] and not r["hit_at_5"]) or (not r["gold"] and not r["refused"])]}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
