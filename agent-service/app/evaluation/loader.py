from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.evaluation.models import Case, Turn


class DatasetError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cases(path: Path, groups: set[str] | None = None, ids: set[str] | None = None) -> list[Case]:
    if not path.is_file():
        raise DatasetError(f"评测集不存在：{path}")
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        try: raw = json.loads(line)
        except json.JSONDecodeError as exc: raise DatasetError(f"第 {number} 行不是有效 JSON：{exc}") from exc
        if raw.get("schema_version") != "2.0": raise DatasetError(f"{raw.get('id', number)} 缺少 schema_version=2.0")
        case_id, group = raw.get("id"), raw.get("group")
        if not case_id or not group: raise DatasetError(f"第 {number} 行缺少 id/group")
        if groups and group not in groups or ids and case_id not in ids: continue
        turns_raw = raw.get("turns") or []
        if not turns_raw: raise DatasetError(f"{case_id} 没有 turns")
        cases.append(Case(case_id, group, raw.get("snapshot_id", ""), raw.get("snapshot_sha256", ""), [Turn(t["question"], t.get("expected", {})) for t in turns_raw]))
    if not cases: raise DatasetError("筛选后没有评测用例")
    if len({case.id for case in cases}) != len(cases): raise DatasetError("评测集包含重复 case id")
    return cases
