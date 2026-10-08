"""Store, retrieval, security and service integration tests."""

from __future__ import annotations

import asyncio
import os
import sqlite3

import pytest

from harness.search.contracts import (
    ChunkRecord,
    DocumentRecord,
    MetadataFilter,
    SearchMode,
    SearchRequest,
    SearchScope,
    TemporalFilter,
)
from harness.search.store import SearchIndexStore, scope_clause

from search_helpers import FakeEmbeddingProvider, instrument, make_document, make_service


async def _seed(service, provider):
    instrument(service, provider)
    await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand. Cloud growth accelerated.",
        title="NVDA 10-K", source_type="filing", source_id="nvda-10k", namespace="filing",
        published_at="2026-02-21", entity_type="company", entity_id="NVDA",
    )
    await service.ingest_text(
        "Tesla margins compressed due to pricing pressure and product mix shifts.",
        title="TSLA 10-Q", source_type="filing", source_id="tsla-10q", namespace="filing",
        published_at="2025-04-01", entity_type="company", entity_id="TSLA",
    )


def test_store_roundtrip_and_scope(tmp_path):
    store = SearchIndexStore(str(tmp_path / "s.db"))
    doc = make_document("d1", ["hello world"], namespace="x", title="T")
    store.upsert_document(doc, state="INDEXED")
    store.save_chunks(doc.chunks)
    assert store.get_document("d1")["title"] == "T"
    assert store.list_chunks("d1")[0]["content"] == "hello world"
    assert store.integrity_ok()
    store.close()


def test_scope_clause_operator_and_scoped():
    sql, params = scope_clause(SearchScope(is_operator=True))
    assert sql == "1=1" and params == []
    sql, params = scope_clause(SearchScope(workspace_id="wsA", visibilities=("public", "workspace")))
    assert "public" in sql
    assert "wsA" in params


@pytest.mark.asyncio
async def test_hybrid_semantic_keyword_modes():
    service, _ = make_service(rerank_enabled=False)
    provider = FakeEmbeddingProvider()
    await _seed(service, provider)

    semantic = await service.semantic("nvidia ai revenue")
    assert semantic.hits and semantic.hits[0].citation.label.startswith("NVDA")

    keyword = await service.keyword("pricing pressure")
    assert keyword.hits and keyword.hits[0].citation.label.startswith("TSLA")

    hybrid = await service.hybrid("nvidia revenue")
    assert hybrid.hits


@pytest.mark.asyncio
async def test_temporal_point_in_time_excludes_future():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    req = SearchRequest(query="revenue", mode="hybrid", top_k=5,
                        temporal=TemporalFilter(as_of="2026-01-01"))
    result = await service.search(req)
    labels = {h.citation.label for h in result.hits}
    assert all("NVDA" not in label for label in labels)


@pytest.mark.asyncio
async def test_metadata_and_entity_filters():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    filtered = await service.search(
        SearchRequest(query="margins", mode="keyword", top_k=5,
                      filters=MetadataFilter(entity_id="TSLA"))
    )
    assert filtered.hits and all(h.provenance.document_id.endswith("tsla-10q") for h in filtered.hits)


@pytest.mark.asyncio
async def test_dedup_identical_content():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    # A third identical document must be deduplicated, not vectorized twice.
    result = await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand. Cloud growth accelerated.",
        title="NVDA copy", source_type="filing", source_id="nvda-copy", namespace="filing",
    )
    assert result.deduplicated is True


@pytest.mark.asyncio
async def test_neighbors_included():
    service, _ = make_service(rerank_enabled=False, context_neighbor_radius=1)
    instrument(service, FakeEmbeddingProvider())
    doc = make_document(
        "doc-n", ["alpha revenue paragraph one.", "beta margin paragraph two.", "gamma guidance three."],
        namespace="research", source_type="filing", source_id="n", title="N",
    )
    await service.index_documents([doc])
    result = await service.semantic("beta margin")
    hit = result.hits[0]
    assert hit.neighbors is not None
    assert hit.neighbors.get("previous") or hit.neighbors.get("next")


@pytest.mark.asyncio
async def test_router_does_not_force_semantic_on_numbers():
    from harness.search.router import route_query

    numeric = route_query("What was NVDA revenue FY2026?")
    assert numeric.mode == SearchMode.KEYWORD.value
    assert numeric.structured_first is True
    conceptual = route_query("What factors are driving AI infrastructure demand?")
    assert conceptual.mode == SearchMode.HYBRID.value
    assert conceptual.decompose is True


@pytest.mark.asyncio
async def test_fallback_when_embedding_unavailable():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    service.embedder._available = False
    service.embedder._provider = None
    result = await service.search(SearchRequest(query="nvidia revenue", mode="semantic", top_k=5))
    assert result.stats.semantic_available is False
    assert result.stats.fallback == "keyword"
    # Keyword-only docs are still reachable via the FTS fallback.
    assert result.hits


@pytest.mark.asyncio
async def test_debug_trace_shape():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    trace = service.debug_trace(SearchRequest(query="nvidia revenue", mode="hybrid"))
    assert trace["normalizedQuery"] == "nvidia revenue"
    assert "filterSql" in trace and "keywordCandidates" in trace


# ── Security ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workspace_isolation_all_modes():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    private = DocumentRecord(
        document_id="ws-a-doc", source_type="filing", source_id="a", namespace="filing",
        title="A secret", visibility="workspace", workspace_id="wsA",
        chunks=[ChunkRecord(chunk_id="ws-a-doc:0", content="secret alpha revenue growth", document_id="ws-a-doc")],
    )
    await service.index_documents([private])
    for mode in ("keyword", "semantic", "hybrid"):
        allowed = await service.search(SearchRequest(
            query="secret alpha", mode=mode, top_k=5,
            scope=SearchScope(workspace_id="wsA", visibilities=("public", "workspace")),
        ))
        denied = await service.search(SearchRequest(
            query="secret alpha", mode=mode, top_k=5,
            scope=SearchScope(workspace_id="wsB", visibilities=("public", "workspace")),
        ))
        assert allowed.hits, mode
        assert not denied.hits, mode


@pytest.mark.asyncio
async def test_private_owner_isolation():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    private = DocumentRecord(
        document_id="user-a", source_type="uploaded", source_id="a", namespace="research",
        title="Private", visibility="private", owner_id="userA",
        chunks=[ChunkRecord(chunk_id="user-a:0", content="my confidential thesis", document_id="user-a")],
    )
    await service.index_documents([private])
    as_a = await service.search(SearchRequest(
        query="confidential thesis", mode="hybrid",
        scope=SearchScope(owner_id="userA", visibilities=("public", "private")),
    ))
    as_b = await service.search(SearchRequest(
        query="confidential thesis", mode="hybrid",
        scope=SearchScope(owner_id="userB", visibilities=("public", "private")),
    ))
    assert as_a.hits and not as_b.hits


# ── Adapters ────────────────────────────────────────────────────────────────


def test_memory_adapter_reads_real_table():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE MemoryRecord (id TEXT, memoryType TEXT, scope TEXT, scopeId TEXT, subject TEXT, "
        "content TEXT, confidence REAL, importance REAL, source TEXT, status TEXT, createdAt TEXT, updatedAt TEXT)"
    )
    conn.execute(
        "INSERT INTO MemoryRecord VALUES ('m1','semantic','general',NULL,'NVDA',"
        "'Nvidia data center demand is strong','0.9',0.8,'run','active','t','t')"
    )
    conn.commit()
    from harness.search.adapters import collect_documents

    docs = collect_documents(conn)
    assert any(d.namespace == "memory" for d in docs)
    memory_doc = next(d for d in docs if d.namespace == "memory")
    assert memory_doc.chunks and "Nvidia" in memory_doc.chunks[0].content


@pytest.mark.asyncio
async def test_admin_stats_and_events():
    service, _ = make_service(rerank_enabled=False)
    await _seed(service, FakeEmbeddingProvider())
    await service.hybrid("nvidia")
    stats = service.admin_stats()
    assert stats["index"]["documents"] >= 2
    assert stats["search"]["recentQueries"] >= 1
    events = service.store.recent_events(limit=10)
    assert any(e["kind"] == "search.query" for e in events)
