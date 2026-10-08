"""SearchService — the façade every caller (tools, router, UI) talks to.

    agent/route → SearchService → { router, retrieve, rerank, context }
                                        ↓
                          SearchIndexStore (SQLite vector + FTS)
                                        ↓
                              EmbeddingService (providers)

Owns the index store, the embedding service, the cache and observability. The
service is process-wide (built once at boot) but every query re-resolves the
embedding provider from the run's ``ModelSettings`` so a run uses its own
credentials.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from ..persistence import new_id, now_iso
from .adapters import collect_documents
from .citations import record_hits_as_evidence, render_citations
from .config import SearchConfig, load_config
from .context import ContextAssembler
from .contracts import (
    ChunkRecord,
    DocumentRecord,
    IndexState,
    MetadataFilter,
    QueryExpansion,
    SearchHit,
    SearchMode,
    SearchRequest,
    SearchResult,
    SearchScope,
    TemporalFilter,
)
from .embeddings.cache import EmbeddingCache
from .embeddings.service import EmbeddingService
from .indexer import IndexResult, index_document, reindex_document
from .rerank import build_reranker, rerank_hits
from .retrieve import normalize_query, retrieve
from .router import route_query
from .store import SearchIndexStore

_INDEX_ORIGINS = ("memory", "evidence", "documents", "skills")


class SearchService:
    def __init__(
        self,
        config: Optional[SearchConfig] = None,
        *,
        memory_store: Any = None,
        memory_service: Any = None,
        evidence_store: Any = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.config = config or load_config()
        self.memory_store = memory_store
        self.memory_service = memory_service
        self.evidence_store = evidence_store
        self._external_on_event = on_event
        self.store = SearchIndexStore(self.config.db_path, config=self.config)
        self.cache = EmbeddingCache(self.store.connection, max_entries=self.config.cache_max_entries)
        self.embedder = EmbeddingService(self.config, cache=self.cache, on_event=self._emit)
        self.context_assembler = ContextAssembler(self.config)
        self._configured_settings: Any = None

    # ── configuration ───────────────────────────────────────────────────────

    def configure(self, settings: Any = None, overrides: Optional[dict[str, Any]] = None) -> None:
        """Re-resolve the embedding provider (per run, from its credentials)."""
        self._configured_settings = settings or self._configured_settings
        self.embedder.configure(self._configured_settings, overrides)

    async def warm_index(self, *, namespaces: Optional[list[str]] = None) -> dict[str, Any]:
        """Resolve the embedding provider from the environment and index sources.

        Used by the boot warm-up; safe to call repeatedly (incremental).
        """
        self.configure(None)
        return await self.bulk_index(namespaces=namespaces)

    def schedule_warm_index(self, *, namespaces: Optional[list[str]] = None) -> Any:
        """Schedule a best-effort background index build at boot.

        Non-blocking: the task runs on the caller's event loop and failures are
        recorded as an event, never raised. Disable with
        `HARNESS_SEARCH_WARM_INDEX=0` (tests set this so warm-up never races the
        suite).
        """
        import asyncio
        import os

        if not self.config.enabled:
            return None
        if os.environ.get("HARNESS_SEARCH_WARM_INDEX", "1").strip().lower() in ("0", "false", "no", "off"):
            return None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        previously = getattr(self, "_warm_task", None)
        if previously is not None and not previously.done():
            return previously

        async def _run() -> None:
            try:
                summary = await self.warm_index(namespaces=namespaces)
                self._emit("search.index.warmup", {"detail": summary})
            except Exception as exc:  # noqa: BLE001 - warm-up must never break boot
                self._emit("search.index.warmup_failed", {"detail": {"error": str(exc)}})

        self._warm_task = loop.create_task(_run())
        return self._warm_task

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        try:
            self.store.record_event(event, data)
        except Exception:  # noqa: BLE001
            pass
        if self._external_on_event is not None:
            try:
                self._external_on_event(event, data)
            except Exception:  # noqa: BLE001
                pass

    # ── search ──────────────────────────────────────────────────────────────

    async def search(
        self,
        request: SearchRequest,
        *,
        settings: Any = None,
        record: bool = True,
    ) -> SearchResult:
        if settings is not None:
            self.configure(settings)
        elif not self.embedder.available and self.config.embedding_provider:
            self.configure(None)
        if not request.query_id:
            request.query_id = new_id("q")

        t0 = time.monotonic()
        result = await retrieve(self.store, self.embedder, request, config=self.config)

        if (request.rerank if request.rerank is not None else self.config.rerank_enabled) and result.hits:
            reranker = build_reranker(self.config, settings or self._configured_settings)
            rerank_started = time.monotonic()
            wide = result.hits[: self.config.rerank_candidates]
            reranked = await rerank_hits(
                wide, result.normalized_query or request.query, reranker,
                top_k=request.top_k, score_weight=self.config.rerank_score_weight,
            )
            result.hits = reranked
            result.stats.rerank_ms = (time.monotonic() - rerank_started) * 1000.0
            result.stats.reranked = True
            result.stats.returned = len(reranked)

        if record:
            self._emit(
                "search.query",
                {
                    "queryId": request.query_id,
                    "runId": request.run_id,
                    "agentId": request.agent_id,
                    "namespace": request.namespace,
                    "mode": result.mode,
                    "latencyMs": (time.monotonic() - t0) * 1000.0,
                    "candidates": result.stats.candidates,
                    "results": len(result.hits),
                    "deduped": result.stats.deduped,
                    "cacheHit": result.stats.cache_hits > 0,
                    "provider": self.embedder.provider_id,
                    "model": self.embedder.model_id,
                    "detail": {
                        "semanticAvailable": result.stats.semantic_available,
                        "fallback": result.stats.fallback,
                    },
                },
            )
        return result

    async def search_routed(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        scope: Optional[SearchScope] = None,
        filters: Optional[MetadataFilter] = None,
        temporal: Optional[TemporalFilter] = None,
        namespace: Optional[str] = None,
        mode: Optional[str] = None,
        settings: Any = None,
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> SearchResult:
        decision = route_query(query, default_mode=self.config.default_mode)
        request = SearchRequest(
            query=query,
            mode=mode or decision.mode,
            top_k=top_k or self.config.default_top_k,
            namespace=namespace,
            filters=filters or MetadataFilter(),
            temporal=temporal or TemporalFilter(),
            scope=scope or SearchScope(),
            run_id=run_id,
            agent_id=agent_id,
        )
        result = await self.search(request, settings=settings)
        result.method = f"routed:{decision.reason}"
        return result

    async def semantic(
        self, query: str, *, top_k: Optional[int] = None, scope: Optional[SearchScope] = None,
        filters: Optional[MetadataFilter] = None, namespace: Optional[str] = None, settings: Any = None,
    ) -> SearchResult:
        return await self.search(
            SearchRequest(query=query, mode=SearchMode.SEMANTIC.value, top_k=top_k or self.config.default_top_k,
                          scope=scope or SearchScope(), filters=filters or MetadataFilter(), namespace=namespace),
            settings=settings,
        )

    async def keyword(
        self, query: str, *, top_k: Optional[int] = None, scope: Optional[SearchScope] = None,
        filters: Optional[MetadataFilter] = None, namespace: Optional[str] = None, settings: Any = None,
    ) -> SearchResult:
        return await self.search(
            SearchRequest(query=query, mode=SearchMode.KEYWORD.value, top_k=top_k or self.config.default_top_k,
                          scope=scope or SearchScope(), filters=filters or MetadataFilter(), namespace=namespace),
            settings=settings,
        )

    async def hybrid(
        self, query: str, *, top_k: Optional[int] = None, scope: Optional[SearchScope] = None,
        filters: Optional[MetadataFilter] = None, namespace: Optional[str] = None, settings: Any = None,
    ) -> SearchResult:
        return await self.search(
            SearchRequest(query=query, mode=SearchMode.HYBRID.value, top_k=top_k or self.config.default_top_k,
                          scope=scope or SearchScope(), filters=filters or MetadataFilter(), namespace=namespace),
            settings=settings,
        )

    async def build_context(self, result: SearchResult) -> Any:
        return self.context_assembler.assemble(result.hits, query=result.query)

    # ── indexing ────────────────────────────────────────────────────────────

    async def index_documents(self, documents: list[DocumentRecord]) -> list[IndexResult]:
        results: list[IndexResult] = []
        for doc in documents:
            results.append(await index_document(self.store, self.embedder, doc, config=self.config))
        return results

    async def bulk_index(
        self, *, namespaces: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """Collect documents from existing stores and index them (idempotent)."""
        connection = self._memory_connection()
        if connection is None:
            return {"indexed": 0, "documents": 0, "error": "no agent-memory connection attached"}
        documents = collect_documents(connection, namespaces=namespaces)
        started = time.monotonic()
        results = await self.index_documents(documents)
        indexed = sum(1 for r in results if r.state in (IndexState.INDEXED.value, IndexState.STALE.value))
        unchanged = sum(1 for r in results if r.unchanged)
        summary = {
            "documents": len(documents),
            "indexed": indexed,
            "unchanged": unchanged,
            "failed": sum(1 for r in results if r.state == IndexState.FAILED.value),
            "deduplicated": sum(1 for r in results if r.deduplicated),
            "vectors": sum(r.vectors for r in results),
            "missingVectors": sum(r.missing_vectors for r in results),
            "elapsedMs": round((time.monotonic() - started) * 1000.0, 2),
            "namespaces": namespaces or list(_INDEX_ORIGINS),
        }
        self._emit("search.index.bulk", {"detail": summary})
        return summary

    async def process_jobs(self, *, limit: int = 20) -> dict[str, Any]:
        """Process pending index jobs (namespace-level, idempotent)."""
        jobs = self.store.list_jobs(state=IndexState.PENDING.value, limit=limit)
        processed = 0
        for job in jobs:
            if not self.store.claim_job(job["jobId"]):
                continue
            namespace = None
            try:
                import json

                payload = json.loads(job.get("payload") or "{}")
                namespace = payload.get("namespaces")
            except (TypeError, ValueError):
                namespace = None
            try:
                await self.bulk_index(namespaces=namespace)
                self.store.finish_job(job["jobId"], IndexState.INDEXED.value)
            except Exception as exc:  # noqa: BLE001
                self.store.finish_job(job["jobId"], IndexState.FAILED.value, error=str(exc))
            processed += 1
        return {"processed": processed, "pending": len(jobs) - processed}

    def enqueue_index(self, *, namespaces: Optional[list[str]] = None) -> str:
        job_id = new_id("job")
        self.store.enqueue_job(job_id, document_id=None, operation="index",
                               namespace=(namespaces[0] if namespaces else None),
                               payload={"namespaces": namespaces})
        return job_id

    async def reindex_document(self, document_id: str, *, reembed: bool = False) -> IndexResult:
        return await reindex_document(self.store, self.embedder, document_id, config=self.config, reembed=reembed)

    def delete_document(self, document_id: str) -> bool:
        return self.store.delete_document(document_id)

    # ── direct document ingestion ───────────────────────────────────────────

    async def ingest_text(
        self, text: str, *, title: str = "", source_type: str = "uploaded", source_id: str = "",
        namespace: str = "research", uri: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
        visibility: str = "public", workspace_id: Optional[str] = None, owner_id: Optional[str] = None,
        published_at: Optional[str] = None, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
        document_type: Optional[str] = None, language: str = "en", strategy: Optional[str] = None,
    ) -> IndexResult:
        from .chunking import chunk_text, split_sentences

        resolved_strategy = strategy or self.config.chunk_strategy
        semantic_vectors = None
        # Embedding-based semantic chunking: when the strategy is `semantic` and a
        # provider is available, split on real embedding similarity between
        # sentences; otherwise the chunker falls back to lexical cohesion.
        if resolved_strategy == "semantic" and self.embedder.available:
            sentences = split_sentences(text)
            if sentences:
                try:
                    outcome = await self.embedder.embed_texts(sentences)
                    if all(v is not None for v in outcome.vectors):
                        semantic_vectors = outcome.vectors  # type: ignore[assignment]
                except Exception:  # noqa: BLE001 - fall back to lexical chunking
                    semantic_vectors = None
        document_id = f"{source_type}:{source_id or new_id('doc')}"
        chunks = chunk_text(
            text, document_id=document_id, strategy=resolved_strategy,
            target_chars=self.config.chunk_target_chars, overlap_chars=self.config.chunk_overlap_chars,
            min_chars=self.config.chunk_min_chars, max_chars=self.config.chunk_max_chars,
            semantic_vectors=semantic_vectors,
        )
        doc = DocumentRecord(
            document_id=document_id, source_type=source_type, source_id=source_id or document_id,
            namespace=namespace, title=title or source_id or "Untitled", uri=uri,
            metadata=metadata or {}, visibility=visibility, workspace_id=workspace_id, owner_id=owner_id,
            published_at=published_at, retrieved_at=now_iso(), entity_type=entity_type, entity_id=entity_id,
            document_type=document_type or source_type, language=language, chunks=chunks,
        )
        return await index_document(self.store, self.embedder, doc, config=self.config)

    # ── related / context ───────────────────────────────────────────────────

    async def find_similar(self, text: str, *, top_k: int = 5, scope: Optional[SearchScope] = None,
                           filters: Optional[MetadataFilter] = None, settings: Any = None) -> SearchResult:
        if settings is not None:
            self.configure(settings)
        request = SearchRequest(
            query=text, mode=SearchMode.SEMANTIC.value, top_k=top_k,
            scope=scope or SearchScope(), filters=filters or MetadataFilter(),
            expansion=QueryExpansion.DISABLED.value, neighbor=False, rerank=False,
        )
        return await self.search(request)

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_document(document_id)

    def get_document_context(self, document_id: str, *, chunk_id: Optional[str] = None, radius: int = 1) -> dict[str, Any]:
        document = self.store.get_document(document_id)
        chunks = self.store.list_chunks(document_id)
        if chunk_id:
            index = next((i for i, c in enumerate(chunks) if c["chunkId"] == chunk_id), None)
            if index is not None:
                low = max(0, index - radius)
                chunks = chunks[low : index + radius + 1]
        return {"document": document, "chunks": chunks}

    def list_documents(self, *, namespace: Optional[str] = None, state: Optional[str] = None,
                       limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_documents(namespace=namespace, state=state, limit=limit)

    # ── provenance bridging ─────────────────────────────────────────────────

    def record_evidence(self, hits: list[SearchHit], *, research_id: Optional[str] = None) -> list[str]:
        return record_hits_as_evidence(self.evidence_store, hits, research_id=research_id)

    def render_citations(self, hits: list[SearchHit]) -> str:
        return render_citations(hits)

    # ── admin / observability ───────────────────────────────────────────────

    def admin_stats(self) -> dict[str, Any]:
        store_stats = self.store.stats()
        events = self.store.recent_events(limit=200)
        latencies = [e["latencyMs"] for e in events if e.get("latencyMs") is not None and e["kind"] == "search.query"]
        query_count = sum(1 for e in events if e["kind"] == "search.query")
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
        failures = sum(1 for e in events if e["kind"] == "search.embedding.failed")
        return {
            "embedding": {
                "available": self.embedder.available,
                "reason": self.embedder.reason,
                "provider": self.embedder.provider_id,
                "model": self.embedder.model_id,
                "version": self.embedder.version,
                "dimensions": self.embedder.dimensions,
                "distanceMetric": self.embedder.distance_metric,
                "cache": self.cache.stats(),
                "lastStats": self.embedder.last_stats,
            },
            "index": store_stats,
            "search": {
                "recentQueries": query_count,
                "avgLatencyMs": round(avg_latency, 2),
                "embeddingFailures": failures,
            },
            "config": {
                "defaultMode": self.config.default_mode,
                "defaultTopK": self.config.default_top_k,
                "chunkStrategy": self.config.chunk_strategy,
                "rerankEnabled": self.config.rerank_enabled,
            },
        }

    def debug_trace(self, request: SearchRequest, *, settings: Any = None) -> dict[str, Any]:
        """A synchronous, structured view of the retrieval pipeline internals."""
        from .retrieve import build_filter_sql, keyword_candidates, expand_query

        normalized = normalize_query(request.query)
        expanded = expand_query(normalized) if request.expansion == QueryExpansion.AUTOMATIC.value else None
        query = expanded or normalized
        filter_sql, params = build_filter_sql(request.filters, request.temporal)
        from .store import scope_clause

        scope_sql, scope_params = scope_clause(request.scope)
        kw = keyword_candidates(
            self.store, query, request.filters, request.temporal, request.scope,
            min(self.config.max_candidates, max(request.top_k * self.config.candidate_multiplier, request.top_k)),
        )
        return {
            "query": request.query,
            "normalizedQuery": normalized,
            "expandedQuery": expanded,
            "mode": request.mode,
            "filterSql": filter_sql,
            "filterParams": params,
            "scopeSql": scope_sql,
            "scopeParams": scope_params,
            "keywordCandidates": [{"chunkId": c, "bm25": round(s, 4)} for c, s in kw],
            "semanticAvailable": self.embedder.available,
            "semanticReason": self.embedder.reason,
            "vectorModels": self.store.vector_models(),
            "rerankProvider": self.config.rerank_provider or "local-lexical",
        }

    # ── helpers ─────────────────────────────────────────────────────────────

    def _memory_connection(self) -> Any:
        if self.memory_store is None:
            return None
        return getattr(self.memory_store, "_db", None) or getattr(self.memory_store, "connection", None)

    def health(self) -> dict[str, Any]:
        return {
            "ok": self.store.integrity_ok(),
            "embeddingAvailable": self.embedder.available,
            "stats": self.store.stats(),
        }

    def close(self) -> None:
        task = getattr(self, "_warm_task", None)
        if task is not None and not task.done():
            try:
                task.cancel()
            except Exception:  # noqa: BLE001
                pass
        self.store.close()


__all__ = ["SearchService"]
