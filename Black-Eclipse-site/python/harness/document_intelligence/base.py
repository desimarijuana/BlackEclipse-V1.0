"""Document adapter base — the ONE contract every format adapter implements.

An adapter turns raw bytes into a `DocumentIR`. It declares which document kinds
it handles and exposes a single async `parse`. Adapters never choose a provider,
never touch the network and never persist anything: they are pure(ish) format
readers that receive a `ParseContext` carrying the already-validated bytes, the
config and optional services (OCR, a vision model, PDF rendering, an asset
store).

Capabilities differ per format — a CSV has no pages, a PDF has no worksheets —
so instead of forcing one interface, `Capabilities` advertises what a kind can
actually produce and the orchestrator/UI read it honestly (spec §8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from .config import DocumentConfig, document_config
from .errors import DocumentError, DocumentErrorClass
from .ir import (
    DateFacts,
    DocumentIR,
    Page,
    Section,
    Sheet,
    compute_overall_text_method,
    content_hash,
)

#: ISO-ish date forms we recognize in metadata / text without guessing.
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")


@dataclass
class Capabilities:
    """What a document kind can actually produce. Absent abilities are honest."""

    pages: bool = False
    text: bool = True
    structure: bool = False
    tables: bool = False
    images: bool = False
    links: bool = False
    annotations: bool = False
    entities: bool = False
    render: bool = False
    sheets: bool = False
    formulas: bool = False
    charts: bool = False
    ocr: bool = False
    vision: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {k: bool(v) for k, v in self.__dict__.items()}


@dataclass
class ParseContext:
    """Everything an adapter may need for one parse. Services are optional."""

    cfg: DocumentConfig = field(default_factory=document_config)
    run_settings: Any = None
    aux_settings: Any = None
    bridge: Any = None
    asset_store: Any = None
    emitter: Any = None
    run_id: Optional[str] = None
    user_id: Optional[str] = None
    # Injected services (set by the orchestrator; None when unavailable).
    # `ocr(decoded_image) -> OCRInfo` is the deterministic OCR bridge.
    ocr: Optional[Callable[..., Any]] = None
    # `vision_ocr(image_bytes, page_index) -> OCRInfo` uses a vision model.
    vision_ocr: Optional[Callable[..., Any]] = None
    # `analyze_image(image_bytes, question, *, mode) -> VisionResult`.
    analyze_image: Optional[Callable[..., Any]] = None
    # Free-form provenance the caller carries onto the IR.
    extra: dict[str, Any] = field(default_factory=dict)


class DocumentAdapter(Protocol):
    """A format adapter. `kinds` are the document kinds it handles."""

    name: str
    kinds: tuple[str, ...]

    def capabilities(self) -> Capabilities: ...

    async def parse(self, data: bytes, *, name: str, kind: str, ctx: ParseContext) -> DocumentIR: ...


# ── shared helpers ─────────────────────────────────────────────────────────────

def make_document_id(sha256: str) -> str:
    return "doc_" + sha256[:24]


def first_date(text: str) -> Optional[str]:
    """The first ISO date found in `text`, normalized to `YYYY-MM-DD`."""
    if not text:
        return None
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = match.group(1), match.group(2), match.group(3)
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
        return None
    return f"{year}-{month}-{day}"


def finalize_ir(
    ir: DocumentIR,
    *,
    parser: str,
    sha256: str,
    data: bytes,
    dates: Optional[DateFacts] = None,
) -> DocumentIR:
    """Fill the fields every adapter must set consistently (identity, method, dates)."""
    import time

    ir.parser = parser
    ir.sha256 = sha256
    ir.content_hash = content_hash(data)
    if not ir.document_id:
        ir.document_id = make_document_id(sha256)
    if not ir.created_at:
        ir.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ir.page_count = len(ir.pages)
    ir.sheet_count = len(ir.sheets)
    ir.text_method = compute_overall_text_method(ir.pages, ir.sheets)

    # Aggregate tables/images/links from pages + sheets so top-level access is simple.
    if not ir.tables:
        for page in ir.pages:
            ir.tables.extend(page.tables)
        for sheet in ir.sheets:
            ir.tables.extend(sheet.tables)
    if not ir.images:
        for page in ir.pages:
            ir.images.extend(page.images)
    if not ir.links:
        links: list[str] = []
        for page in ir.pages:
            links.extend(page.links)
        for sheet in ir.sheets:
            links.extend(sheet.links)
        ir.links = list(dict.fromkeys(links))[:1000]

    # Point-in-time: keep any adapter-provided dates; otherwise try metadata/text.
    if dates is not None:
        ir.dates = dates
    if ir.dates.retrieved_at is None:
        ir.dates.retrieved_at = ir.created_at
    if ir.dates.publication_date is None:
        for key in ("creationDate", "created", "createdAt", "publicationDate", "date", "dcterms:created"):
            value = ir.metadata.get(key)
            if value:
                found = first_date(str(value))
                if found:
                    ir.dates.publication_date = found
                    break
        else:
            found = first_date(ir.plain_text(limit=4000))
            if found:
                ir.dates.publication_date = found

    # Confidence: the mean per-page/sheet confidence that actually produced content.
    confidences: list[float] = []
    for page in ir.pages:
        if page.text.strip() or page.blocks:
            if page.ocr_confidence is not None:
                confidences.append(page.ocr_confidence)
            elif page.has_text_layer:
                confidences.append(0.95)
    if confidences:
        ir.confidence = round(sum(confidences) / len(confidences), 3)
    elif ir.sheet_count or ir.plain_text(limit=1):
        ir.confidence = 0.9
    else:
        ir.confidence = 0.0
    return ir


def build_sections(pages: list[Page], *, include_cells: bool = False) -> list[Section]:
    """Derive heading-bounded sections from page blocks (a deterministic structure)."""
    sections: list[Section] = []
    current: Optional[Section] = None
    breadcrumb: list[str] = []
    counter = 0
    for page in pages:
        for block in page.blocks:
            if block.kind in ("heading", "slide_title"):
                level = block.level or 1
                breadcrumb = breadcrumb[: max(0, level - 1)] + [block.text]
                counter += 1
                current = Section(
                    section_id=f"sec_{counter}", title=block.text, level=level,
                    page=page.index, path=list(breadcrumb), block_ids=[block.block_id],
                )
                sections.append(current)
            elif current is not None:
                current.block_ids.append(block.block_id)
    return sections


def ensure_nonempty(ir: DocumentIR, *, kind: str) -> None:
    """A parse that produced literally nothing is a failure, not an empty success."""
    if ir.pages or ir.sheets:
        return
    if ir.plain_text(limit=1):
        return
    # A document with zero pages/sheets is acceptable only for structured text
    # formats that carry no paging concept; adapters that DO page must produce one.
    if kind in ("pdf", "docx", "pptx", "odt", "doc", "ppt", "rtf"):
        raise DocumentError(
            DocumentErrorClass.PARTIAL_EXTRACTION,
            f"the {kind} produced no pages — the container may be corrupt",
        )


__all__ = [
    "Capabilities", "ParseContext", "DocumentAdapter",
    "make_document_id", "first_date", "finalize_ir", "build_sections", "ensure_nonempty",
]
