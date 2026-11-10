"""Plain data contracts for the source layer.

These are the wire shapes returned by the HTTP routes and the agent tools.
They are deliberately small: a source *card* is bounded regardless of whether
the file is 2 MB or 4 TB, which is what keeps the model context constant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Format classes. One classifier drives probe, indexing and query routing.
CLASSES = (
    "table", "document", "text", "code", "image", "audio", "video",
    "archive", "database", "binary", "empty", "unknown",
)


@dataclass
class RootRecord:
    id: str
    path: str
    label: str
    created_at: str
    last_scan_at: Optional[str] = None
    file_count: int = 0
    total_bytes: int = 0
    status: str = "READY"
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileRecord:
    id: int
    root_id: str
    relpath: str
    name: str
    ext: str
    size: int
    mtime: float
    klass: str
    magic: Optional[str] = None
    indexed_at: Optional[str] = None
    chunk_count: int = 0
    scanned_at: Optional[str] = None
    root_path: str = ""

    @property
    def abspath(self) -> str:
        if not self.root_path:
            return self.relpath
        import os

        return os.path.join(self.root_path, self.relpath.replace("/", os.sep))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCard:
    """The bounded preview of a file or folder. Never contains the content."""

    path: str
    name: str
    klass: str
    size: int
    mtime: float
    magic: Optional[str] = None
    # Text preview windows (already bounded and decoded).
    head: str = ""
    tail: str = ""
    truncated: bool = False
    # Tabular metadata.
    columns: list[dict[str, Any]] = field(default_factory=list)
    rows_hint: Optional[int] = None
    delimiter: Optional[str] = None
    # Media / document metadata.
    pages: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    entries: Optional[int] = None
    # Index state.
    indexed: bool = False
    chunks: int = 0
    index_state: str = "NOT_INDEXED"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def brief(self, *, max_head: int = 900) -> dict[str, Any]:
        """A context-sized card: the model gets this, not the file."""
        data = self.to_dict()
        data["head"] = (self.head or "")[:max_head]
        data["tail"] = (self.tail or "")[-max_head // 3:]
        return data


@dataclass
class Hit:
    root_id: str
    relpath: str
    name: str
    klass: str
    size: int
    mtime: float
    score: float = 0.0
    engine: str = "metadata"
    snippet: Optional[str] = None
    line: Optional[int] = None
    offset: Optional[int] = None
    page: Optional[int] = None
    chunk_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryPlan:
    mode: str
    engines: list[str] = field(default_factory=list)
    reason: str = ""
    candidates: int = 0
    budget_bytes: int = 0
    budget_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    query: str
    plan: QueryPlan
    hits: list[Hit] = field(default_factory=list)
    scanned_files: int = 0
    scanned_bytes: int = 0
    elapsed_ms: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "plan": self.plan.to_dict(),
            "hits": [h.to_dict() for h in self.hits],
            "scannedFiles": self.scanned_files,
            "scannedBytes": self.scanned_bytes,
            "elapsedMs": self.elapsed_ms,
            "truncated": self.truncated,
            "warnings": self.warnings,
        }


@dataclass
class SqlResult:
    ok: bool
    sql: str
    source: Optional[str] = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: int = 0
    bytes_read: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanStats:
    root_id: str
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    files_seen: int = 0
    bytes_seen: int = 0
    elapsed_ms: int = 0
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rootId": self.root_id, "added": self.added, "updated": self.updated,
            "unchanged": self.unchanged, "removed": self.removed,
            "filesSeen": self.files_seen, "bytesSeen": self.bytes_seen,
            "elapsedMs": self.elapsed_ms, "truncated": self.truncated,
            "error": self.error,
        }


__all__ = [
    "CLASSES", "RootRecord", "FileRecord", "SourceCard", "Hit",
    "QueryPlan", "SearchResult", "SqlResult", "ScanStats",
]
