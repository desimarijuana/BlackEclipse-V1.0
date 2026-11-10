"""Streaming text extraction and content-defined chunking.

Every reader consumes a bounded window and yields chunks; nothing is loaded
whole. That is the difference between indexing a 40 GB log and crashing on it.
Formats that cannot be streamed safely (scanned PDFs, media, opaque binaries)
produce no chunks and are reported as such instead of being guessed at.
"""

from __future__ import annotations

import codecs
import hashlib
import html
import json
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Iterator, Optional

from .config import SourceConfig
from .contracts import FileRecord, SourceCard

_WS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+")
_TAG = re.compile(r"<[^>]+>")
_CANCEL = None


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text).replace("\r\n", "\n").replace("\r", "\n").strip()


def iter_text_chunks(
    path: str,
    *,
    chunk_chars: int = 1_200,
    overlap: int = 150,
    max_bytes: int = 64 * 1024 * 1024,
    max_chunks: int = 2_000,
    start_offset: int = 0,
    cancel=None,
) -> Iterator[dict]:
    """Yield ``{text,start,end,ord}`` from a text file, streaming."""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buffer = ""
    buffer_start = start_offset
    ordinal = 0
    consumed = 0
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        if start_offset:
            handle.seek(start_offset)
        while consumed < max_bytes and ordinal < max_chunks:
            if cancel is not None and cancel.is_set():
                return
            block = handle.read(min(256 * 1024, max_bytes - consumed))
            if not block:
                break
            consumed += len(block)
            digest.update(block)
            buffer += decoder.decode(block)
            while len(buffer) >= chunk_chars and ordinal < max_chunks:
                cut = _split_point(buffer, chunk_chars)
                piece = buffer[:cut]
                text = normalize_text(piece)
                if text:
                    yield {"text": text, "start": buffer_start, "end": buffer_start + cut, "ord": ordinal}
                    ordinal += 1
                step = max(1, cut - overlap)
                buffer = buffer[step:]
                buffer_start += step
    tail = normalize_text(buffer + decoder.decode(b"", final=True))
    if tail and ordinal < max_chunks:
        yield {"text": tail, "start": buffer_start, "end": buffer_start + len(tail), "ord": ordinal}
    yield {"_digest": digest.hexdigest(), "_bytes": consumed, "_done": True}


def _split_point(buffer: str, target: int) -> int:
    """Prefer a paragraph/sentence/space boundary near the target."""
    window = buffer[: target + 200]
    for marker in ("\n\n", "\n", ". ", " "):
        index = window.rfind(marker, int(target * 0.6), target + 200)
        if index > 0:
            return index + len(marker)
    return target


def extract_chunks(
    file: FileRecord,
    path: str,
    *,
    card: Optional[SourceCard] = None,
    config: SourceConfig,
    cancel=None,
) -> tuple[list[dict], dict]:
    """Extract indexable chunks for one file. Returns (chunks, meta)."""
    klass = file.klass or "unknown"
    meta: dict = {"reason": "", "bytes": 0, "hash": None}
    try:
        if file.size > config.index_max_file_bytes:
            meta["reason"] = "over the indexing byte ceiling"
            return [], meta
        if klass in ("text", "code"):
            chunks = []
            for item in iter_text_chunks(
                path,
                chunk_chars=config.chunk_chars,
                overlap=config.chunk_overlap,
                max_bytes=config.index_max_file_bytes,
                max_chunks=config.index_max_chunks_per_file,
                cancel=cancel,
            ):
                if item.get("_done"):
                    meta["hash"] = item["_digest"]
                    meta["bytes"] = item["_bytes"]
                    break
                chunks.append(item)
            return chunks, meta
        if klass == "table":
            return _table_chunks(file, path, config, cancel), meta
        if klass == "document":
            return _document_chunks(file, path, config, cancel), meta
        if klass == "archive":
            return _archive_chunks(path, config), meta
        if klass == "database":
            return _database_chunks(path, config), meta
        meta["reason"] = f"{klass} sources are indexed by metadata only"
        return [], meta
    except Exception as exc:  # noqa: BLE001 - extraction failure is reported, not fatal
        meta["reason"] = f"extraction failed: {exc}"
        return [], meta


def _table_chunks(file: FileRecord, path: str, config: SourceConfig, cancel) -> list[dict]:
    """Index a bounded sample: header + rows. SQL remains the precise path."""
    chunks: list[dict] = []
    suffix = Path(path).suffix.lower()
    if suffix in (".csv", ".tsv"):
        import csv

        with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t" if suffix == ".tsv" else ",")
            header = next(reader, [])
            if header:
                chunks.append({
                    "text": "Columns: " + " | ".join(str(c) for c in header[:60]),
                    "start": 0, "end": 0, "ord": 0,
                })
            buffer: list[str] = []
            size = 0
            for index, row in enumerate(reader):
                if index >= 2_000 or cancel is not None and cancel.is_set():
                    break
                line = " | ".join(str(c) for c in row[:60])
                buffer.append(line)
                size += len(line)
                if size >= config.chunk_chars:
                    chunks.append({
                        "text": "\n".join(buffer), "start": 0, "end": 0, "ord": len(chunks),
                    })
                    buffer, size = [], 0
            if buffer:
                chunks.append({"text": "\n".join(buffer), "start": 0, "end": 0, "ord": len(chunks)})
        return chunks

    if suffix == ".parquet":
        try:
            from .query import run_sql

            result = run_sql(path, "SELECT * FROM t LIMIT 200", cfg=config, max_rows=200)
            if result.ok and result.columns:
                lines = ["Columns: " + " | ".join(result.columns)]
                lines.extend(" | ".join(str(v) for v in row) for row in result.rows)
                return [{"text": "\n".join(lines), "start": 0, "end": 0, "ord": 0}]
        except Exception:  # noqa: BLE001
            pass
        return chunks

    if suffix in (".xlsx", ".xls", ".ods"):
        return _xlsx_chunks(path, config)
    return chunks


def _document_chunks(file: FileRecord, path: str, config: SourceConfig, cancel) -> list[dict]:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return _pdf_chunks(path, config, cancel)
    if suffix in (".docx", ".pptx", ".odt", ".ods", ".odp", ".epub"):
        return _zip_document_chunks(path, config)
    if suffix == ".rtf":
        raw = Path(path).read_text(encoding="latin-1", errors="replace")[: config.index_max_file_bytes]
        text = raw.replace("\\par", "\n")
        text = re.sub(r"\\[a-z]+-?\d* ?", " ", text)
        return _chunk_text(normalize_text(text), config)
    return []


def _pdf_chunks(path: str, config: SourceConfig, cancel) -> list[dict]:
    try:
        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(path, strict=False)
        chunks: list[dict] = []
        total = 0
        for index, page in enumerate(reader.pages[: config.index_pdf_max_pages]):
            if cancel is not None and cancel.is_set():
                break
            text = normalize_text(page.extract_text() or "")
            if not text:
                continue
            for piece in _chunks_from_text(text, config):
                piece["ord"] = len(chunks)
                piece["page"] = index + 1
                chunks.append(piece)
            total += len(text)
            if total >= config.index_max_file_bytes // 2:
                break
        return chunks
    except Exception:  # noqa: BLE001 - an unreadable PDF yields no text, honestly
        return []


def _zip_document_chunks(path: str, config: SourceConfig) -> list[dict]:
    suffixes = Path(path).suffix.lower()
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if suffixes == ".docx":
                parts = [n for n in names if n == "word/document.xml"]
            elif suffixes == ".pptx":
                parts = sorted(n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            elif suffixes == ".epub":
                parts = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
            else:
                parts = [n for n in names if n in ("content.xml",)]
            chunks: list[dict] = []
            budget = config.index_max_file_bytes
            for name in parts[: config.index_max_chunks_per_file]:
                info = archive.getinfo(name)
                if info.file_size > budget:
                    continue
                raw = archive.read(name)[:budget]
                text = _TAG.sub(" ", raw.decode("utf-8", "replace"))
                text = html.unescape(text)
                for piece in _chunks_from_text(normalize_text(text), config):
                    piece["ord"] = len(chunks)
                    chunks.append(piece)
                budget -= len(raw)
                if budget <= 0:
                    break
            return chunks
    except Exception:  # noqa: BLE001
        return []


def _xlsx_chunks(path: str, config: SourceConfig) -> list[dict]:
    try:
        from openpyxl import load_workbook  # noqa: PLC0415

        workbook = load_workbook(path, read_only=True, data_only=True)
        chunks: list[dict] = []
        budget = config.index_max_file_bytes
        for sheet in workbook.worksheets:
            lines = [f"Sheet: {sheet.title}"]
            for row in sheet.iter_rows(max_row=1_000, values_only=True):
                line = " | ".join("" if v is None else str(v) for v in row[:40])
                if line.strip(" |"):
                    lines.append(line)
                if sum(len(x) for x in lines) >= budget:
                    break
            text = normalize_text("\n".join(lines))
            for piece in _chunks_from_text(text, config):
                piece["ord"] = len(chunks)
                chunks.append(piece)
            budget -= len(text)
            if budget <= 0:
                break
        return chunks
    except Exception:  # noqa: BLE001
        return []


def _archive_chunks(path: str, config: SourceConfig) -> list[dict]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()[:5_000]
        text = "Archive entries:\n" + "\n".join(names)
        return _chunks_from_text(text, config)
    except Exception:  # noqa: BLE001 - tar/7z listing needs an opener; card still shows a count
        return []


def _database_chunks(path: str, config: SourceConfig) -> list[dict]:
    try:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        finally:
            con.close()
        lines = [f"Database objects: {len(rows)}"]
        for kind, name, sql in rows[:500]:
            lines.append(f"{kind}: {name}")
            if sql:
                lines.append(normalize_text(sql)[:600])
        return _chunks_from_text("\n".join(lines), config)
    except Exception:  # noqa: BLE001
        return []


def _chunk_text(text: str, config: SourceConfig) -> list[dict]:
    return _chunks_from_text(text, config)


def _chunks_from_text(text: str, config: SourceConfig) -> list[dict]:
    chunks: list[dict] = []
    step = max(200, config.chunk_chars)
    overlap = max(0, config.chunk_overlap)
    start = 0
    while start < len(text) and len(chunks) < config.index_max_chunks_per_file:
        end = min(len(text), start + step)
        piece = normalize_text(text[start:end])
        if piece:
            chunks.append({"text": piece, "start": start, "end": end, "ord": len(chunks)})
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


__all__ = ["extract_chunks", "iter_text_chunks", "normalize_text", "chunk_text_for_tests"]


def chunk_text_for_tests(text: str, config: SourceConfig) -> list[dict]:
    """Exposed for tests: chunk an in-memory string with the same rules."""
    return _chunks_from_text(text, config)
