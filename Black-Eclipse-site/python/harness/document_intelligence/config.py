"""The `document:` configuration section.

Same pattern as `vision/config.py` and `computer/config.py`: env-var driven with
dataclass defaults and an optional JSON override at `<app>/.black-eclipse/document.json`
(`HARNESS_DOCUMENT_CONFIG` overrides the path); env wins over the file, the file
wins over the defaults. This module only READS config — it never opens a file,
parses a document or calls a model.

Hard ceilings (max file bytes, max pages, archive limits, OCR confidence bounds)
are non-negotiable: an operator may lower a limit but not remove it, so a
decompression bomb or an unbounded archive can never be processed regardless of
configuration (spec §31/§32/§52).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ARTIFACTS_RELPATH = ".black-eclipse/documents"

# Non-negotiable ceilings, independent of operator config.
MAX_FILE_BYTES_CEILING = 512 * 1024 * 1024       # 512 MiB
MAX_PAGES_CEILING = 10_000
MAX_ARCHIVE_BYTES_CEILING = 2 * 1024 * 1024 * 1024   # 2 GiB uncompressed
MAX_ARCHIVE_FILES_CEILING = 100_000
MAX_ARCHIVE_RATIO_CEILING = 1_000                # compression-ratio bomb guard
MAX_ARCHIVE_DEPTH_CEILING = 8
MAX_TIMEOUT_CEILING = 3_600                      # 1 hour
MAX_TABLE_CELLS_CEILING = 5_000_000
MAX_CSV_ROWS_CEILING = 50_000_000

OCR_BACKENDS = ("auto", "winocr", "tesseract", "none")

# Formats we understand. Anything else fails with UNSUPPORTED_FORMAT honestly.
SUPPORTED_EXTENSIONS = frozenset({
    "pdf", "docx", "doc", "odt", "rtf",
    "pptx", "ppt", "odp",
    "xlsx", "xls", "xlsb", "ods", "csv", "tsv",
    "json", "jsonl", "xml", "yaml", "yml", "toml",
    "html", "htm", "epub",
    "md", "mdx", "markdown", "txt", "rst", "log",
    "png", "jpg", "jpeg", "webp", "gif", "tif", "tiff", "bmp", "svg",
    "zip", "tar", "gz", "7z",
})


def _truthy(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _int(value: Any, default: int, *, low: int, high: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(parsed, high))


def _float(value: Any, default: float, *, low: float, high: float) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(parsed, high))


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _app_root() -> Optional[Path]:
    try:
        from ..eclipse_memory.config import repo_root  # noqa: PLC0415

        resolved = repo_root()
        return Path(resolved) if resolved else None
    except Exception:  # noqa: BLE001 - a missing config is simply no app root
        return None


def _config_file_overrides() -> dict[str, Any]:
    root = _app_root()
    if root is None:
        return {}
    override_path = os.environ.get("HARNESS_DOCUMENT_CONFIG")
    path = Path(override_path) if override_path else root / ".black-eclipse" / "document.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    block = payload.get("document")
    return block if isinstance(block, dict) else payload


@dataclass
class DocumentConfig:
    """The resolved `document:` configuration for this process."""

    enabled: bool = True
    # Limits (lowered only, never above the hard ceiling).
    max_file_bytes: int = 64 * 1024 * 1024          # 64 MiB
    max_pages: int = 2_000
    processing_timeout_seconds: int = 300
    # OCR.
    ocr_enabled: bool = True
    ocr_backend: str = "auto"                       # auto|winocr|tesseract|none
    ocr_language: str = "eng"
    ocr_confidence_threshold: float = 0.60          # below this, consider vision fallback
    ocr_vision_fallback: bool = True                # use a vision model when OCR is weak/absent
    ocr_max_pages: int = 200                        # cap OCR'd pages per document
    # Vision (delegated to the vision subsystem).
    vision_enabled: bool = True
    # Cache / index.
    cache_enabled: bool = True
    index_enabled: bool = True
    cache_ttl_seconds: int = 7 * 86_400
    # Archives.
    archive_enabled: bool = True
    max_archive_bytes: int = 256 * 1024 * 1024      # total uncompressed
    max_archive_files: int = 2_000
    max_archive_ratio: int = 200                    # uncompressed/compressed
    max_archive_depth: int = 2
    # Tabular / spreadsheet.
    max_table_cells: int = 2_000_000
    max_csv_rows: int = 5_000_000
    query_engine: str = "duckdb"                    # duckdb|pandas|none
    query_timeout_seconds: int = 60
    # Display.
    preview_rows: int = 50
    preview_columns: int = 30
    # Security.
    injection_guard: bool = True
    sensitive_scan: bool = True
    allow_macros: bool = False                      # macro-enabled docs are refused
    allow_html_external_resources: bool = False
    # Retrieval.
    chunk_target_chars: int = 1_200
    chunk_overlap_chars: int = 150
    # Storage / telemetry.
    artifacts_root: Path = field(default_factory=Path)
    storage_dir: Path = field(default_factory=Path)
    telemetry: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "limits": {
                "maxFileBytes": self.max_file_bytes, "maxPages": self.max_pages,
                "processingTimeoutSeconds": self.processing_timeout_seconds,
            },
            "ocr": {
                "enabled": self.ocr_enabled, "backend": self.ocr_backend,
                "language": self.ocr_language, "confidenceThreshold": self.ocr_confidence_threshold,
                "visionFallback": self.ocr_vision_fallback, "maxPages": self.ocr_max_pages,
            },
            "vision": {"enabled": self.vision_enabled},
            "cache": {"enabled": self.cache_enabled, "ttlSeconds": self.cache_ttl_seconds},
            "index": {"enabled": self.index_enabled},
            "archives": {
                "enabled": self.archive_enabled, "maxBytes": self.max_archive_bytes,
                "maxFiles": self.max_archive_files, "maxRatio": self.max_archive_ratio,
                "maxDepth": self.max_archive_depth,
            },
            "tabular": {
                "maxTableCells": self.max_table_cells, "maxCsvRows": self.max_csv_rows,
                "queryEngine": self.query_engine, "queryTimeoutSeconds": self.query_timeout_seconds,
            },
            "security": {
                "injectionGuard": self.injection_guard, "sensitiveScan": self.sensitive_scan,
                "allowMacros": self.allow_macros,
                "allowHtmlExternalResources": self.allow_html_external_resources,
            },
            "retrieval": {"chunkTargetChars": self.chunk_target_chars, "chunkOverlapChars": self.chunk_overlap_chars},
            "storage": str(self.storage_dir),
        }


def load_document_config() -> DocumentConfig:
    overrides = _config_file_overrides()
    env = os.environ

    def nested(section: str, key: str, default: Any) -> Any:
        block = overrides.get(section)
        if isinstance(block, dict) and key in block:
            return block[key]
        return overrides.get(key, default)

    def pick(env_key: str, section: str, key: str, default: Any) -> Any:
        if env_key in env:
            return env[env_key]
        return nested(section, key, default)

    repo = _app_root() or Path(".")
    artifacts_root = repo / _ARTIFACTS_RELPATH

    cfg = DocumentConfig(
        enabled=_truthy(pick("HARNESS_DOCUMENT_ENABLED", "enabled", "enabled", True), True),
        max_file_bytes=_int(
            pick("DOCUMENT_MAX_FILE_SIZE", "limits", "maxFileBytes", 64 * 1024 * 1024),
            64 * 1024 * 1024, low=1024, high=MAX_FILE_BYTES_CEILING,
        ),
        max_pages=_int(
            pick("MAX_PAGES", "limits", "maxPages", 2_000),
            2_000, low=1, high=MAX_PAGES_CEILING,
        ),
        processing_timeout_seconds=int(_int(
            pick("DOCUMENT_PROCESSING_TIMEOUT", "limits", "processingTimeoutSeconds", 300),
            300, low=5, high=MAX_TIMEOUT_CEILING,
        )),
        ocr_enabled=_truthy(pick("HARNESS_DOCUMENT_OCR_ENABLED", "ocr", "enabled", True), True),
        ocr_backend=_choice(pick("OCR_PROVIDER", "ocr", "backend", "auto"), OCR_BACKENDS, "auto"),
        ocr_language=str(pick("HARNESS_DOCUMENT_OCR_LANGUAGE", "ocr", "language", "eng") or "eng"),
        ocr_confidence_threshold=_float(
            pick("OCR_CONFIDENCE_THRESHOLD", "ocr", "confidenceThreshold", 0.60),
            0.60, low=0.0, high=1.0,
        ),
        ocr_vision_fallback=_truthy(pick("HARNESS_DOCUMENT_OCR_VISION_FALLBACK", "ocr", "visionFallback", True), True),
        ocr_max_pages=_int(pick("HARNESS_DOCUMENT_OCR_MAX_PAGES", "ocr", "maxPages", 200), 200, low=1, high=MAX_PAGES_CEILING),
        vision_enabled=_truthy(pick("HARNESS_DOCUMENT_VISION_ENABLED", "vision", "enabled", True), True),
        cache_enabled=_truthy(pick("DOCUMENT_CACHE_ENABLED", "cache", "enabled", True), True),
        index_enabled=_truthy(pick("DOCUMENT_INDEX_ENABLED", "index", "enabled", True), True),
        cache_ttl_seconds=_int(pick("HARNESS_DOCUMENT_CACHE_TTL", "cache", "ttlSeconds", 7 * 86_400), 7 * 86_400, low=0, high=365 * 86_400),
        archive_enabled=_truthy(pick("HARNESS_DOCUMENT_ARCHIVE_ENABLED", "archives", "enabled", True), True),
        max_archive_bytes=_int(
            pick("MAX_ARCHIVE_SIZE", "archives", "maxBytes", 256 * 1024 * 1024),
            256 * 1024 * 1024, low=1024, high=MAX_ARCHIVE_BYTES_CEILING,
        ),
        max_archive_files=_int(pick("MAX_ARCHIVE_FILES", "archives", "maxFiles", 2_000), 2_000, low=1, high=MAX_ARCHIVE_FILES_CEILING),
        max_archive_ratio=_int(pick("HARNESS_DOCUMENT_ARCHIVE_RATIO", "archives", "maxRatio", 200), 200, low=1, high=MAX_ARCHIVE_RATIO_CEILING),
        max_archive_depth=_int(pick("HARNESS_DOCUMENT_ARCHIVE_DEPTH", "archives", "maxDepth", 2), 2, low=0, high=MAX_ARCHIVE_DEPTH_CEILING),
        max_table_cells=_int(pick("HARNESS_DOCUMENT_MAX_TABLE_CELLS", "tabular", "maxTableCells", 2_000_000), 2_000_000, low=1, high=MAX_TABLE_CELLS_CEILING),
        max_csv_rows=_int(pick("HARNESS_DOCUMENT_MAX_CSV_ROWS", "tabular", "maxCsvRows", 5_000_000), 5_000_000, low=1, high=MAX_CSV_ROWS_CEILING),
        query_engine=_choice(pick("HARNESS_DOCUMENT_QUERY_ENGINE", "tabular", "queryEngine", "duckdb"), ("duckdb", "pandas", "none"), "duckdb"),
        query_timeout_seconds=_int(pick("HARNESS_DOCUMENT_QUERY_TIMEOUT", "tabular", "queryTimeoutSeconds", 60), 60, low=1, high=600),
        preview_rows=_int(pick("HARNESS_DOCUMENT_PREVIEW_ROWS", "display", "previewRows", 50), 50, low=1, high=1000),
        preview_columns=_int(pick("HARNESS_DOCUMENT_PREVIEW_COLUMNS", "display", "previewColumns", 30), 30, low=1, high=200),
        injection_guard=_truthy(pick("HARNESS_DOCUMENT_INJECTION_GUARD", "security", "injectionGuard", True), True),
        sensitive_scan=_truthy(pick("HARNESS_DOCUMENT_SENSITIVE_SCAN", "security", "sensitiveScan", True), True),
        allow_macros=_truthy(pick("HARNESS_DOCUMENT_ALLOW_MACROS", "security", "allowMacros", False), False),
        allow_html_external_resources=_truthy(
            pick("HARNESS_DOCUMENT_HTML_EXTERNAL", "security", "allowHtmlExternalResources", False), False,
        ),
        chunk_target_chars=_int(pick("HARNESS_DOCUMENT_CHUNK_CHARS", "retrieval", "chunkTargetChars", 1_200), 1_200, low=200, high=20_000),
        chunk_overlap_chars=_int(pick("HARNESS_DOCUMENT_CHUNK_OVERLAP", "retrieval", "chunkOverlapChars", 150), 150, low=0, high=5_000),
        telemetry=_truthy(pick("HARNESS_DOCUMENT_TELEMETRY", "telemetry", "telemetry", True), True),
    )
    cfg.artifacts_root = artifacts_root
    cfg.storage_dir = artifacts_root / "assets"
    return cfg


_CONFIG_CACHE: Optional[DocumentConfig] = None


def document_config(refresh: bool = False) -> DocumentConfig:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None or refresh:
        _CONFIG_CACHE = load_document_config()
    return _CONFIG_CACHE


def document_enabled() -> bool:
    return document_config().enabled


__all__ = [
    "DocumentConfig", "document_config", "document_enabled", "load_document_config",
    "SUPPORTED_EXTENSIONS", "OCR_BACKENDS", "MAX_FILE_BYTES_CEILING", "MAX_PAGES_CEILING",
    "MAX_ARCHIVE_BYTES_CEILING", "MAX_ARCHIVE_FILES_CEILING", "MAX_ARCHIVE_RATIO_CEILING",
    "MAX_ARCHIVE_DEPTH_CEILING", "MAX_TIMEOUT_CEILING", "MAX_TABLE_CELLS_CEILING", "MAX_CSV_ROWS_CEILING",
]
