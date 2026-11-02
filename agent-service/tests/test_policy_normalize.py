from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.rag.policy_normalize import ROOT, SOURCES, detect_type, normalize_one, run


def test_existing_eight_sources_are_readable_and_repeatable(tmp_path: Path) -> None:
    source_dir = ROOT / "data/RAG"
    output_dir = tmp_path / "normalized"
    first = run(source_dir, output_dir, SOURCES)
    assert len(first["documents"]) == 8
    assert not [item for item in first["documents"] if item["status"] == "failed"]
    assert len(list(output_dir.glob("*.md"))) == 8
    originals = {p.name: p.read_bytes() for p in source_dir.iterdir() if p.is_file()}
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in output_dir.glob("*.md")}
    manifest_before = (output_dir / "manifest.json").read_bytes()
    second = run(source_dir, output_dir, SOURCES)
    assert second == first
    assert (output_dir / "manifest.json").read_bytes() == manifest_before
    assert {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in output_dir.glob("*.md")} == before
    assert {p.name: p.read_bytes() for p in source_dir.iterdir() if p.is_file()} == originals
    for md_path in output_dir.glob("*.md"):
        content = md_path.read_text(encoding="utf-8")
        assert len(content) > 500
        assert "/G21" not in content
        body = content.split("\n---\n", 1)[1]
        assert all(noise not in body for noise in ("站内搜索", "收藏", "分享", "请输入关键字", "2026/10/14"))


def make_mhtml(body: str, number: str = "京建发〔2025〕360号") -> bytes:
    message = EmailMessage()
    message["Content-Base"] = "https://example.gov.test/policy"
    message.set_content(f"<html><h1>测试政策</h1><p>{number}</p><div class='arc_cont'>{body}</div></html>", subtype="html")
    return message.as_bytes()


def test_damaged_and_missing_body_fail_without_markdown(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "normalized"
    source.mkdir()
    bad = source / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\nnot a usable PDF")
    empty = source / "empty.doc"
    empty.write_bytes(make_mhtml(""))
    specs = {
        "bad.pdf": {"id": "bad", "type": "pdf", "text_source": "pdf_text", "title": "测试政策", "document_number": "京建发〔2025〕360号"},
        "empty.doc": {"id": "empty", "type": "mhtml", "text_source": "mhtml_html", "title": "测试政策", "document_number": "京建发〔2025〕360号"},
    }
    config = tmp_path / "config.json"
    config.write_text(json.dumps(specs, ensure_ascii=False), encoding="utf-8")
    manifest = run(source, output, config)
    assert all(item["status"] == "failed" for item in manifest["documents"])
    assert not list(output.glob("*.md"))
    assert detect_type(empty.read_bytes()) == "mhtml"


def test_document_number_mismatch_fails(tmp_path: Path) -> None:
    source = tmp_path / "wrong.doc"
    source.write_bytes(make_mhtml("一、这是可阅读的测试政策正文。" * 15, "京建发〔2025〕999号"))
    spec = {"type": "mhtml", "text_source": "mhtml_html", "title": "测试政策", "document_number": "京建发〔2025〕360号"}
    with pytest.raises(ValueError, match="document number mismatch"):
        normalize_one(source, spec, tmp_path, False)


def test_changed_original_replaces_its_own_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "normalized"
    source_dir.mkdir()
    source = source_dir / "policy.doc"
    spec = {"id": "policy", "type": "mhtml", "text_source": "mhtml_html", "title": "测试政策", "document_number": "京建发〔2025〕360号"}
    config = tmp_path / "config.json"
    config.write_text(json.dumps({source.name: spec}, ensure_ascii=False), encoding="utf-8")
    source.write_bytes(make_mhtml("一、首套住房贷款额度为100万元。" * 15))
    first = run(source_dir, output_dir, config)
    first_md = (output_dir / "policy.md").read_text(encoding="utf-8")
    source.write_bytes(make_mhtml("一、首套住房贷款额度为120万元。" * 15))
    second = run(source_dir, output_dir, config)
    second_md = (output_dir / "policy.md").read_text(encoding="utf-8")
    assert first["documents"][0]["original_sha256"] != second["documents"][0]["original_sha256"]
    assert "100万元" in first_md and "120万元" in second_md
    assert len(list(output_dir.glob("*.md"))) == 1
