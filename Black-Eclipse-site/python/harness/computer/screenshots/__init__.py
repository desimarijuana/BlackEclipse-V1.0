"""Screenshot subsystem — capture, region intelligence and change detection.

    capture.py    encode a driver ScreenFrame to PNG; persist under artifacts
    regions.py    window segmentation, cropping and a perceptual screen digest
    diff.py       before/after change detection over regions

The point is to avoid repeatedly sending a whole high-resolution screen to a
model: the agent can ask for the full screen, one window, or a region, and
change detection tells it whether an action actually did anything.
"""

from __future__ import annotations

from .capture import ScreenCapture
from .diff import ScreenDiff
from .regions import region_digest, segment_windows

__all__ = ["ScreenCapture", "ScreenDiff", "region_digest", "segment_windows"]
