from __future__ import annotations

import json
from pathlib import Path


def load_pricing(path: Path | None) -> dict | None:
    if path is None: return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw


def estimate_cost(details: dict, pricing: dict | None) -> float | None:
    if not pricing or details.get("prompt_tokens") is None or details.get("completion_tokens") is None: return None
    return round((details["prompt_tokens"] * pricing["input_usd_per_million"] + details["completion_tokens"] * pricing["output_usd_per_million"]) / 1_000_000, 8)
