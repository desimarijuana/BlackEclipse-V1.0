"""Incremental, resumable directory scanning.

A scan never opens file content: it stats entries, classifies by extension, and
writes catalog rows in bounded batches. That is what makes a million-file folder
take minutes once, and a re-scan seconds. Unknown extensions are classified
lazily at probe time, when the file is actually opened.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .catalog import Catalog, extension_of, normalize_relpath, now_iso
from .config import SourceConfig, load_config
from .contracts import RootRecord, ScanStats
from .probe import (
    ARCHIVE_EXTS, AUDIO_EXTS, CODE_EXTS, DOC_EXTS, IMAGE_EXTS, TABLE_EXTS,
    TEXT_EXTS, VIDEO_EXTS,
)

_CANCELLED = threading.Event()


def quick_class(ext: str) -> str:
    """Classify by extension only. Never touches the file."""
    if ext in ("parquet", "csv", "tsv", "jsonl", "ndjson", "xlsx", "xls"):
        return "table"
    if ext in ("pdf", "docx", "pptx", "epub", "odt", "ods", "odp", "rtf", "doc", "ppt"):
        return "document"
    if ext in ("sqlite", "sqlite3", "db"):
        return "database"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in CODE_EXTS:
        return "code"
    if ext in TEXT_EXTS:
        return "text"
    if ext in ("bin", "exe", "dll", "so", "dylib", "dat", "iso", "img", "o", "a", "class"):
        return "binary"
    return "unknown"


def scan_root(
    catalog: Catalog,
    root: RootRecord,
    *,
    config: Optional[SourceConfig] = None,
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> ScanStats:
    """Walk one root, upserting changed files and removing vanished ones."""
    cfg = config or catalog.config
    started = time.monotonic()
    stats = ScanStats(root_id=root.id)
    epoch = catalog.begin_scan(root.id)
    token = cancel or _CANCELLED
    stack: list[tuple[str, int]] = [(root.path, 0)]
    ignored = set(cfg.ignore_dirs)
    pending = 0
    last_commit = time.monotonic()

    def commit() -> None:
        nonlocal pending, last_commit
        if pending:
            catalog._db.commit()  # noqa: SLF001 - the scanner owns the write path
            pending = 0
        last_commit = time.monotonic()

    try:
        while stack:
            if token.is_set():
                commit()
                stats.error = "cancelled"
                catalog._db.execute(
                    "UPDATE Root SET status='PARTIAL' WHERE id=?", (root.id,)
                )
                catalog._db.commit()
                stats.elapsed_ms = int((time.monotonic() - started) * 1000)
                return stats
            directory, depth = stack.pop()
            try:
                entries = os.scandir(directory)
            except OSError:
                continue
            with entries:
                for entry in entries:
                    if token.is_set():
                        break
                    try:
                        if entry.is_symlink() and not cfg.follow_symlinks:
                            continue
                        if entry.is_dir(follow_symlinks=cfg.follow_symlinks):
                            if entry.name in ignored or depth >= cfg.max_depth:
                                continue
                            stack.append((entry.path, depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=cfg.follow_symlinks):
                            continue
                        info = entry.stat(follow_symlinks=cfg.follow_symlinks)
                    except OSError:
                        continue
                    stats.files_seen += 1
                    stats.bytes_seen += int(info.st_size)
                    if stats.files_seen > cfg.max_scan_files:
                        stats.truncated = True
                        break
                    rel = normalize_relpath(os.path.relpath(entry.path, root.path))
                    ext = extension_of(entry.name)
                    outcome = catalog.upsert_file(
                        root.id,
                        {
                            "relpath": rel,
                            "name": entry.name,
                            "ext": ext,
                            "size": int(info.st_size),
                            "mtime": float(info.st_mtime),
                            "inode": str(getattr(info, "st_ino", "") or ""),
                            "root_path": root.path,
                            "klass": quick_class(ext),
                        },
                        epoch,
                    )
                    pending += 1
                    if outcome == "added":
                        stats.added += 1
                    elif outcome == "updated":
                        stats.updated += 1
                    else:
                        stats.unchanged += 1
                    if pending >= cfg.scan_batch or (time.monotonic() - last_commit) > 2.0:
                        commit()
                        if on_progress:
                            on_progress(_progress(stats, started))
                if stats.truncated:
                    break
        commit()
        if stats.truncated:
            catalog._db.execute(
                "UPDATE Root SET status='PARTIAL', lastScanAt=? WHERE id=?",
                (now_iso(), root.id),
            )
            catalog._db.commit()
        else:
            stats.removed = catalog.finish_scan(root.id, epoch)
        stats.elapsed_ms = int((time.monotonic() - started) * 1000)
        if on_progress:
            on_progress(_progress(stats, started))
        return stats
    except Exception as exc:  # noqa: BLE001 - a scan failure is a reported state
        commit()
        catalog.set_root_error(root.id, str(exc))
        stats.error = str(exc)
        stats.elapsed_ms = int((time.monotonic() - started) * 1000)
        return stats


def _progress(stats: ScanStats, started: float) -> dict[str, Any]:
    return {
        "rootId": stats.root_id,
        "filesSeen": stats.files_seen,
        "added": stats.added,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "bytesSeen": stats.bytes_seen,
        "elapsedMs": int((time.monotonic() - started) * 1000),
        "truncated": stats.truncated,
    }


__all__ = ["scan_root", "quick_class"]
