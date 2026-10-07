"""Visual change detection between two screen frames.

A before/after comparison that answers the question an agent actually has after
an action: *did anything change, and where?* Without PIL it degrades to a digest
comparison (whole-frame changed / not changed) honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import Bounds
from .capture import frame_digest


@dataclass
class ChangeRegion:
    bounds: Bounds
    changed: bool
    difference: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"bounds": self.bounds.to_dict(), "changed": self.changed, "difference": round(self.difference, 4)}


@dataclass
class DiffResult:
    changed: bool
    before_digest: str = ""
    after_digest: str = ""
    changed_fraction: float = 0.0
    regions: list[ChangeRegion] = field(default_factory=list)
    method: str = "digest"

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed, "beforeDigest": self.before_digest,
            "afterDigest": self.after_digest, "changedFraction": round(self.changed_fraction, 4),
            "regions": [r.to_dict() for r in self.regions], "method": self.method,
        }


class ScreenDiff:
    """Compares two `ScreenFrame`s (or two digests) for change."""

    def compare(
        self,
        before: Any,
        after: Any,
        *,
        grid: int = 8,
        threshold: float = 0.02,
    ) -> DiffResult:
        before_digest = frame_digest(before) if not isinstance(before, str) else before
        after_digest = frame_digest(after) if not isinstance(after, str) else after

        before_img = getattr(before, "data", None) if not isinstance(before, str) else None
        after_img = getattr(after, "data", None) if not isinstance(after, str) else None
        if before_img is not None and after_img is not None:
            try:
                return self._pixel_diff(before_img, after_img, getattr(before, "bounds", Bounds()), grid=grid, threshold=threshold)
            except Exception:  # noqa: BLE001
                pass
        changed = before_digest != after_digest
        return DiffResult(
            changed=changed, before_digest=before_digest, after_digest=after_digest,
            changed_fraction=1.0 if changed else 0.0,
            regions=[ChangeRegion(bounds=getattr(before, "bounds", Bounds()), changed=changed)],
            method="digest",
        )

    def _pixel_diff(self, before_img: Any, after_img: Any, bounds: Bounds, *, grid: int, threshold: float) -> DiffResult:
        from PIL import ImageChops  # noqa: PLC0415

        small_before = before_img.convert("L").resize((grid * 8, grid * 8))
        small_after = after_img.convert("L").resize((grid * 8, grid * 8))
        diff = ImageChops.difference(small_before, small_after)
        # `tobytes()` is the forward-compatible accessor (Pillow 14 deprecates
        # `getdata()`); an "L" image is one byte per pixel, so this is exact.
        pixels = list(diff.tobytes())
        total = len(pixels) or 1
        changed_px = sum(1 for p in pixels if p > 16)
        fraction = changed_px / total

        # Per-cell change, mapped back to screen regions.
        cell_w = bounds.width / grid
        cell_h = bounds.height / grid
        w = grid * 8
        regions: list[ChangeRegion] = []
        for gy in range(grid):
            for gx in range(grid):
                cell_vals = [pixels[gy * 8 * w + gx * 8 + dy * w + dx] for dy in range(8) for dx in range(8)]
                cell_changed = sum(1 for p in cell_vals if p > 16) / 64
                regions.append(ChangeRegion(
                    bounds=Bounds(int(bounds.x + gx * cell_w), int(bounds.y + gy * cell_h),
                                  int(cell_w), int(cell_h)),
                    changed=cell_changed > threshold, difference=cell_changed,
                ))
        return DiffResult(
            changed=fraction > threshold, before_digest=frame_digest(before_img),
            after_digest=frame_digest(after_img), changed_fraction=fraction,
            regions=regions, method="pixel",
        )


__all__ = ["ChangeRegion", "DiffResult", "ScreenDiff"]
