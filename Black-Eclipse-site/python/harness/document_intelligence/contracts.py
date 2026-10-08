"""Public IR contracts for the document intelligence subsystem."""

from __future__ import annotations

from .ir import (
    BBox,
    BBoxUnit,
    Block,
    BlockKind,
    DateFacts,
    DocumentIR,
    DocumentImage,
    DocumentKind,
    ExtractionStatus,
    Page,
    Provenance,
    Section,
    Sheet,
    Table,
    TableCell,
    TextMethod,
    block_id,
    compute_overall_text_method,
    content_hash,
)

__all__ = [
    "BBox", "BBoxUnit", "Block", "BlockKind", "DateFacts", "DocumentIR", "DocumentImage",
    "DocumentKind", "ExtractionStatus", "Page", "Provenance", "Section", "Sheet",
    "Table", "TableCell", "TextMethod", "block_id", "compute_overall_text_method", "content_hash",
]
