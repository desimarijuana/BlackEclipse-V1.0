"""Embedding model registry.

Tracks provider/model/dimensions/version/metric/capabilities/active. The
registry is the single source of truth for "which vector space is this", so the
store never mixes incompatible vectors and a migration from an old model to a
new one is an explicit, observable operation.
"""

from __future__ import annotations

from typing import Optional

from .base import EmbeddingCapabilities, EmbeddingModelInfo


def _cap(dims: int, *, max_tokens: int = 8_192, native: Optional[int] = None) -> EmbeddingCapabilities:
    return EmbeddingCapabilities(
        max_input_tokens=max_tokens,
        native_dimensions=native if native is not None else dims,
        distance_metric="cosine",
    )


# Declared models. Only dimensions that are publicly documented are listed; an
# unknown model discovered dynamically carries dimensions from the config or is
# marked unknown (0) and refused until declared — a guessed dimension is worse
# than an honest refusal.
_DECLARED: list[EmbeddingModelInfo] = [
    # OpenAI
    EmbeddingModelInfo("openai", "text-embedding-3-small", 1536, capabilities=_cap(1536, max_tokens=8191)),
    EmbeddingModelInfo("openai", "text-embedding-3-large", 3072, capabilities=_cap(3072, max_tokens=8191)),
    EmbeddingModelInfo("openai", "text-embedding-ada-002", 1536, capabilities=_cap(1536, max_tokens=8191)),
    # Google
    EmbeddingModelInfo("google", "text-embedding-004", 768, capabilities=_cap(768, max_tokens=2048)),
    EmbeddingModelInfo("google", "gemini-embedding-001", 768, capabilities=_cap(768, max_tokens=2048)),
    # Cohere
    EmbeddingModelInfo("cohere", "embed-english-v3.0", 1024, capabilities=_cap(1024, max_tokens=512)),
    EmbeddingModelInfo("cohere", "embed-multilingual-v3.0", 1024, capabilities=_cap(1024, max_tokens=512)),
    # Voyage
    EmbeddingModelInfo("voyage", "voyage-3", 1024, capabilities=_cap(1024, max_tokens=32000)),
    EmbeddingModelInfo("voyage", "voyage-3-lite", 512, capabilities=_cap(512, max_tokens=32000)),
    EmbeddingModelInfo("voyage", "voyage-finance-2", 1024, capabilities=_cap(1024, max_tokens=32000)),
    # Local / OpenAI-compatible (Ollama, LM Studio, vLLM)
    EmbeddingModelInfo("ollama", "nomic-embed-text", 768, capabilities=_cap(768, max_tokens=8192)),
    EmbeddingModelInfo("ollama", "mxbai-embed-large", 1024, capabilities=_cap(1024, max_tokens=512)),
    EmbeddingModelInfo("lmstudio", "nomic-embed-text-v1.5", 768, capabilities=_cap(768, max_tokens=8192)),
    EmbeddingModelInfo("local", "bge-m3", 1024, capabilities=_cap(1024, max_tokens=8192)),
]

# Provider ids that speak the OpenAI /embeddings protocol.
OPENAI_COMPATIBLE_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "ollama", "lmstudio", "local", "custom", "openai_compatible", "vllm", "together", "deepinfra"}
)


class EmbeddingModelRegistry:
    """Register/lookup embedding models by (provider, model) or default."""

    def __init__(self, models: Optional[list[EmbeddingModelInfo]] = None) -> None:
        self._models: dict[tuple[str, str], EmbeddingModelInfo] = {}
        self._defaults: dict[str, str] = {}
        for model in models if models is not None else _DECLARED:
            self.register(model)
        # A sensible default per provider (first declared wins).
        for (provider, name), _ in self._models.items():
            self._defaults.setdefault(provider, name)

    def register(self, model: EmbeddingModelInfo) -> None:
        self._models[(model.provider, model.model)] = model
        if model.active:
            self._defaults.setdefault(model.provider, model.model)

    def get(self, provider: str, model: str) -> Optional[EmbeddingModelInfo]:
        return self._models.get((provider, model))

    def default_model(self, provider: str) -> Optional[str]:
        return self._defaults.get(provider)

    def list_models(self, *, active_only: bool = False) -> list[EmbeddingModelInfo]:
        models = list(self._models.values())
        if active_only:
            models = [m for m in models if m.active]
        return models

    def is_openai_compatible(self, provider: str) -> bool:
        return provider in OPENAI_COMPATIBLE_PROVIDERS


__all__ = ["EmbeddingModelRegistry", "OPENAI_COMPATIBLE_PROVIDERS"]
