"""Unified Retrieval / Search Intelligence Layer.

    agent → SearchService → { router, retrieve, rerank, context }
                              ↓
                    SearchIndexStore (SQLite vector + FTS5)
                              ↓
                     EmbeddingService (providers)

Vector storage is SQLite (the repo is zero-config / SQLite-first), NOT
PostgreSQL + pgvector: introducing a second database would break the app's core
``npm install && npm run dev`` promise. The embedding-provider abstraction, the
vector-space/version registry, hybrid retrieval, reranking, provenance and
citations are all storage-agnostic, so the store can be swapped for pgvector
without touching callers. See ``docs/harness/search-retrieval.md``.
"""

from .config import SearchConfig, load_config
from .contracts import (
    Citation,
    DocumentRecord,
    IndexState,
    MetadataFilter,
    Provenance,
    QueryExpansion,
    SearchHit,
    SearchMode,
    SearchRequest,
    SearchResult,
    SearchScope,
    SearchStats,
    TemporalFilter,
)
from .errors import SearchError
from .service import SearchService
from .store import SearchIndexStore

__all__ = [
    "Citation",
    "DocumentRecord",
    "IndexState",
    "MetadataFilter",
    "Provenance",
    "QueryExpansion",
    "SearchConfig",
    "SearchError",
    "SearchHit",
    "SearchIndexStore",
    "SearchMode",
    "SearchRequest",
    "SearchResult",
    "SearchScope",
    "SearchService",
    "SearchStats",
    "TemporalFilter",
    "load_config",
]
