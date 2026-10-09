"""Content classification — the ONE place a MIME type, category and preview kind
are derived. Extensions are a hint, never proof: where bytes are available the
leading magic bytes are sniffed, and the caller may always override with an
explicit type. Nothing here executes or interprets content.
"""

from __future__ import annotations

import mimetypes
import posixpath
import re
from typing import Optional

from .model import ArtifactCategory

# Magic-byte signatures. This is a bounded, best-effort sniff — never a security
# decision on its own (the storage layer also enforces size and confinement).
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # refined below (WEBP has WEBP at offset 8)
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x1f\x8b", "application/gzip"),
    (b"ID3", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"\x00\x00\x00\x18ftyp", "video/mp4"),
    (b"\x00\x00\x00\x20ftyp", "video/mp4"),
    (b"SQLite format 3\x00", "application/vnd.sqlite3"),
)

_MIME_OVERRIDES: dict[str, str] = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "ndjson": "application/x-ndjson",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "toml": "application/toml",
    "xml": "application/xml",
    "html": "text/html",
    "htm": "text/html",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "parquet": "application/vnd.apache.parquet",
    "py": "text/x-python",
    "ts": "text/x-typescript",
    "tsx": "text/x-typescript",
    "js": "text/javascript",
    "jsx": "text/javascript",
    "sql": "application/sql",
    "sh": "text/x-shellscript",
    "log": "text/plain",
    "txt": "text/plain",
    "svg": "image/svg+xml",
    "zip": "application/zip",
    "gz": "application/gzip",
    "tar": "application/x-tar",
}

# The category a MIME type maps to when no producer hint is available.
_MIME_CATEGORY: tuple[tuple[str, ArtifactCategory], ...] = (
    ("image/", ArtifactCategory.IMAGE),
    ("audio/", ArtifactCategory.AUDIO),
    ("video/", ArtifactCategory.VIDEO),
    ("text/csv", ArtifactCategory.DATASET),
    ("text/tab-separated", ArtifactCategory.DATASET),
    ("application/json", ArtifactCategory.DATASET),
    ("application/x-ndjson", ArtifactCategory.DATASET),
    ("application/vnd.apache.parquet", ArtifactCategory.DATASET),
    ("application/vnd.openxmlformats-officedocument.spreadsheetml", ArtifactCategory.SPREADSHEET),
    ("application/vnd.ms-excel", ArtifactCategory.SPREADSHEET),
    ("application/pdf", ArtifactCategory.DOCUMENT),
    ("application/msword", ArtifactCategory.DOCUMENT),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml", ArtifactCategory.DOCUMENT),
    ("application/vnd.openxmlformats-officedocument.presentationml", ArtifactCategory.PRESENTATION),
    ("application/vnd.ms-powerpoint", ArtifactCategory.PRESENTATION),
    ("text/markdown", ArtifactCategory.DOCUMENT),
    ("text/html", ArtifactCategory.DOCUMENT),
    ("text/plain", ArtifactCategory.DOCUMENT),
    ("text/x-python", ArtifactCategory.CODE),
    ("text/x-typescript", ArtifactCategory.CODE),
    ("text/javascript", ArtifactCategory.CODE),
    ("application/sql", ArtifactCategory.CODE),
    ("text/x-shellscript", ArtifactCategory.SCRIPT),
    ("application/zip", ArtifactCategory.ARCHIVE),
    ("application/gzip", ArtifactCategory.ARCHIVE),
    ("application/x-tar", ArtifactCategory.ARCHIVE),
)

_EXT_CATEGORY: dict[str, ArtifactCategory] = {
    "png": ArtifactCategory.IMAGE, "jpg": ArtifactCategory.IMAGE,
    "jpeg": ArtifactCategory.IMAGE, "webp": ArtifactCategory.IMAGE,
    "gif": ArtifactCategory.IMAGE, "svg": ArtifactCategory.IMAGE,
    "csv": ArtifactCategory.DATASET, "tsv": ArtifactCategory.DATASET,
    "json": ArtifactCategory.DATASET, "ndjson": ArtifactCategory.DATASET,
    "parquet": ArtifactCategory.DATASET,
    "xlsx": ArtifactCategory.SPREADSHEET, "xls": ArtifactCategory.SPREADSHEET,
    "pdf": ArtifactCategory.DOCUMENT, "docx": ArtifactCategory.DOCUMENT,
    "doc": ArtifactCategory.DOCUMENT, "md": ArtifactCategory.DOCUMENT,
    "markdown": ArtifactCategory.DOCUMENT, "txt": ArtifactCategory.DOCUMENT,
    "html": ArtifactCategory.DOCUMENT, "htm": ArtifactCategory.DOCUMENT,
    "pptx": ArtifactCategory.PRESENTATION, "ppt": ArtifactCategory.PRESENTATION,
    "py": ArtifactCategory.CODE, "ts": ArtifactCategory.CODE,
    "tsx": ArtifactCategory.CODE, "js": ArtifactCategory.CODE,
    "jsx": ArtifactCategory.CODE, "sql": ArtifactCategory.CODE,
    "sh": ArtifactCategory.SCRIPT, "bash": ArtifactCategory.SCRIPT,
    "ps1": ArtifactCategory.SCRIPT,
    "log": ArtifactCategory.LOG,
    "zip": ArtifactCategory.ARCHIVE, "gz": ArtifactCategory.ARCHIVE,
    "tar": ArtifactCategory.ARCHIVE,
    "mp3": ArtifactCategory.AUDIO, "wav": ArtifactCategory.AUDIO,
    "ogg": ArtifactCategory.AUDIO, "flac": ArtifactCategory.AUDIO,
    "mp4": ArtifactCategory.VIDEO, "webm": ArtifactCategory.VIDEO,
    "mov": ArtifactCategory.VIDEO,
}

_UNSAFE_NAME = re.compile(r"[^\w.\- ]+", re.UNICODE)


def extension_of(name: str) -> str:
    """Lowercase extension without the dot. A dotfile has no extension."""
    base = posixpath.basename(name or "")
    if "." not in base or base.startswith(".") and base.count(".") == 1:
        return ""
    return base.rsplit(".", 1)[-1].casefold()


def safe_display_name(name: str, *, fallback: str = "artifact") -> str:
    """A display name with path separators and control characters removed.

    This is for STORAGE key derivation and UI display; the original filename is
    kept verbatim in `originalName` for provenance.
    """
    base = posixpath.basename((name or "").replace("\\", "/"))
    base = _UNSAFE_NAME.sub("_", base).strip(" .")
    if not base:
        return fallback
    return base[:200]


def guess_mime(name: str, explicit: Optional[str] = None, *, header: bytes = b"") -> str:
    """Resolve a MIME type from (in priority): explicit hint, magic bytes, ext."""
    if explicit and explicit.strip():
        return explicit.strip().lower()
    sniffed = sniff_mime(header)
    if sniffed:
        return sniffed
    ext = extension_of(name)
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    guessed, _ = mimetypes.guess_type(name or "")
    return guessed or "application/octet-stream"


def sniff_mime(header: bytes) -> Optional[str]:
    if not header:
        return None
    for magic, mime in _MAGIC:
        if header.startswith(magic):
            if magic == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
                return "image/webp"
            if magic == b"PK\x03\x04":
                # A ZIP container may be an OOXML document; refine by name later.
                return "application/zip"
            return mime
    return None


def category_for(
    name: str, mime: str, *, source_tool: Optional[str] = None
) -> ArtifactCategory:
    """Content-derived category. A producer hint wins, then MIME, then extension.

    Extensions alone never establish the category: MIME (which may come from
    sniffing) is consulted first.
    """
    tool = (source_tool or "").casefold()
    if "backtest" in tool or "quant" in tool:
        return ArtifactCategory.BACKTEST
    if "chart" in tool or "plot" in tool or "matplotlib" in tool:
        return ArtifactCategory.CHART
    lowered = (mime or "").lower()
    for prefix, category in _MIME_CATEGORY:
        if lowered.startswith(prefix):
            return category
    ext = extension_of(name)
    return _EXT_CATEGORY.get(ext, ArtifactCategory.OTHER)


def preview_kind(mime: str, category: ArtifactCategory, name: str = "") -> str:
    """The renderer a client should use. Never implies the file is safe."""
    lowered = (mime or "").lower()
    ext = extension_of(name)
    if lowered.startswith("image/"):
        return "image"
    if lowered.startswith("audio/"):
        return "audio"
    if lowered.startswith("video/"):
        return "video"
    if lowered == "application/pdf":
        return "pdf"
    if lowered in ("text/csv", "text/tab-separated-values") or ext in ("csv", "tsv"):
        return "table"
    if lowered in ("application/json", "application/x-ndjson") or ext in ("json", "ndjson"):
        return "json"
    if lowered == "text/markdown" or ext in ("md", "markdown"):
        return "markdown"
    if lowered == "text/html" or ext in ("html", "htm"):
        return "html"
    if category == ArtifactCategory.CODE or ext in (
        "py", "ts", "tsx", "js", "jsx", "sql", "sh", "bash", "ps1", "rs", "go", "java", "c", "cpp",
    ):
        return "code"
    if lowered.startswith("text/") or ext in ("txt", "log", "yml", "yaml", "toml", "xml", "ini", "cfg"):
        return "text"
    return "unsupported"


#: Preview kinds a client may render inline. `html` is deliberately rendered in
#: an isolated context by the client, never in the app origin.
INLINE_PREVIEW_KINDS: frozenset[str] = frozenset(
    {"image", "pdf", "table", "json", "markdown", "code", "text", "audio", "video", "html"}
)


__all__ = [
    "category_for",
    "extension_of",
    "guess_mime",
    "INLINE_PREVIEW_KINDS",
    "preview_kind",
    "safe_display_name",
    "sniff_mime",
]
