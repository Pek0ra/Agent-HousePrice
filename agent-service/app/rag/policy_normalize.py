"""Offline policy transcription. No code in the chat request path imports this module."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pymupdf
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
SOURCES = Path(__file__).with_name("policy_sources.json")
NORMALIZER_VERSION = 2
NUMBER = re.compile(r"(?:京建发〔\d{4}〕\d+号|公告\s*20\d{2}年第\d+号)")
GARBAGE = re.compile(r"/G\d{1,3}\b")
DATE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")
CLAUSE = re.compile(r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+[.．、])")
NOISE = re.compile(r"(?:站内搜索|请输入关键字|扫码|扫一扫|收藏|分享|网站地图|政府网站标识码|京公网安备|2026/10/14 17:|^https?://|^\d+/\d+$)")
FIELDS = ("version_id", "source_url", "original_path", "original_sha256", "title", "document_number", "issuing_authority", "publication_date", "effective_date", "retrieved_at", "parse_method", "verification_status")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if b"mime-version:" in data[:512].lower():
        message = BytesParser(policy=policy.default).parsebytes(data)
        if any(part.get_content_type() == "text/html" for part in message.walk()):
            return "mhtml"
    raise ValueError("unsupported or damaged file signature")


def html_paragraphs(data: bytes, selector: str) -> list[str]:
    soup = BeautifulSoup(data, "html.parser")
    body = soup.select_one(selector)
    if body is None:
        raise ValueError(f"HTML body selector missing: {selector}")
    for tag in body.select("script,style,nav,footer,button,.share,.collect"):
        tag.decompose()
    paragraphs = []
    for tag in body.find_all(["p", "div"], recursive=True):
        if tag.find(["p", "div"]):
            continue
        value = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        if value:
            for chunk in re.split(r"(?<=[。；：])\s+(?=[一二三四五六七八九十]+、)", value):
                if chunk and chunk not in paragraphs[-1:]:
                    paragraphs.append(chunk)
    if not paragraphs:
        paragraphs = [re.sub(r"\s+", " ", x).strip() for x in body.stripped_strings]
    return [x for x in paragraphs if x]


def mhtml_paragraphs(data: bytes) -> tuple[list[str], str | None, str]:
    message = BytesParser(policy=policy.default).parsebytes(data)
    part = next((x for x in message.walk() if x.get_content_type() == "text/html"), None)
    if part is None:
        raise ValueError("MHTML has no HTML part")
    html = part.get_payload(decode=True)
    return html_paragraphs(html, ".arc_cont"), part.get("Content-Location") or message.get("Content-Base"), BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def pdf_lines(data: bytes) -> list[str]:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
        lines = [line.strip() for page in document for line in page.get_text().splitlines() if line.strip()]
        document.close()
        return lines
    except Exception as exc:
        raise ValueError(f"PDF unreadable: {exc}") from exc


def ocr_lines(data: bytes) -> list[str]:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
        lines = [line.strip() for page in document for line in page.get_text(textpage=page.get_textpage_ocr(language="chi_sim", dpi=200, full=True)).splitlines() if line.strip()]
        document.close()
        return lines
    except Exception as exc:
        raise ValueError(f"official HTML unavailable and OCR unavailable: {exc}") from exc


def is_garbled(lines: list[str]) -> bool:
    text = "".join(lines)
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    return bool(GARBAGE.search(text)) or chinese < 80 or (len(text) > 300 and chinese / len(text) < 0.25)


def printed_pdf_paragraphs(lines: list[str], number: str | None) -> list[str]:
    clean = []
    for line in lines:
        if NOISE.search(line) or line.startswith("[") or re.fullmatch(r"\d{4}/\d\d/\d\d.*", line):
            continue
        if line in {"PDF格式下载", "打印", "政策解读：", "关于我们", "法律声明"}:
            continue
        clean.append(line)
    if number:
        start = next((i for i, x in enumerate(clean) if number in x), None)
        if start is None:
            raise ValueError(f"document number missing from PDF: {number}")
        # The printed title immediately precedes the number, sometimes on two lines.
        clean = clean[max(0, start - 2):]
    # Browser prints wrap policy paragraphs at fixed line widths. Join only wrapped
    # lines; indentation and numbered clauses mark a new paragraph.
    paragraphs: list[str] = []
    for line in clean:
        if line.startswith("　　") or CLAUSE.match(line) or not paragraphs or NUMBER.fullmatch(line):
            paragraphs.append(line.strip())
        else:
            paragraphs[-1] += line.strip()
    return paragraphs


def iso_date(text: str) -> str | None:
    match = DATE.search(text)
    return f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}" if match else None


def markdown_body(paragraphs: list[str], title: str, number: str | None) -> str:
    lines = [f"# {title}", ""]
    if number and number not in "\n".join(paragraphs):
        lines += [number, ""]
    for paragraph in paragraphs:
        p = paragraph.strip()
        if not p or p == title:
            continue
        if CLAUSE.match(p):
            level = 2 if re.match(r"^[一二三四五六七八九十]+、", p) else 3 if p.startswith("（") else 4
            lines += ["#" * level + " " + p, ""]
        else:
            lines += [p, ""]
    return "\n".join(lines).rstrip() + "\n"


def front_matter(metadata: dict) -> str:
    return "---\n" + "\n".join(f"{key}: {json.dumps(metadata.get(key), ensure_ascii=False)}" for key in FIELDS) + "\n---\n\n"


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_one(path: Path, spec: dict, cache_dir: Path, refresh: bool) -> tuple[str, dict, str]:
    data = path.read_bytes()
    if spec.get("expected_sha256") and sha256(data) != spec["expected_sha256"]:
        raise ValueError("unreadable-text PDF hash changed; visually verify it and update expected_sha256")
    kind = detect_type(data)
    expected_kind = spec["type"]
    if kind != expected_kind:
        raise ValueError(f"file type conflict: detected {kind}, expected {expected_kind}")
    expected_number = spec.get("document_number")
    source_url = spec.get("source_url")
    status = "machine_checked"
    if kind == "mhtml":
        paragraphs, embedded_url, full_html_text = mhtml_paragraphs(data)
        if source_url and embedded_url != source_url:
            raise ValueError(f"MHTML source URL mismatch: {embedded_url}")
        if expected_number and expected_number not in full_html_text:
            raise ValueError("MHTML document number mismatch")
        if spec["title"] not in full_html_text:
            raise ValueError("MHTML title mismatch")
        source_url = embedded_url
        method = "mhtml_html"
    else:
        lines = pdf_lines(data)
        if spec["text_source"] == "official_html":
            cache_path = cache_dir / (spec["id"] + ".html")
            selector = spec.get("body_selector", "#mainText")
            if refresh or not cache_path.exists():
                request = Request(source_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.beijing.gov.cn/"})
                try:
                    with urlopen(request, timeout=30) as response:
                        fetched = response.read()
                except Exception:
                    if cache_path.exists():
                        fetched = cache_path.read_bytes()
                    elif is_garbled(lines):
                        paragraphs = printed_pdf_paragraphs(ocr_lines(data), expected_number)
                        method = "pdf_ocr"
                        status = "needs_manual_review"
                        fetched = None
                    else:
                        raise ValueError("official HTML unavailable")
                if fetched is None:
                    cached = None
                else:
                    cached = fetched
                # Verify before replacing a known good snapshot.
                if cached is not None:
                    if spec.get("official_html_approved") and sha256(cached) != spec.get("approved_html_sha256"):
                        raise ValueError("approved official HTML snapshot changed; review before re-approval")
                    candidate = html_paragraphs(cached, selector)
                    page_text = BeautifulSoup(cached, "html.parser").get_text(" ", strip=True)
                    if expected_number and expected_number not in page_text:
                        raise ValueError("official HTML document number mismatch")
                    title_core = spec["title"][spec["title"].find("关于"):]
                    if title_core not in page_text or len("".join(candidate)) < 120:
                        raise ValueError("official HTML title/body missing")
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    if not cache_path.exists() or cache_path.read_bytes() != cached:
                        cache_path.write_bytes(cached)
            if cache_path.exists():
                cached = cache_path.read_bytes()
                if spec.get("official_html_approved") and sha256(cached) != spec.get("approved_html_sha256"):
                    raise ValueError("approved official HTML snapshot changed; review before re-approval")
                page_text = BeautifulSoup(cached, "html.parser").get_text(" ", strip=True)
                if expected_number and expected_number not in page_text:
                    raise ValueError("cached official HTML document number mismatch")
                title_core = spec["title"][spec["title"].find("关于"):]
                if title_core not in page_text:
                    raise ValueError("cached official HTML title mismatch")
                paragraphs = html_paragraphs(cached, selector)
                method = "pdf_official_html"
                if is_garbled(lines):
                    if not spec.get("official_html_approved", False):
                        status = "needs_manual_review"
                elif expected_number and expected_number not in "".join(lines):
                    raise ValueError("PDF and official HTML document numbers conflict")
        else:
            if is_garbled(lines):
                raise ValueError("PDF text is garbled; official HTML or reviewed OCR required")
            paragraphs = printed_pdf_paragraphs(lines, expected_number)
            method = "pdf_text"
    # Stop at the signed date. Some sites append policy links and page controls.
    final_date = next((i for i in range(len(paragraphs) - 1, -1, -1) if re.fullmatch(r"20\d{2}年\d{1,2}月\d{1,2}日", paragraphs[i])), None)
    if final_date is not None:
        paragraphs = paragraphs[:final_date + 1]
    body_text = "\n".join(paragraphs)
    if len(body_text) < 120 or len(re.findall(r"[\u3400-\u9fff]", body_text)) < 70:
        raise ValueError("policy body missing or too short")
    if GARBAGE.search(body_text) or NOISE.search(body_text):
        raise ValueError("garbled text or website controls remain in body")
    if expected_number and expected_number not in body_text and kind != "mhtml" and spec["text_source"] != "official_html":
        raise ValueError(f"document number mismatch or missing: {expected_number}")
    if kind != "mhtml" and spec["title"] not in body_text and spec["title"] not in path.stem:
        raise ValueError("title mismatch")
    for sample in spec.get("must_contain", []):
        if sample not in body_text:
            raise ValueError(f"key expression missing: {sample}")
    if spec.get("publication_date") and final_date is not None and iso_date(paragraphs[final_date]) != spec["publication_date"]:
        raise ValueError("publication date conflicts with signed date")
    if spec.get("effective_date"):
        y, m, d = spec["effective_date"].split("-")
        if f"{int(y)}年{int(m)}月{int(d)}日" not in body_text and "次日起施行" not in body_text:
            raise ValueError("effective date absent from policy body")
    md = markdown_body(paragraphs, spec["title"], expected_number)
    metadata = {
        "version_id": spec["id"],
        "source_url": source_url,
        "original_path": display_path(path),
        "original_sha256": sha256(data),
        "title": spec["title"],
        "document_number": expected_number,
        "issuing_authority": spec.get("issuing_authority"),
        "publication_date": spec.get("publication_date"),
        "effective_date": spec.get("effective_date"),
        "retrieved_at": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat() if method == "pdf_official_html" else None,
        "parse_method": method,
        "verification_status": status,
    }
    return front_matter(metadata) + md, metadata, status


def run(source_dir: Path, output_dir: Path, config: Path, refresh: bool = False) -> dict:
    specs = json.loads(config.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"documents": []}
    old = {item["original_path"]: item for item in previous["documents"]}
    results = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        relative = display_path(path)
        spec = specs.get(path.name)
        if not spec:
            results.append({"original_path": relative, "status": "failed", "reason": "source not configured"})
            continue
        target = output_dir / (spec["id"] + ".md")
        digest = sha256(path.read_bytes())
        recipe_digest = sha256(json.dumps({"normalizer_version": NORMALIZER_VERSION, "source": spec}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        prior = old.get(relative)
        if not refresh and prior and prior.get("original_sha256") == digest and prior.get("recipe_sha256") == recipe_digest and target.exists() and prior.get("status") != "failed":
            results.append(prior)
            continue
        try:
            content, metadata, status = normalize_one(path, spec, source_dir / "official_html", refresh)
            target.write_text(content, encoding="utf-8", newline="\n")
            results.append({"original_path": relative, "original_sha256": digest, "recipe_sha256": recipe_digest, "markdown_path": display_path(target), "text_source": spec["text_source"], "status": status, "missing_metadata": [key for key in FIELDS if metadata.get(key) is None], "sampled_expressions": spec.get("must_contain", [])})
        except Exception as exc:
            if target.exists():
                target.unlink()
            results.append({"original_path": relative, "original_sha256": digest, "status": "failed", "reason": str(exc)})
    manifest = {"schema_version": 1, "documents": results}
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != serialized:
        manifest_path.write_text(serialized, encoding="utf-8", newline="\n")
    report_path = output_dir / "reports" / "quality_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = ["# 政策规范化质量报告", "", "仅记录文本抽取与来源核对；不判断政策当下效力。", "", "| 原文件 | 状态 | 文字来源 | 缺失元数据 | 抽样表达 / 失败原因 |", "| --- | --- | --- | --- | --- |"]
    for item in results:
        name = Path(item["original_path"]).name.replace("|", "\\|")
        sample = "、".join(item.get("sampled_expressions", [])) or item.get("reason", "")
        report.append(f"| {name} | {item['status']} | {item.get('text_source', '')} | {', '.join(item.get('missing_metadata', [])) or '无'} | {sample} |")
    report += ["", "## 人工核对", "", "两份公报 PDF 的文本层不可读。360/565 号已根据用户确认，以政府官网 HTML 的文号、正文、关键数字及有效性标记作为引用审核依据；不要求 PDF 文本层可读。官网正文与本地 PDF 未做逐页版式对照。", "", "条款之间的适用关系仍须按日期、地域及后续文件逐项判断；官网有效标记不表示每一旧条款均未被后续政策调整。", ""]
    report_text = "\n".join(report)
    if not report_path.exists() or report_path.read_text(encoding="utf-8") != report_text:
        report_path.write_text(report_text, encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data/RAG")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/RAG/normalized")
    parser.add_argument("--config", type=Path, default=SOURCES)
    parser.add_argument("--refresh-official", action="store_true")
    args = parser.parse_args()
    manifest = run(args.source_dir.resolve(), args.output_dir.resolve(), args.config.resolve(), args.refresh_official)
    for item in manifest["documents"]:
        print(f"{item['status']}: {item['original_path']} -> {item.get('markdown_path', item.get('reason'))}")
    if any(item["status"] == "failed" for item in manifest["documents"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
