"""Provider-neutral data contracts for the search layer.

The stable result contract is ``SearchResult`` → ``SearchHit``. Every hit
carries full provenance and a ready-to-render ``Citation``; anonymous text
blobs are never returned. These shapes are mirrored by the TS client in
``src/lib/harness/search-types.ts``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class SearchMode(str, enum.Enum):
    """How a query is executed. Hybrid is the default."""

    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class IndexState(str, enum.Enum):
    """The lifecycle state of an indexed document."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    STALE = "STALE"
    DELETED = "DELETED"


class QueryExpansion(str, enum.Enum):
    DISABLED = "disabled"
    AUTOMATIC = "automatic"
    AGENT = "agent"


@dataclass
class EntityRef:
    type: str = ""
    id: str = ""
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id, "name": self.name}


@dataclass
class TemporalFilter:
    """Point-in-time + range filtering. All bounds are ISO-8601 strings.

    ``as_of`` is fail-closed: a document published after the boundary is
    excluded unless the caller explicitly asks for undated/late material
    (``include_undated`` covers documents with no published timestamp).
    """

    as_of: Optional[str] = None
    published_from: Optional[str] = None
    published_to: Optional[str] = None
    retrieved_from: Optional[str] = None
    retrieved_to: Optional[str] = None
    effective_as_of: Optional[str] = None
    include_undated: bool = True

    def is_empty(self) -> bool:
        return not any(
            (
                self.as_of,
                self.published_from,
                self.published_to,
                self.retrieved_from,
                self.retrieved_to,
                self.effective_as_of,
            )
        )


@dataclass
class MetadataFilter:
    """Structured filters. Security filters live on ``SearchScope``, not here."""

    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    source_types: list[str] = field(default_factory=list)
    document_types: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(
            (
                self.entity_type,
                self.entity_id,
                self.source_types,
                self.document_types,
                self.languages,
                self.namespaces,
                self.tickers,
                self.sectors,
                self.industries,
                self.source_ids,
                self.meta,
            )
        )


@dataclass
class SearchScope:
    """The authorization boundary. Applied IN SQL, before scoring.

    The layer never scans everything and filters afterward — the scope clause is
    part of every query, so an unauthorized row is never a candidate.
    """

    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    # Visibility tiers the caller may read. Default: public + own workspace.
    visibilities: tuple[str, ...] = ("public",)
    is_operator: bool = False
    # When True the scope is unconditional (operator/debug). Still explicit.
    unrestricted: bool = False

    def allowed_visibilities(self) -> tuple[str, ...]:
        if self.unrestricted or self.is_operator:
            return ("public", "workspace", "private", "restricted")
        allowed = set(self.visibilities) | {"public"}
        return tuple(sorted(allowed))


@dataclass
class Provenance:
    source_type: str = ""
    source_id: str = ""
    document_id: str = ""
    chunk_id: str = ""
    section: Optional[str] = None
    page: Optional[int] = None
    uri: Optional[str] = None
    publisher: Optional[str] = None
    authority: float = 0.0
    trust: str = "UNTRUSTED"
    method: str = "native"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceType": self.source_type,
            "sourceId": self.source_id,
            "documentId": self.document_id,
            "chunkId": self.chunk_id,
            "section": self.section,
            "page": self.page,
            "uri": self.uri,
            "publisher": self.publisher,
            "authority": self.authority,
            "trust": self.trust,
            "method": self.method,
        }


@dataclass
class Citation:
    label: str = ""
    document_id: str = ""
    chunk_id: str = ""
    source_type: str = ""
    source_id: str = ""
    uri: Optional[str] = None
    section: Optional[str] = None
    page: Optional[int] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    quote: str = ""

    def render(self) -> str:
        lines = [f"Source: {self.label}"]
        if self.section:
            lines.append(f"Section: {self.section}")
        if self.page is not None:
            lines.append(f"Page: {self.page}")
        if self.published_at:
            lines.append(f"Published: {self.published_at}")
        lines.append(f"Document ID: {self.document_id}")
        lines.append(f"Chunk ID: {self.chunk_id}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "documentId": self.document_id,
            "chunkId": self.chunk_id,
            "sourceType": self.source_type,
            "sourceId": self.source_id,
            "uri": self.uri,
            "section": self.section,
            "page": self.page,
            "publishedAt": self.published_at,
            "retrievedAt": self.retrieved_at,
            "quote": self.quote,
        }


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    content: str
    score: float = 0.0
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    rerank_score: Optional[float] = None
    kind: str = "chunk"
    entity: Optional[EntityRef] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    effective_at: Optional[str] = None
    provenance: Provenance = field(default_factory=Provenance)
    citation: Citation = field(default_factory=Citation)
    metadata: dict[str, Any] = field(default_factory=dict)
    neighbors: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.chunk_id,
            "content": self.content,
            "score": round(self.score, 4),
            "vectorScore": None if self.vector_score is None else round(self.vector_score, 4),
            "keywordScore": None if self.keyword_score is None else round(self.keyword_score, 4),
            "rerankScore": None if self.rerank_score is None else round(self.rerank_score, 4),
            "kind": self.kind,
            "entity": self.entity.to_dict() if self.entity else None,
            "timestamps": {
                "publishedAt": self.published_at,
                "retrievedAt": self.retrieved_at,
                "effectiveAt": self.effective_at,
            },
            "provenance": self.provenance.to_dict(),
            "citation": self.citation.to_dict(),
            "metadata": self.metadata,
            "neighbors": self.neighbors,
        }


@dataclass
class SearchStats:
    candidates: int = 0
    vector_candidates: int = 0
    keyword_candidates: int = 0
    returned: int = 0
    deduped: int = 0
    elapsed_ms: float = 0.0
    embedding_ms: float = 0.0
    rerank_ms: float = 0.0
    cache_hits: int = 0
    semantic_available: bool = True
    reranked: bool = False
    expanded: bool = False
    fallback: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "vectorCandidates": self.vector_candidates,
            "keywordCandidates": self.keyword_candidates,
            "returned": self.returned,
            "deduped": self.deduped,
            "elapsedMs": round(self.elapsed_ms, 2),
            "embeddingMs": round(self.embedding_ms, 2),
            "rerankMs": round(self.rerank_ms, 2),
            "cacheHits": self.cache_hits,
            "semanticAvailable": self.semantic_available,
            "reranked": self.reranked,
            "expanded": self.expanded,
            "fallback": self.fallback,
        }


@dataclass
class SearchResult:
    query: str = ""
    normalized_query: str = ""
    expanded_query: Optional[str] = None
    mode: str = SearchMode.HYBRID.value
    hits: list[SearchHit] = field(default_factory=list)
    method: str = "search"
    warnings: list[str] = field(default_factory=list)
    stats: SearchStats = field(default_factory=SearchStats)
    query_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "search_result",
            "query": self.query,
            "normalizedQuery": self.normalized_query,
            "expandedQuery": self.expanded_query,
            "mode": self.mode,
            "method": self.method,
            "hits": [h.to_dict() for h in self.hits],
            "warnings": self.warnings,
            "stats": self.stats.to_dict(),
            "queryId": self.query_id,
        }


@dataclass
class SearchRequest:
    query: str = ""
    mode: str = SearchMode.HYBRID.value
    top_k: int = 10
    namespace: Optional[str] = None
    filters: MetadataFilter = field(default_factory=MetadataFilter)
    temporal: TemporalFilter = field(default_factory=TemporalFilter)
    scope: SearchScope = field(default_factory=SearchScope)
    rerank: Optional[bool] = None
    expansion: str = QueryExpansion.AUTOMATIC.value
    neighbor: bool = True
    min_score: float = 0.0
    query_id: str = ""
    run_id: Optional[str] = None
    agent_id: Optional[str] = None


# ── Indexing records ────────────────────────────────────────────────────────


@dataclass
class ChunkRecord:
    chunk_id: str
    content: str
    document_id: str = ""
    section_id: Optional[str] = None
    ordinal: int = 0
    kind: str = "paragraph"
    page: Optional[int] = None
    token_count: int = 0
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionRecord:
    section_id: str
    document_id: str
    heading: str = ""
    parent_id: Optional[str] = None
    section_path: str = ""
    ordinal: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentRecord:
    document_id: str
    source_type: str = "unknown"
    source_id: str = ""
    namespace: str = "research"
    title: str = ""
    description: str = ""
    uri: Optional[str] = None
    mime_type: Optional[str] = None
    language: str = "en"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    document_type: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    effective_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    visibility: str = "public"
    authority: float = 0.0
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    sections: list[SectionRecord] = field(default_factory=list)
    chunks: list[ChunkRecord] = field(default_factory=list)


__all__ = [
    "ChunkRecord",
    "Citation",
    "DocumentRecord",
    "EntityRef",
    "IndexState",
    "MetadataFilter",
    "Provenance",
    "QueryExpansion",
    "SearchHit",
    "SearchMode",
    "SearchRequest",
    "SearchResult",
    "SearchScope",
    "SearchStats",
    "SectionRecord",
    "TemporalFilter",
]
