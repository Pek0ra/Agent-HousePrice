from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    question: str
    expected: dict[str, Any]


@dataclass
class Case:
    id: str
    group: str
    snapshot_id: str
    snapshot_sha256: str
    turns: list[Turn]


@dataclass
class Actual:
    case_id: str
    group: str
    turn_index: int
    question: str
    expected: dict[str, Any]
    http_status: int | None
    elapsed_ms: float
    body: dict[str, Any] | None
    raw_body: str
    error: str | None = None
    regression: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
