"""Search subsystem configuration.

One config object governs the whole retrieval layer: embedding provider/model,
batching, chunking, ranking weights, caching, and the on-disk index location.

Precedence (highest first):

    1. explicit constructor argument / ``overrides`` mapping
    2. environment variable (``HARNESS_SEARCH_*``)
    3. built-in default

Nothing here is a secret. Provider credentials are resolved per run from the
existing ``ModelSettings`` / provider environment variables — see
``embeddings/providers.py`` — never stored in this config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_DEFAULT_DB_FILENAME = "search.db"


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _float(value: Any, default: float, *, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def search_db_dir() -> Path:
    """``<repo>/.black-eclipse/search`` — derived artifacts, never user folders.

    Mirrors the dedicated-store precedent in
    ``code/intel/persistence/index.py`` (``.black-eclipse/code-index``).
    """
    try:
        from ..eclipse_memory.config import repo_root  # noqa: PLC0415

        base = Path(repo_root())
    except Exception:  # noqa: BLE001 - a missing repo root must not crash config
        base = Path(os.path.expanduser("~"))
    path = base / ".black-eclipse" / "search"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> str:
    override = os.environ.get("ECLIPSE_SEARCH_DB_PATH")
    if override:
        return os.path.abspath(override)
    return str(search_db_dir() / _DEFAULT_DB_FILENAME)


@dataclass
class SearchConfig:
    """All tunables for the retrieval layer. Weight defaults are explained."""

    enabled: bool = True

    # ── Embeddings ──────────────────────────────────────────────────────────
    # An explicit provider/model pair. Empty model ⇒ the registry's default for
    # the provider (if one is declared). When no provider is configured the
    # layer degrades to keyword/FTS search and reports semantic unavailable.
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 0
    embedding_version: str = "1"
    # Distance metric for the vector space. Cosine is the documented default.
    distance_metric: str = "cosine"

    batch_size: int = 64
    max_batch_chars: int = 96_000
    max_concurrent_batches: int = 4
    embedding_timeout_s: float = 30.0
    embedding_max_retries: int = 3
    embedding_backoff_base: float = 0.5
    embedding_backoff_cap: float = 8.0
    # Simple token-bucket rate limit shared per provider (requests/minute).
    embedding_requests_per_minute: int = 600
    cache_enabled: bool = True
    cache_max_entries: int = 200_000

    # ── Chunking ────────────────────────────────────────────────────────────
    chunk_strategy: str = "structural"  # fixed | sliding | semantic | structural
    chunk_target_chars: int = 1_200
    chunk_overlap_chars: int = 150
    chunk_min_chars: int = 80
    chunk_max_chars: int = 8_000

    # ── Retrieval ───────────────────────────────────────────────────────────
    default_mode: str = "hybrid"  # semantic | keyword | hybrid
    default_top_k: int = 10
    candidate_multiplier: int = 5
    max_candidates: int = 500
    rrf_k: int = 60
    # Ranking weights (understandable + testable). Applied to normalized
    # component scores in the fusion stage; vector/keyword use RRF first.
    vector_weight: float = 1.0
    keyword_weight: float = 1.0
    entity_boost: float = 0.25
    metadata_boost: float = 0.10
    freshness_weight: float = 0.0  # 0 by default: historical research must not be skewed
    authority_weight: float = 0.15
    rerank_score_weight: float = 0.6

    rerank_enabled: bool = True
    rerank_candidates: int = 50
    rerank_provider: str = ""  # "" = local deterministic reranker only
    rerank_model: str = ""

    # ── Context assembly ────────────────────────────────────────────────────
    context_max_tokens: int = 6_000
    context_per_source_limit: int = 4
    context_per_document_limit: int = 6
    context_neighbor_radius: int = 1
    context_diversity: bool = True

    # ── Storage / ops ───────────────────────────────────────────────────────
    db_path: str = ""
    vector_scan_limit: int = 50_000
    indexing_batch_commit: int = 200
    event_retention: int = 20_000
    source_authority: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.db_path:
            self.db_path = default_db_path()

    def resolved_weights(self) -> dict[str, float]:
        return {
            "vector": self.vector_weight,
            "keyword": self.keyword_weight,
            "entity": self.entity_boost,
            "metadata": self.metadata_boost,
            "freshness": self.freshness_weight,
            "authority": self.authority_weight,
            "rerank": self.rerank_score_weight,
        }


_ENV_MAP: dict[str, tuple[str, str]] = {
    "enabled": ("HARNESS_SEARCH_ENABLED", "bool"),
    "embedding_provider": ("HARNESS_SEARCH_EMBEDDING_PROVIDER", "str"),
    "embedding_model": ("HARNESS_SEARCH_EMBEDDING_MODEL", "str"),
    "embedding_dimensions": ("HARNESS_SEARCH_EMBEDDING_DIMENSIONS", "int"),
    "embedding_version": ("HARNESS_SEARCH_EMBEDDING_VERSION", "str"),
    "distance_metric": ("HARNESS_SEARCH_DISTANCE_METRIC", "str"),
    "batch_size": ("HARNESS_SEARCH_BATCH_SIZE", "int"),
    "chunk_strategy": ("HARNESS_SEARCH_CHUNK_STRATEGY", "str"),
    "chunk_target_chars": ("HARNESS_SEARCH_CHUNK_CHARS", "int"),
    "chunk_overlap_chars": ("HARNESS_SEARCH_CHUNK_OVERLAP", "int"),
    "default_mode": ("HARNESS_SEARCH_MODE", "str"),
    "default_top_k": ("HARNESS_SEARCH_TOP_K", "int"),
    "rerank_enabled": ("HARNESS_SEARCH_RERANK", "bool"),
    "rerank_provider": ("HARNESS_SEARCH_RERANK_PROVIDER", "str"),
    "rerank_model": ("HARNESS_SEARCH_RERANK_MODEL", "str"),
    "context_max_tokens": ("HARNESS_SEARCH_CONTEXT_TOKENS", "int"),
    "cache_enabled": ("HARNESS_SEARCH_CACHE", "bool"),
    "db_path": ("ECLIPSE_SEARCH_DB_PATH", "str"),
}

_INT_BOUNDS = {
    "embedding_dimensions": (0, 100_000),
    "batch_size": (1, 2_048),
    "chunk_target_chars": (200, 20_000),
    "chunk_overlap_chars": (0, 5_000),
    "default_top_k": (1, 100),
    "context_max_tokens": (256, 200_000),
}


def load_config(overrides: Optional[dict[str, Any]] = None) -> SearchConfig:
    """Build a config from env + explicit overrides (overrides win)."""
    values: dict[str, Any] = {}
    for field_name, (env_name, kind) in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        if kind == "bool":
            values[field_name] = _bool(raw, True)
        elif kind == "int":
            low, high = _INT_BOUNDS.get(field_name, (0, 10_000_000))
            values[field_name] = _int(raw, 0, low=low, high=high)
        else:
            values[field_name] = raw.strip()

    if overrides:
        values.update({k: v for k, v in overrides.items() if v is not None})

    config = SearchConfig(**values)
    config.db_path = config.db_path or default_db_path()
    return config


__all__ = ["SearchConfig", "default_db_path", "load_config", "search_db_dir"]
