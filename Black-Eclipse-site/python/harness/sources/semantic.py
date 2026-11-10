"""Opt-in semantic index over source chunks.

Embeddings are a *rerank* layer, never the primary access path. Metadata and SQL
filters run first; only the surviving files are scored. The vector table is
sharded by the catalog's file ids, and a query loads a bounded number of vectors
so a terabyte corpus cannot turn one search into an out-of-memory event.

When no provider is configured the class reports ``available = False`` and the
planner falls back to FTS. Semantic search is never faked.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable, Optional

from .catalog import Catalog
from .config import SourceConfig
from .contracts import FileRecord
from .extract import extract_chunks

# A query loads at most this many vectors. 50k × 1536 × 4 bytes ≈ 300 MB.
_QUERY_VECTOR_CAP = 50_000


def run_sync(coro: Any) -> Any:
    """Run a coroutine from sync code, even inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class SemanticIndex:
    def __init__(
        self,
        catalog: Catalog,
        config: SourceConfig,
        *,
        embedder: Optional[Any] = None,
    ) -> None:
        self.catalog = catalog
        self.config = config
        self._embedder = embedder
        self._lock = threading.Lock()
        self._reason = "" if embedder is not None else "not resolved"
        self._resolved = embedder is not None

    # ── availability ────────────────────────────────────────────────────────

    def _service(self) -> Any:
        if self._embedder is not None:
            return self._embedder
        with self._lock:
            if self._resolved and self._embedder is not None:
                return self._embedder
            try:
                from ..search.config import load_config as load_search_config  # noqa: PLC0415
                from ..search.embeddings.service import EmbeddingService  # noqa: PLC0415

                service = EmbeddingService(load_search_config())
                service.configure()
                self._embedder = service
                self._reason = "" if service.available else (service.reason or "unavailable")
            except Exception as exc:  # noqa: BLE001 - absence is an honest state
                self._embedder = None
                self._reason = f"embedding layer unavailable: {exc}"
            finally:
                self._resolved = True
        return self._embedder

    @property
    def available(self) -> bool:
        if not self.config.semantic_enabled:
            return False
        service = self._service()
        return bool(service is not None and getattr(service, "available", False))

    @property
    def reason(self) -> str:
        if not self.config.semantic_enabled:
            return "semantic indexing is disabled (HARNESS_SOURCES_SEMANTIC=1 enables it)"
        self._service()
        return self._reason or "unavailable"

    @property
    def model_key(self) -> str:
        service = self._service()
        return service.model_key() if service is not None else ""

    # ── indexing ────────────────────────────────────────────────────────────

    async def index_files(
        self, files: Iterable[FileRecord], *, cancel=None, max_vectors: Optional[int] = None
    ) -> dict[str, Any]:
        service = self._service()
        if service is None or not getattr(service, "available", False):
            return {"available": False, "reason": self.reason, "embedded": 0}
        model = service.model_key()
        cap = int(max_vectors or self.config.semantic_max_vectors)
        embedded = 0
        for file in files:
            if embedded >= cap:
                break
            if cancel is not None and cancel.is_set():
                break
            chunks, _ = extract_chunks(
                file, file.abspath, config=self.config, cancel=cancel
            )
            texts = [c["text"] for c in chunks if len(c["text"]) >= self.config.semantic_min_chars]
            if not texts:
                continue
            vectors: list[tuple[int, list[float]]] = []
            for start in range(0, len(texts), self.config.semantic_batch):
                batch = texts[start:start + self.config.semantic_batch]
                outcome = await service.embed_texts(batch)
                if not outcome.ok:
                    return {
                        "available": True, "model": model, "embedded": embedded,
                        "error": "the embedding provider rejected part of the batch",
                    }
                for offset, vector in enumerate(outcome.vectors):
                    if vector is not None:
                        vectors.append((start + offset, list(vector)))
            if vectors:
                self.catalog.put_vectors(file.id, vectors[: cap - embedded], model=model)
                embedded += min(len(vectors), cap - embedded)
        return {"available": True, "model": model, "embedded": embedded}

    # ── search ──────────────────────────────────────────────────────────────

    async def search(
        self, query: str, files: Iterable[FileRecord], *, top_k: int = 20, cancel=None
    ) -> list[tuple[int, int, float]]:
        service = self._service()
        if service is None or not getattr(service, "available", False):
            return []
        query_vector = await service.embed_query(query)
        if not query_vector:
            return []
        return self.score(query_vector, files, top_k=top_k, cancel=cancel)

    def search_sync(
        self, query: str, files: Iterable[FileRecord], *, top_k: int = 20, cancel=None
    ) -> list[tuple[int, int, float]]:
        return run_sync(self.search(query, files, top_k=top_k, cancel=cancel))

    def score(
        self,
        query_vector: list[float],
        files: Iterable[FileRecord],
        *,
        top_k: int = 20,
        cancel=None,
    ) -> list[tuple[int, int, float]]:
        service = self._service()
        model = service.model_key() if service is not None else ""
        if not model:
            return []
        ids = [f.id for f in files][:_QUERY_VECTOR_CAP]
        rows = self.catalog.vectors_for_files(
            ids, model=model, limit=min(self.config.semantic_max_vectors, _QUERY_VECTOR_CAP)
        )
        if not rows:
            return []
        try:
            import numpy as np  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - numpy is a declared dependency; be honest if absent
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        norm = float(np.linalg.norm(query)) or 1.0
        scored: list[tuple[int, int, float]] = []
        # Group by dimensions; a corpus can hold more than one vector space.
        for file_id, ordinal, blob in rows:
            if cancel is not None and cancel.is_set():
                break
            vector = np.frombuffer(blob, dtype=np.float32)
            if vector.size != query.size:
                continue
            similarity = float(np.dot(vector, query) / (np.linalg.norm(vector) * norm or 1.0))
            scored.append((file_id, ordinal, similarity))
        scored.sort(key=lambda item: -item[2])
        return scored[: max(1, top_k)]


__all__ = ["SemanticIndex", "run_sync"]
