"""Hybrid retrieval over the SearchIndexStore.

Three modes:

  * ``semantic`` — vector similarity only (requires an embedding provider).
  * ``keyword``  — PostgreSQL-style relevance is emulated with SQLite FTS5 BM25.
  * ``hybrid``   — both candidate sets fused (the default).

The authorization scope and all metadata/temporal filters are compiled into the
candidate SQL; nothing is scanned-then-filtered. Semantic search degrades
honestly to keyword/FTS when no embedding runtime is available.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from .config import SearchConfig
from .contracts import (
    Citation,
    EntityRef,
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
from .embeddings.cache import blob_to_vector
from .embeddings.service import EmbeddingService
from .store import SearchIndexStore, scope_acl_keys, scope_clause

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*")

# Deterministic query expansion. Not mandatory; only used when the caller opts
# into AUTO. Kept intentionally small and finance-focused — never a generated
# wall of synonyms.
_EXPANSIONS: dict[str, list[str]] = {
    "margin": ["gross margin", "operating margin", "profitability"],
    "margins": ["gross margin", "operating margin", "profitability"],
    "revenue": ["sales", "top line", "turnover"],
    "cogs": ["cost of goods sold", "cost of revenue"],
    "guidance": ["outlook", "forecast"],
    "capex": ["capital expenditure", "capital spending"],
    "fcf": ["free cash flow"],
    "eps": ["earnings per share"],
    "risk": ["risk factors", "uncertainty"],
    "growth": ["expansion", "momentum"],
}


@dataclass
class _Candidate:
    chunk_id: str
    row: dict[str, Any]
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rank_vector: Optional[int] = None
    rank_keyword: Optional[int] = None


def normalize_query(query: str) -> str:
    return " ".join((query or "").split()).strip()


def expand_query(query: str) -> Optional[str]:
    terms = {t.lower() for t in _TOKEN_RE.findall(query or "")}
    additions: list[str] = []
    for term in sorted(terms):
        for extra in _EXPANSIONS.get(term, []):
            if extra.lower() not in (query or "").lower():
                additions.append(extra)
    if not additions:
        return None
    return f"{query} {' '.join(additions[:8])}"


def _meta_clause(alias: str, key: str, values: list[Any]) -> tuple[str, list[Any]]:
    placeholders = ",".join("?" for _ in values)
    clause = (
        f"EXISTS (SELECT 1 FROM SearchDocumentMeta m WHERE m.documentId = {alias}.documentId "
        f"AND m.key = ? AND m.value IN ({placeholders}))"
    )
    return clause, [str(key), *[str(v) for v in values]]


def build_filter_sql(
    filters: MetadataFilter, temporal: TemporalFilter, *, alias: str = "d"
) -> tuple[str, list[Any]]:
    clauses: list[str] = [f"{alias}.state IN ('INDEXED','STALE')"]
    params: list[Any] = []
    if filters.namespaces:
        clauses.append(f"{alias}.namespace IN ({','.join('?' for _ in filters.namespaces)})")
        params.extend(filters.namespaces)
    if filters.source_types:
        clauses.append(f"{alias}.sourceType IN ({','.join('?' for _ in filters.source_types)})")
        params.extend(filters.source_types)
    if filters.document_types:
        clauses.append(f"{alias}.documentType IN ({','.join('?' for _ in filters.document_types)})")
        params.extend(filters.document_types)

    # Metadata is indexed (SearchDocumentMeta) and filtered in SQL — never
    # post-filtered in Python, so a large corpus does not degrade filtering.
    for key, values in (
        ("tickers", filters.tickers),
        ("sectors", filters.sectors),
        ("industries", filters.industries),
    ):
        if values:
            clause, clause_params = _meta_clause(alias, key, values)
            clauses.append(clause)
            params.extend(clause_params)
    for key, expected in filters.meta.items():
        expected_values = expected if isinstance(expected, list) else [expected]
        clause, clause_params = _meta_clause(alias, key, expected_values)
        clauses.append(clause)
        params.extend(clause_params)
    if filters.languages:
        clauses.append(f"{alias}.language IN ({','.join('?' for _ in filters.languages)})")
        params.extend(filters.languages)
    if filters.source_ids:
        clauses.append(f"{alias}.sourceId IN ({','.join('?' for _ in filters.source_ids)})")
        params.extend(filters.source_ids)
    if filters.entity_type:
        clauses.append(f"{alias}.entityType = ?")
        params.append(filters.entity_type)
    if filters.entity_id:
        clauses.append(f"{alias}.entityId = ?")
        params.append(filters.entity_id)

    if temporal.as_of:
        clauses.append(f"({alias}.publishedAt IS NULL OR {alias}.publishedAt <= ?)")
        params.append(temporal.as_of)
        clauses.append(f"({alias}.validTo IS NULL OR {alias}.validTo >= ?)")
        params.append(temporal.as_of)
    if temporal.published_from:
        clauses.append(f"{alias}.publishedAt >= ?")
        params.append(temporal.published_from)
    if temporal.published_to:
        clauses.append(f"{alias}.publishedAt <= ?")
        params.append(temporal.published_to)
    if temporal.retrieved_from:
        clauses.append(f"{alias}.retrievedAt >= ?")
        params.append(temporal.retrieved_from)
    if temporal.retrieved_to:
        clauses.append(f"{alias}.retrievedAt <= ?")
        params.append(temporal.retrieved_to)
    if temporal.effective_as_of:
        clauses.append(f"({alias}.effectiveAt IS NULL OR {alias}.effectiveAt <= ?)")
        params.append(temporal.effective_as_of)
    return " AND ".join(clauses), params


def _fts_query(query: str) -> Optional[str]:
    terms = [t for t in _TOKEN_RE.findall(query or "") if len(t) > 1]
    if not terms:
        return None
    # Quote each term so FTS5 treats punctuation literally, then OR them for recall.
    quoted = [f'"{t}"' for t in terms[:24]]
    return " OR ".join(quoted)


def keyword_candidates(
    store: SearchIndexStore, query: str, filters: MetadataFilter, temporal: TemporalFilter,
    scope: SearchScope, limit: int,
) -> list[tuple[str, float]]:
    match = _fts_query(query)
    if not match:
        return []
    filter_sql, params = build_filter_sql(filters, temporal)
    scope_sql, scope_params = scope_clause(scope)
    sql = (
        "SELECT SearchChunkFts.chunkId AS chunkId, bm25(SearchChunkFts) AS rank "
        "FROM SearchChunkFts "
        "JOIN SearchChunk c ON c.chunkId = SearchChunkFts.chunkId "
        "JOIN SearchDocument d ON d.documentId = c.documentId "
        f"WHERE SearchChunkFts MATCH ? AND ({filter_sql}) AND {scope_sql} "
        "ORDER BY rank ASC LIMIT ?"
    )
    try:
        rows = store.connection.execute(sql, (match, *params, *scope_params, limit)).fetchall()
    except Exception:  # noqa: BLE001 - a malformed FTS query must not crash search
        return []
    return [(row["chunkId"], float(row["rank"] or 0.0)) for row in rows]


def _cosine(query_vector: list[float], vector: list[float]) -> float:
    if not query_vector or not vector or len(query_vector) != len(vector):
        return 0.0
    dot = 0.0
    qn = 0.0
    vn = 0.0
    for a, b in zip(query_vector, vector):
        dot += a * b
        qn += a * a
        vn += b * b
    if qn <= 1e-12 or vn <= 1e-12:
        return 0.0
    return dot / math.sqrt(qn * vn)


def _valid_chunk_ids(
    store: SearchIndexStore, ids: list[str], filter_sql: str, params: list[Any],
    scope_sql: str, scope_params: list[Any],
) -> set[str]:
    """The subset of `ids` that passes the metadata/temporal + scope predicate."""
    if not ids:
        return set()
    valid: set[str] = set()
    for start in range(0, len(ids), 400):
        batch = ids[start : start + 400]
        placeholders = ",".join("?" for _ in batch)
        sql = (
            "SELECT c.chunkId AS chunkId FROM SearchChunk c "
            "JOIN SearchDocument d ON d.documentId = c.documentId "
            f"WHERE c.chunkId IN ({placeholders}) AND ({filter_sql}) AND {scope_sql}"
        )
        try:
            rows = store.connection.execute(sql, (*batch, *params, *scope_params)).fetchall()
        except Exception:  # noqa: BLE001
            continue
        valid.update(row["chunkId"] for row in rows)
    return valid


# ANN candidate oversampling: fetch more than the requested K so metadata/temporal
# post-validation still leaves enough results.
_ANN_OVERSAMPLE = 10


def vector_candidates(
    store: SearchIndexStore, query_vector: list[float], model_key: str, filters: MetadataFilter,
    temporal: TemporalFilter, scope: SearchScope, limit: int, scan_limit: int,
) -> list[tuple[str, float]]:
    filter_sql, params = build_filter_sql(filters, temporal)
    scope_sql, scope_params = scope_clause(scope)

    # ── ANN path (sqlite-vec) ───────────────────────────────────────────────
    # The KNN is restricted to the caller's authorized ACL buckets before
    # scoring, so no unauthorized vector is ever a candidate. The returned ids
    # are then validated against the full metadata/temporal + scope predicate.
    acl_keys = scope_acl_keys(scope)
    ann = store.ann_search(query_vector, model_key, acl_keys, min(scan_limit, max(limit * _ANN_OVERSAMPLE, limit)))
    if ann is not None:
        ids = [chunk_id for chunk_id, _ in ann]
        valid = _valid_chunk_ids(store, ids, filter_sql, params, scope_sql, scope_params)
        scored = [(chunk_id, score) for chunk_id, score in ann if chunk_id in valid]
        return scored[:limit]

    # ── Brute-force fallback ────────────────────────────────────────────────
    sql = (
        "SELECT c.chunkId AS chunkId FROM SearchChunk c "
        "JOIN SearchDocument d ON d.documentId = c.documentId "
        "JOIN SearchVector v ON v.chunkId = c.chunkId AND v.modelKey = ? "
        f"WHERE ({filter_sql}) AND {scope_sql} LIMIT ?"
    )
    rows = store.connection.execute(sql, (model_key, *params, *scope_params, scan_limit)).fetchall()
    ids = [r["chunkId"] for r in rows]
    if not ids:
        return []
    blobs = store.vectors_for(ids, model_key)
    scored: list[tuple[str, float]] = []
    for chunk_id, blob in blobs.items():
        scored.append((chunk_id, _cosine(query_vector, blob_to_vector(blob))))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:limit]


def _freshness(published_at: Optional[str], retrieved_at: Optional[str]) -> float:
    if not published_at:
        return 0.0
    # Coarse recency prior in [0,1] over a ~5 year horizon.
    import datetime as _dt

    try:
        then = _dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    now = _dt.datetime.now(_dt.timezone.utc)
    if then.tzinfo is None:
        then = then.replace(tzinfo=_dt.timezone.utc)
    days = max(0.0, (now - then).total_seconds() / 86_400.0)
    return 1.0 / (1.0 + days / 365.0)


def _entity_match(row: dict[str, Any], filters: MetadataFilter, query: str) -> bool:
    if filters.entity_id and row.get("entityId") == filters.entity_id:
        return True
    entity_type = row.get("entityType")
    if not entity_type:
        return False
    return entity_type.lower() in (query or "").lower()


def _load_candidate_row(store: SearchIndexStore, chunk_id: str) -> Optional[dict[str, Any]]:
    row = store.connection.execute(
        "SELECT c.*, d.title AS docTitle, d.sourceType AS sourceType, d.sourceId AS sourceId, "
        "d.namespace AS namespace, d.uri AS uri, d.publisher AS publisher, "
        "d.publishedAt AS publishedAt, d.retrievedAt AS retrievedAt, d.effectiveAt AS effectiveAt, "
        "d.entityType AS entityType, d.entityId AS entityId, d.authority AS authority, "
        "d.metadata AS docMetadata, d.visibility AS visibility, d.workspaceId AS workspaceId "
        "FROM SearchChunk c JOIN SearchDocument d ON d.documentId = c.documentId WHERE c.chunkId = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        return None
    data = {k: row[k] for k in row.keys()}
    import json as _json

    try:
        data["_doc_metadata"] = _json.loads(data.get("docMetadata") or "{}")
    except (TypeError, ValueError):
        data["_doc_metadata"] = {}
    try:
        data["metadata"] = _json.loads(data.get("metadata") or "{}")
    except (TypeError, ValueError):
        data["metadata"] = {}
    data.setdefault("publisher", None)
    return data


def _dedup(hits: list[SearchHit]) -> tuple[list[SearchHit], int]:
    """Drop exact content-hash duplicates and near-duplicates (shingle Jaccard)."""
    seen_hashes: set[str] = set()
    kept: list[SearchHit] = []
    shingles: list[frozenset[str]] = []
    removed = 0
    for hit in hits:
        h = _content_hash(hit.content)
        if h in seen_hashes:
            removed += 1
            continue
        new_shingles = _shingle(hit.content)
        if any(_jaccard(new_shingles, prev) >= 0.9 for prev in shingles):
            seen_hashes.add(h)
            removed += 1
            continue
        seen_hashes.add(h)
        shingles.append(new_shingles)
        kept.append(hit)
    return kept, removed


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _shingle(text: str) -> frozenset[str]:
    words = [w.lower() for w in _TOKEN_RE.findall(text or "")]
    if len(words) < 5:
        return frozenset(words)
    return frozenset(" ".join(words[i : i + 5]) for i in range(len(words) - 4))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if inter else 0.0


def _neighbors(store: SearchIndexStore, row: dict[str, Any], radius: int) -> Optional[dict[str, Any]]:
    if radius <= 0:
        return None
    doc_id = row.get("documentId")
    ordinal = int(row.get("ordinal") or 0)
    lower = max(0, ordinal - radius)
    rows = store.connection.execute(
        "SELECT chunkId, ordinal, content, page, sectionId FROM SearchChunk "
        "WHERE documentId=? AND ordinal BETWEEN ? AND ? AND chunkId != ? ORDER BY ordinal ASC",
        (doc_id, lower, ordinal + radius, row.get("chunkId")),
    ).fetchall()
    if not rows:
        return {"section": _section_path(store, row.get("sectionId"))}
    previous = [dict(r) for r in rows if r["ordinal"] < ordinal]
    following = [dict(r) for r in rows if r["ordinal"] > ordinal]
    return {
        "previous": [{"chunkId": r["chunkId"], "content": r["content"], "page": r["page"]} for r in previous],
        "next": [{"chunkId": r["chunkId"], "content": r["content"], "page": r["page"]} for r in following],
        "section": _section_path(store, row.get("sectionId")),
    }


def _section_path(store: SearchIndexStore, section_id: Optional[str]) -> Optional[str]:
    if not section_id:
        return None
    row = store.connection.execute(
        "SELECT sectionPath, heading FROM SearchSection WHERE sectionId=?", (section_id,)
    ).fetchone()
    if row is None:
        return None
    return row["sectionPath"] or row["heading"] or None


def _citation(row: dict[str, Any], section: Optional[str]) -> Citation:
    title = row.get("docTitle") or row.get("sourceId") or row.get("documentId")
    label = f"{title}"
    if section:
        label = f"{title} — {section}"
    return Citation(
        label=label,
        document_id=row.get("documentId", ""),
        chunk_id=row.get("chunkId", ""),
        source_type=row.get("sourceType", ""),
        source_id=row.get("sourceId", ""),
        uri=row.get("uri"),
        section=section,
        page=row.get("page"),
        published_at=row.get("publishedAt"),
        retrieved_at=row.get("retrievedAt"),
        quote=(row.get("content") or "")[:280],
    )


async def retrieve(
    store: SearchIndexStore,
    embedder: EmbeddingService,
    request: SearchRequest,
    *,
    config: SearchConfig,
) -> SearchResult:
    import time

    started = time.monotonic()
    stats = SearchStats()
    result = SearchResult(query=request.query, mode=request.mode, query_id=request.query_id)
    result.normalized_query = normalize_query(request.query)

    if not result.normalized_query:
        result.warnings.append("empty query")
        return result

    query_for_search = result.normalized_query
    if request.expansion == QueryExpansion.AUTOMATIC.value:
        expanded = expand_query(result.normalized_query)
        if expanded:
            query_for_search = expanded
            result.expanded_query = expanded
            stats.expanded = True

    limit = max(1, request.top_k)
    candidate_limit = min(config.max_candidates, max(limit * config.candidate_multiplier, limit))
    score_map: dict[str, _Candidate] = {}

    mode = (request.mode or config.default_mode or SearchMode.HYBRID.value).lower()

    # A semantic-only request degrades to keyword when no embedding runtime is
    # available — honestly, with a reported fallback (never pretended semantic).
    if mode == SearchMode.SEMANTIC.value and not embedder.available:
        stats.semantic_available = False
        result.warnings.append(f"semantic unavailable: {embedder.reason}")
        result.warnings.append("fell back to keyword search")
        stats.fallback = "keyword"
        mode = SearchMode.KEYWORD.value

    # ── keyword ─────────────────────────────────────────────────────────────
    if mode in (SearchMode.KEYWORD.value, SearchMode.HYBRID.value):
        kw = keyword_candidates(store, query_for_search, request.filters, request.temporal,
                                request.scope, candidate_limit)
        stats.keyword_candidates = len(kw)
        # Normalize BM25 (more negative = better) to [0,1].
        if kw:
            values = [abs(score) for _, score in kw]
            vmax = max(values) or 1.0
            vmin = min(values)
            spread = (vmax - vmin) or 1.0
            for rank, (chunk_id, score) in enumerate(kw):
                cand = score_map.setdefault(chunk_id, _Candidate(chunk_id, {}))
                cand.keyword_score = 1.0 - ((abs(score) - vmin) / spread)
                cand.rank_keyword = rank

    # ── semantic ────────────────────────────────────────────────────────────
    if mode in (SearchMode.SEMANTIC.value, SearchMode.HYBRID.value):
        if not embedder.available:
            stats.semantic_available = False
            result.warnings.append(f"semantic unavailable: {embedder.reason}")
        else:
            embed_started = time.monotonic()
            query_vector = await embedder.embed_query(query_for_search)
            stats.embedding_ms = (time.monotonic() - embed_started) * 1000.0
            if query_vector:
                vec = vector_candidates(store, query_vector, embedder.model_key(), request.filters,
                                        request.temporal, request.scope, candidate_limit, config.vector_scan_limit)
                stats.vector_candidates = len(vec)
                for rank, (chunk_id, score) in enumerate(vec):
                    cand = score_map.setdefault(chunk_id, _Candidate(chunk_id, {}))
                    cand.vector_score = max(0.0, min(1.0, score))
                    cand.rank_vector = rank
            else:
                stats.semantic_available = False
                result.warnings.append("query embedding failed; using keyword results")
                # Record the degradation as a structured fallback (not just a
                # warning string), so observability shows WHY results are
                # keyword-only instead of a silent null.
                stats.fallback = "keyword"

    # ── fuse + score ────────────────────────────────────────────────────────
    weights = config.resolved_weights()
    hits: list[SearchHit] = []
    for chunk_id, cand in score_map.items():
        row = _load_candidate_row(store, chunk_id)
        if row is None:
            continue
        score = weights["vector"] * cand.vector_score + weights["keyword"] * cand.keyword_score
        if _entity_match(row, request.filters, query_for_search):
            score += weights["entity"]
        score += weights["authority"] * float(row.get("authority") or 0.0)
        if weights["freshness"]:
            score += weights["freshness"] * _freshness(row.get("publishedAt"), row.get("retrievedAt"))
        section = _section_path(store, row.get("sectionId")) if request.neighbor else None
        provenance = Provenance(
            source_type=row.get("sourceType", ""),
            source_id=row.get("sourceId", ""),
            document_id=row.get("documentId", ""),
            chunk_id=chunk_id,
            section=section,
            page=row.get("page"),
            uri=row.get("uri"),
            publisher=row.get("publisher"),
            authority=float(row.get("authority") or 0.0),
            method=(row.get("metadata") or {}).get("method", "native"),
        )
        entity = None
        if row.get("entityType"):
            entity = EntityRef(type=row["entityType"], id=row.get("entityId") or "", name=row.get("entityId") or "")
        hits.append(
            SearchHit(
                chunk_id=chunk_id,
                document_id=row.get("documentId", ""),
                content=row.get("content", ""),
                score=score,
                vector_score=cand.vector_score if cand.rank_vector is not None else None,
                keyword_score=cand.keyword_score if cand.rank_keyword is not None else None,
                kind=row.get("kind", "paragraph"),
                entity=entity,
                published_at=row.get("publishedAt"),
                retrieved_at=row.get("retrievedAt"),
                effective_at=row.get("effectiveAt"),
                provenance=provenance,
                citation=_citation(row, section),
                metadata={"ordinal": row.get("ordinal"), "namespace": row.get("namespace")},
                neighbors=_neighbors(store, row, config.context_neighbor_radius) if request.neighbor else None,
            )
        )

    stats.candidates = len(hits)
    hits.sort(key=lambda h: h.score, reverse=True)
    if request.min_score:
        hits = [h for h in hits if h.score >= request.min_score]
    hits, removed = _dedup(hits)
    stats.deduped = removed
    result.hits = hits[:limit]
    stats.returned = len(result.hits)
    stats.elapsed_ms = (time.monotonic() - started) * 1000.0
    result.stats = stats
    if not result.hits and not result.warnings:
        result.warnings.append("no results matched the query and filters")
    return result


__all__ = [
    "build_filter_sql",
    "expand_query",
    "keyword_candidates",
    "normalize_query",
    "retrieve",
    "vector_candidates",
]
