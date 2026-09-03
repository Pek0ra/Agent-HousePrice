from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BusinessMetricDocument:
    document_id: str
    title: str
    keywords: tuple[str, ...]
    status: str
    clarification: str | None
    resolution_terms: tuple[str, ...]
    content: str


@dataclass(frozen=True)
class RetrievalResult:
    documents: tuple[BusinessMetricDocument, ...]
    context: str
    needs_clarification: bool
    clarification_question: str | None

    @property
    def document_ids(self) -> list[str]:
        return [document.document_id for document in self.documents]


class MarkdownBusinessKnowledgeRetriever:
    """Small deterministic retriever backed by version-controlled Markdown files."""

    def __init__(self, knowledge_dir: Path | None = None, top_k: int = 3) -> None:
        self._knowledge_dir = knowledge_dir or Path(__file__).with_name("knowledge")
        self._top_k = top_k
        self._documents = tuple(
            self._load_document(path) for path in sorted(self._knowledge_dir.glob("*.md"))
        )
        if not self._documents:
            raise RuntimeError(f"No business knowledge documents found in {self._knowledge_dir}")

    def retrieve(self, question: str) -> RetrievalResult:
        normalized_question = question.casefold().replace(" ", "")
        ranked: list[tuple[int, BusinessMetricDocument]] = []
        for document in self._documents:
            matched = [
                keyword for keyword in document.keywords
                if keyword.casefold().replace(" ", "") in normalized_question
            ]
            if matched:
                ranked.append((sum(len(keyword) for keyword in matched), document))
        ranked.sort(key=lambda item: (-item[0], item[1].document_id))
        documents = tuple(document for _, document in ranked[: self._top_k])

        ambiguous = next(
            (
                document
                for document in documents
                if document.status == "ambiguous"
                and not any(
                    term.casefold().replace(" ", "") in normalized_question
                    for term in document.resolution_terms
                )
            ),
            None,
        )
        context = "\n\n".join(
            f"METRIC {document.document_id} ({document.title})\n{document.content}"
            for document in documents
        )
        if not context:
            context = "未检索到额外业务指标定义；不得自行创造指标口径。"
        return RetrievalResult(
            documents=documents,
            context=context,
            needs_clarification=ambiguous is not None,
            clarification_question=ambiguous.clarification if ambiguous else None,
        )

    @staticmethod
    def _load_document(path: Path) -> BusinessMetricDocument:
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise ValueError(f"Missing front matter in {path}")
        try:
            header, content = raw[4:].split("\n---\n", maxsplit=1)
        except ValueError as exc:
            raise ValueError(f"Invalid front matter in {path}") from exc
        metadata: dict[str, str] = {}
        for line in header.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                raise ValueError(f"Invalid metadata line in {path}: {line}")
            metadata[key.strip()] = value.strip()

        def csv_values(key: str) -> tuple[str, ...]:
            return tuple(value.strip() for value in metadata.get(key, "").split(",") if value.strip())

        return BusinessMetricDocument(
            document_id=metadata["id"],
            title=metadata["title"],
            keywords=csv_values("keywords"),
            status=metadata.get("status", "defined"),
            clarification=metadata.get("clarification") or None,
            resolution_terms=csv_values("resolution_terms"),
            content=content.strip(),
        )
