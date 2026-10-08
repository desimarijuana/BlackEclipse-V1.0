"""Visual comparison: before/after, UI regression, chart/document revisions.

A deterministic pixel diff runs first (no model): changed regions are computed on
a downscaled grid so it works without heavy dependencies and is stable. A vision
model then DESCRIBES what changed when asked; it never becomes the source of the
region geometry.

Used by `visual_compare`, `image_diff` and `screen_compare`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import Region, VisionInput, VisionResult, VisionUsage, VisualObservation
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, to_rgb
from .providers import call_model
from .routing import RoutingPlan


@dataclass
class ChangedRegion:
    region: Region
    magnitude: float

    def to_dict(self) -> dict[str, Any]:
        return {"region": self.region.to_dict(), "bbox": self.region.to_list(), "magnitude": round(self.magnitude, 3)}


@dataclass
class CompareOutcome:
    changed_pixels_ratio: float
    changed: bool
    regions: list[ChangedRegion]
    description: str = ""
    confidence: float = 0.0
    method: str = "pixel"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed, "changedPixelsRatio": round(self.changed_pixels_ratio, 4),
            "regions": [r.to_dict() for r in self.regions], "description": self.description,
            "confidence": round(self.confidence, 3), "method": self.method, "warnings": self.warnings,
        }


def pixel_diff(
    before: DecodedImage,
    after: DecodedImage,
    *,
    grid: int = 8,
    threshold: float = 0.02,
) -> CompareOutcome:
    """Deterministic per-cell difference between two images.

    Images are normalized to a common size on a `grid`-cell lattice; each cell's
    mean absolute luma difference is measured and cells over `threshold` become
    changed regions in normalized coordinates scaled back to the first image.
    """
    if before.image is None or after.image is None:
        raise VisionError(VisionErrorClass.INVALID_IMAGE, "both images must have pixels to compare")
    try:
        from PIL import Image, ImageChops  # noqa: PLC0415

        width = max(before.width, after.width)
        height = max(before.height, after.height)
        size = (max(1, width), max(1, height))
        a = to_rgb(before.image).resize(size, Image.BILINEAR)
        b = to_rgb(after.image).resize(size, Image.BILINEAR)
        diff = ImageChops.difference(a.convert("L"), b.convert("L"))
    except Exception as exc:  # noqa: BLE001
        raise VisionError(VisionErrorClass.INVALID_IMAGE, f"the pixel diff failed: {exc}", cause=exc) from exc

    cell_w = max(1, width // grid)
    cell_h = max(1, height // grid)
    changed: list[ChangedRegion] = []
    total_changed = 0
    pixels = diff.tobytes()
    total = len(pixels) or 1
    for row in range(grid):
        for col in range(grid):
            left = col * cell_w
            top = row * cell_h
            right = min(width, left + cell_w)
            bottom = min(height, top + cell_h)
            if right <= left or bottom <= top:
                continue
            region_pixels: list[int] = []
            for y in range(top, bottom):
                base = y * width
                region_pixels.extend(pixels[base + left:base + right])
            if not region_pixels:
                continue
            mean = sum(region_pixels) / len(region_pixels) / 255.0
            if mean >= threshold:
                total_changed += len(region_pixels)
                changed.append(ChangedRegion(
                    region=Region(left, top, right - left, bottom - top, label="changed"),
                    magnitude=mean,
                ))
    ratio = total_changed / total
    return CompareOutcome(
        changed_pixels_ratio=ratio, changed=bool(changed), regions=changed, method="pixel",
    )


_COMPARE_PROMPT = (
    "You are Eclipse's visual-comparison engine. Two images are provided: the "
    "FIRST is the 'before', the SECOND is the 'after'. Describe precisely what "
    "changed between them. Do not describe unchanged content.\n"
    "Question: {question}\n"
    "Reply with one JSON object: "
    '{{"description": "<what changed>", "changes": [{{"text": "...", "confidence": 0..1}}], "confidence": 0..1}}'
)


async def compare_images(
    before: DecodedImage,
    after: DecodedImage,
    input: VisionInput,
    plan: RoutingPlan,
    *,
    use_model: bool = True,
    threshold: float = 0.02,
    timeout_s: float = 120.0,
) -> tuple[CompareOutcome, Any]:
    """Deterministic diff, then an optional model description of the changes."""
    outcome = pixel_diff(before, after, threshold=threshold)
    if not use_model:
        return outcome, None
    result = None
    try:
        prompt = _COMPARE_PROMPT.format(question=input.question or "What changed?")
        result = await call_model(
            plan.settings, prompt, [before.image, after.image], task="vision",
            timeout_s=timeout_s, structured=True, backend=plan.kind,
        )
        from .analyze import extract_json  # noqa: PLC0415

        payload = extract_json(result.text)
        if payload is None:
            outcome.warnings.append("the model reply was not valid JSON; returning the deterministic diff only")
            return outcome, result
        outcome.description = str(payload.get("description") or "")
        try:
            outcome.confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.5))))
        except (TypeError, ValueError):
            outcome.confidence = 0.5
    except VisionError as exc:
        outcome.warnings.append(f"the model description was unavailable ({exc.error_class.value})")
    return outcome, result


def build_compare_result(
    outcome: CompareOutcome, result: Any, *, asset_id: Optional[str], provenance: Optional[dict[str, Any]],
) -> VisionResult:
    usage = VisionUsage()
    if result is not None:
        usage = VisionUsage(
            input_tokens=getattr(result, "usage", VisionUsage()).input_tokens,
            output_tokens=getattr(result, "usage", VisionUsage()).output_tokens,
            total_tokens=getattr(result, "usage", VisionUsage()).total_tokens,
        )
    observations = [
        VisualObservation(
            text=f"region changed (magnitude {r.magnitude:.2f})", kind="observed",
            region=r.region, confidence=min(1.0, r.magnitude), method="deterministic",
        )
        for r in outcome.regions
    ]
    return VisionResult(
        ok=True, mode="compare", description=outcome.description,
        observations=observations, regions=observations,
        comparison=outcome.to_dict(), confidence=outcome.confidence,
        provider=getattr(result, "provider", None), model=getattr(result, "model", None),
        backend=getattr(result, "backend", "pixel") if result is not None else "pixel",
        latency_ms=getattr(result, "latency_ms", 0), usage=usage,
        provenance=provenance or {}, warnings=outcome.warnings, asset_id=asset_id,
    )


__all__ = ["ChangedRegion", "CompareOutcome", "pixel_diff", "compare_images", "build_compare_result"]
