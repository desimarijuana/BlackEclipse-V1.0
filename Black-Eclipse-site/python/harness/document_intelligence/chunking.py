"""Chunking — split a DocumentIR into retrieval units with full locators.

A chunk is a bounded span of text plus everything needed to cite it: document,
version, page, section, block, table, cell, sheet. Chunks never cross a table
boundary silently and always keep the block's provenance. Large tables are
chunked row-wise; a spreadsheet cell run becomes a chunk keyed by sheet+cell.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import DocumentConfig, document_config
from .ir import Block, DocumentIR, Provenance


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    version: int
    text: str
    kind: str = "paragraph"
    page: Optional[int] = None
    sheet: Optional[str] = None
    section: Optional[str] = None
    block_id: Optional[str] = None
    table_id: Optional[str] = None
    cell: Optional[str] = None
    order: int = 0
    bbox: Optional[list[float]] = None
    method: str = "native"
    confidence: float = 1.0
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunkId": self.chunk_id, "documentId": self.document_id, "version": self.version,
            "text": self.text, "kind": self.kind, "page": self.page, "sheet": self.sheet,
            "section": self.section, "blockId": self.block_id, "tableId": self.table_id,
            "cell": self.cell, "order": self.order, "bbox": self.bbox, "method": self.method,
            "confidence": self.confidence, "contentHash": self.content_hash,
        }


def _digest(text: str) -> str:
    return "chk_" + hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:32]


def chunk_ir(ir: DocumentIR, *, cfg: Optional[DocumentConfig] = None) -> list[Chunk]:
    cfg = cfg or document_config()
    target = max(200, cfg.chunk_target_chars)
    overlap = max(0, min(cfg.chunk_overlap_chars, target // 2))
    chunks: list[Chunk] = []
    counter = 0

    # Section lookup by block id.
    block_section: dict[str, str] = {}
    for section in ir.sections:
        for block_id in section.block_ids:
            block_section[block_id] = section.title

    for page in ir.pages:
        section_for_page = _page_section(page, ir)
        blocks = page.blocks
        if not blocks and page.text.strip():
            # A page whose text never became discrete blocks (some structured
            # formats) is still chunked, so nothing extracted is unsearchable.
            blocks = [Block(kind="paragraph", text=page.text, block_id=f"p{page.index}",
                            provenance=Provenance(method=page.text_method))]
        for block in blocks:
            if not block.text.strip():
                continue
            section = block_section.get(block.block_id) or section_for_page
            for piece in _split(block.text, target, overlap):
                counter += 1
                chunks.append(Chunk(
                    chunk_id=f"{ir.document_id[:12]}_c{counter}", document_id=ir.document_id,
                    version=ir.version, text=piece, kind=block.kind, page=page.index,
                    section=section, block_id=block.block_id, order=counter,
                    bbox=block.bbox.to_list() if block.bbox else None,
                    method=(block.provenance.method if block.provenance else page.text_method),
                    confidence=(block.provenance.confidence if block.provenance else 0.9),
                    content_hash=_digest(piece),
                ))
        # Tables: one chunk per row-group, with the page's section.
        for table in page.tables:
            chunks.extend(_table_chunks(ir, table, page.index, None, section_for_page, counter, target))
            counter = chunks[-1].order if chunks else counter

    for sheet in ir.sheets:
        for table in sheet.tables:
            header = " | ".join(table.headers)
            rows_per_chunk = max(1, target // max(20, len(header) + 10))
            for start in range(0, len(table.rows), rows_per_chunk):
                block_rows = table.rows[start:start + rows_per_chunk]
                text = "\n".join(" | ".join(r) for r in block_rows)
                if not text.strip():
                    continue
                counter += 1
                first_cell = _cell_ref(start, 0)
                chunks.append(Chunk(
                    chunk_id=f"{ir.document_id[:12]}_c{counter}", document_id=ir.document_id,
                    version=ir.version, text=f"{sheet.name}\n{header}\n{text}", kind="table_row",
                    sheet=sheet.name, table_id=table.table_id, cell=first_cell, order=counter,
                    method="native", confidence=0.95, content_hash=_digest(text),
                ))
        # Individual formula cells are cited precisely.
        for cell in sheet.cells:
            if cell.formula:
                text = f"{sheet.name}!{_cell_ref(cell.row, cell.column)}: {cell.text} (formula {cell.formula})"
                counter += 1
                chunks.append(Chunk(
                    chunk_id=f"{ir.document_id[:12]}_c{counter}", document_id=ir.document_id,
                    version=ir.version, text=text, kind="formula", sheet=sheet.name,
                    cell=_cell_ref(cell.row, cell.column), order=counter,
                    method="native", confidence=0.98, content_hash=_digest(text),
                ))
    return chunks


def _table_chunks(ir: DocumentIR, table: Any, page: int, sheet: Optional[str], section: Optional[str],
                  counter: int, target: int) -> list[Chunk]:
    out: list[Chunk] = []
    header = " | ".join(table.headers) if table.headers else ""
    rows_per_chunk = max(1, target // max(20, len(header) + 10))
    for start in range(0, len(table.rows), rows_per_chunk):
        block_rows = table.rows[start:start + rows_per_chunk]
        text = "\n".join(" | ".join(r) for r in block_rows)
        if not text.strip():
            continue
        counter += 1
        out.append(Chunk(
            chunk_id=f"{ir.document_id[:12]}_c{counter}", document_id=ir.document_id, version=ir.version,
            text=(f"{header}\n{text}" if header else text), kind="table", page=page, sheet=sheet,
            section=section, table_id=table.table_id, order=counter, method="native", confidence=0.9,
            content_hash=_digest(text),
        ))
    return out


def _page_section(page: Any, ir: DocumentIR) -> Optional[str]:
    for section in ir.sections:
        if section.page == page.index:
            return section.title
    return None


def _split(text: str, target: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= target:
        return [text] if text else []
    pieces: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + target)
        if end < n:
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + target // 2:
                end = boundary + 1
        pieces.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def _cell_ref(row: int, col: int) -> str:
    letters = ""
    col0 = col
    while True:
        letters = chr(65 + col0 % 26) + letters
        col0 = col0 // 26 - 1
        if col0 < 0:
            break
    return f"{letters}{row + 1}"


__all__ = ["Chunk", "chunk_ir", "_cell_ref"]
