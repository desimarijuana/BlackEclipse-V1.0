"""Extraction: fetch → normalize → segment → evidence (raw text preserved).

Python does not re-implement web transport or HTML/PDF parsing: those live in the
existing TS `web_fetch` capability (SSRF-hardened, cheerio HTML, PDF text
extraction, XBRL/JSON/text handling). This module calls that capability through
the `DataBridge`, normalizes the result into the engine's `Evidence` contract,
segments it, and computes a content hash + retrieval timestamp.

Two hard rules:

  * The raw extracted content is ALWAYS preserved. An LLM summary is never the
    only artifact.
  * Structured extraction NEVER guesses. A value that cannot be reliably
    extracted is NOT_FOUND; an ambiguous one is AMBIGUOUS — never a fabricated
    number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .web_contracts import Evidence, content_hash, evidence_id
from .web_security import get_boundary, assert_safe_url
from .web_sources import (
    classify_source_type,
    make_source,
    publisher_for,
    resolve_entity,
)

MAX_RAW_CHARS = 200_000


@dataclass
class FetchResult:
    ok: bool
    url: str
    text: str = ""
    title: Optional[str] = None
    status: str = "UNAVAILABLE"
    error: Optional[str] = None
    extraction: Optional[str] = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    contentHash: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


async def fetch(url: str, *, bridge: Any, timeout_s: float = 20.0) -> FetchResult:
    """Fetch a page through the existing SSRF-hardened bridge. Never fetches directly."""
    safe, reason = _safe(url)
    if not safe:
        return FetchResult(ok=False, url=url, error=f"url rejected: {reason}", status="ERROR")
    if bridge is None:
        return FetchResult(ok=False, url=url, error="data bridge not configured", status="UNAVAILABLE")
    try:
        payload = await bridge.fetch("web_fetch", {"url": url})
    except Exception as exc:  # noqa: BLE001 - a fetch error is an unavailable answer
        return FetchResult(ok=False, url=url, error=str(exc), status="ERROR")
    if payload.get("status") != "OK":
        return FetchResult(
            ok=False,
            url=url,
            status=payload.get("status", "UNAVAILABLE"),
            error=payload.get("error") or "page could not be retrieved",
            diagnostics=list(payload.get("diagnostics") or []),
        )
    text = str(payload.get("text") or "")
    return FetchResult(
        ok=bool(text.strip()),
        url=payload.get("url") or url,
        text=text[:MAX_RAW_CHARS],
        title=payload.get("title"),
        status="OK",
        extraction=payload.get("extraction"),
        diagnostics=list(payload.get("diagnostics") or []),
        contentHash=content_hash(text),
        raw=payload,
    )


def _safe(url: str) -> tuple[bool, Optional[str]]:
    try:
        from .web_security import validate_url

        return validate_url(url)
    except Exception:  # noqa: BLE001
        return True, None


def fetch_to_evidence(result: FetchResult, *, entity_hint: Optional[str] = None, published_at: Optional[str] = None) -> Optional[Evidence]:
    """Convert a successful fetch into provenance-carrying `Evidence`.

    The text is raw and UNTRUSTED. `knownAt` defaults to the publication time when
    known; otherwise it is left unset (a strict cutoff then excludes it).
    """
    if not result.ok or not result.text:
        return None
    source = make_source(result.url, title=result.title, published_at=published_at, content_hash_value=result.contentHash)
    entity = resolve_entity(entity_hint) if entity_hint else None
    return Evidence(
        evidenceId=evidence_id(source_url=result.url, raw_text=result.text),
        sourceId=source.sourceId,
        sourceUrl=result.url,
        sourceType=source.sourceType,
        publisher=source.publisher,
        entityId=(entity.entityId if entity else None),
        publishedAt=published_at,
        knownAt=published_at,
        retrievedAt=_now(),
        documentId=source.contentHash,
        rawText=result.text,
        contentHash=result.contentHash or content_hash(result.text),
        confidence=0.0,
        provenance={
            "title": result.title,
            "domain": source.domain,
            "extraction": result.extraction,
            "publisher": source.publisher,
        },
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ── Page segmentation ──────────────────────────────────────────────────────────


@dataclass
class Segment:
    section: Optional[str]
    text: str
    kind: str = "paragraph"


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def segment_markdown(text: str, *, max_segments: int = 200) -> list[Segment]:
    """Split extracted markdown/text into sections, preserving headings.

    The bridge's `web_fetch` returns readable text/markdown with headings; this
    preserves section structure so evidence can cite a section, and keeps tables
    (lines containing `|`) intact as `table` segments.
    """
    segments: list[Segment] = []
    current_section: Optional[str] = None
    buffer: list[str] = []
    in_table = False

    def flush(kind: str = "paragraph") -> None:
        nonlocal buffer
        chunk = "\n".join(buffer).strip()
        if chunk:
            segments.append(Segment(section=current_section, text=chunk, kind=kind))
        buffer = []

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        heading = _HEADING_RE.match(line.strip())
        if heading:
            flush("table" if in_table else "paragraph")
            in_table = False
            current_section = heading.group(2).strip()
            continue
        is_table = line.strip().startswith("|")
        if in_table and not is_table:
            flush("table")
            in_table = False
        if is_table:
            in_table = True
        buffer.append(line)
        if len(segments) >= max_segments:
            break
    flush("table" if in_table else "paragraph")
    return segments[:max_segments]


# ── Structured extraction (deterministic; never guesses) ─────────────────────────

NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"


def extract_number(text: str, label: str) -> dict[str, Any]:
    """Extract a labelled number from text. NOT_FOUND / AMBIGUOUS, never a guess.

    Locates the label, then scans a bounded window after it for numbers with an
    optional scale word ("million"/"billion"/"%"). A bare 4-digit year ("fiscal
    2025") is a strong false positive, so scaled candidates are preferred; two
    distinct preferred values yield AMBIGUOUS.
    """
    if not text or not label:
        return {"status": NOT_FOUND, "value": None, "span": None}
    number_re = re.compile(r"(-?\$?\d[\d,]*\.?\d*)\s*(billion|million|thousand|bn|m|k|%)?", re.IGNORECASE)
    _scale = {"billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
    found: list[dict[str, Any]] = []
    for label_match in re.finditer(re.escape(label), text, re.IGNORECASE):
        tail = text[label_match.end() : label_match.end() + 120]
        # Prefer the same line/statement so a neighbouring metric's number is not
        # mistaken for this label's value; fall back to a short bounded window.
        window = re.split(r"[\n;]", tail)[0]
        for match in number_re.finditer(window):
            raw = match.group(1).replace(",", "").replace("$", "")
            try:
                value = float(raw)
            except ValueError:
                continue
            scale = (match.group(2) or "").lower()
            found.append({"value": value * _scale.get(scale, 1.0), "span": match.group(0).strip(), "scale": scale or None})
        if found:
            break
    if not found:
        return {"status": NOT_FOUND, "value": None, "span": None}
    scaled = [f for f in found if f["scale"]]
    pool = scaled or found
    unique = {round(f["value"], 6) for f in pool}
    if len(unique) > 1:
        return {"status": AMBIGUOUS, "value": None, "candidates": pool[:5], "span": None}
    return {"status": "OK", "value": pool[0]["value"], "span": pool[0]["span"], "scale": pool[0]["scale"]}


def structured_extract(schema: dict[str, list[str]], text: str) -> dict[str, Any]:
    """Extract a caller-specified schema (field → label aliases) from text.

    Returns, per field, either a value with its source span or `NOT_FOUND`/
    `AMBIGUOUS`. A schema entry may be a plain string label or a list of aliases.
    """
    out: dict[str, Any] = {}
    for field_name, labels in (schema or {}).items():
        aliases = labels if isinstance(labels, list) else [labels]
        best: Optional[dict[str, Any]] = None
        for alias in aliases:
            result = extract_number(text, alias)
            if result.get("status") == "OK":
                best = {**result, "label": alias}
                break
            if result.get("status") == AMBIGUOUS and best is None:
                best = {**result, "label": alias}
        out[field_name] = best or {"status": NOT_FOUND, "value": None, "span": None}
    return out


def wrap_untrusted_for_model(text: str, *, source: str) -> str:
    """Wrap extracted text through the untrusted-content boundary for a model."""
    return get_boundary().wrap(text, source=source)


# ── Period detection for deterministic enrichment ───────────────────────────────

# Metric label families the engine can recognize in a financial page. The value
# is a list of label aliases; the first unambiguous hit wins.
FINANCIAL_METRIC_LABELS: dict[str, list[str]] = {
    "revenue": ["revenue", "total revenue", "net revenue", "net sales", "top line"],
    "netIncome": ["net income", "net earnings", "net profit"],
    "eps": ["diluted eps", "earnings per share", "eps"],
    "grossMargin": ["gross margin"],
    "operatingMargin": ["operating margin"],
    "freeCashFlow": ["free cash flow", "fcf"],
    "operatingIncome": ["operating income", "operating profit"],
}


def detect_period(text: str) -> Optional[str]:
    """Detect the first fiscal period label stated in text, or None.

    Reuses the same shapes the Phase-4 `periods` module parses, so an enriched
    value's period is comparable with a mandate leg's requirement.
    """
    if not text:
        return None
    quarter = re.search(
        r"\b(?:FY\s*)?((?:19|20)\d{2})\s*[-/ ]?\s*Q([1-4])\b|\bQ([1-4])\s*(?:FY\s*)?((?:19|20)\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if quarter:
        if quarter.group(1):
            return f"FY{quarter.group(1)}-Q{quarter.group(2)}"
        return f"FY{quarter.group(4)}-Q{quarter.group(3)}"
    year = re.search(r"\b(?:fiscal|fy)\s*((?:19|20)\d{2})\b", text, re.IGNORECASE)
    if year:
        return f"FY{year.group(1)}"
    year = re.search(r"\b((?:19|20)\d{2})\b", text)
    if year:
        return f"FY{year.group(1)}"
    return None


def enrich_structured(text: str) -> Optional[dict[str, Any]]:
    """Extract the first unambiguous financial metric from a page, with its span.

    Returns `{metric, value, unit, span, period}` or None. Never guesses: an
    ambiguous or absent metric yields None.
    """
    extracted = structured_extract(FINANCIAL_METRIC_LABELS, text or "")
    for metric, value in extracted.items():
        if value.get("status") == "OK":
            return {
                "metric": metric,
                "value": value["value"],
                "unit": value.get("scale"),
                "span": value.get("span"),
                "period": detect_period(text),
            }
    return None


__all__ = [
    "FetchResult",
    "fetch",
    "fetch_to_evidence",
    "Segment",
    "segment_markdown",
    "NOT_FOUND",
    "AMBIGUOUS",
    "extract_number",
    "structured_extract",
    "wrap_untrusted_for_model",
    "MAX_RAW_CHARS",
]
