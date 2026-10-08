"""Vision contracts — the vocabulary every vision layer speaks.

These are provider-agnostic value objects. Nothing here reaches a model,
network, filesystem or the OS; it is data plus pure helpers, so the whole
contract is testable without any external dependency.

The central objects:

    VisionInput   — WHAT to look at (a resolved source plus options)
    VisionResult  — WHAT was observed (structured, provenance-carrying)
    ImageAsset    — a stored, content-addressed image plus its metadata
    Region        — a rectangle in image pixel coordinates

`VisionResult` deliberately distinguishes OBSERVED vs INFERRED vs COMPUTED, and
carries provenance for every observation, so a visual claim can flow into the
Evidence & Research Engine without losing where it came from.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


# ── geometry ──────────────────────────────────────────────────────────────────

@dataclass
class Region:
    """A rectangle in image pixel coordinates (top-left origin)."""

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    label: str = ""

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_list(self) -> list[int]:
        """Canonical `[x, y, width, height]`."""
        return [self.x, self.y, self.width, self.height]

    def to_bbox(self) -> list[int]:
        """Corner convention `[left, top, right, bottom]`."""
        return [self.x, self.y, self.right, self.bottom]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "bbox": self.to_bbox(),
        }
        if self.label:
            out["label"] = self.label
        return out

    @staticmethod
    def from_any(value: Any) -> Optional["Region"]:
        """Coerce dict / [x,y,w,h] / Region into a Region."""
        if value is None:
            return None
        if isinstance(value, Region):
            return value
        if isinstance(value, dict):
            try:
                if "bbox" in value and isinstance(value["bbox"], (list, tuple)):
                    return Region.from_bbox(value["bbox"], label=str(value.get("label", "")))
                return Region(
                    int(value.get("x", 0)), int(value.get("y", 0)),
                    int(value.get("width", value.get("w", 0))),
                    int(value.get("height", value.get("h", 0))),
                    str(value.get("label", "")),
                )
            except (TypeError, ValueError):
                return None
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                x, y, width, height = (int(v) for v in value)
            except (TypeError, ValueError):
                return None
            return Region(x, y, width, height)
        return None

    @staticmethod
    def from_bbox(value: Any, *, label: str = "") -> Optional["Region"]:
        """Coerce a corner `[left, top, right, bottom]` (or dict) into a Region.

        This is the convention models emit as `bbox`; it is kept separate from
        `from_any` (which reads `[x, y, width, height]`) so a 4-number list is
        never ambiguously interpreted.
        """
        if value is None:
            return None
        if isinstance(value, Region):
            return value
        if isinstance(value, dict):
            if "x" in value or "width" in value or "w" in value:
                return Region.from_any(value)
            if "bbox" in value:
                return Region.from_bbox(value["bbox"], label=str(value.get("label", label)))
            return None
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                left, top, right, bottom = (int(v) for v in value)
            except (TypeError, ValueError):
                return None
            return Region(left, top, max(0, right - left), max(0, bottom - top), label)
        return None


# ── source / capability enums ─────────────────────────────────────────────────

SourceKind = Literal[
    "path",       # local filesystem path
    "url",        # http(s) image URL
    "base64",     # raw base64 or data URI
    "bytes",      # in-memory bytes
    "screenshot", # a fresh screen capture
    "clipboard",  # the OS clipboard image
    "browser",    # a browser page screenshot
    "document",   # a page rendered from a document (PDF etc.)
]

VisionMode = Literal[
    "analyze",     # general question answering about the image
    "describe",    # free-form description
    "ground",      # locate a described element / return coordinates
    "ocr",         # text extraction
    "chart",       # chart-specific analysis
    "document",    # document/PDF/table vision
    "compare",     # compare two images
]

PrivacyMode = Literal["cloud_allowed", "cloud_preferred", "local_preferred", "local_only"]

#: How a claim/observation came to be known. Deterministic facts outrank the
#: model's reading, which outranks an inference. This mirrors the research
#: engine's `ClaimStatus` vocabulary in spirit.
ObservationKind = Literal["observed", "inferred", "computed", "verified", "unverified", "conflicting"]


class EvidenceStatus(str, Enum):
    """Whether a visual observation is safe to treat as evidence."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    COMPUTED = "computed"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"


# ── input ─────────────────────────────────────────────────────────────────────

@dataclass
class VisionInput:
    """A fully-specified vision request.

    `source` is interpreted per `source_kind`; the orchestrator resolves it into
    a concrete image. `question` is the agent's ask (never an instruction trusted
    from the image itself). `mode` selects the analysis path.
    """

    source: str = ""
    source_kind: SourceKind = "path"
    question: str = ""
    mode: VisionMode = "analyze"
    # Optional region of interest in image pixels (analysis is cropped to it).
    region: Optional[Region] = None
    # The source the agent chose for THIS run (so native-first can be attempted).
    model_settings: Any = None
    # Routing hints.
    privacy: Optional[PrivacyMode] = None
    local_only: bool = False
    sensitive: bool = False
    max_cost: Optional[float] = None
    task_hint: Optional[str] = None
    # Options bag (schema version, ocr language, tiling on/off, preprocessing).
    options: dict[str, Any] = field(default_factory=dict)
    # Free-form provenance the caller wants carried onto the result.
    provenance: dict[str, Any] = field(default_factory=dict)

    def cache_options(self) -> dict[str, Any]:
        """Only the options that change the RESULT identity (for cache keys)."""
        relevant = {
            k: self.options.get(k)
            for k in (
                "language", "tiling", "max_tiles", "preprocess", "max_dimension",
                "quality", "schema_version", "compare_with", "tile_overlap",
            )
            if k in self.options
        }
        region = self.region.to_list() if self.region else None
        return {"mode": self.mode, "question": self.question, "region": region, **relevant}


# ── observations ──────────────────────────────────────────────────────────────

@dataclass
class VisualObservation:
    """One thing seen in an image, with provenance and a confidence."""

    text: str
    kind: ObservationKind = "observed"
    region: Optional[Region] = None
    confidence: float = 0.0
    # The processing method: "model" | "ocr" | "deterministic" | "market_data".
    method: str = "model"
    source: Optional[dict[str, Any]] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "kind": self.kind,
            "region": self.region.to_dict() if self.region else None,
            "confidence": round(self.confidence, 3), "method": self.method,
            "source": self.source, "details": self.details,
        }


@dataclass
class OCRSpan:
    """A word/line of recognized text with its box and confidence."""

    text: str
    region: Region
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bounds": self.region.to_dict(),
            "x": self.region.x, "y": self.region.y,
            "width": self.region.width, "height": self.region.height,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class VisionUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False
    cost: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisionResult:
    """The normalized result of a vision request.

    `ok` is the single honesty gate: a failed request sets `ok=False` and an
    error, and NEVER fabricates observations. An empty-but-successful result is
    legitimate (nothing was found); a failure is not an empty result.
    """

    ok: bool
    mode: str = "analyze"
    description: str = ""
    observations: list[VisualObservation] = field(default_factory=list)
    text: list[OCRSpan] = field(default_factory=list)
    objects: list[VisualObservation] = field(default_factory=list)
    regions: list[VisualObservation] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    chart: Optional[dict[str, Any]] = None
    comparison: Optional[dict[str, Any]] = None
    structured: Optional[dict[str, Any]] = None
    confidence: float = 0.0
    provider: Optional[str] = None
    model: Optional[str] = None
    backend: str = "none"
    latency_ms: int = 0
    usage: VisionUsage = field(default_factory=VisionUsage)
    provenance: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    error: Optional[dict[str, Any]] = None
    # The asset id of the (possibly preprocessed) image that was analyzed.
    asset_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "vision_result",
            "ok": self.ok,
            "mode": self.mode,
            "description": self.description,
            "observations": [o.to_dict() for o in self.observations],
            "text": [t.to_dict() for t in self.text],
            "objects": [o.to_dict() for o in self.objects],
            "regions": [o.to_dict() for o in self.regions],
            "tables": self.tables,
            "chart": self.chart,
            "comparison": self.comparison,
            "structured": self.structured,
            "confidence": round(self.confidence, 3),
            "provider": self.provider,
            "model": self.model,
            "backend": self.backend,
            "latency_ms": self.latency_ms,
            "usage": self.usage.to_dict(),
            "provenance": self.provenance,
            "cached": self.cached,
            "truncated": self.truncated,
            "warnings": self.warnings,
            "error": self.error,
            "asset_id": self.asset_id,
        }

    @staticmethod
    def failure(error: "Any", *, mode: str = "analyze", latency_ms: int = 0) -> "VisionResult":
        from .errors import VisionError

        payload = error.to_dict() if isinstance(error, VisionError) else {
            "errorClass": "INTERNAL_ERROR", "message": str(error),
        }
        return VisionResult(ok=False, mode=mode, error=payload, latency_ms=latency_ms, backend="none")


# ── asset ─────────────────────────────────────────────────────────────────────

def content_digest(data: bytes) -> str:
    """SHA-256 of raw image bytes (content-addressed identity)."""
    return "img_" + hashlib.sha256(data).hexdigest()


@dataclass
class ImageAsset:
    """A stored image plus its metadata. Binary lives in object storage, never
    in a relational table; only this metadata is recorded."""

    asset_id: str
    sha256: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    storage_uri: str
    source_kind: str = "path"
    source_ref: Optional[str] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    created_at: str = ""
    expires_at: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "Region", "VisionInput", "VisionResult", "VisionUsage", "VisualObservation",
    "OCRSpan", "ImageAsset", "EvidenceStatus", "ObservationKind",
    "SourceKind", "VisionMode", "PrivacyMode", "content_digest", "now_iso",
]
