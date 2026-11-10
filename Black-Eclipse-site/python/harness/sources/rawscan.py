"""Bounded parallel content scan — the honest fallback before any index exists.

This is deliberately *not* a full-text index. It reads files in 1 MiB windows,
stops on a byte budget, a time budget, a result cap, or cancellation, and it
reports exactly what it covered. A cold terabyte corpus is not searchable in
milliseconds; this makes the first query useful and bounded instead of a hang.
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from .config import SourceConfig
from .contracts import FileRecord, Hit

_SKIP_CLASSES = {"image", "audio", "video", "archive", "binary", "database", "empty"}
_CONTEXT = 180
_WINDOW = 1024 * 1024


def raw_scan(
    files: Iterable[FileRecord],
    query: str,
    *,
    config: SourceConfig,
    regex: bool = False,
    case_sensitive: bool = False,
    cancel=None,
    max_results: Optional[int] = None,
) -> tuple[list[Hit], int, int, bool, list[str]]:
    """Return (hits, scanned_bytes, scanned_files, truncated, warnings)."""
    started = time.monotonic()
    deadline = started + config.scan_timeout_s
    warnings: list[str] = []
    pattern = _compile(query, regex=regex, case_sensitive=case_sensitive)
    if pattern is None:
        return [], 0, 0, False, ["empty or invalid pattern"]

    candidates = [
        f for f in files
        if f.klass not in _SKIP_CLASSES
        and 0 < f.size <= config.scan_max_file_bytes
    ]
    skipped_large = sum(1 for f in files if f.size > config.scan_max_file_bytes)
    if skipped_large:
        warnings.append(f"{skipped_large} file(s) skipped: over the per-file scan ceiling")
    if not candidates:
        return [], 0, 0, False, warnings + ["no text-like files matched the filters"]

    limit = int(max_results or config.max_results)
    hits: list[Hit] = []
    scanned_bytes = 0
    scanned_files = 0
    truncated = False
    bytes_left = config.scan_max_bytes
    name_lower = query.casefold() if not regex else ""

    pending: dict = {}
    with ThreadPoolExecutor(max_workers=max(1, config.scan_workers)) as pool:
        for file in candidates:
            if bytes_left <= 0 or time.monotonic() >= deadline or len(hits) >= limit:
                truncated = True
                break
            if cancel is not None and cancel.is_set():
                return hits, scanned_bytes, scanned_files, True, warnings + ["cancelled"]
            allowance = min(config.scan_max_file_bytes, bytes_left)
            abs_path = file.abspath
            if not abs_path or not os.path.exists(abs_path):
                continue
            # Charge the file's real size (bounded by the per-file cap), not the
            # per-file allowance — otherwise one small file would consume the
            # entire corpus budget.
            bytes_left -= min(max(1, file.size), allowance)
            pending[pool.submit(_scan_one, abs_path, file, pattern, allowance, limit, name_lower, cancel)] = file
            if len(pending) >= max(1, config.scan_workers) * 4:
                completed = _collect(pending)
                for file_hits, read_bytes, capped in completed:
                    scanned_files += 1
                    scanned_bytes += read_bytes
                    hits.extend(file_hits)
                    truncated = truncated or capped
                if len(hits) >= limit:
                    truncated = True
                    break
        for file_hits, read_bytes, capped in _collect(pending):
            scanned_files += 1
            scanned_bytes += read_bytes
            hits.extend(file_hits)
            truncated = truncated or capped

    if time.monotonic() >= deadline:
        truncated = True
        warnings.append(f"stopped at the {config.scan_timeout_s:g}s scan budget")
    if scanned_bytes >= config.scan_max_bytes:
        truncated = True
        warnings.append("stopped at the scan byte budget")
    if len(hits) > limit:
        hits = hits[:limit]
        truncated = True
    hits.sort(key=lambda h: (-h.score, -h.mtime))
    return hits, scanned_bytes, scanned_files, truncated, warnings


def _collect(pending: dict) -> list[tuple[list[Hit], int, bool]]:
    out: list[tuple[list[Hit], int, bool]] = []
    for future in as_completed(list(pending)):
        pending.pop(future, None)
        try:
            out.append(future.result())
        except Exception:  # noqa: BLE001 - one unreadable file is not a scan failure
            out.append(([], 0, False))
    return out


def _compile(query: str, *, regex: bool, case_sensitive: bool):
    if not query:
        return None
    try:
        return re.compile(query if regex else re.escape(query), 0 if case_sensitive else re.IGNORECASE)
    except re.error:
        return None


def _scan_one(
    abs_path: str, file: FileRecord, pattern, allowance: int, limit: int,
    name_lower: str, cancel=None,
) -> tuple[list[Hit], int, bool]:
    hits: list[Hit] = []
    read_bytes = 0
    line_at_buffer_start = 1
    tail = ""
    capped = False
    try:
        with open(abs_path, "rb") as handle:
            while read_bytes < allowance:
                if cancel is not None and cancel.is_set():
                    break
                block = handle.read(min(_WINDOW, allowance - read_bytes))
                if not block:
                    break
                read_bytes += len(block)
                text = tail + block.decode("utf-8", "replace")
                for match in pattern.finditer(text):
                    start = max(0, match.start() - _CONTEXT)
                    end = min(len(text), match.end() + _CONTEXT)
                    snippet = " ".join(text[start:end].split())
                    line = line_at_buffer_start + text[: match.start()].count("\n")
                    boost = 2.0 if name_lower and name_lower in file.name.casefold() else 1.0
                    hits.append(Hit(
                        root_id=file.root_id, relpath=file.relpath, name=file.name,
                        klass=file.klass, size=file.size, mtime=file.mtime,
                        score=boost, engine="scan", snippet=snippet[:500], line=line,
                        offset=read_bytes - len(block) + max(0, match.start() - len(tail)),
                    ))
                    if len(hits) >= limit:
                        return hits, read_bytes, True
                keep = 512
                if len(text) > keep:
                    dropped = text[:-keep]
                    line_at_buffer_start += dropped.count("\n")
                    tail = text[-keep:]
                else:
                    tail = text
        return hits, read_bytes, capped
    except OSError:
        return hits, read_bytes, capped


__all__ = ["raw_scan"]
