"""Indexing pipeline.

    Document -> chunk -> embed (batched, cached) -> vectors + FTS -> INDEXED

Indexing is idempotent (upsert by ids), deduplicates identical content by hash,
and records explicit states (PENDING/PROCESSING/INDEXED/FAILED/RETRYING). A
failure is observable and never silently swallowed. Embedding is best-effort:
when no provider is available the document is still keyword-indexed and the
result reports ``vectorsMissing`` honestly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .config import SearchConfig
from .contracts import DocumentRecord, IndexState
from .embeddings.service import EmbeddingService
from .errors import SearchError
from .store import SearchIndexStore


@dataclass
class IndexResult:
    document_id: str
    state: str
    chunks: int = 0
    vectors: int = 0
    missing_vectors: int = 0
    deduplicated: bool = False
    unchanged: bool = False
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "documentId": self.document_id,
            "state": self.state,
            "chunks": self.chunks,
            "vectors": self.vectors,
            "missingVectors": self.missing_vectors,
            "deduplicated": self.deduplicated,
            "unchanged": self.unchanged,
            "error": self.error,
            "warnings": self.warnings,
        }


def content_hash_of(doc: DocumentRecord) -> str:
    material = "\n".join(c.content for c in doc.chunks)
    if not material:
        material = f"{doc.title}|{doc.description}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def index_document(
    store: SearchIndexStore,
    embedder: EmbeddingService,
    doc: DocumentRecord,
    *,
    config: SearchConfig,
    skip_dedup: bool = False,
    force: bool = False,
) -> IndexResult:
    result = IndexResult(document_id=doc.document_id, state=IndexState.PROCESSING.value)
    if not doc.chunks:
        result.state = IndexState.FAILED.value
        result.error = "document has no chunks"
        store.upsert_document(doc, state=IndexState.FAILED.value)
        store.set_document_state(doc.document_id, IndexState.FAILED.value, error=result.error)
        return result

    if not doc.content_hash:
        doc.content_hash = content_hash_of(doc)

    # Incremental re-index: identical content already INDEXED under the SAME id
    # is left untouched (no re-embedding), so a bulk re-index only pays for what
    # changed. `force=True` overrides this.
    existing_same = store.get_document(doc.document_id)
    want_vectors = embedder.available
    same_state = existing_same is not None and existing_same.get("state")
    skippable_state = same_state == IndexState.INDEXED.value or (
        # A keyword-only (STALE) document is already complete while no embedding
        # provider is available; when one appears it is re-indexed to add vectors.
        same_state == IndexState.STALE.value and not want_vectors
    )
    if (
        not force
        and existing_same is not None
        and existing_same.get("contentHash") == doc.content_hash
        and skippable_state
    ):
        result.state = same_state or IndexState.INDEXED.value
        result.unchanged = True
        result.chunks = int(existing_same.get("chunkCount") or 0)
        return result

    # Dedup: identical content already indexed under a different id ⇒ do not
    # create duplicate vectors. Idempotent re-index of the same id proceeds.
    if not skip_dedup:
        existing = store.find_by_content_hash(doc.content_hash)
        if existing and existing["documentId"] != doc.document_id and existing["state"] == IndexState.INDEXED.value:
            store.upsert_document(doc, state=IndexState.INDEXED.value)
            store.set_document_state(doc.document_id, IndexState.INDEXED.value, indexed_at=existing.get("indexedAt"),
                                     chunk_count=existing.get("chunkCount") or 0)
            result.state = IndexState.INDEXED.value
            result.deduplicated = True
            result.warnings.append("identical content already indexed; vectors reused")
            return result

    store.upsert_document(doc, state=IndexState.PROCESSING.value)
    try:
        store.save_sections(doc.sections)
        saved = store.save_chunks(doc.chunks)
        result.chunks = saved
    except Exception as exc:  # noqa: BLE001 - a storage failure is a FAILED state, never a crash
        result.state = IndexState.FAILED.value
        result.error = str(exc)
        store.set_document_state(doc.document_id, IndexState.FAILED.value, error=result.error)
        return result

    if embedder.available:
        try:
            outcome = await embedder.embed_texts([c.content for c in doc.chunks])
            entries = [
                (chunk.chunk_id, vector)
                for chunk, vector in zip(doc.chunks, outcome.vectors)
                if vector is not None
            ]
            if entries:
                acl = store.acl_keys(doc.visibility, doc.workspace_id, doc.owner_id)
                result.vectors = store.store_vectors(
                    entries,
                    model_key=embedder.model_key(),
                    provider=embedder.provider_id,
                    model=embedder.model_id,
                    version=embedder.version,
                    dims=embedder.dimensions or len(entries[0][1]),
                    acl_by_chunk={cid: acl for cid, _ in entries},
                )
            result.missing_vectors = len(doc.chunks) - len(entries)
        except SearchError as exc:
            result.warnings.append(f"embedding failed: {exc.message}")
            result.missing_vectors = len(doc.chunks)
    else:
        result.warnings.append(f"keyword-only index: {embedder.reason}")
        result.missing_vectors = len(doc.chunks)

    state = IndexState.INDEXED.value if result.missing_vectors == 0 else IndexState.STALE.value
    result.state = state
    from ..persistence import now_iso

    store.set_document_state(doc.document_id, state, indexed_at=now_iso(), chunk_count=result.chunks)
    return result


async def reindex_document(
    store: SearchIndexStore, embedder: EmbeddingService, document_id: str, *, config: SearchConfig,
    reembed: bool = False,
) -> IndexResult:
    """Re-embed an already-indexed document from its stored chunks."""
    result = IndexResult(document_id=document_id, state=IndexState.PROCESSING.value)
    document = store.get_document(document_id)
    if document is None:
        result.state = IndexState.FAILED.value
        result.error = "document not found"
        return result
    chunks = store.list_chunks(document_id)
    if not chunks:
        result.state = IndexState.FAILED.value
        result.error = "document has no stored chunks"
        return result
    if not embedder.available:
        result.state = IndexState.FAILED.value
        result.error = f"embedding unavailable: {embedder.reason}"
        return result
    if reembed and embedder.model_key():
        store.delete_vectors_for_model(embedder.model_key())
    outcome = await embedder.embed_texts([c["content"] for c in chunks])
    entries = [
        (chunk["chunkId"], vector) for chunk, vector in zip(chunks, outcome.vectors) if vector is not None
    ]
    if entries:
        acl = store.acl_keys(
            document.get("visibility") or "public", document.get("workspaceId"), document.get("ownerId")
        )
        result.vectors = store.store_vectors(
            entries,
            model_key=embedder.model_key(),
            provider=embedder.provider_id,
            model=embedder.model_id,
            version=embedder.version,
            dims=embedder.dimensions or len(entries[0][1]),
            acl_by_chunk={cid: acl for cid, _ in entries},
        )
    result.chunks = len(chunks)
    result.missing_vectors = len(chunks) - len(entries)
    result.state = IndexState.INDEXED.value if result.missing_vectors == 0 else IndexState.STALE.value
    from ..persistence import now_iso

    store.set_document_state(document_id, result.state, indexed_at=now_iso(), chunk_count=result.chunks)
    return result


__all__ = ["IndexResult", "content_hash_of", "index_document", "reindex_document"]
