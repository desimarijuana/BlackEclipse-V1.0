"""Embedding provider abstraction.

An ``EmbeddingProvider`` is the ONLY place that knows a provider's HTTP quirks.
Adding a provider that speaks the OpenAI embeddings protocol needs no new class
(it is a registry entry served by ``OpenAICompatibleEmbeddingProvider``); adding
a genuinely new API family is one subclass plus a registry line.

Providers that cannot actually serve embeddings are never registered merely to
satisfy the interface. When no provider is configured, the search layer reports
semantic search unavailable and degrades to keyword/FTS — it never fabricates a
vector.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddingCapabilities:
    max_input_tokens: int = 8_192
    batch_limit: int = 2_048
    supports_batch: bool = True
    normalize: bool = True
    native_dimensions: int = 0
    distance_metric: str = "cosine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxInputTokens": self.max_input_tokens,
            "batchLimit": self.batch_limit,
            "supportsBatch": self.supports_batch,
            "normalize": self.normalize,
            "nativeDimensions": self.native_dimensions,
            "distanceMetric": self.distance_metric,
        }


@dataclass
class EmbeddingModelInfo:
    """One embedding model's identity in the registry.

    ``dimensions`` is authoritative for the vector space: vectors from a model
    with different dimensions OR a different ``version`` are never mixed.
    """

    provider: str
    model: str
    dimensions: int
    version: str = "1"
    distance_metric: str = "cosine"
    capabilities: EmbeddingCapabilities = field(default_factory=EmbeddingCapabilities)
    active: bool = True
    description: str = ""

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "version": self.version,
            "distanceMetric": self.distance_metric,
            "active": self.active,
            "description": self.description,
            "key": self.key,
            "capabilities": self.capabilities.to_dict(),
        }


class EmbeddingProvider(abc.ABC):
    """Translate text to vectors for one provider/model."""

    provider_id: str = ""
    model: str = ""
    dimensions: int = 0
    version: str = "1"
    distance_metric: str = "cosine"

    @abc.abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch. Must return one vector per input, in order."""

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0] if vectors else []

    def get_model(self) -> str:
        return self.model

    def get_dimensions(self) -> int:
        return self.dimensions

    def get_provider(self) -> str:
        return self.provider_id

    def get_version(self) -> str:
        return self.version

    def get_capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            native_dimensions=self.dimensions, distance_metric=self.distance_metric
        )

    def close(self) -> None:  # pragma: no cover - optional lifecycle hook
        return None


class EmbeddingProviderError(Exception):
    """Internal signal used by providers to mark a transient failure."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


__all__ = [
    "EmbeddingCapabilities",
    "EmbeddingModelInfo",
    "EmbeddingProvider",
    "EmbeddingProviderError",
]
