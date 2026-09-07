from __future__ import annotations

import json
from pathlib import Path


def load_baseline(path: Path | None) -> dict[tuple[str, int], bool]:
    if path is None: return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line); result[(item["case_id"], item["turn_index"])] = bool(item.get("passed"))
    return result
