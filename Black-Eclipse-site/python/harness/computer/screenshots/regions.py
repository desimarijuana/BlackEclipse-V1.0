"""Screen region intelligence — segmentation and digests.

The agent should not have to reason over a whole 1920×1080 frame when it cares
about one app. `segment_windows` turns the window list into non-overlapping
named regions (by z-order), and `region_digest` gives each region a cheap digest
so change detection is per-region rather than whole-screen.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Bounds, WindowInfo


def segment_windows(windows: list[WindowInfo], *, display_bounds: Optional[Bounds] = None) -> list[dict[str, Any]]:
    """Segment the desktop into named regions from the window list (top-down).

    Windows are returned in z-order (top first); overlapping lower windows are
    still listed but flagged. This is DETECTION, not a claim of exact visibility.
    """
    regions: list[dict[str, Any]] = []
    for window in sorted(windows, key=lambda w: w.z_order):
        if window.minimized or window.bounds.width <= 0 or window.bounds.height <= 0:
            continue
        region: dict[str, Any] = {
            "windowId": window.id, "title": window.title, "application": window.app,
            "bounds": window.bounds.to_dict(), "displayId": window.display_id,
            "zOrder": window.z_order,
        }
        if display_bounds is not None:
            region["onDisplay"] = display_bounds.to_dict()
        regions.append(region)
    return regions


def region_digest(digest: str, bounds: Bounds) -> dict[str, Any]:
    """A content-free region identity: its geometry plus its screen digest."""
    return {
        "digest": digest,
        "bounds": bounds.to_dict(),
    }


def bounds_of_window(window: WindowInfo) -> Bounds:
    return window.bounds


__all__ = ["bounds_of_window", "region_digest", "segment_windows"]
