"""Incremental text indexing for source files.

The indexer is deliberately lazy: it only touches files a query has already
selected, and it stops at a file/time/chunk budget. Nothing about opening a
terabyte corpus requires indexing it. This is the "pay once per region you
touch" half of the design.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from .catalog import Catalog
from .config import SourceConfig
from .contracts import FileRecord
from .extract import extract_chunks

_INDEXABLE = {"text", "code", "table", "document", "archive", "database"}


def index_files(
    catalog: Catalog,
    files: Iterable[FileRecord],
    *,
    config: Optional[SourceConfig] = None,
    limit_files: int = 200,
    budget_s: float = 45.0,
    cancel=None,
) -> dict[str, Any]:
    """Index up to ``limit_files`` files. Returns counters + warnings."""
    cfg = config or catalog.config
    started = time.monotonic()
    deadline = started + max(1.0, budget_s)
    result = {
        "indexed": 0, "skipped": 0, "chunks": 0, "bytes": 0,
        "reasons": {}, "elapsedMs": 0,
    }
    total_chunks = catalog.chunk_count()
    for file in files:
        if result["indexed"] + result["skipped"] >= limit_files:
            break
        if time.monotonic() >= deadline:
            result["reasons"]["budget"] = "stopped at the indexing time budget"
            break
        if cancel is not None and cancel.is_set():
            result["reasons"]["cancelled"] = "indexing was cancelled"
            break
        if file.klass not in _INDEXABLE:
            result["skipped"] += 1
            continue
        if file.size > cfg.index_max_file_bytes:
            result["skipped"] += 1
            result["reasons"]["size"] = "some files are over the indexing ceiling"
            continue
        if total_chunks >= cfg.index_max_chunks_total:
            result["reasons"]["chunks"] = "the chunk ceiling is reached"
            break
        chunks, meta = extract_chunks(file, file.abspath, config=cfg, cancel=cancel)
        if not chunks:
            reason = meta.get("reason") or "no extractable text"
            result["reasons"][reason] = result["reasons"].get(reason, 0) + 1
            result["skipped"] += 1
            continue
        chunks = chunks[: cfg.index_max_chunks_per_file]
        stored = catalog.replace_chunks(file, chunks)
        catalog.mark_indexed(file.id, stored, meta.get("hash"))
        total_chunks += stored
        result["indexed"] += 1
        result["chunks"] += stored
        result["bytes"] += int(meta.get("bytes") or 0)
    result["elapsedMs"] = int((time.monotonic() - started) * 1000)
    return result


def unindexed(
    catalog: Catalog,
    *,
    root_ids: Optional[list[str]] = None,
    limit: int = 500,
) -> list[FileRecord]:
    """Files the catalog has not indexed yet, newest first."""
    files = catalog.list_files(root_ids=root_ids, limit=limit * 4, order="mtime_desc")
    return [f for f in files if not f.indexed_at and f.klass in _INDEXABLE][:limit]


__all__ = ["index_files", "unindexed"]
