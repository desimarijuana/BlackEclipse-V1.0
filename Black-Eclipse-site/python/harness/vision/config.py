"""The `vision:` configuration section.

Same pattern as `computer/config.py`: env-var driven with dataclass defaults and
an optional JSON override at `<app>/.black-eclipse/vision.json`; env wins over
the file, the file wins over the defaults. This module only READS config — it
never fetches, decodes or analyzes an image.

Hard ceilings (max image pixels, max bytes, redirect count) are non-negotiable:
an operator may lower a limit but not remove it (a decompression bomb must never
be decodable regardless of configuration).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ARTIFACTS_RELPATH = ".black-eclipse/vision"

# Non-negotiable ceilings, independent of operator config.
MAX_IMAGE_BYTES_CEILING = 64 * 1024 * 1024      # 64 MiB
MAX_PIXELS_CEILING = 200_000_000                # 200 MP (bomb guard)
MAX_DIMENSION_CEILING = 32_768
MAX_TILES_CEILING = 64
MAX_REDIRECTS_CEILING = 5

PRIVACY_MODES = ("cloud_allowed", "cloud_preferred", "local_preferred", "local_only")
OCR_BACKENDS = ("auto", "winocr", "tesseract", "none")


def _truthy(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


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
    override_path = os.environ.get("HARNESS_VISION_CONFIG")
    path = Path(override_path) if override_path else root / ".black-eclipse" / "vision.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    block = payload.get("vision")
    return block if isinstance(block, dict) else payload


@dataclass
class VisionConfig:
    """The resolved `vision:` configuration for this process."""

    enabled: bool = True
    # The auxiliary/fallback vision model (used when the run's native model
    # cannot see images). None = fall back to the runtime's vision task profile.
    vision_model: Optional[str] = None
    # Ordered fallback candidates (provider/model or bare model ids). Empty = the
    # runtime's `vision` task profile decides.
    fallback_priority: list[str] = field(default_factory=list)
    # Routing / privacy.
    privacy_mode: str = "cloud_allowed"     # cloud_allowed|cloud_preferred|local_preferred|local_only
    allow_cloud_for_sensitive: bool = False
    # Image limits (lowered only, never above the hard ceiling).
    max_image_bytes: int = 16 * 1024 * 1024
    max_pixels: int = 40_000_000
    max_dimension: int = 4096               # analysis downscale target
    max_tiles: int = 16
    tile_overlap: float = 0.1
    # Preprocessing.
    preprocess: bool = True
    strip_metadata: bool = True
    jpeg_quality: int = 88
    # OCR.
    ocr_enabled: bool = True
    ocr_backend: str = "auto"               # auto|winocr|tesseract|none
    ocr_language: str = "eng"
    # Cache.
    cache_enabled: bool = True
    cache_ttl_seconds: int = 86_400
    cache_max_entries: int = 512
    # URL fetching / SSRF.
    allow_url_fetch: bool = True
    allowed_schemes: list[str] = field(default_factory=lambda: ["https", "http"])
    max_redirects: int = 3
    url_timeout_seconds: int = 20
    # Security.
    injection_guard: bool = True             # treat in-image text as data, scan it
    sensitive_scan: bool = True              # detect credentials/PII in images
    # Storage.
    artifacts_root: Path = field(default_factory=Path)
    storage_dir: Path = field(default_factory=Path)
    # Telemetry.
    telemetry: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "visionModel": self.vision_model,
            "fallbackPriority": list(self.fallback_priority),
            "privacy": {
                "mode": self.privacy_mode,
                "allowCloudForSensitive": self.allow_cloud_for_sensitive,
            },
            "limits": {
                "maxImageBytes": self.max_image_bytes,
                "maxPixels": self.max_pixels,
                "maxDimension": self.max_dimension,
                "maxTiles": self.max_tiles,
                "tileOverlap": self.tile_overlap,
            },
            "preprocess": {"enabled": self.preprocess, "stripMetadata": self.strip_metadata},
            "ocr": {"enabled": self.ocr_enabled, "backend": self.ocr_backend, "language": self.ocr_language},
            "cache": {
                "enabled": self.cache_enabled, "ttlSeconds": self.cache_ttl_seconds,
                "maxEntries": self.cache_max_entries,
            },
            "url": {
                "allowFetch": self.allow_url_fetch, "schemes": list(self.allowed_schemes),
                "maxRedirects": self.max_redirects, "timeoutSeconds": self.url_timeout_seconds,
            },
            "security": {"injectionGuard": self.injection_guard, "sensitiveScan": self.sensitive_scan},
            "storage": str(self.storage_dir),
        }


def load_vision_config() -> VisionConfig:
    overrides = _config_file_overrides()

    def nested(section: str, key: str, default: Any) -> Any:
        block = overrides.get(section)
        if isinstance(block, dict) and key in block:
            return block[key]
        return overrides.get(key, default)

    app_root = _app_root()
    default_artifacts = (app_root / _ARTIFACTS_RELPATH) if app_root else Path(".black-eclipse/vision")
    raw_artifacts = os.environ.get("HARNESS_VISION_ARTIFACTS_DIR")
    artifacts_root = Path(raw_artifacts).expanduser() if raw_artifacts else default_artifacts

    cfg = VisionConfig(
        enabled=_truthy(os.environ.get("HARNESS_VISION_ENABLED"), bool(overrides.get("enabled", True))),
        vision_model=os.environ.get("HARNESS_VISION_MODEL") or overrides.get("vision_model"),
        fallback_priority=_csv(
            os.environ.get("HARNESS_VISION_FALLBACK") or overrides.get("fallback_priority", [])
        ),
        privacy_mode=_choice(
            os.environ.get("HARNESS_VISION_PRIVACY") or nested("privacy", "mode", "cloud_allowed"),
            PRIVACY_MODES, "cloud_allowed",
        ),
        allow_cloud_for_sensitive=_truthy(
            os.environ.get("HARNESS_VISION_ALLOW_CLOUD_SENSITIVE"),
            bool(nested("privacy", "allow_cloud_for_sensitive", False)),
        ),
        max_image_bytes=_int(
            os.environ.get("HARNESS_VISION_MAX_BYTES"), int(nested("limits", "max_image_bytes", 16 * 1024 * 1024)),
            low=1024, high=MAX_IMAGE_BYTES_CEILING,
        ),
        max_pixels=_int(
            os.environ.get("HARNESS_VISION_MAX_PIXELS"), int(nested("limits", "max_pixels", 40_000_000)),
            low=10_000, high=MAX_PIXELS_CEILING,
        ),
        max_dimension=_int(
            os.environ.get("HARNESS_VISION_MAX_DIMENSION"), int(nested("limits", "max_dimension", 4096)),
            low=256, high=MAX_DIMENSION_CEILING,
        ),
        max_tiles=_int(
            os.environ.get("HARNESS_VISION_MAX_TILES"), int(nested("limits", "max_tiles", 16)),
            low=1, high=MAX_TILES_CEILING,
        ),
        tile_overlap=_float(
            os.environ.get("HARNESS_VISION_TILE_OVERLAP"), float(nested("limits", "tile_overlap", 0.1)),
            low=0.0, high=0.5,
        ),
        preprocess=_truthy(os.environ.get("HARNESS_VISION_PREPROCESS"), bool(nested("preprocess", "enabled", True))),
        strip_metadata=_truthy(
            os.environ.get("HARNESS_VISION_STRIP_METADATA"), bool(nested("preprocess", "strip_metadata", True))
        ),
        jpeg_quality=_int(
            os.environ.get("HARNESS_VISION_JPEG_QUALITY"), int(nested("preprocess", "jpeg_quality", 88)),
            low=40, high=100,
        ),
        ocr_enabled=_truthy(os.environ.get("HARNESS_VISION_OCR_ENABLED"), bool(nested("ocr", "enabled", True))),
        ocr_backend=_choice(
            os.environ.get("HARNESS_VISION_OCR_BACKEND") or nested("ocr", "backend", "auto"),
            OCR_BACKENDS, "auto",
        ),
        ocr_language=str(os.environ.get("HARNESS_VISION_OCR_LANGUAGE") or nested("ocr", "language", "eng")),
        cache_enabled=_truthy(os.environ.get("HARNESS_VISION_CACHE"), bool(nested("cache", "enabled", True))),
        cache_ttl_seconds=_int(
            os.environ.get("HARNESS_VISION_CACHE_TTL"), int(nested("cache", "ttl_seconds", 86_400)),
            low=0, high=30 * 86_400,
        ),
        cache_max_entries=_int(
            os.environ.get("HARNESS_VISION_CACHE_MAX"), int(nested("cache", "max_entries", 512)),
            low=1, high=10_000,
        ),
        allow_url_fetch=_truthy(os.environ.get("HARNESS_VISION_URL_FETCH"), bool(nested("url", "allow_fetch", True))),
        allowed_schemes=_csv(
            os.environ.get("HARNESS_VISION_URL_SCHEMES") or nested("url", "schemes", ["https", "http"])
        ) or ["https", "http"],
        max_redirects=_int(
            os.environ.get("HARNESS_VISION_MAX_REDIRECTS"), int(nested("url", "max_redirects", 3)),
            low=0, high=MAX_REDIRECTS_CEILING,
        ),
        url_timeout_seconds=_int(
            os.environ.get("HARNESS_VISION_URL_TIMEOUT"), int(nested("url", "timeout_seconds", 20)),
            low=1, high=120,
        ),
        injection_guard=_truthy(
            os.environ.get("HARNESS_VISION_INJECTION_GUARD"), bool(nested("security", "injection_guard", True))
        ),
        sensitive_scan=_truthy(
            os.environ.get("HARNESS_VISION_SENSITIVE_SCAN"), bool(nested("security", "sensitive_scan", True))
        ),
        artifacts_root=artifacts_root,
        telemetry=_truthy(os.environ.get("HARNESS_VISION_TELEMETRY"), bool(overrides.get("telemetry", True))),
    )
    cfg.storage_dir = artifacts_root / "assets"
    return cfg


# ── Public helpers (the ONE place the config is resolved) ────────────────────

_CONFIG_CACHE: Optional[VisionConfig] = None


def vision_config(refresh: bool = False) -> VisionConfig:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None or refresh:
        _CONFIG_CACHE = load_vision_config()
    return _CONFIG_CACHE


def vision_enabled() -> bool:
    return vision_config().enabled


__all__ = [
    "VisionConfig",
    "MAX_DIMENSION_CEILING",
    "MAX_IMAGE_BYTES_CEILING",
    "MAX_PIXELS_CEILING",
    "MAX_REDIRECTS_CEILING",
    "MAX_TILES_CEILING",
    "OCR_BACKENDS",
    "PRIVACY_MODES",
    "load_vision_config",
    "vision_config",
    "vision_enabled",
]
