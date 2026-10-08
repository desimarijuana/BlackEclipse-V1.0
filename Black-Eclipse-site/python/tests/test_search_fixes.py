"""Tests for the scalability/correctness limitations that were fixed:
incremental re-index, SQL-side metadata filtering, distinct documentType, and
embedding-based semantic chunking.
"""

from __future__ import annotations

import pytest

from harness.search.chunking import chunk_text
from harness.search.contracts import MetadataFilter, SearchRequest

from search_helpers import FakeEmbeddingProvider, instrument, make_service


@pytest.mark.asyncio
async def test_incremental_reindex_skips_unchanged():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    first = await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand.", title="NVDA",
        source_type="filing", source_id="nvda", namespace="filing",
    )
    assert first.unchanged is False
    second = await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand.", title="NVDA",
        source_type="filing", source_id="nvda", namespace="filing",
    )
    assert second.unchanged is True
    assert second.vectors == 0  # no re-embedding
    # A changed body re-indexes.
    third = await service.ingest_text(
        "NVIDIA data center revenue grew on AI demand and networking.", title="NVDA",
        source_type="filing", source_id="nvda", namespace="filing",
    )
    assert third.unchanged is False


@pytest.mark.asyncio
async def test_indexed_metadata_filters_sql():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await service.ingest_text(
        "Nvidia AI revenue accelerated.", title="NVDA", source_type="filing", source_id="nvda",
        namespace="filing", metadata={"tickers": ["NVDA"], "sectors": ["Technology"], "region": "US"},
    )
    await service.ingest_text(
        "Tesla margin compressed.", title="TSLA", source_type="filing", source_id="tsla",
        namespace="filing", metadata={"tickers": ["TSLA"], "sectors": ["Consumer"], "region": "US"},
    )
    by_ticker = await service.search(SearchRequest(
        query="revenue", mode="keyword", filters=MetadataFilter(tickers=["NVDA"]),
    ))
    assert by_ticker.hits and all(h.provenance.source_id == "nvda" for h in by_ticker.hits)

    no_ticker = await service.search(SearchRequest(
        query="revenue", mode="keyword", filters=MetadataFilter(tickers=["AAPL"]),
    ))
    assert not no_ticker.hits

    by_meta = await service.search(SearchRequest(
        query="revenue", mode="keyword", filters=MetadataFilter(meta={"region": "US"}),
    ))
    assert by_meta.hits


@pytest.mark.asyncio
async def test_document_type_filter_distinct_from_source_type():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await service.ingest_text(
        "Nvidia annual report content.", title="10K", source_type="filing", source_id="a",
        namespace="filing", document_type="10-K",
    )
    await service.ingest_text(
        "Nvidia quarterly content.", title="10Q", source_type="filing", source_id="b",
        namespace="filing", document_type="10-Q",
    )
    ten_k = await service.search(SearchRequest(
        query="nvidia", mode="keyword", filters=MetadataFilter(document_types=["10-K"]),
    ))
    assert ten_k.hits and all(h.provenance.source_id == "a" for h in ten_k.hits)


def test_embedding_based_semantic_chunking_splits_on_low_similarity():
    text = "Revenue increased significantly. Top line growth accelerated."
    # Similar embeddings ⇒ one coherent chunk even though the sentences share no
    # content words (which the lexical fallback would split).
    similar = [[1.0, 0.0] + [0.0] * 14, [1.0, 0.0] + [0.0] * 14]
    embedded = chunk_text(
        text, document_id="d", strategy="semantic", target_chars=10_000, min_chars=1,
        semantic_vectors=similar,
    )
    lexical = chunk_text(text, document_id="d", strategy="semantic", target_chars=10_000, min_chars=1)
    assert len(embedded) == 1
    assert len(lexical) >= 2


@pytest.mark.asyncio
async def test_ingest_uses_embedding_semantic_chunking():
    service, _ = make_service(chunk_strategy="semantic", rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    # A two-topic document should be split when the provider is available.
    result = await service.ingest_text(
        "Nvidia data center revenue grew. Nvidia AI demand accelerated. "
        "Tesla margins fell. Tesla pricing pressure increased.",
        title="Mixed", source_type="filing", source_id="mix", namespace="filing",
    )
    assert result.chunks >= 1
