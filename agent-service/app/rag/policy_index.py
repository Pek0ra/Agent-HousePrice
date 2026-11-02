"""Versioned Beijing policy corpus and a separate Qdrant index."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data/RAG/normalized"
MODEL = "BAAI/bge-small-zh-v1.5"
MODEL_VERSION = f"fastembed-{version('fastembed')}-bge-small-zh-v1.5"
COLLECTION = "beijing_policy_v1"
HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
GARBAGE = re.compile(r"/G\d+|\ufffd")
EXACT = re.compile(r"(?:[A-Za-z]*〔?\d{4}〕?\d+号|\d{4}[-年./]\d{1,2}(?:[-月./]\d{1,2})?|\d+(?:\.\d+)?\s*(?:%|％|平方米|平米|万元|元|年|套))")


@dataclass
class PolicyFile:
    metadata: dict[str, Any]
    body: str
    path: Path
    status: str
    effective_from: str | None
    effective_basis: str
    effective_check: str
    enactment_text: str
    precedence_text: str


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_notices(body: str) -> tuple[str, str]:
    notices = []
    for line in body.splitlines():
        value = HEADING.sub(lambda match: match.group(2), line).strip()
        if re.match(r"(?:[一二三四五六七八九十]+、)?本(?:通知|公告)自.+(?:施行|执行)", value):
            notices.append(value)
    enactment = " ".join(notices)
    precedence = " ".join(sentence.strip() + "。" for notice in notices
        for sentence in re.findall(r"原有政策[^。]*不一致[^。]*", notice))
    return enactment, precedence


def load_corpus(directory: Path = CORPUS) -> tuple[list[PolicyFile], list[dict[str, Any]]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    source_catalog_path = Path(__file__).with_name("policy_sources.json")
    source_catalog = json.loads(source_catalog_path.read_text(encoding="utf-8")) if source_catalog_path.exists() else {}
    entries = manifest["documents"]
    names = [Path(item["markdown_path"]).name for item in entries]
    if len(names) != len(set(names)) or set(names) != {p.name for p in directory.glob("*.md")}:
        raise ValueError("manifest and Markdown files must correspond one to one")
    files, report = [], []
    for entry in entries:
        path = directory / Path(entry["markdown_path"]).name
        try:
            raw = path.read_text(encoding="utf-8")
            match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
            if not match:
                raise ValueError("missing YAML front matter")
            meta = yaml.safe_load(match[1])
            body = match[2].strip()
            if not isinstance(meta, dict) or not body or GARBAGE.search(body):
                raise ValueError("empty body or broken glyph")
            if meta.get("original_path") != entry["original_path"] or meta.get("original_sha256") != entry["original_sha256"]:
                raise ValueError("original provenance mismatch")
            if meta.get("verification_status") != entry["status"]:
                raise ValueError("review status mismatch")
            source = source_catalog.get(Path(entry["original_path"]).name)
            if source and (source.get("source_url") != meta.get("source_url") or
                           source.get("document_number") != meta.get("document_number") or
                           source.get("id") != meta.get("version_id")):
                raise ValueError("document number or source URL differs from source catalog")
            if not re.fullmatch(r"https://[^\s]+", str(meta.get("source_url", ""))):
                raise ValueError("invalid official source URL")
            if not meta.get("version_id") or not meta.get("title"):
                raise ValueError("missing identity")
            number = meta.get("document_number")
            if number and number not in body:
                raise ValueError("document number absent from body")
            if number and "beijing.gov.cn" in meta["source_url"] and "housing" in meta["version_id"]:
                year = re.search(r"〔(\d{4})〕(\d+)号", number)
                if not year or year.group(1) not in meta["version_id"] or year.group(2) not in meta["version_id"]:
                    raise ValueError("document number and version mismatch")
            pub = meta.get("publication_date")
            if isinstance(pub, date):
                pub = pub.isoformat()
            if not pub:
                raise ValueError("missing publication date")
            date.fromisoformat(pub)
            effective = meta.get("effective_date")
            if isinstance(effective, date):
                effective = effective.isoformat()
            enactment_text, precedence_text = _file_notices(body)
            basis, check = enactment_text or "front matter effective_date", "machine_checked"
            if effective:
                date.fromisoformat(effective)
                target_date = date.fromisoformat(effective)
                written = f"{target_date.year}年{target_date.month}月{target_date.day}日"
                if written not in body and "自印发次日起施行" not in body:
                    raise ValueError("effective date has no basis in policy body")
            else:
                phrase = re.search(r"本通知自印发次日起施行[^。]*。", body)
                if phrase:
                    effective = (date.fromisoformat(pub) + timedelta(days=1)).isoformat()
                    basis, check = phrase.group(), "derived_unverified"
                else:
                    basis, check = "生效日期未明确", "unknown"
            meta["publication_date"] = pub
            meta["effective_date"] = effective
            files.append(PolicyFile(meta, body, path, entry["status"], effective, basis, check,
                                    enactment_text, precedence_text))
            report.append({"file": path.name, "status": entry["status"], "effective_from": effective,
                           "effective_check": check, "chunks": 0, "excluded_reason": None})
        except Exception as exc:
            report.append({"file": path.name, "status": "excluded", "effective_from": None,
                           "effective_check": "unknown", "chunks": 0, "excluded_reason": str(exc)})
    return files, report


def _topic(path: str, text: str) -> str:
    joined = path + text
    if "公积金" in joined or "贷款" in joined:
        return "provident_fund"
    if "契税" in joined or "增值税" in joined or "退税" in joined or "个人所得税政策" in joined:
        return "tax"
    if "限购" in joined or "购买" in joined:
        return "purchase_restriction"
    return "housing"


def _explicit_end_date(content: str) -> tuple[str | None, str | None]:
    """Extract only a literal policy range; do not infer a document-wide expiry."""
    match = re.search(
        r"自(20\d{2})年(\d{1,2})月(\d{1,2})日至(20\d{2})年(\d{1,2})月(\d{1,2})日",
        content,
    )
    if not match:
        return None, None
    try:
        start = date(*map(int, match.groups()[:3]))
        end = date(*map(int, match.groups()[3:]))
    except ValueError:
        return None, None
    return (end.isoformat(), match.group()) if start <= end else (None, None)


def _subject_scope(text: str) -> tuple[str | None, dict[str, str]]:
    scope = {"city": "北京市"}
    has_year_requirement = bool(re.search(r"连续缴纳满\d+年|\d+年及以上", text))
    if "五环内" in text and "非本市户籍" in text and has_year_requirement:
        scope.update(household="nonlocal", ring="inner")
        return "nonlocal_purchase_social_years", scope
    if "五环外" in text and "非本市户籍" in text and has_year_requirement:
        scope.update(household="nonlocal", ring="outer")
        return "nonlocal_purchase_social_years", scope
    if "公积金" in text and "二套" in text and "最低首付款比例" in text:
        scope.update(loan="provident_fund", home="second")
        return "provident_second_down_payment", scope
    if "公积金" in text and "二套" in text and "最高贷款额度" in text:
        scope.update(loan="provident_fund", home="second", contributors="any")
        return "provident_second_loan_cap", scope
    return None, scope


def _atomic_parts(file: PolicyFile, path: str, own: str) -> list[tuple[str, str, str]]:
    """Separate only compound clauses whose policy subjects have different lifetimes."""
    version = file.metadata["version_id"]
    if version == "bj-housing-2025-360" and "最高贷款额度为100万元，最低首付款比例不低于30%" in own:
        condition = "借款申请人使用公积金贷款购买二套住房的，"
        return [
            ("base", path, f"{condition}最低首付款比例不低于30%。"),
            ("loan_cap", path + " > 最高贷款额度", f"{condition}最高贷款额度为100万元。"),
        ]
    if version in {"bj-housing-2024-400-web", "bj-housing-2025-565-bulletin"} and "非本市户籍" in own and "五环内" in own and "五环外" in own:
        text = re.sub(r"^#{1,6}\s*", "", own).strip()
        inner, outer = text.split("；", 1)
        prefix = "非本市户籍居民家庭"
        if prefix not in outer:
            outer = prefix + outer
        return [("base", path, inner.rstrip("。") + "。"),
                ("outer", path + " > 五环外", outer.rstrip("。") + "。")]
    return [("base", path, own)]


def chunks(file: PolicyFile) -> list[dict[str, Any]]:
    """Index atomic clauses with inherited conditions and shared supplements."""
    stack: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    tail = False
    for line in file.body.splitlines():
        stripped = line.strip()
        bare = HEADING.sub(lambda match: match.group(2), stripped)
        if re.match(r"(?:[一二三四五六七八九十]+、)?本(?:通知|公告)自.+(?:施行|执行)", bare):
            tail = True
        if tail:
            continue
        heading = HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            stack[:] = stack[:level-1]
            current = {"level": level, "title": title, "path": " > ".join(
                [item["title"] for item in stack] + [title]),
                "parents": list(stack), "lines": [stripped], "shared_notes": []}
            stack.append(current)
            units.append(current)
        elif stripped:
            if current is None:
                continue
            if stripped.startswith("同时符合多项条件") and current["level"] >= 4 and current["parents"]:
                current["parents"][-1]["shared_notes"].append(stripped)
            else:
                current["lines"].append(stripped)
        elif current and current["lines"] and current["lines"][-1] != "":
            current["lines"].append("")
    result = []
    first_clause_period = next((_explicit_end_date(unit["lines"][0]) for unit in units
                                if unit["level"] == 2 and _explicit_end_date(unit["lines"][0])[0]),
                               (None, None))
    for ordinal, unit in enumerate(units):
        own = "\n\n".join(part for part in unit["lines"] if part).strip()
        path = unit["path"]
        context = "\n".join(parent["lines"][0] for parent in unit["parents"])
        shared = "\n".join(note for parent in [*unit["parents"], unit]
                           for note in parent["shared_notes"])
        version = file.metadata["version_id"]
        for part_key, part_path, part_text in _atomic_parts(file, path, own):
            content = "\n\n".join(value for value in (context, part_text, shared) if value)
            effective_to, end_basis = _explicit_end_date(content)
            inherited_period = False
            if not effective_to and first_clause_period[0]:
                effective_to, end_basis = first_clause_period
                inherited_period = True
            subject, scope = _subject_scope(part_text)
            if version == "tax-2026-3":
                subject = "replacement_income_tax_refund"
            elif version == "bj-gjj-rate-2025-05-08":
                subject = "provident_loan_interest_rate"
            chunk_id = (_sha(f"{version}:{ordinal}:{path}")[:32] if part_key == "base"
                        else _sha(f"{version}:{ordinal}:{path}:{part_key}")[:32])
            result.append({
            "chunk_id": chunk_id, "clause_id": f"{version}:{ordinal}:{part_key}",
            "chunk_kind": "clause",
            "version_id": version,
            "document_number": file.metadata.get("document_number"), "title": file.metadata["title"],
            "clause_path": part_path, "city": "北京市", "topic": _topic(part_path, content),
            "policy_subject": subject, "applicability_scope": scope,
            "publication_date": file.metadata["publication_date"], "effective_from": file.effective_from,
            "effective_to": effective_to, "effective_end_basis": end_basis,
            "effective_end_check": ("first_clause_scope_machine_inferred_unverified" if inherited_period
                                    else "literal_range_machine_extracted" if end_basis else "unknown"),
            "effective_basis": file.effective_basis,
            "effective_check": file.effective_check, "review_status": file.status,
            "date_evidence": {"start": file.effective_basis,
                              "explicit_end": end_basis,
                              "publication": file.metadata["publication_date"]},
            "file_enactment_text": file.enactment_text,
            "file_precedence_text": file.precedence_text,
            "parent_context": context, "shared_supplement": shared,
            "superseded_from": None, "supersession_check": "unknown",
            "version_relations": [],
            "source_url": file.metadata["source_url"], "original_path": file.metadata["original_path"],
            "content_hash": _sha(content), "content": content, "model_version": MODEL_VERSION,
            })
    if file.enactment_text:
        version = file.metadata["version_id"]
        notice = file.enactment_text
        result.append({
            "chunk_id": _sha(f"{version}:file_notice")[:32],
            "clause_id": f"{version}:file_notice", "chunk_kind": "file_notice",
            "version_id": version, "document_number": file.metadata.get("document_number"),
            "title": file.metadata["title"],
            "clause_path": file.metadata["title"] + " > 文件级施行与冲突说明",
            "city": "北京市", "topic": _topic(file.metadata["title"], notice),
            "policy_subject": None, "applicability_scope": {"city": "北京市"},
            "publication_date": file.metadata["publication_date"],
            "effective_from": file.effective_from, "effective_to": None,
            "effective_end_basis": None, "effective_end_check": "unknown",
            "effective_basis": file.effective_basis, "effective_check": file.effective_check,
            "review_status": file.status,
            "date_evidence": {"start": file.effective_basis, "explicit_end": None,
                              "publication": file.metadata["publication_date"]},
            "file_enactment_text": notice, "file_precedence_text": file.precedence_text,
            "parent_context": file.metadata["title"], "shared_supplement": "",
            "superseded_from": None, "supersession_check": "unknown", "version_relations": [],
            "source_url": file.metadata["source_url"], "original_path": file.metadata["original_path"],
            "content_hash": _sha(notice), "content": notice, "model_version": MODEL_VERSION,
        })
    return result


def relate_versions(chunks_by_id: dict[str, dict[str, Any]]) -> None:
    """Propose clause-level replacements; never mark them legally confirmed."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for chunk in chunks_by_id.values():
        subject = chunk["policy_subject"]
        if subject:
            scope = chunk["applicability_scope"]
            groups.setdefault((subject, scope.get("ring", "all")), []).append(chunk)
    for (subject, _), members in groups.items():
        members.sort(key=lambda chunk: (chunk["effective_from"] or "9999", chunk["publication_date"]))
        for older in members:
            newer = next((candidate for candidate in members
                          if candidate["version_id"] != older["version_id"]
                          and candidate["effective_from"] and older["effective_from"]
                          and candidate["effective_from"] > older["effective_from"]), None)
            if newer is None:
                continue
            if subject == "provident_second_loan_cap":
                relation_scope = {"contributors": "both"}
                relation_type = "partial_overlap"
            else:
                relation_scope = older["applicability_scope"]
                relation_type = "same_scope_conflict_candidate"
                older["superseded_from"] = newer["effective_from"]
                older["supersession_check"] = "machine_proposed_unverified"
            link = {"clause_id": newer["clause_id"], "version_id": newer["version_id"],
                    "effective_from": newer["effective_from"], "relation": relation_type,
                    "overlap_scope": relation_scope, "check": "machine_proposed_unverified"}
            older["version_relations"].append({**link, "direction": "replaced_by"})
            newer["version_relations"].append({"clause_id": older["clause_id"],
                "version_id": older["version_id"], "effective_from": newer["effective_from"],
                "relation": relation_type, "overlap_scope": relation_scope,
                "check": "machine_proposed_unverified", "direction": "replaces"})


def exact_terms(text: str) -> set[str]:
    return {x.replace("％", "%").replace(" ", "") for x in EXACT.findall(text)}
