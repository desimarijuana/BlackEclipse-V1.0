"""Shared helpers for the search test suite.

A deterministic embedding provider lets semantic/vector tests run with no network
and no real model, while still exercising the real batching, cache, store and
retrieval code paths. It is defined here (test-only) and injected directly into
the service — no fake provider is ever registered in production.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile

from harness.search import SearchConfig, SearchService
from harness.search.contracts import ChunkRecord, DocumentRecord


class FakeEmbeddingProvider:
    """A deterministic bag-of-words embedder over a fixed vocabulary."""

    provider_id = "fake"
    model = "fake-embed"
    version = "1"
    dimensions = 16
    distance_metric = "cosine"

    VOCAB = [
        "nvidia", "tesla", "revenue", "margin", "margins", "data", "center", "pricing",
        "ai", "growth", "risk", "guidance", "cash", "flow", "demand", "cloud",
    ]

    def get_provider(self) -> str:
        return self.provider_id

    def get_model(self) -> str:
        return self.model

    def get_version(self) -> str:
        return self.version

    def get_dimensions(self) -> int:
        return self.dimensions

    def _vec(self, text: str) -> list[float]:
        low = (text or "").lower()
        vector = [0.0] * self.dimensions
        for index, word in enumerate(self.VOCAB):
            if word in low:
                vector[index] = 1.0
        # A tiny deterministic lexical component so out-of-vocab text is not all-zero.
        digest = hashlib.sha256(low.encode("utf-8")).digest()
        for i in range(self.dimensions):
            vector[i] += digest[i] / 255.0 * 0.05
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


def make_service(**cfg: object) -> tuple[SearchService, str]:
    directory = tempfile.mkdtemp(prefix="be-search-")
    config = SearchConfig(db_path=os.path.join(directory, "search.db"), **cfg)
    service = SearchService(config)
    return service, directory


def instrument(service: SearchService, provider: FakeEmbeddingProvider | None = None) -> FakeEmbeddingProvider:
    provider = provider or FakeEmbeddingProvider()
    service.embedder._provider = provider
    service.embedder._available = True
    service.embedder._provider_model = f"{provider.provider_id}/{provider.model}@{provider.version}"
    service.embedder._reason = ""
    return provider


def make_document(document_id: str, chunks: list[str], **kwargs: object) -> DocumentRecord:
    chunk_records = [
        ChunkRecord(chunk_id=f"{document_id}:{i}", content=text, document_id=document_id, ordinal=i)
        for i, text in enumerate(chunks)
    ]
    return DocumentRecord(document_id=document_id, chunks=chunk_records, **kwargs)


__all__ = [
    "FakeEmbeddingProvider",
    "instrument",
    "make_document",
    "make_service",
]
