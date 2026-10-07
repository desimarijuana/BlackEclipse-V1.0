"""Screen capture + artifact persistence.

Wraps a driver's `capture()` and persists the PNG under the gitignored artifacts
root (never the operator's checkout). Also crops a stored frame to a region and
produces a perceptual digest without any heavy dependency (a downsampled average
grid), so change detection works even when PIL is absent.
"""

from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from typing import Any, Optional

from ..models import Bounds
from ..drivers.base import ScreenFrame


def frame_digest(frame: Any) -> str:
    """A perceptual-ish digest of a frame: downsampled luma grid hashed.

    Uses PIL when available; otherwise hashes the raw bytes. Deterministic for
    an unchanged screen so change detection is stable.
    """
    data = getattr(frame, "data", None)
    if data is not None:
        try:
            small = data.convert("L").resize((32, 32))
            return hashlib.sha256(small.tobytes()).hexdigest()[:20]
        except Exception:  # noqa: BLE001
            pass
    raw = getattr(frame, "png_bytes", None)
    if raw:
        return hashlib.sha256(raw).hexdigest()[:20]
    return ""


class ScreenCapture:
    """Capture frames from a driver and persist them."""

    def __init__(self, *, driver: Any, screenshots_dir: Path) -> None:
        self._driver = driver
        self._dir = Path(screenshots_dir)

    async def full(self, *, display_id: Optional[str] = None) -> ScreenFrame:
        return await self._driver.capture(display_id=display_id)

    async def window(self, window_id: str) -> ScreenFrame:
        return await self._driver.capture(window_id=window_id)

    async def region(self, bounds: Bounds) -> ScreenFrame:
        return await self._driver.capture(region=bounds)

    def crop(self, frame: ScreenFrame, bounds: Bounds, *, origin: Optional[Bounds] = None) -> Optional[Any]:
        """Crop a PIL frame to `bounds`. `origin` is the frame's own top-left in
        screen coordinates (defaults to the frame's bounds)."""
        if getattr(frame, "data", None) is None:
            return None
        base = origin or frame.bounds
        try:
            left = bounds.x - base.x
            top = bounds.y - base.y
            return frame.data.crop((left, top, left + bounds.width, top + bounds.height))
        except Exception:  # noqa: BLE001
            return None

    def persist(self, frame: ScreenFrame, *, session_id: str, label: str = "screen") -> Optional[str]:
        """Write the frame as a PNG; return the path or None when unavailable."""
        png = getattr(frame, "png_bytes", None)
        if png is None and getattr(frame, "data", None) is not None:
            try:
                buffer = io.BytesIO()
                frame.data.save(buffer, format="PNG")
                png = buffer.getvalue()
            except Exception:  # noqa: BLE001
                png = None
        if png is None:
            return None
        try:
            directory = self._dir / session_id
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{label}-{int(time.time() * 1000)}.png"
            path.write_bytes(png)
            return str(path)
        except OSError:
            return None

    def size(self, frame: ScreenFrame) -> tuple[int, int]:
        return (frame.width, frame.height)


__all__ = ["ScreenCapture", "frame_digest"]
