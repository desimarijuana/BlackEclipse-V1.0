"""The query router: pick the cheapest engine that can answer, then fuse.

Terabyte corpora cannot be searched by one universal index. The router derives a
candidate set from the catalog first, then decides between metadata, FTS,
DuckDB and a bounded raw scan. Every plan carries a budget and reports what it
actually covered.
"""

from __future__ import annotations

import fnmatch
import os
import re
import time
from typing import Any, Optional

from .catalog import Catalog
from .config import SourceConfig
from .contracts import Hit, QueryPlan, SearchResult
from .rawscan import raw_scan

_AGGREGATE = re.compile(r"\b(sum|avg|average|count|min|max|median|group\s+by|top\s+\d+)\b", re.IGNORECASE)
_METADATA_HINTS = re.compile(r"^\*?\.?[a-z0-9]{1,8}$|^(largest|biggest|newest|oldest|recent)\b", re.IGNORECASE)
_SQL_START = re.compile(r"^\s*(select|with|describe|summarize|pivot)\b", re.IGNORECASE)


def plan_and_search(
    catalog: Catalog,
    *,
    query: str = "",
    mode: str = "auto",
    root_ids: Optional[list[str]] = None,
    path_prefix: Optional[str] = None,
    klass: Optional[str] = None,
    name_like: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    modified_after: Optional[float] = None,
    limit: int = 50,
    regex: bool = False,
    case_sensitive: bool = False,
    cancel=None,
    cfg: Optional[SourceConfig] = None,
    semantic: Optional[Any] = None,
) -> SearchResult:
    config = cfg or catalog.config
    started = time.monotonic()
    limit = max(1, min(int(limit or 50), config.max_results))
    filters = dict(
        root_ids=root_ids, klass=klass, path_prefix=path_prefix, name_like=name_like,
        min_size=min_size, max_size=max_size, modified_after=modified_after,
    )
    candidates = catalog.count_files(root_ids=root_ids, klass=klass)
    plan = QueryPlan(
        mode=mode, candidates=candidates, reason="",
        budget_bytes=config.scan_max_bytes, budget_seconds=config.scan_timeout_s,
    )
    resolved = _resolve_mode(mode, query, klass, filters, semantic)
    plan.mode = resolved
    hits: list[Hit] = []
    warnings: list[str] = []
    scanned_files = 0
    scanned_bytes = 0
    truncated = False

    if resolved == "metadata":
        plan.engines = ["metadata"]
        plan.reason = "metadata predicates answer this without reading content"
        hits = _metadata_hits(catalog, query=query, limit=limit, **filters)
    elif resolved == "text":
        plan.engines = ["fts", "metadata"]
        plan.reason = "lexical index over chunked text; metadata fills in filenames"
        fts = catalog.search_chunks(
            query, root_ids=root_ids, path_prefix=path_prefix, limit=limit
        )
        hits.extend(_fts_hits(fts))
        hits.extend(_metadata_hits(catalog, query=query, limit=max(5, limit // 3), **filters))
        if len(hits) < limit:
            files = catalog.candidates_for_scan(limit=min(1_000, config.max_results * 5), **filters)
            unindexed = [f for f in files if not f.indexed_at]
            if unindexed:
                raw_hits, scanned_bytes, scanned_files, raw_trunc, raw_warn = raw_scan(
                    unindexed, query, config=config, regex=regex,
                    case_sensitive=case_sensitive, cancel=cancel, max_results=limit,
                )
                hits.extend(raw_hits)
                truncated = truncated or raw_trunc
                warnings.extend(raw_warn)
                plan.engines.append("scan")
        if not hits:
            plan.reason += "; nothing matched, and no unindexed text candidates were available"
    elif resolved == "raw":
        plan.engines = ["scan"]
        plan.reason = "bounded parallel scan over the candidate files"
        files = catalog.candidates_for_scan(limit=min(20_000, config.max_results * 100), **filters)
        if not files:
            warnings.append("no files matched the catalog filters")
        raw_hits, scanned_bytes, scanned_files, truncated, raw_warn = raw_scan(
            files, query, config=config, regex=regex, case_sensitive=case_sensitive,
            cancel=cancel, max_results=limit,
        )
        hits.extend(raw_hits)
        warnings.extend(raw_warn)
    elif resolved == "similar":
        plan.engines = ["vectors", "metadata"]
        plan.reason = "cosine similarity over the opt-in vector subset, filtered first"
        if semantic is None or not getattr(semantic, "available", False):
            warnings.append("semantic search is unavailable: no embedding provider is configured")
            plan.reason = "vectors unavailable; falling back to metadata"
            hits = _metadata_hits(catalog, query=query, limit=limit, **filters)
        else:
            files = catalog.list_files(limit=min(5_000, config.semantic_max_vectors // 8), **filters)
            try:
                scored = semantic.search_sync(query, files, top_k=limit, cancel=cancel)
            except Exception as exc:  # noqa: BLE001 - similarity failure is reportable
                scored = []
                warnings.append(f"vector search failed: {exc}")
            by_id = {f.id: f for f in files}
            for file_id, ordinal, score in scored:
                file = by_id.get(file_id)
                if file is None:
                    continue
                hits.append(Hit(
                    root_id=file.root_id, relpath=file.relpath, name=file.name,
                    klass=file.klass, size=file.size, mtime=file.mtime,
                    score=float(score), engine="vectors", chunk_id=ordinal,
                ))
    else:  # pragma: no cover - resolved() only returns the four above
        plan.engines = ["metadata"]

    hits = _fuse(hits, query=query, limit=limit)
    if len(hits) >= limit:
        truncated = truncated or True
    return SearchResult(
        query=query, plan=plan, hits=hits, scanned_files=scanned_files,
        scanned_bytes=scanned_bytes,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        truncated=truncated, warnings=_dedupe(warnings),
    )


def _resolve_mode(mode: str, query: str, klass: Optional[str], filters: dict, semantic) -> str:
    if mode in ("metadata", "text", "raw", "similar"):
        return mode
    text = (query or "").strip()
    if not text:
        return "metadata"
    if _SQL_START.match(text):
        return "metadata"  # SQL is executed by the service, not the text router
    if klass == "table" and _AGGREGATE.search(text):
        return "metadata"
    if _METADATA_HINTS.match(text) and not any(ch.isspace() for ch in text):
        return "metadata"
    if semantic is not None and getattr(semantic, "available", False) and query.startswith("~"):
        return "similar"
    return "text"


def _metadata_hits(catalog: Catalog, *, query: str, limit: int, **filters) -> list[Hit]:
    text = (query or "").strip()
    files = []
    if text and any(ch in text for ch in "*?["):
        for file in catalog.list_files(limit=min(5_000, catalog.count_files(root_ids=filters.get("root_ids"))), **filters):
            if fnmatch.fnmatch(file.name.lower(), text.lower()):
                files.append(file)
    else:
        files = catalog.list_files(
            name_like=text or filters.get("name_like"), limit=limit, **{
                k: v for k, v in filters.items() if k != "name_like"
            }
        )
    hits = []
    for index, file in enumerate(files[:limit]):
        score = 1.0 + max(0.0, 0.5 - index * 0.01)
        if text and text.casefold() in file.name.casefold():
            score += 0.5
        hits.append(Hit(
            root_id=file.root_id, relpath=file.relpath, name=file.name,
            klass=file.klass, size=file.size, mtime=file.mtime,
            score=score, engine="metadata",
        ))
    return hits


def _fts_hits(rows: list[dict[str, Any]]) -> list[Hit]:
    hits = []
    for row in rows:
        rank = float(row.get("rank") or 0.0)
        hits.append(Hit(
            root_id=row["rootId"], relpath=row["relpath"], name=row["name"],
            klass=row["klass"], size=int(row["size"]), mtime=float(row["mtime"]),
            score=1.0 + max(0.0, -rank), engine="fts",
            snippet=row.get("snippet") or "", offset=int(row.get("startOff") or 0),
            page=row.get("page"), chunk_id=int(row.get("ord") or 0),
        ))
    return hits


def _fuse(hits: list[Hit], *, query: str, limit: int) -> list[Hit]:
    """Dedupe by file+offset and keep the best-scoring copy of each match."""
    best: dict[tuple[str, str, int], Hit] = {}
    for hit in hits:
        key = (hit.root_id, hit.relpath, int(hit.offset or 0))
        current = best.get(key)
        if current is None or hit.score > current.score:
            best[key] = hit
    ordered = sorted(best.values(), key=lambda h: (-h.score, -h.mtime, h.relpath))
    return ordered[:limit]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def absolute_path(catalog: Catalog, hit: Hit) -> Optional[str]:
    root = catalog.get_root(hit.root_id)
    if not root:
        return None
    return os.path.join(root.path, hit.relpath.replace("/", os.sep))


__all__ = ["plan_and_search", "absolute_path"]
