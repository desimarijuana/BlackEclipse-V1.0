"""Configuration for the large-corpus source layer (``sources``).

A *source root* is a folder or drive the operator registers. Nothing is copied:
the catalog stores one row per file and every read/query goes back to the
original bytes. Derived state (chunk index, vectors, DuckDB spill files) lives
under ``<repo>/.black-eclipse/sources`` and is disposable.

Everything here is bounded. There is no "unlimited" setting: the layer is meant
to survive a terabyte corpus on a small machine, so every budget has a ceiling
that configuration may lower but never raise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Hard ceilings. Configuration can only lower a budget, never exceed these.
MAX_SCAN_FILES_CEILING = 20_000_000
MAX_DEPTH_CEILING = 256
MAX_INDEX_BYTES_CEILING = 2 * 1024 * 1024 * 1024      # 2 GiB per file
MAX_CHUNKS_TOTAL_CEILING = 50_000_000
MAX_READ_BYTES_CEILING = 8 * 1024 * 1024             # 8 MiB per read window
MAX_SCAN_BYTES_CEILING = 64 * 1024 * 1024 * 1024     # 64 GiB per raw scan
MAX_QUERY_ROWS_CEILING = 5_000
MAX_VECTORS_CEILING = 5_000_000


def sources_dir() -> Path:
    """``<repo>/.black-eclipse/sources`` — derived state, never user folders."""
    override = os.environ.get("ECLIPSE_SOURCES_DIR")
    if override:
        path = Path(os.path.abspath(override))
    else:
        try:
            from ..eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
        except Exception:  # noqa: BLE001 - a missing repo root must not crash config
            base = Path(os.path.expanduser("~"))
        path = base / ".black-eclipse" / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> str:
    override = os.environ.get("ECLIPSE_SOURCES_DB_PATH")
    if override:
        return os.path.abspath(override)
    return str(sources_dir() / "sources.db")


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


DEFAULT_IGNORE_DIRS = (
    ".git", ".hg", ".svn", ".black-eclipse", "$RECYCLE.BIN",
    "System Volume Information", "node_modules", "__pycache__",
    ".venv", "venv", "site-packages",
)


@dataclass
class SourceConfig:
    """All tunables for the source layer, resolved for this process."""

    enabled: bool = True
    db_path: str = field(default_factory=default_db_path)
    tmp_dir: str = ""
    # Roots.
    max_roots: int = 32
    # Scan.
    max_scan_files: int = 2_000_000
    max_depth: int = 64
    scan_batch: int = 500
    ignore_dirs: tuple[str, ...] = DEFAULT_IGNORE_DIRS
    follow_symlinks: bool = False
    # Index (text chunks).
    index_max_file_bytes: int = 64 * 1024 * 1024
    index_max_chunks_per_file: int = 2_000
    index_max_chunks_total: int = 5_000_000
    chunk_chars: int = 1_200
    chunk_overlap: int = 150
    index_pdf_max_pages: int = 500
    # Read windows.
    window_bytes: int = 256 * 1024
    max_read_bytes: int = 1024 * 1024
    max_line_window: int = 5_000
    # Raw scan fallback.
    scan_max_bytes: int = 512 * 1024 * 1024
    scan_max_file_bytes: int = 64 * 1024 * 1024
    scan_timeout_s: float = 20.0
    scan_workers: int = 4
    # DuckDB.
    query_timeout_s: float = 30.0
    query_memory_limit: str = "1GB"
    query_max_rows: int = 500
    query_threads: int = 2
    # Results.
    max_results: int = 200
    # Semantic index (opt-in).
    semantic_enabled: bool = False
    semantic_max_vectors: int = 500_000
    semantic_batch: int = 32
    semantic_min_chars: int = 120

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        if self.tmp_dir:
            Path(self.tmp_dir).mkdir(parents=True, exist_ok=True)


def load_config(overrides: Optional[dict[str, Any]] = None) -> SourceConfig:
    overrides = overrides or {}
    env = os.environ
    base = SourceConfig()
    cfg = SourceConfig(
        enabled=_bool(overrides.get("enabled", env.get("HARNESS_SOURCES_ENABLED")), base.enabled),
        db_path=str(overrides.get("db_path") or default_db_path()),
        tmp_dir=str(overrides.get("tmp_dir") or (sources_dir() / "tmp")),
        max_roots=_int(overrides.get("max_roots", env.get("HARNESS_SOURCES_MAX_ROOTS")), 32, low=1, high=128),
        max_scan_files=_int(
            overrides.get("max_scan_files", env.get("HARNESS_SOURCES_MAX_FILES")),
            base.max_scan_files, low=1_000, high=MAX_SCAN_FILES_CEILING,
        ),
        max_depth=_int(overrides.get("max_depth", env.get("HARNESS_SOURCES_MAX_DEPTH")), 64, low=1, high=MAX_DEPTH_CEILING),
        scan_batch=_int(overrides.get("scan_batch"), 500, low=50, high=10_000),
        follow_symlinks=_bool(overrides.get("follow_symlinks", env.get("HARNESS_SOURCES_FOLLOW_LINKS")), False),
        index_max_file_bytes=_int(
            overrides.get("index_max_file_bytes", env.get("HARNESS_SOURCES_INDEX_MAX_BYTES")),
            base.index_max_file_bytes, low=1024, high=MAX_INDEX_BYTES_CEILING,
        ),
        index_max_chunks_per_file=_int(
            overrides.get("index_max_chunks_per_file", env.get("HARNESS_SOURCES_MAX_CHUNKS_FILE")),
            2_000, low=1, high=1_000_000,
        ),
        index_max_chunks_total=_int(
            overrides.get("index_max_chunks_total", env.get("HARNESS_SOURCES_MAX_CHUNKS")),
            base.index_max_chunks_total, low=1_000, high=MAX_CHUNKS_TOTAL_CEILING,
        ),
        chunk_chars=_int(overrides.get("chunk_chars", env.get("HARNESS_SOURCES_CHUNK_CHARS")), 1_200, low=200, high=20_000),
        chunk_overlap=_int(overrides.get("chunk_overlap", env.get("HARNESS_SOURCES_CHUNK_OVERLAP")), 150, low=0, high=5_000),
        index_pdf_max_pages=_int(overrides.get("index_pdf_max_pages", env.get("HARNESS_SOURCES_PDF_PAGES")), 500, low=1, high=10_000),
        window_bytes=_int(overrides.get("window_bytes", env.get("HARNESS_SOURCES_WINDOW_BYTES")), 256 * 1024, low=1024, high=MAX_READ_BYTES_CEILING),
        max_read_bytes=_int(overrides.get("max_read_bytes", env.get("HARNESS_SOURCES_MAX_READ_BYTES")), 1024 * 1024, low=1024, high=MAX_READ_BYTES_CEILING),
        max_line_window=_int(overrides.get("max_line_window", env.get("HARNESS_SOURCES_MAX_LINES")), 5_000, low=1, high=200_000),
        scan_max_bytes=_int(
            overrides.get("scan_max_bytes", env.get("HARNESS_SOURCES_SCAN_MAX_BYTES")),
            base.scan_max_bytes, low=1024 * 1024, high=MAX_SCAN_BYTES_CEILING,
        ),
        scan_max_file_bytes=_int(
            overrides.get("scan_max_file_bytes", env.get("HARNESS_SOURCES_SCAN_MAX_FILE_BYTES")),
            base.scan_max_file_bytes, low=1024 * 1024, high=MAX_INDEX_BYTES_CEILING,
        ),
        scan_timeout_s=_float(overrides.get("scan_timeout_s", env.get("HARNESS_SOURCES_SCAN_TIMEOUT")), 20.0, low=0.5, high=600.0),
        scan_workers=_int(overrides.get("scan_workers", env.get("HARNESS_SOURCES_SCAN_WORKERS")), 4, low=1, high=16),
        query_timeout_s=_float(overrides.get("query_timeout_s", env.get("HARNESS_SOURCES_QUERY_TIMEOUT")), 30.0, low=0.5, high=600.0),
        query_memory_limit=str(overrides.get("query_memory_limit") or env.get("HARNESS_SOURCES_QUERY_MEMORY") or "1GB"),
        query_max_rows=_int(
            overrides.get("query_max_rows", env.get("HARNESS_SOURCES_QUERY_ROWS")),
            500, low=1, high=MAX_QUERY_ROWS_CEILING,
        ),
        query_threads=_int(overrides.get("query_threads", env.get("HARNESS_SOURCES_QUERY_THREADS")), 2, low=1, high=32),
        max_results=_int(overrides.get("max_results", env.get("HARNESS_SOURCES_MAX_RESULTS")), 200, low=1, high=2_000),
        semantic_enabled=_bool(overrides.get("semantic_enabled", env.get("HARNESS_SOURCES_SEMANTIC")), False),
        semantic_max_vectors=_int(
            overrides.get("semantic_max_vectors", env.get("HARNESS_SOURCES_MAX_VECTORS")),
            base.semantic_max_vectors, low=100, high=MAX_VECTORS_CEILING,
        ),
        semantic_batch=_int(overrides.get("semantic_batch", env.get("HARNESS_SOURCES_BATCH")), 32, low=1, high=256),
        semantic_min_chars=_int(overrides.get("semantic_min_chars"), 120, low=1, high=10_000),
    )
    cfg.ensure_dirs()
    return cfg


__all__ = [
    "SourceConfig", "load_config", "sources_dir", "default_db_path",
    "DEFAULT_IGNORE_DIRS", "MAX_INDEX_BYTES_CEILING", "MAX_SCAN_FILES_CEILING",
]
