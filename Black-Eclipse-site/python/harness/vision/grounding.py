"""Visual grounding: locate a described element and return coordinates.

Three strategies, from cheapest/most deterministic to most expensive:

    1. OCR  — when the target is text and the OS OCR engine finds it.
    2. model — ask the vision model for a bounding box (UI grounding).
    3. hybrid — OCR first; fall back to the model only when OCR misses.

A grounded element carries a bounding box, a centre point, a confidence and the
method, so Computer Use / Browser Vision can validate coordinates before acting.
Deterministic OCR is never replaced by an LLM guess when OCR already found it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import Region
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage
from .ocr import OCRRun, run_ocr
from .providers import call_model
from .routing import RoutingPlan

_GROUND_SCHEMA = {
    "type": "object",
    "properties": {
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "role": {"type": "string"},
                    "bbox": {"type": ["array", "object", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["label"],
            },
        },
        "found": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
}

_GROUND_PROMPT = (
    "You are Eclipse's visual grounding engine looking at a screenshot to help an "
    "automation agent. Locate the element described below and report its bounding "
    "box in IMAGE PIXELS (top-left origin).\n"
    "Target: {target}\n"
    "Reply with one JSON object:\n"
    '{{"found": true|false, "elements": [{{"label": "...", "role": "button|input|link|text|icon|other", '
    '"bbox": [x, y, width, height], "confidence": 0..1}}], "confidence": 0..1}}\n'
    'If the target is not present, return {{"found": false, "elements": []}}.'
)


@dataclass
class GroundedElement:
    label: str
    region: Optional[Region]
    confidence: float = 0.0
    method: str = "model"
    role: str = "element"
    source: Optional[dict[str, Any]] = None

    @property
    def center(self) -> Optional[tuple[int, int]]:
        return self.region.center if self.region else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "element": self.label,
            "role": self.role,
            "bbox": self.region.to_bbox() if self.region else None,
            "bounds": self.region.to_dict() if self.region else None,
            "center": list(self.center) if self.center else None,
            "confidence": round(self.confidence, 3),
            "method": self.method,
            "source": self.source,
        }


@dataclass
class GroundingOutcome:
    found: bool
    elements: list[GroundedElement] = field(default_factory=list)
    method: str = "model"
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    ocr: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found, "method": self.method,
            "confidence": round(self.confidence, 3),
            "elements": [e.to_dict() for e in self.elements],
            "warnings": self.warnings, "ocr": self.ocr,
        }


def ground_from_ocr(run: OCRRun, target: str, *, min_confidence: float = 0.0) -> list[GroundedElement]:
    """Locate a text target inside an OCR result (deterministic, no model)."""
    needle = (target or "").strip().lower()
    if not needle:
        return []
    elements: list[GroundedElement] = []
    for span in run.spans:
        if needle in span.text.strip().lower():
            elements.append(GroundedElement(
                label=span.text, region=span.region, confidence=max(span.confidence, 0.5),
                method="ocr", role="text", source={"engine": run.engine},
            ))
    return [e for e in elements if e.confidence >= min_confidence]


async def ground_image(
    decoded: DecodedImage,
    target: str,
    plan: RoutingPlan,
    *,
    use_ocr: bool = True,
    timeout_s: float = 90.0,
    min_confidence: float = 0.0,
) -> GroundingOutcome:
    """Ground `target` in the image using OCR then (if needed) the model.

    Raises `VisionError` only on a provider failure when OCR could not answer;
    an absent target is `found=False`, an honest negative.
    """
    if not target or not target.strip():
        raise VisionError(VisionErrorClass.INVALID_INPUT, "grounding requires a target description")

    ocr_dict: Optional[dict[str, Any]] = None
    if use_ocr:
        try:
            ocr_run = run_ocr(decoded)
            ocr_dict = ocr_run.to_dict()
            ocr_elements = ground_from_ocr(ocr_run, target, min_confidence=min_confidence)
            if ocr_elements:
                return GroundingOutcome(
                    found=True, elements=ocr_elements, method="ocr",
                    confidence=max(e.confidence for e in ocr_elements), ocr=ocr_dict,
                )
        except VisionError:
            ocr_dict = {"available": False}

    # Fall back to model grounding.
    prompt = _GROUND_PROMPT.format(target=target)
    result = await call_model(plan.settings, prompt, [decoded.image], task="vision",
                              timeout_s=timeout_s, structured=True, backend=plan.kind)
    from .analyze import extract_json  # noqa: PLC0415

    payload = extract_json(result.text)
    if payload is None:
        return GroundingOutcome(
            found=False, method="model", confidence=0.0, ocr=ocr_dict,
            warnings=["the model reply was not valid JSON; no element was grounded"],
        )
    elements: list[GroundedElement] = []
    for item in payload.get("elements", []) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("text") or "").strip()
        if not label:
            continue
        region = Region.from_bbox(item.get("bbox") or item.get("bounds") or item.get("region"))
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        elements.append(GroundedElement(
            label=label, region=region, confidence=max(0.0, min(1.0, confidence)),
            method="model", role=str(item.get("role") or "element"),
        ))
    found = bool(payload.get("found", bool(elements))) and bool(elements)
    confidence = max((e.confidence for e in elements), default=0.0)
    if payload.get("confidence") is not None:
        try:
            confidence = max(confidence, float(payload["confidence"]))
        except (TypeError, ValueError):
            pass
    return GroundingOutcome(found=found, elements=elements, method="model",
                            confidence=confidence, ocr=ocr_dict)


__all__ = ["GroundedElement", "GroundingOutcome", "ground_from_ocr", "ground_image"]
