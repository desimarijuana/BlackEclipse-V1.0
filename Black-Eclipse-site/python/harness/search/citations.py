"""Citations and the Evidence bridge.

Every hit can produce a citation; a hit can also be written into the research
``EvidenceStore`` so search-derived passages participate in the Evidence &
Research engine's provenance graph, conflict detection and claim verification.
"""

from __future__ import annotations

from typing import Any, Optional

from .contracts import SearchHit

MAX_EVIDENCE_PER_RESULT = 200


def render_citations(hits: list[SearchHit]) -> str:
    blocks = []
    for index, hit in enumerate(hits, start=1):
        blocks.append(f"[{index}] {hit.citation.render()}")
    return "\n\n".join(blocks)


def hit_to_evidence(hit: SearchHit) -> Optional[dict[str, Any]]:
    """Map a hit to the research Evidence contract (best-effort)."""
    try:
        from ..research.web_contracts import (  # noqa: PLC0415
            content_hash,
            evidence_id,
            source_id,
        )
    except Exception:  # noqa: BLE001
        return None
    url = hit.provenance.uri or f"search://{hit.provenance.source_type or 'index'}/{hit.provenance.source_id or hit.document_id}"
    sid = source_id(url)
    return {
        "evidenceId": evidence_id(source_url=url, raw_text=hit.content, page=hit.provenance.page),
        "sourceId": sid,
        "sourceUrl": url,
        "sourceType": hit.provenance.source_type or "unknown",
        "publisher": hit.provenance.publisher,
        "documentId": hit.document_id,
        "page": hit.provenance.page,
        "section": hit.provenance.section,
        "publishedAt": hit.published_at,
        "retrievedAt": hit.retrieved_at,
        "effectiveAt": hit.effective_at,
        "rawText": hit.content,
        "contentHash": content_hash(hit.content),
        "confidence": min(1.0, max(0.0, hit.score)),
        "contentTrust": "UNTRUSTED",
        "provenance": {
            "chunkId": hit.chunk_id,
            "documentId": hit.document_id,
            "method": "vector_search",
            "vectorScore": hit.vector_score,
            "keywordScore": hit.keyword_score,
            "rerankScore": hit.rerank_score,
            "searchSource": hit.provenance.source_type,
        },
    }


def record_hits_as_evidence(store: Any, hits: list[SearchHit], *, research_id: Optional[str] = None) -> list[str]:
    """Persist hits as Evidence. Returns the evidence ids written."""
    if store is None or not hits:
        return []
    ids: list[str] = []
    for hit in hits[:MAX_EVIDENCE_PER_RESULT]:
        evidence = hit_to_evidence(hit)
        if evidence is None:
            return []
        try:
            store.save_evidence(evidence, research_id=research_id)
            ids.append(evidence["evidenceId"])
        except Exception:  # noqa: BLE001 - one bad hit must not stop the rest
            continue
    return ids


__all__ = ["MAX_EVIDENCE_PER_RESULT", "hit_to_evidence", "record_hits_as_evidence", "render_citations"]
