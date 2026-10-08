"""Embedding subsystem for the search layer."""

from .base import EmbeddingCapabilities, EmbeddingModelInfo, EmbeddingProvider
from .batcher import BatchEmbedResult, EmbeddingBatcher, RateLimiter
from .cache import EmbeddingCache, blob_to_vector, cache_key, normalize_content, vector_to_blob
from .providers import (
    CohereEmbeddingProvider,
    GoogleEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    VoyageEmbeddingProvider,
)
from .registry import EmbeddingModelRegistry
from .service import EmbeddingOutcome, EmbeddingService

__all__ = [
    "BatchEmbedResult",
    "CohereEmbeddingProvider",
    "EmbeddingBatcher",
    "EmbeddingCache",
    "EmbeddingCapabilities",
    "EmbeddingModelInfo",
    "EmbeddingModelRegistry",
    "EmbeddingOutcome",
    "EmbeddingProvider",
    "EmbeddingService",
    "GoogleEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "RateLimiter",
    "VoyageEmbeddingProvider",
    "blob_to_vector",
    "cache_key",
    "normalize_content",
    "vector_to_blob",
]
