"""OCR through the existing Computer Use OCR engines.

No second OCR stack: this wraps `harness.computer.ocr.build_ocr_engine` (OS-native
Windows OCR / Tesseract / honest null) and normalizes its result into the vision
`OCRSpan` contract. The engine is chosen from the vision config; a missing engine
is a classified `OCR_UNAVAILABLE`, never a fake result.

Deterministic OCR runs BEFORE any model call so the agent does not pay a model to
transcribe text the OS can read for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import Region, OCRSpan
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage


@lru_cache(maxsize=4)
def _engine_for(backend: str) -> Any:
    from ..computer.ocr import build_ocr_engine  # noqa: PLC0415

    return build_ocr_engine(backend)


def get_ocr_engine(cfg: Optional[VisionConfig] = None) -> Any:
    cfg = cfg or vision_config()
    backend = "none" if not cfg.ocr_enabled else cfg.ocr_backend
    try:
        return _engine_for(backend)
    except Exception as exc:  # noqa: BLE001
        raise VisionError(VisionErrorClass.OCR_UNAVAILABLE, f"the OCR engine could not be built: {exc}", cause=exc) from exc


@dataclass
class OCRRun:
    available: bool
    engine: str
    text: str
    spans: list[OCRSpan] = field(default_factory=list)
    confidence: float = 0.0
    lines: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "engine": self.engine, "text": self.text,
            "confidence": round(self.confidence, 3), "spanCount": len(self.spans),
            "lines": self.lines[:200], "error": self.error,
        }


def _to_bounds(region: Optional[Region]) -> Any:
    if region is None:
        return None
    from ..computer.models import Bounds  # noqa: PLC0415

    return Bounds(x=region.x, y=region.y, width=region.width, height=region.height)


def run_ocr(
    decoded: DecodedImage,
    *,
    region: Optional[Region] = None,
    cfg: Optional[VisionConfig] = None,
) -> OCRRun:
    """Run OCR over (a region of) a decoded image.

    Returns an honest `OCRRun`; raises only when the engine cannot even be built.
    An engine that is present but reads nothing yields `available=True, text=""`.
    """
    cfg = cfg or vision_config()
    if not cfg.ocr_enabled:
        raise VisionError(VisionErrorClass.OCR_UNAVAILABLE, "OCR is disabled")
    engine = get_ocr_engine(cfg)
    if not getattr(engine, "available", False):
        raise VisionError(
            VisionErrorClass.OCR_UNAVAILABLE,
            f"the OCR engine {getattr(engine, 'id', 'unknown')!r} is not available on this machine",
        )
    image = decoded.image
    if image is None:
        raise VisionError(VisionErrorClass.INVALID_IMAGE, "the image has no pixels to OCR")
    try:
        result = engine.read(image, bounds=_to_bounds(region))
    except Exception as exc:  # noqa: BLE001 - an OCR failure is classified
        raise VisionError(VisionErrorClass.OCR_FAILED, f"OCR failed: {exc}", cause=exc) from exc
    if not getattr(result, "available", False):
        raise VisionError(
            VisionErrorClass.OCR_FAILED, getattr(result, "error", None) or "the OCR engine returned no result"
        )

    spans: list[OCRSpan] = []
    for word in getattr(result, "words", []) or []:
        bounds = getattr(word, "bounds", None)
        spans.append(OCRSpan(
            text=str(getattr(word, "text", "")),
            region=Region(x=getattr(bounds, "x", 0), y=getattr(bounds, "y", 0),
                          width=getattr(bounds, "width", 0), height=getattr(bounds, "height", 0)),
            confidence=float(getattr(word, "confidence", 0.0)),
        ))
    lines = [
        {
            "text": str(getattr(line, "text", "")),
            "bounds": getattr(line.bounds, "to_dict", lambda: {})() if getattr(line, "bounds", None) else {},
            "confidence": round(float(getattr(line, "confidence", 0.0)), 3),
        }
        for line in (getattr(result, "lines", []) or [])[:200]
    ]
    return OCRRun(
        available=True, engine=getattr(result, "engine", getattr(engine, "id", "ocr")),
        text=str(getattr(result, "text", "")), spans=spans,
        confidence=float(getattr(result, "confidence", 0.0)), lines=lines,
    )


def ocr_available(cfg: Optional[VisionConfig] = None) -> bool:
    try:
        engine = get_ocr_engine(cfg)
        return bool(getattr(engine, "available", False))
    except VisionError:
        return False


__all__ = ["OCRRun", "run_ocr", "get_ocr_engine", "ocr_available"]
