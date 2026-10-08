"""Document → Evidence bridge (spec §29/§41/§59).

Every extracted fact that carries text and a locator can become the SAME
`research.web_contracts.Evidence` object the web research engine uses, persisted
through `EvidenceStore.save_evidence` with full provenance (document, version,
page, section, block, table, cell, sheet, method, confidence). This is how a
document claim flows into the one Evidence & Research Engine — there is no second
knowledge graph.

Chunks are the unit: each chunk becomes one Evidence item, and a chunk's locator
is preserved verbatim so an answer can cite document/page/table/cell.
"""

from __future__ import annotations

from typing import Any, Optional

from .ir import DocumentIR

MAX_EVIDENCE_PER_DOCUMENT = 800


def _source_url(document_id: str, *, kind: str = "document", name: str = "") -> str:
    ref = name or document_id
    return f"document://{ref.replace(chr(92), '/')}"


def record_document_evidence(
    store: Any,
    chunks: list[Any],
    ir: DocumentIR,
    *,
    research_id: Optional[str] = None,
) -> list[str]:
    """Persist document chunks as Evidence. Returns the evidence ids written."""
    if store is None or not chunks:
        return []
    try:
        from ..research.web_contracts import Evidence, content_hash, evidence_id, source_id  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []

    url = _source_url(ir.document_id, name=ir.file_name or "")
    sid = source_id(url)
    try:
        store.save_source(
            {
                "sourceId": sid, "canonicalUrl": url, "domain": "document",
                "publisher": ir.parser, "sourceType": "unknown",
                "retrievedAt": ir.dates.retrieved_at, "contentHash": ir.content_hash,
            },
            research_id=research_id,
        )
    except Exception:  # noqa: BLE001
        pass

    ids: list[str] = []
    for chunk in chunks[:MAX_EVIDENCE_PER_DOCUMENT]:
        text = (chunk.text or "").strip()
        if not text:
            continue
        try:
            ev = Evidence(
                evidenceId=evidence_id(source_url=url, raw_text=text, page=chunk.page),
                sourceId=sid, sourceUrl=url, sourceType="unknown", publisher=ir.parser,
                documentId=ir.document_id, page=chunk.page, section=chunk.section,
                rawText=text, contentHash=content_hash(text), confidence=float(chunk.confidence or 0.5),
                contentTrust="UNTRUSTED",
                provenance={
                    "documentId": ir.document_id, "version": ir.version, "page": chunk.page,
                    "section": chunk.section, "blockId": chunk.block_id, "tableId": chunk.table_id,
                    "cell": chunk.cell, "sheet": chunk.sheet, "chunkId": chunk.chunk_id,
                    "method": chunk.method, "kind": chunk.kind, "parser": ir.parser,
                    "extractionMethod": chunk.method,
                },
            )
            store.save_evidence(ev.model_dump(), research_id=research_id)
            ids.append(ev.evidenceId)
        except Exception:  # noqa: BLE001 - one bad chunk must not stop the rest
            continue
    return ids


def evidence_for_hit(chunk: Any, ir: DocumentIR) -> dict[str, Any]:
    """Build the citation-shaped provenance for one retrieval hit."""
    return {
        "claim": (chunk.text or "")[:400],
        "source": {
            "documentId": ir.document_id, "version": ir.version, "fileName": ir.file_name,
            "page": chunk.page, "section": chunk.section, "blockId": chunk.block_id,
            "tableId": chunk.table_id, "cell": chunk.cell, "sheet": chunk.sheet,
        },
        "extraction": {"method": chunk.method, "confidence": chunk.confidence},
    }


__all__ = ["record_document_evidence", "evidence_for_hit", "MAX_EVIDENCE_PER_DOCUMENT"]
