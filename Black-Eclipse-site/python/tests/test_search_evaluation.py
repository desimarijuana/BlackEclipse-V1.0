"""Search evaluation tests."""

from __future__ import annotations

import pytest

from harness.search.evaluate import (
    DATASET,
    CORPUS,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    run_evaluation,
    seed_corpus,
)

from search_helpers import FakeEmbeddingProvider, instrument, make_service


def test_metric_functions():
    retrieved = ["a", "b", "c", "d"]
    relevant = ["b", "d", "z"]
    assert recall_at_k(retrieved, relevant, 4) == pytest.approx(2 / 3)
    assert precision_at_k(retrieved, relevant, 4) == pytest.approx(2 / 4)
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)
    assert 0.0 < ndcg_at_k(retrieved, relevant, 4) <= 1.0
    assert recall_at_k([], relevant, 4) == 0.0


def test_dataset_size_is_representative():
    assert len(DATASET) >= 50
    assert len(CORPUS) >= 10


@pytest.mark.asyncio
async def test_keyword_evaluation_quality():
    service, _ = make_service(rerank_enabled=False)
    await seed_corpus(service)
    report = await run_evaluation(service, DATASET, k=10, mode="keyword")
    assert report.cases == len(DATASET)
    # A deterministic keyword baseline should retrieve a good share of relevant docs.
    assert report.recall_at_k >= 0.5
    assert report.mrr > 0.0


@pytest.mark.asyncio
async def test_hybrid_evaluation_runs_with_embeddings():
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await seed_corpus(service)
    report = await run_evaluation(service, DATASET[:10], k=10, mode="hybrid")
    assert report.cases == 10
    assert report.ndcg > 0.0
