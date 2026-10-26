"""Embedding layer tests: cache, batching, retry, provider parsing, registry."""

from __future__ import annotations

import asyncio

import pytest

from harness.search.embeddings import providers as P
from harness.search.embeddings.batcher import EmbeddingBatcher
from harness.search.embeddings.cache import EmbeddingCache, cache_key, normalize_content, vector_to_blob, blob_to_vector
from harness.search.embeddings.base import EmbeddingProvider, EmbeddingProviderError
from harness.search.embeddings.registry import EmbeddingModelRegistry
from harness.search.embeddings.service import EmbeddingService

from search_helpers import FakeEmbeddingProvider


def test_cache_key_normalizes():
    a = cache_key("Hello   World", "openai", "m", "1")
    b = cache_key("hello world", "openai", "m", "1")
    assert a == b
    c = cache_key("hello world", "openai", "m", "2")
    assert a != c
    assert normalize_content("A\n B\tC") == "a b c"


def test_vector_blob_roundtrip():
    vector = [0.1, 0.2, -0.3, 1.0]
    assert blob_to_vector(vector_to_blob(vector)) == pytest.approx(vector, rel=1e-6)


def test_cache_roundtrip(tmp_path):
    import sqlite3

    db = sqlite3.connect(str(tmp_path / "c.db"))
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE EmbeddingCache (cacheKey TEXT PRIMARY KEY, provider TEXT, model TEXT, version TEXT, "
               "dims INTEGER, vector BLOB, createdAt TEXT)")
    cache = EmbeddingCache(db)
    assert cache.get("missing") is None
    cache.put("k", [1.0, 2.0], provider="p", model="m", version="1", created_at="now")
    cache.commit()
    assert cache.get("k") == pytest.approx([1.0, 2.0])


class _FlakyProvider(EmbeddingProvider):
    provider_id = "flaky"
    model = "flaky"
    dimensions = 2

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def embed_batch(self, texts):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise EmbeddingProviderError("transient", retryable=True)
        return [[float(i), 0.0] for i, _ in enumerate(texts)]


def test_batcher_retries_then_succeeds():
    provider = _FlakyProvider(fail_times=2)
    batcher = EmbeddingBatcher(provider, max_retries=3, backoff_base=0.0, backoff_cap=0.0)
    result = asyncio.run(batcher.embed(["a", "b"]))
    assert result.ok
    assert result.vectors == [[0.0, 0.0], [1.0, 0.0]]
    assert result.retries == 2


def test_batcher_splits_batches():
    provider = FakeEmbeddingProvider()
    batcher = EmbeddingBatcher(provider, batch_size=2)
    texts = [f"nvidia text {i}" for i in range(5)]
    result = asyncio.run(batcher.embed(texts))
    assert result.batches == 3
    assert len(result.vectors) == 5


def test_provider_parsers(monkeypatch):
    async def fake_post(url, *, headers, payload, timeout):
        if "embeddings" in url and "voyage" in headers.get("Authorization", ""):
            return {"data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}
        return {"data": [{"index": 0, "embedding": [1.0, 0.0]}, {"index": 1, "embedding": [0.0, 1.0]}]}

    monkeypatch.setattr(P, "_post_json", fake_post)
    openai = P.OpenAICompatibleEmbeddingProvider(provider_id="openai", model="text-embedding-3-small", dimensions=2, api_key="k")
    vectors = asyncio.run(openai.embed_batch(["a", "b"]))
    assert len(vectors) == 2

    async def fake_google(url, *, headers, payload, timeout):
        return {"embeddings": [{"values": [3.0, 4.0]}]}

    monkeypatch.setattr(P, "_post_json", fake_google)
    google = P.GoogleEmbeddingProvider(model="text-embedding-004", dimensions=2, api_key="k")
    vectors = asyncio.run(google.embed_batch(["a"]))
    # Normalized to unit length.
    assert vectors[0] == pytest.approx([0.6, 0.8], rel=1e-5)


def test_registry_dimensions_and_defaults():
    registry = EmbeddingModelRegistry()
    assert registry.get("openai", "text-embedding-3-small").dimensions == 1536
    assert registry.get("voyage", "voyage-3").dimensions == 1024
    assert registry.default_model("openai") == "text-embedding-3-small"
    assert registry.is_openai_compatible("ollama")


def test_embedding_service_cache_hit(tmp_path):
    service = EmbeddingService.__new__(EmbeddingService)
    from harness.search.config import SearchConfig

    service.config = SearchConfig(db_path=str(tmp_path / "s.db"))
    service.registry = EmbeddingModelRegistry()
    service.cache = None
    service._on_event = None
    service._provider = FakeEmbeddingProvider()
    service._available = True
    service._provider_model = "fake/fake-embed@1"
    service._reason = ""
    service.last_stats = {}
    first = asyncio.run(service.embed_texts(["nvidia revenue"]))
    assert first.vectors[0] is not None


class _RejectingProvider(EmbeddingProvider):
    provider_id = "rejecting"
    model = "rejecting"
    dimensions = 2

    def __init__(self) -> None:
        self.calls = 0

    async def embed_batch(self, texts):
        self.calls += 1
        raise EmbeddingProviderError("embedding endpoint returned 404", retryable=False)


def test_embedding_service_opens_circuit_after_provider_wide_rejection(tmp_path):
    """A provider that rejects every input must be asked ONCE, not per document.

    The boot warm-index calls `embed_texts` for each document; a broken endpoint
    used to produce one doomed request per document (thousands of 404s), which
    starved the event loop and made every API route slow.
    """
    from harness.search.config import SearchConfig
    from harness.search.errors import EmbeddingUnavailable

    service = EmbeddingService(SearchConfig(db_path=str(tmp_path / "s.db")))
    provider = _RejectingProvider()
    service._provider = provider
    service._available = True
    service._provider_model = "rejecting/rejecting@1"
    service._reason = ""

    first = asyncio.run(service.embed_texts(["a", "b"]))
    assert first.failures == 2
    assert provider.calls == 1
    assert not service.available
    assert "rejected all" in service.reason

    # The next document is refused without touching the network again.
    with pytest.raises(EmbeddingUnavailable):
        asyncio.run(service.embed_texts(["c"]))
    assert provider.calls == 1


def test_configure_does_not_rearm_an_open_circuit_within_cooldown(tmp_path, monkeypatch):
    """`configure()` runs on every search; it must not re-arm a broken provider.

    Without the cooldown, each search resolved the (unchanged) provider and
    cleared the circuit, so a permanently 404ing endpoint was retried once per
    query — thousands of doomed calls, and multi-second API latency.
    """
    from harness.search.config import SearchConfig
    from harness.search.embeddings.providers import OpenAICompatibleEmbeddingProvider

    calls: list[list[str]] = []

    async def reject(self, texts):  # noqa: ANN001 - bound like the real method
        calls.append(list(texts))
        raise EmbeddingProviderError("embedding endpoint returned 404", retryable=False)

    monkeypatch.setattr(OpenAICompatibleEmbeddingProvider, "embed_batch", reject)
    service = EmbeddingService(
        SearchConfig(
            db_path=str(tmp_path / "s.db"),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
    )
    service.configure(None)
    assert service.available

    first = asyncio.run(service.embed_texts(["a"]))
    assert first.failures == 1
    assert not service.available
    asked = len(calls)

    # A later, unchanged resolution keeps the circuit open.
    service.configure(None)
    assert not service.available
    with pytest.raises(Exception):
        asyncio.run(service.embed_texts(["b"]))
    assert len(calls) == asked
