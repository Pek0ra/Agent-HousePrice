"""Guard the manually labeled development/holdout evaluation corpus."""

from collections import Counter
import json
from pathlib import Path


def test_jev_routing_corpus_is_balanced_and_disjoint() -> None:
    path = Path(__file__).parent / "data" / "jev_routing_160.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 160
    assert len({row["id"] for row in rows}) == len({row["question"] for row in rows}) == 160
    assert Counter(row["split"] for row in rows) == {"dev": 80, "test": 80}
    assert set(row["id"] for row in rows if row["split"] == "dev").isdisjoint(
        row["id"] for row in rows if row["split"] == "test"
    )
    for split in ("dev", "test"):
        subset = [row for row in rows if row["split"] == split]
        assert set(Counter(row["intent"] for row in subset).values()) == {10}
        assert Counter(row["source"] for row in subset) == {"mysql": 40, "hive": 20, "none": 20}
    assert all(row["hive_available"] is True and row["previous"] is None for row in rows)
