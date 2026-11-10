"""Format probing: open anything in milliseconds without reading it.

The contract is narrow: read at most a few kilobytes from the head and tail,
identify the format from magic bytes (never trust the extension alone), then
return a *card* with whatever metadata is cheap to obtain — schema, row count,
page count, image size, archive entry count. Expensive work (full text, OCR,
rendering) never happens here; it is deferred to the indexer or to an explicit
read window.
"""

from __future__ import annotations

import os
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Optional

from .config import SourceConfig
from .contracts import SourceCard

TEXT_EXTS = {
    "txt", "md", "markdown", "rst", "log", "csv", "tsv", "json", "jsonl", "ndjson",
    "xml", "yaml", "yml", "toml", "ini", "cfg", "conf", "env", "sql",
}
CODE_EXTS = {
    "py", "js", "jsx", "ts", "tsx", "java", "cs", "go", "rs", "rb", "php", "c",
    "h", "cpp", "hpp", "swift", "kt", "scala", "sh", "ps1", "bat", "lua", "r",
    "dart", "ex", "exs", "sql", "html", "css", "scss", "vue", "svelte",
}
TABLE_EXTS = {"csv", "tsv", "parquet", "jsonl", "ndjson", "xlsx", "xls"}
DOC_EXTS = {"pdf", "docx", "pptx", "epub", "odt", "ods", "odp", "rtf", "doc", "ppt"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff", "ico", "svg", "heic"}
AUDIO_EXTS = {"mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "wma"}
VIDEO_EXTS = {"mp4", "mkv", "mov", "avi", "webm", "wmv", "flv", "m4v"}
ARCHIVE_EXTS = {"zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar", "zst"}

_MAGIC = (
    (b"%PDF-", "pdf"),
    (b"PAR1", "parquet"),
    (b"PAR2", "parquet"),
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"SQLite format 3\x00", "sqlite"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "riff"),
    (b"OggS", "ogg"),
    (b"ID3", "mp3"),
    (b"fLaC", "flac"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07", "rar"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"BM", "bmp"),
    (b"MZ", "exe"),
    (b"\x7fELF", "elf"),
    (b"ustar", "tar"),
)


def sniff_magic(head: bytes) -> Optional[str]:
    """Identify a container from its first bytes. ``tar`` may be at 257."""
    for prefix, name in _MAGIC:
        if head.startswith(prefix):
            return name
    if len(head) > 262 and head[257:262] == b"ustar":
        return "tar"
    if head[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if head[:4] == b"II*\x00" or head[:4] == b"MM\x00*":
        return "tiff"
    return None


def classify(ext: str, magic: Optional[str], head: bytes) -> str:
    """Map extension + magic + sample to one class used by routing."""
    ext = (ext or "").lower()
    if magic in ("parquet",):
        return "table"
    if magic in ("sqlite",):
        return "database"
    if magic in ("png", "jpeg", "gif", "bmp", "ico", "tiff", "riff") and ext not in VIDEO_EXTS:
        # RIFF is wav or webp; the extension disambiguates.
        if magic == "riff" and ext == "webp":
            return "image"
        if magic == "riff" and ext in AUDIO_EXTS:
            return "audio"
        return "image" if ext in IMAGE_EXTS else ("audio" if ext in AUDIO_EXTS else "binary")
    if magic in ("pdf",):
        return "document"
    if magic in ("zip", "gzip", "bzip2", "xz", "zstd", "7z", "rar", "tar"):
        if ext in ("docx", "xlsx", "pptx", "odt", "ods", "odp", "epub"):
            return "document"
        return "archive"
    if magic in ("mp3", "flac", "ogg"):
        return "audio"
    if magic in VIDEO_EXTS:
        return "video"
    if ext in TABLE_EXTS:
        return "table"
    if ext in DOC_EXTS:
        return "document"
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
    # Unknown extension: decide from the sample. A high printable ratio is text.
    return "text" if looks_like_text(head) else "binary"


def looks_like_text(sample: bytes) -> bool:
    text = _decode(sample)
    if not text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
    return printable / max(1, len(text)) >= 0.85


def read_head(path: str, count: int) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read(count)
    except OSError:
        return b""


def read_tail(path: str, count: int) -> bytes:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.seek(max(0, size - count))
            return handle.read(count)
    except OSError:
        return b""


def _decode(sample: bytes) -> str:
    if not sample:
        return ""
    if sample[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return sample.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return sample.decode(encoding)
        except UnicodeDecodeError:
            continue
    return sample.decode("utf-8", errors="replace")


def decode_sample(sample: bytes) -> str:
    return _decode(sample)


def readable_strings(sample: bytes, *, min_len: int = 4, limit: int = 2_000) -> str:
    """Extract printable runs from a binary sample (bounded)."""
    runs = re.findall(rb"[ -~]{%d,}" % min_len, sample)
    text = "\n".join(run.decode("ascii", "replace") for run in runs[:400])
    return text[:limit]


def probe_file(
    path: str,
    *,
    klass_hint: Optional[str] = None,
    size: Optional[int] = None,
    mtime: Optional[float] = None,
    config: Optional[SourceConfig] = None,
    max_head: int = 4096,
    max_tail: int = 1024,
) -> SourceCard:
    """Build a bounded card for one file. Never raises for a missing file."""
    cfg = config
    head = read_head(path, max_head)
    tail = read_tail(path, max_tail) if (size or 0) > max_head else b""
    try:
        actual_size = int(size if size is not None else os.path.getsize(path))
        actual_mtime = float(mtime if mtime is not None else os.path.getmtime(path))
    except OSError:
        actual_size, actual_mtime = 0, 0.0
    name = Path(path).name
    ext = Path(name).suffix.lower().lstrip(".")
    magic = sniff_magic(head)
    klass = klass_hint or classify(ext, magic, head)
    card = SourceCard(
        path=str(path), name=name, klass=klass, size=actual_size,
        mtime=actual_mtime, magic=magic,
    )
    if actual_size == 0:
        card.klass = "empty"
        card.warnings.append("empty file")
        return card

    if klass in ("text", "code"):
        card.head = _decode(head)
        card.tail = _decode(tail) if tail else ""
        card.truncated = actual_size > len(head) + len(tail)
    elif klass in ("table", "document", "archive", "database", "image", "audio", "video"):
        _fill_structured(card, path, head, ext, magic, cfg)
    else:
        card.head = readable_strings(head, limit=1200)
        card.truncated = True
        card.warnings.append("opaque binary; preview is printable runs only")
    return card


def _fill_structured(
    card: SourceCard, path: str, head: bytes, ext: str, magic: Optional[str], cfg: Optional[SourceConfig]
) -> None:
    budget = (cfg.index_max_file_bytes if cfg else 64 * 1024 * 1024)
    if card.klass == "table":
        _fill_table(card, path, head, ext)
    elif card.klass == "document":
        if magic == "pdf" or ext == "pdf":
            card.pages = _pdf_pages(path)
        elif magic == "zip":
            card.entries = _zip_entries(path)
            card.warnings.append("Office/EPUB content is indexed on demand")
        else:
            card.warnings.append("legacy Office format; conversion is required to read it")
    elif card.klass == "archive":
        if magic == "zip":
            card.entries = _zip_entries(path)
        elif magic == "tar":
            card.entries = _tar_entries(path)
        else:
            card.warnings.append("compressed container; entries are listed on demand")
    elif card.klass == "database":
        card.warnings.append("open read-only through SQL; no copy is made")
    elif card.klass == "image":
        width, height = _image_size(head, magic)
        card.width, card.height = width, height
    elif card.klass == "audio":
        card.warnings.append("audio metadata only; transcription is a separate opt-in")
    elif card.klass == "video":
        card.warnings.append("video metadata only; frames/transcripts are separate tools")
    if card.size > budget and card.klass in ("table", "document"):
        card.warnings.append("large source: indexing is bounded and may be partial")


def _fill_table(card: SourceCard, path: str, head: bytes, ext: str) -> None:
    sample = _decode(head[:8192])
    if ext in ("csv", "tsv"):
        try:
            import csv
            import io

            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            card.delimiter = dialect.delimiter
            reader = csv.reader(io.StringIO(sample), dialect)
            header = next(reader, [])
            card.columns = [{"name": str(c).strip(), "type": "string"} for c in header[:40]]
        except Exception:  # noqa: BLE001 - a bad sample is not an error
            card.delimiter = "\t" if ext == "tsv" else ","
    try:
        from .query import describe_source

        described = describe_source(path)
        if described.get("ok"):
            card.columns = described.get("columns") or card.columns
            card.rows_hint = described.get("rows")
            card.delimiter = described.get("delimiter") or card.delimiter
        else:
            card.warnings.append(described.get("error") or "could not describe the table")
    except Exception as exc:  # noqa: BLE001 - DuckDB absent is an honest state
        card.warnings.append(f"schema unavailable: {exc}")


def _pdf_pages(path: str) -> Optional[int]:
    try:
        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(path, strict=False)
        return len(reader.pages)
    except Exception:  # noqa: BLE001 - an unreadable PDF is reported as unknown
        return None


def _zip_entries(path: str) -> Optional[int]:
    try:
        with zipfile.ZipFile(path) as archive:
            return len(archive.namelist())
    except Exception:  # noqa: BLE001
        return None


def _tar_entries(path: str) -> Optional[int]:
    try:
        import tarfile  # noqa: PLC0415

        count = 0
        with tarfile.open(path, "r:*") as archive:
            for _ in archive:
                count += 1
                if count > 100_000:
                    break
        return count
    except Exception:  # noqa: BLE001
        return None


def _image_size(head: bytes, magic: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    try:
        if magic == "png" and len(head) >= 24:
            width, height = struct.unpack(">II", head[16:24])
            return int(width), int(height)
        if magic == "gif" and len(head) >= 10:
            width, height = struct.unpack("<HH", head[6:10])
            return int(width), int(height)
        if magic == "bmp" and len(head) >= 26:
            width, height = struct.unpack("<ii", head[18:26])
            return abs(int(width)), abs(int(height))
    except Exception:  # noqa: BLE001
        return None, None
    return None, None


__all__ = [
    "probe_file", "classify", "sniff_magic", "read_head", "read_tail",
    "decode_sample", "looks_like_text", "readable_strings", "TEXT_EXTS", "CODE_EXTS",
]
