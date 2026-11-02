"""Qdrant backed policy indexing and scoped hybrid retrieval."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.rag.policy_index import COLLECTION, CORPUS, MODEL, MODEL_VERSION, chunks, exact_terms, load_corpus, relate_versions


def _deps():
    from fastembed import TextEmbedding
    from qdrant_client import QdrantClient, models
    return TextEmbedding, QdrantClient, models


def _point_id(point: Any) -> str:
    # Server Qdrant renders UUID point IDs with hyphens; chunk_id is stable hex.
    return str(point.id).replace("-", "")


def _requested_clause_scope(query: str) -> tuple[set[str], str | None]:
    subjects: set[str] = set()
    if any(term in query for term in ("退税", "退个税", "个税退还")) and any(
            term in query for term in ("换购", "换房", "旧房")):
        subjects.add("replacement_income_tax_refund")
    if "公积金" in query and ("二套" in query or "第二套" in query):
        if "首付" in query:
            subjects.add("provident_second_down_payment")
        if "贷款额度" in query or "最高额度" in query:
            subjects.add("provident_second_loan_cap")
    if "公积金" in query and "利率" in query:
        subjects.add("provident_loan_interest_rate")
    ring = None
    if any(word in query for word in ("非京籍", "非本市户籍")) and any(
            word in query for word in ("社保", "个税", "缴纳", "年限", "五环内", "五环外")):
        subjects.add("nonlocal_purchase_social_years")
        if "五环内" in query and "五环外" not in query:
            ring = "inner"
        elif "五环外" in query and "五环内" not in query:
            ring = "outer"
    return subjects, ring


class PolicyStore:
    def __init__(self, location: str = "data/policy_qdrant", *, model=None, client=None):
        TextEmbedding, QdrantClient, self.models = _deps()
        self.model = model or TextEmbedding(model_name=MODEL)
        self.client = client or (QdrantClient(url=location) if location.startswith(("http://", "https://"))
                                 else QdrantClient(path=location))

    def _vector(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.model.embed(texts)]

    def _ensure(self, size: int):
        if not self.client.collection_exists(COLLECTION):
            self.client.create_collection(COLLECTION, vectors_config=self.models.VectorParams(
                size=size, distance=self.models.Distance.COSINE))
            for field in ("version_id", "clause_id", "city", "topic", "policy_subject",
                          "review_status", "effective_from", "superseded_from"):
                self.client.create_payload_index(COLLECTION, field, self.models.PayloadSchemaType.KEYWORD)
        else:
            config = self.client.get_collection(COLLECTION).config.params.vectors
            if config.size != size:
                raise RuntimeError("Qdrant vector size differs from embedding model")

    def _all(self) -> list[Any]:
        if not self.client.collection_exists(COLLECTION):
            return []
        result, offset = [], None
        while True:
            page, offset = self.client.scroll(COLLECTION, limit=256, offset=offset, with_payload=True, with_vectors=False)
            result.extend(page)
            if offset is None:
                return result

    def build(self, directory: Path = CORPUS) -> list[dict[str, Any]]:
        files, report = load_corpus(directory)
        desired = {c["chunk_id"]: c for f in files for c in chunks(f)}
        relate_versions(desired)
        counts = {f.metadata["version_id"]: len(chunks(f)) for f in files}
        for row in report:
            version = row["file"].removesuffix(".md")
            row["chunks"] = counts.get(version, 0)
            if row["status"] == "needs_manual_review":
                row["excluded_reason"] = "formal answers: manual review pending"
        existing = {_point_id(point): point.payload for point in self._all()}
        stale = [key for key in existing if key not in desired or existing[key] != desired[key]]
        if stale:
            self.client.delete(COLLECTION, points_selector=self.models.PointIdsList(points=stale), wait=True)
        changed = [c for key, c in desired.items() if key not in existing or key in stale]
        if changed:
            vectors = self._vector([f"{c['clause_path']}\n{c['content']}\n{c['file_enactment_text']}"
                                    for c in changed])
            self._ensure(len(vectors[0]))
            self.client.upsert(COLLECTION, [self.models.PointStruct(id=c["chunk_id"], vector=v, payload=c)
                                            for c, v in zip(changed, vectors)], wait=True)
        for row in report:
            row["updated_chunks"] = sum(c["version_id"] == row["file"].removesuffix(".md") for c in changed)
        return report

    def inspect(self) -> dict[str, Any]:
        points = self._all()
        versions: dict[str, int] = {}
        for point in points:
            version = point.payload["version_id"]
            versions[version] = versions.get(version, 0) + 1
        return {"collection": COLLECTION, "model": MODEL, "model_version": MODEL_VERSION,
                "points": len(points), "versions": versions}

    def search(self, query: str, *, city: str = "北京市", topic: str | None = None,
               as_of: str | None = None, published_by_date: bool = False,
               include_unreviewed: bool = False, limit: int = 6) -> dict[str, Any]:
        if city != "北京市":
            return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence": [],
                    "limitations": [f"当前政策语料仅覆盖北京市，不能回答{city}政策。"]}
        if not self.client.collection_exists(COLLECTION):
            raise RuntimeError("policy index has not been built")
        if as_of:
            from datetime import date
            date.fromisoformat(as_of)
        points = self._all()
        requested_subjects, requested_ring = _requested_clause_scope(query)
        compact_query = re.sub(r"\s+", "", query)
        named = {p.payload["document_number"] for p in points
                 if p.payload.get("document_number") and re.sub(r"\s+", "", p.payload["document_number"]) in compact_query}
        number_tokens = re.findall(r"(20\d{2})\D{0,4}?(\d{1,4})号", compact_query)
        if number_tokens:
            named.update(p.payload["document_number"] for p in points
                         if p.payload.get("document_number") and any(
                             re.search(rf"{year}\D{{0,4}}?{number}号", re.sub(r"\s+", "", p.payload["document_number"]))
                             for year, number in number_tokens))
        if named and not include_unreviewed and any(p.payload["review_status"] != "machine_checked"
               for p in points if p.payload.get("document_number") in named):
            return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence": [],
                    "limitations": ["指定文号对应文件仍需人工核对，不得用其他版本替代回答"]}
        if as_of and not published_by_date:
            expired = [p.payload for p in points if p.payload.get("effective_to") and p.payload["effective_to"] < as_of
                       and p.payload["review_status"] == "machine_checked" and p.payload["city"] == city
                       and (p.payload.get("document_number") in named or
                            (requested_subjects and p.payload.get("policy_subject") in requested_subjects))]
            if expired:
                end = min(p["effective_to"] for p in expired)
                return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence": [],
                        "limitations": [f"相关已收录条款明示适用期截至{end}；现有资料不能证明{as_of}仍享有该优惠，需核对后续政策。"]}
        eligible = []
        superseded = []
        for point in points:
            p = point.payload
            if p["city"] != city or (topic and p["topic"] != topic):
                continue
            if requested_subjects and p.get("policy_subject") not in requested_subjects:
                continue
            if requested_ring and p.get("applicability_scope", {}).get("ring") != requested_ring:
                continue
            if not include_unreviewed and p["review_status"] != "machine_checked":
                continue
            if named and p.get("document_number") not in named:
                continue
            if as_of:
                if p["effective_from"] and p["effective_from"] > as_of:
                    continue
                if p["publication_date"] > as_of and (published_by_date or not p["effective_from"]
                    or p["effective_from"] >= p["publication_date"]):
                    continue
                if p.get("effective_to") and p["effective_to"] < as_of:
                    continue
                if p.get("superseded_from") and p["superseded_from"] <= as_of:
                    if requested_subjects and p.get("policy_subject") in requested_subjects:
                        superseded.append(p)
                    continue
                if (p.get("policy_subject") == "provident_second_loan_cap"
                        and "夫妻双方" in query and any(
                            relation.get("relation") == "partial_overlap"
                            and relation.get("direction") == "replaced_by"
                            and relation.get("effective_from", "9999") <= as_of
                            for relation in p.get("version_relations", []))):
                    if requested_subjects and p.get("policy_subject") in requested_subjects:
                        superseded.append(p)
                    continue
            eligible.append(point)
        ids = {_point_id(p) for p in eligible}
        if not ids:
            notes = ["无符合审核和日期条件的政策条款"]
            if not include_unreviewed and requested_subjects and any(
                point.payload.get("policy_subject") in requested_subjects
                and point.payload.get("review_status") == "needs_manual_review"
                and (not as_of or point.payload["publication_date"] <= as_of)
                for point in points
            ):
                notes.append("相关条款来自尚未人工审核的文件，正式结论须待人工核对。")
            if superseded:
                notes.append("旧条款与后续条款在该适用范围疑似冲突，机器覆盖关系待人工核对；不能把旧条款作为该日结论。")
            return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence": [], "limitations": notes}
        expanded = query.replace("首套", "首套 家庭唯一住房").replace("二套", "二套 第二套住房")
        vector = self._vector([expanded])[0]
        conditions = [self.models.FieldCondition(key="city", match=self.models.MatchValue(value=city))]
        conditions.append(self.models.HasIdCondition(has_id=[point.id for point in eligible]))
        if topic:
            conditions.append(self.models.FieldCondition(key="topic", match=self.models.MatchValue(value=topic)))
        if not include_unreviewed:
            conditions.append(self.models.FieldCondition(key="review_status", match=self.models.MatchValue(value="machine_checked")))
        qdrant_started = time.perf_counter()
        dense = self.client.query_points(COLLECTION, query=vector,
            query_filter=self.models.Filter(must=conditions), limit=min(len(eligible), 100), with_payload=True).points
        qdrant_duration_ms = round((time.perf_counter() - qdrant_started) * 1000, 3)
        rerank_started = time.perf_counter()
        dense_scores = {_point_id(p): p.score for p in dense if _point_id(p) in ids}
        query_exact = exact_terms(query)
        # Chinese bigrams give sparse recall for paraphrases; exact numeric tokens are a hard rerank signal.
        def grams(value: str) -> set[str]:
            chars = re.sub(r"\s+", "", value.lower())
            return {chars[i:i+2] for i in range(len(chars)-1)}
        qgrams = grams(expanded)
        scored = []
        for point in eligible:
            p = point.payload
            hay = p["content"] + p.get("file_enactment_text", "") + (p.get("document_number") or "")
            overlap = len(qgrams & grams(p["clause_path"] + hay)) / max(1, len(qgrams))
            document_hit = bool(p.get("document_number") and p["document_number"] in query)
            exact = exact_terms(hay)
            matched = query_exact & exact
            missing = {term for term in query_exact - exact if not re.match(r"20\d{2}[-年./]", term)}
            dense_score = max(0, dense_scores.get(_point_id(point), 0))
            score = .53 * dense_score + .27 * overlap + .12 * (len(matched) / max(1, len(query_exact))) + .08 * document_hit
            if missing:
                score -= .12 * len(missing) / len(query_exact)
            if p["effective_check"] == "unknown":
                score -= .05
            if requested_subjects == {"provident_loan_interest_rate"}:
                # The introductory heading shares the title words but has no date rule.
                score += .12 if re.search(r"20\d{2}年\d{1,2}月\d{1,2}日", p["content"]) else -.1
            if any(term in query for term in ("施行", "生效", "何时执行", "哪天执行")) and any(term in p["content"] for term in ("施行", "执行")):
                score += .2
            if ("首套" in query or "唯一住房" in query) and "第二套住房" in p["content"] and "唯一住房" not in p["content"]:
                score -= .22
            if ("二套" in query or "第二套" in query) and "家庭唯一住房" in p["content"] and "第二套住房" not in p["content"]:
                score -= .22
            scored.append((score, p))
        scored.sort(key=lambda item: item[0], reverse=True)
        comparison = ("首套" in query or "唯一住房" in query) and ("二套" in query or "第二套" in query)
        # A rate notice states different dates for newly issued and existing loans.
        # Keep its clauses together even when a generic date-question favors one clause.
        rate_scope = requested_subjects == {"provident_loan_interest_rate"}
        cutoff = 0 if rate_scope else .34 if comparison or not scored else max(.34, scored[0][0] - .2)
        evidence = [{**p, "score": round(score, 4), "retrieved_at": datetime.now(timezone.utc).isoformat(),
                     "formal_evidence": p["review_status"] == "machine_checked" and p["effective_check"] != "unknown"}
                    for score, p in scored if score >= cutoff][:limit]
        limitations = []
        if superseded:
            limitations.append("同主题、重叠适用范围的旧条款在后续条款施行当日起不用于该冲突范围；机器提出的覆盖关系尚待人工逐条核对。")
        if not evidence:
            limitations.append("未检索到足够相关且已审核的政策条款")
        if any(p["effective_check"] == "unknown" for p in evidence):
            limitations.append("部分条款生效日期未知，需核对")
        if as_of and any(p["publication_date"] > as_of for p in evidence):
            limitations.append("部分依据在所问历史日期之后才发布，但原文明确写有追溯适用日期；当日可获知的信息应另行核对。")
        if include_unreviewed and any(p["review_status"] == "needs_manual_review" for p in evidence):
            limitations.append("含未人工核对文件，不得作为正式结论")
        if any(item.get("version_relations") for item in evidence):
            limitations.append("条款级前后版本关系为机器提出、未经人工确认；请核对原文与适用范围。")
        if evidence and any(p.payload["review_status"] == "needs_manual_review"
                            and (not as_of or p.payload["publication_date"] <= as_of)
                            and p.payload["topic"] in {item["topic"] for item in evidence}
                            and len(qgrams & grams(p.payload["content"])) / max(1, len(qgrams)) >= .15
                            for p in points):
            limitations.append("存在尚未人工核对的可能重叠条款，版本及适用范围需逐条核对")
        return {"retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence": evidence, "limitations": limitations,
                "timings_ms": {"qdrant": qdrant_duration_ms,
                               "rerank": round((time.perf_counter() - rerank_started) * 1000, 3)}}
