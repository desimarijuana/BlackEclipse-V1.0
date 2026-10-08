"""The Document Intermediate Representation (DocumentIR) — the system's backbone.

Every adapter converts a file into ONE of these structures; every downstream
stage (chunking, indexing, retrieval, comparison, rendering, evidence) reads the
IR, never the raw bytes. This is what lets a PDF page, a DOCX section, a PPTX
slide, an XLSX sheet and an HTML document be reasoned about uniformly while
keeping format-specific detail.

Design rules (spec §19/§20/§21/§59):

* **Coordinates are never lost.** A block keeps its `bbox` in source units and
  the unit is recorded (`points` for PDF/XLSX logical units, `px` for rendered
  images, `emu`/`percent` for OOXML). A missing bbox is `None`, never `[0,0,0,0]`.
* **Provenance is per block.** Every block records how it was obtained
  (`TextMethod`) and a confidence, so a claim can be traced to a page/block/cell.
* **Observed vs extracted vs inferred.** `Block.kind` and `provenance.status`
  keep the distinction the anti-hallucination rule requires.
* **Partial results are first-class.** A page with no text but a failed OCR is
  recorded as such; nothing is fabricated.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


# ── vocabularies ───────────────────────────────────────────────────────────────

DocumentKind = Literal[
    "pdf", "docx", "doc", "odt", "rtf",
    "pptx", "ppt", "odp",
    "xlsx", "xls", "xlsb", "ods", "csv", "tsv",
    "json", "jsonl", "xml", "yaml", "toml",
    "html", "htm", "epub",
    "markdown", "md", "mdx", "txt",
    "image", "archive", "unknown",
]

TextMethod = Literal[
    "native",          # extracted from the format's own text/structure
    "ocr",             # recognized by an OCR engine
    "vision",          # transcribed/derived by a vision model
    "computed",        # produced by our own computation (e.g. a query result)
    "none",            # nothing was obtained
]

ExtractionStatus = Literal["observed", "extracted", "inferred", "generated", "unknown"]

BlockKind = Literal[
    "heading", "paragraph", "list", "list_item", "table", "image", "chart",
    "figure", "caption", "footnote", "header", "footer", "link",
    "code", "quote", "form", "annotation", "shape", "slide_title",
    "speaker_note", "cell", "page_break", "other",
]


class BBoxUnit(str, Enum):
    POINTS = "points"      # PDF/typographic points; also XLSX logical units
    PX = "px"              # rendered image pixels
    EMU = "emu"            # OOXML English Metric Units
    PERCENT = "percent"    # relative layout
    NONE = "none"


@dataclass
class BBox:
    """A rectangle in source coordinates. `unit` records what x/y/w/h mean."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    unit: str = BBoxUnit.POINTS.value

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height, "unit": self.unit}

    @staticmethod
    def from_any(value: Any) -> Optional["BBox"]:
        if value is None:
            return None
        if isinstance(value, BBox):
            return value
        if isinstance(value, dict):
            try:
                return BBox(
                    float(value.get("x", 0) or 0), float(value.get("y", 0) or 0),
                    float(value.get("width", value.get("w", 0)) or 0),
                    float(value.get("height", value.get("h", 0)) or 0),
                    str(value.get("unit", BBoxUnit.POINTS.value)),
                )
            except (TypeError, ValueError):
                return None
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                x, y, w, h = (float(v) for v in value)
                return BBox(x, y, w, h)
            except (TypeError, ValueError):
                return None
        return None


@dataclass
class Provenance:
    """How one piece of the IR came to be known (per-block, spec §29/§59)."""

    method: TextMethod = "native"
    status: ExtractionStatus = "extracted"
    confidence: float = 1.0
    engine: Optional[str] = None            # e.g. "pypdfium2", "tesseract", "winocr", a model id
    stage: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TableCell:
    text: str = ""
    row: int = 0
    column: int = 0
    row_span: int = 1
    col_span: int = 1
    formula: Optional[str] = None
    value: Any = None
    bbox: Optional[BBox] = None
    provenance: Optional[Provenance] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "row": self.row, "column": self.column,
            "rowSpan": self.row_span, "colSpan": self.col_span,
            "formula": self.formula, "value": self.value,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass
class Table:
    """A table with per-cell provenance and an id stable within a document."""

    table_id: str = ""
    rows: list[list[str]] = field(default_factory=list)
    cells: list[TableCell] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    page: Optional[int] = None
    sheet: Optional[str] = None
    bbox: Optional[BBox] = None
    provenance: Optional[Provenance] = None
    caption: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tableId": self.table_id, "rows": self.rows,
            "headers": self.headers, "page": self.page, "sheet": self.sheet,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "caption": self.caption,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class Block:
    """One structural element of a page/slide/section."""

    kind: BlockKind = "paragraph"
    text: str = ""
    block_id: str = ""
    level: Optional[int] = None             # heading level
    bbox: Optional[BBox] = None
    order: int = 0
    provenance: Optional[Provenance] = None
    table_id: Optional[str] = None
    image_id: Optional[str] = None
    language: Optional[str] = None
    links: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "text": self.text, "blockId": self.block_id,
            "level": self.level, "bbox": self.bbox.to_dict() if self.bbox else None,
            "order": self.order,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "tableId": self.table_id, "imageId": self.image_id,
            "language": self.language, "links": self.links, "details": self.details,
        }


@dataclass
class DocumentImage:
    """An embedded image/figure extracted from a document."""

    image_id: str = ""
    bbox: Optional[BBox] = None
    content_type: str = "application/octet-stream"
    width: Optional[int] = None
    height: Optional[int] = None
    byte_size: int = 0
    sha256: Optional[str] = None
    asset_id: Optional[str] = None          # populated when persisted to the vision store
    page: Optional[int] = None
    slide: Optional[int] = None
    ocr_text: Optional[str] = None
    caption: Optional[str] = None
    provenance: Optional[Provenance] = None
    # Binary is kept only in-memory for the pipeline; it is never serialized into
    # the IR blob, nor indexed relationally.
    data: Optional[bytes] = field(default=None, repr=False, compare=False)

    def to_dict(self, *, include_data: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "imageId": self.image_id,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "contentType": self.content_type, "width": self.width, "height": self.height,
            "byteSize": self.byte_size, "sha256": self.sha256, "assetId": self.asset_id,
            "page": self.page, "slide": self.slide, "ocrText": self.ocr_text,
            "caption": self.caption,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }
        if include_data and self.data is not None:
            import base64

            out["dataBase64"] = base64.b64encode(self.data).decode("ascii")
        return out


@dataclass
class Page:
    """A page (PDF/DOCX-rendered/HTML) or a slide (PPTX)."""

    index: int = 0
    label: str = ""                         # e.g. slide title, section name, sheet
    width: float = 0.0
    height: float = 0.0
    unit: str = BBoxUnit.POINTS.value
    rotation: int = 0
    text: str = ""
    has_text_layer: bool = False
    blocks: list[Block] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    images: list[DocumentImage] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # speaker notes / comments
    text_method: TextMethod = "none"
    ocr_confidence: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "label": self.label,
            "width": self.width, "height": self.height, "unit": self.unit,
            "rotation": self.rotation, "text": self.text,
            "hasTextLayer": self.has_text_layer,
            "blocks": [b.to_dict() for b in self.blocks],
            "tables": [t.to_dict() for t in self.tables],
            "images": [i.to_dict() for i in self.images],
            "links": self.links, "notes": self.notes,
            "textMethod": self.text_method, "ocrConfidence": self.ocr_confidence,
            "warnings": self.warnings,
        }


@dataclass
class Sheet:
    """An XLSX/ODS/CSV worksheet as structured data (spec §12)."""

    index: int = 0
    name: str = ""
    rows: int = 0
    columns: int = 0
    hidden: bool = False
    cells: list[TableCell] = field(default_factory=list)   # sparse; only non-empty/formula cells
    merges: list[str] = field(default_factory=list)         # e.g. "A1:C1"
    named_ranges: list[dict[str, Any]] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    hidden_rows: list[int] = field(default_factory=list)
    hidden_columns: list[int] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    conditional_formats: list[dict[str, Any]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    text_method: TextMethod = "native"
    # A bounded preview of the top-left grid (values only) for cheap display.
    preview: list[list[Any]] = field(default_factory=list)
    preview_rows: int = 0
    preview_columns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "name": self.name, "rows": self.rows, "columns": self.columns,
            "hidden": self.hidden, "merges": self.merges, "namedRanges": self.named_ranges,
            "charts": self.charts, "hiddenRows": self.hidden_rows[:500],
            "hiddenColumns": self.hidden_columns[:100], "comments": self.comments[:500],
            "conditionalFormats": self.conditional_formats[:500], "links": self.links,
            "tables": [t.to_dict() for t in self.tables],
            "cells": [c.to_dict() for c in self.cells],
            "warnings": self.warnings, "textMethod": self.text_method,
            "preview": self.preview, "previewRows": self.preview_rows, "previewColumns": self.preview_columns,
        }


@dataclass
class Section:
    """A logical section (heading-bounded) for retrieval and structure."""

    section_id: str = ""
    title: str = ""
    level: int = 1
    page: Optional[int] = None
    path: list[str] = field(default_factory=list)   # heading breadcrumb
    block_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DateFacts:
    """Point-in-time metadata (spec §30) — mandatory for financial use cases."""

    publication_date: Optional[str] = None
    filing_date: Optional[str] = None
    effective_date: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    retrieved_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentIR:
    """The unified intermediate representation of one parsed document version."""

    document_id: str = ""
    version: int = 1
    kind: str = "unknown"
    mime_type: str = "application/octet-stream"
    title: Optional[str] = None
    file_name: Optional[str] = None
    sha256: str = ""
    content_hash: str = ""
    byte_size: int = 0
    page_count: int = 0
    sheet_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    dates: DateFacts = field(default_factory=DateFacts)
    pages: list[Page] = field(default_factory=list)
    sheets: list[Sheet] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    images: list[DocumentImage] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    # The overall extraction method: the weakest essential stage, so a partially
    # OCR'd document is never reported as fully native.
    text_method: TextMethod = "none"
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    parser: str = "unknown"
    created_at: str = ""

    # ── derived helpers ────────────────────────────────────────────────────────

    def all_blocks(self) -> list[tuple[int, Block]]:
        out: list[tuple[int, Block]] = []
        for page in self.pages:
            for block in page.blocks:
                out.append((page.index, block))
        for sheet in self.sheets:
            for table in sheet.tables:
                for row in table.cells:
                    out.append((sheet.index, Block(
                        kind="cell", text=row.text, block_id=f"{table.table_id}:{row.row}:{row.column}",
                        provenance=row.provenance, bbox=row.bbox,
                        details={"sheet": sheet.name, "tableId": table.table_id},
                    )))
        return out

    def plain_text(self, *, limit: int = 200_000) -> str:
        parts: list[str] = []
        total = 0
        for page in self.pages:
            if page.text:
                parts.append(page.text)
                total += len(page.text)
        for sheet in self.sheets:
            for table in sheet.tables:
                for row in table.rows:
                    line = "\t".join(row)
                    if line.strip():
                        parts.append(line)
                        total += len(line)
            if total >= limit:
                break
        joined = "\n".join(parts)
        return joined[:limit]

    def to_dict(self, *, include_image_data: bool = False) -> dict[str, Any]:
        return {
            "type": "document_ir",
            "documentId": self.document_id, "version": self.version, "kind": self.kind,
            "mimeType": self.mime_type, "title": self.title, "fileName": self.file_name,
            "sha256": self.sha256, "contentHash": self.content_hash, "byteSize": self.byte_size,
            "pageCount": self.page_count, "sheetCount": self.sheet_count,
            "metadata": self.metadata, "dates": self.dates.to_dict(),
            "pages": [p.to_dict() for p in self.pages],
            "sheets": [s.to_dict() for s in self.sheets],
            "sections": [s.to_dict() for s in self.sections],
            "tables": [t.to_dict() for t in self.tables],
            "images": [i.to_dict(include_data=include_image_data) for i in self.images],
            "links": self.links[:500], "entities": self.entities[:500],
            "textMethod": self.text_method, "confidence": round(self.confidence, 3),
            "warnings": self.warnings, "parser": self.parser, "createdAt": self.created_at,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DocumentIR":
        """Rehydrate an IR from its dict (best-effort; missing fields default).

        Image binaries are intentionally not restored — the IR blob on disk keeps
        metadata only; the asset store holds the bytes.
        """
        if not isinstance(payload, dict):
            raise ValueError("a document IR dict is required")

        def _bbox(value: Any) -> Optional[BBox]:
            return BBox.from_any(value)

        def _prov(value: Any) -> Optional[Provenance]:
            if not isinstance(value, dict):
                return None
            return Provenance(
                method=value.get("method", "native"), status=value.get("status", "extracted"),
                confidence=float(value.get("confidence", 1.0) or 0.0),
                engine=value.get("engine"), stage=value.get("stage"), details=value.get("details") or {},
            )

        pages: list[Page] = []
        for p in payload.get("pages", []) or []:
            if not isinstance(p, dict):
                continue
            blocks = [
                Block(
                    kind=b.get("kind", "paragraph"), text=b.get("text", ""),
                    block_id=b.get("blockId", ""), level=b.get("level"), bbox=_bbox(b.get("bbox")),
                    order=int(b.get("order", 0) or 0), provenance=_prov(b.get("provenance")),
                    table_id=b.get("tableId"), image_id=b.get("imageId"),
                    language=b.get("language"), links=b.get("links") or [], details=b.get("details") or {},
                )
                for b in (p.get("blocks") or []) if isinstance(b, dict)
            ]
            tables = [_table_from_dict(t) for t in (p.get("tables") or []) if isinstance(t, dict)]
            images = [
                DocumentImage(
                    image_id=i.get("imageId", ""), bbox=_bbox(i.get("bbox")),
                    content_type=i.get("contentType", "application/octet-stream"),
                    width=i.get("width"), height=i.get("height"), byte_size=int(i.get("byteSize", 0) or 0),
                    sha256=i.get("sha256"), asset_id=i.get("assetId"), page=i.get("page"),
                    slide=i.get("slide"), ocr_text=i.get("ocrText"), caption=i.get("caption"),
                    provenance=_prov(i.get("provenance")),
                )
                for i in (p.get("images") or []) if isinstance(i, dict)
            ]
            pages.append(Page(
                index=int(p.get("index", 0) or 0), label=p.get("label", ""),
                width=float(p.get("width", 0) or 0), height=float(p.get("height", 0) or 0),
                unit=p.get("unit", BBoxUnit.POINTS.value), rotation=int(p.get("rotation", 0) or 0),
                text=p.get("text", ""), has_text_layer=bool(p.get("hasTextLayer")),
                blocks=blocks, tables=tables, images=images, links=p.get("links") or [],
                notes=p.get("notes") or [], text_method=p.get("textMethod", "none"),
                ocr_confidence=p.get("ocrConfidence"), warnings=p.get("warnings") or [],
            ))
        sheets: list[Sheet] = []
        for s in payload.get("sheets", []) or []:
            if not isinstance(s, dict):
                continue
            sheets.append(Sheet(
                index=int(s.get("index", 0) or 0), name=s.get("name", ""),
                rows=int(s.get("rows", 0) or 0), columns=int(s.get("columns", 0) or 0),
                hidden=bool(s.get("hidden")), merges=s.get("merges") or [],
                named_ranges=s.get("namedRanges") or [],
                tables=[_table_from_dict(t) for t in (s.get("tables") or []) if isinstance(t, dict)],
                charts=s.get("charts") or [], hidden_rows=s.get("hiddenRows") or [],
                hidden_columns=s.get("hiddenColumns") or [], comments=s.get("comments") or [],
                conditional_formats=s.get("conditionalFormats") or [], links=s.get("links") or [],
                warnings=s.get("warnings") or [], text_method=s.get("textMethod", "native"),
                preview=s.get("preview") or [], preview_rows=int(s.get("previewRows", 0) or 0),
                preview_columns=int(s.get("previewColumns", 0) or 0),
                cells=[_cell_from_dict(c) for c in (s.get("cells") or []) if isinstance(c, dict)],
            ))
        sections = [
            Section(
                section_id=sec.get("section_id", sec.get("sectionId", "")), title=sec.get("title", ""),
                level=int(sec.get("level", 1) or 1), page=sec.get("page"),
                path=sec.get("path") or [], block_ids=sec.get("block_ids", sec.get("blockIds", [])) or [],
            )
            for sec in (payload.get("sections") or []) if isinstance(sec, dict)
        ]
        dates = payload.get("dates") or {}
        return DocumentIR(
            document_id=payload.get("documentId", ""), version=int(payload.get("version", 1) or 1),
            kind=payload.get("kind", "unknown"), mime_type=payload.get("mimeType", "application/octet-stream"),
            title=payload.get("title"), file_name=payload.get("fileName"),
            sha256=payload.get("sha256", ""), content_hash=payload.get("contentHash", ""),
            byte_size=int(payload.get("byteSize", 0) or 0), page_count=int(payload.get("pageCount", 0) or 0),
            sheet_count=int(payload.get("sheetCount", 0) or 0), metadata=payload.get("metadata") or {},
            dates=DateFacts(**{k: dates.get(k) for k in (
                "publication_date", "filing_date", "effective_date", "period_start", "period_end", "retrieved_at"
            )}) if isinstance(dates, dict) else DateFacts(),
            pages=pages, sheets=sheets, sections=sections,
            tables=[_table_from_dict(t) for t in (payload.get("tables") or []) if isinstance(t, dict)],
            images=[
                DocumentImage(
                    image_id=i.get("imageId", ""), bbox=_bbox(i.get("bbox")),
                    content_type=i.get("contentType", "application/octet-stream"),
                    width=i.get("width"), height=i.get("height"), byte_size=int(i.get("byteSize", 0) or 0),
                    sha256=i.get("sha256"), asset_id=i.get("assetId"), page=i.get("page"),
                    slide=i.get("slide"), ocr_text=i.get("ocrText"), caption=i.get("caption"),
                )
                for i in (payload.get("images") or []) if isinstance(i, dict)
            ],
            links=payload.get("links") or [], entities=payload.get("entities") or [],
            text_method=payload.get("textMethod", "none"),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            warnings=payload.get("warnings") or [], parser=payload.get("parser", "unknown"),
            created_at=payload.get("createdAt", ""),
        )


def _cell_from_dict(value: dict[str, Any]) -> TableCell:
    return TableCell(
        text=value.get("text", ""), row=int(value.get("row", 0) or 0), column=int(value.get("column", 0) or 0),
        row_span=int(value.get("rowSpan", 1) or 1), col_span=int(value.get("colSpan", 1) or 1),
        formula=value.get("formula"), value=value.get("value"),
        bbox=BBox.from_any(value.get("bbox")),
        provenance=Provenance(**value["provenance"]) if isinstance(value.get("provenance"), dict) else None,
    )


def _table_from_dict(value: dict[str, Any]) -> Table:
    return Table(
        table_id=value.get("tableId", ""), rows=value.get("rows") or [],
        headers=value.get("headers") or [], page=value.get("page"), sheet=value.get("sheet"),
        bbox=BBox.from_any(value.get("bbox")),
        provenance=Provenance(**value["provenance"]) if isinstance(value.get("provenance"), dict) else None,
        caption=value.get("caption"),
        cells=[_cell_from_dict(c) for c in (value.get("cells") or []) if isinstance(c, dict)],
    )


# ── identity helpers ────────────────────────────────────────────────────────────

def content_hash(data: bytes) -> str:
    """SHA-256 of raw document bytes (the dedup / cache identity)."""
    return "doc_" + hashlib.sha256(data).hexdigest()


def block_id(document_id: str, page_index: int, order: int, *, kind: str = "b") -> str:
    return f"{kind}_{document_id[:8]}_{page_index}_{order}"


def compute_overall_text_method(pages: list[Page], sheets: list[Sheet]) -> TextMethod:
    """The weakest essential method, so a partly-OCR'd doc is not called native."""
    methods: set[str] = set()
    for page in pages:
        if page.text.strip() or page.blocks:
            methods.add(page.text_method)
    for sheet in sheets:
        if sheet.rows:
            methods.add(sheet.text_method)
    if not methods:
        return "none"
    if "vision" in methods and "native" not in methods and "ocr" not in methods:
        return "vision"
    if "ocr" in methods and methods <= {"ocr", "none"}:
        return "ocr"
    if "native" in methods and len(methods) == 1:
        return "native"
    # Mixed: report the least certain method present so confidence is honest.
    for m in ("vision", "ocr", "none", "native"):
        if m in methods:
            return m  # type: ignore[return-value]
    return "native"


__all__ = [
    "DocumentIR", "Page", "Sheet", "Block", "Table", "TableCell", "DocumentImage",
    "Section", "BBox", "Provenance", "DateFacts", "BBoxUnit",
    "DocumentKind", "TextMethod", "ExtractionStatus", "BlockKind",
    "content_hash", "block_id", "compute_overall_text_method",
]
