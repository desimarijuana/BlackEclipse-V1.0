"""ANN (sqlite-vec) backend tests.

The vector store uses a real sqlite-vec `vec0` index when the extension is
available, restricted to the caller's authorization buckets BEFORE scoring.
These tests skip cleanly when the extension is absent (the layer then falls back
to brute-force cosine, which the other retrieval tests cover).
"""

from __future__ import annotations

import pytest

from harness.search.contracts import SearchRequest, SearchScope

from search_helpers import FakeEmbeddingProvider, instrument, make_service

pytest.importorskip("sqlite_vec")


async def _seed(service):
    await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand. Cloud growth accelerated.",
        title="NVDA", source_type="filing", source_id="nvda", namespace="filing",
    )
    await service.ingest_text(
        "Tesla margins compressed due to pricing pressure and product mix shifts.",
        title="TSLA", source_type="filing", source_id="tsla", namespace="filing",
    )


@pytest.mark.asyncio
async def test_ann_backend_active_and_table_created():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await _seed(service)
    assert service.store.vec_available is True
    assert service.store.ann_available_for(service.embedder.model_key())


@pytest.mark.asyncio
async def test_ann_search_returns_authorized_matches():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await _seed(service)
    query = await service.embedder.embed_query("nvidia revenue")
    results = service.store.ann_search(query, service.embedder.model_key(), ["public"], 5)
    assert results
    assert results[0][0].startswith("filing:nvda")
    # cosine similarity in a sane range
    assert -1.0 <= results[0][1] <= 1.0


@pytest.mark.asyncio
async def test_ann_matches_bruteforce_topk():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await _seed(service)
    result = await service.semantic("nvidia revenue")
    ann_top = result.hits[0].chunk_id

    # Force the brute-force path and compare the top hit.
    service.store.vec_available = False
    brute = await service.semantic("nvidia revenue")
    assert brute.hits[0].chunk_id == ann_top


@pytest.mark.asyncio
async def test_ann_respects_scope_and_never_leaks():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    from harness.search.contracts import ChunkRecord, DocumentRecord

    private = DocumentRecord(
        document_id="ws-a-doc", source_type="filing", source_id="a", namespace="filing",
        title="A secret", visibility="workspace", workspace_id="wsA",
        chunks=[ChunkRecord(chunk_id="ws-a-doc:0", content="secret alpha revenue growth", document_id="ws-a-doc")],
    )
    await service.index_documents([private])
    allowed = await service.semantic("secret alpha revenue", scope=SearchScope(workspace_id="wsA", visibilities=("public", "workspace")))
    denied = await service.semantic("secret alpha revenue", scope=SearchScope(workspace_id="wsB", visibilities=("public", "workspace")))
    assert allowed.hits and not denied.hits


@pytest.mark.asyncio
async def test_bruteforce_fallback_when_ann_disabled():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await _seed(service)
    service.store.vec_available = False
    result = await service.semantic("nvidia revenue")
    assert result.hits


@pytest.mark.asyncio
async def test_rebuild_ann_from_vectors():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await _seed(service)
    # Drop ANN rows and rebuild from the canonical SearchVector table.
    for meta in service.store.connection.execute("SELECT tableName FROM SearchVectorAnnMeta").fetchall():
        service.store.connection.execute(f"DELETE FROM {meta['tableName']}")
    rebuilt = service.store.rebuild_ann()
    assert rebuilt >= 2
    assert service.store.ann_search(
        await service.embedder.embed_query("nvidia"), service.embedder.model_key(), ["public"], 5
    )


@pytest.mark.asyncio
async def test_dimension_mismatch_refused():
    from harness.search.errors import SearchStoreError

    service, _ = make_service(rerank_enabled=False)
    assert service.store.vec_available
    service.store._ensure_ann_table("space/x", 8)
    with pytest.raises(SearchStoreError):
        service.store._ensure_ann_table("space/x", 16)
