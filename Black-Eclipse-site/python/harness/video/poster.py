"""Poster-frame extraction for video artifact thumbnails (Phase 7).

A video artifact's thumbnail is a REAL frame of the rendered MP4, extracted
with the SAME FFmpeg tree the renderer links against (the BtbN build carries
`ffmpeg.exe` next to the DLLs). No frame, no thumbnail: when the tree is absent
or the object cannot be read, the preview stays `UNSUPPORTED` — this module
never fabricates a poster and never pulls a frame from a different video.

Registered on the shared preview engine by `video/bootstrap.py`
(`set_video_poster_extractor`), so the artifacts layer holds no video import.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("harness.video.poster")

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_TIMEOUT_S = 30
#: Where in the video the poster is taken from, tried in order. 1.5 s clears
#: the opening fade-in (scenes animate in over ~0.2-0.4 s) on every normal
#: video; the 0.5 s fallback still yields a real frame for a minimal render
#: (one 1 s scene), where 1.5 s does not exist. A frame is never fabricated:
#: when no candidate produces one the preview stays UNSUPPORTED.
_POSTER_TIMES: tuple[float, ...] = (1.5, 0.5)
_POSTER_WIDTH = 512


def extract_video_poster(storage: Any, artifact: Any) -> Optional[bytes]:
    """PNG bytes of a representative frame of a video artifact, or None.

    Never raises: a missing FFmpeg tree, an unreadable object or a failed
    extraction all return None (the preview then reports UNSUPPORTED).
    """
    try:
        key = getattr(artifact, "storage_key", None)
        mime = str(getattr(artifact, "mime_type", "") or "").lower()
        if not key or not mime.startswith("video/"):
            return None
        ffmpeg = _ffmpeg_binary()
        if ffmpeg is None:
            return None
        with storage.open(key) as handle:
            source = getattr(handle, "name", None)
            if not source:
                return None
            with tempfile.TemporaryDirectory(prefix="ve-poster-") as tmp:
                for seconds in _POSTER_TIMES:
                    poster = _extract_at(ffmpeg, str(source), Path(tmp), seconds)
                    if poster is not None:
                        return poster
                return None
    except Exception:  # noqa: BLE001 - an absent poster is an honest None
        return None


def _extract_at(ffmpeg: Path, source: str, tmp: Path, seconds: float) -> Optional[bytes]:
    target = tmp / "poster.png"
    if target.exists():
        target.unlink()
    completed = subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-loglevel", "error",
            "-ss", f"{seconds}", "-i", source,
            "-frames:v", "1",
            "-vf", f"scale={_POSTER_WIDTH}:-2",
            "-y", str(target),
        ],
        capture_output=True,
        timeout=_TIMEOUT_S,
        creationflags=_CREATE_NO_WINDOW,
    )
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        return None
    return target.read_bytes()


def _ffmpeg_binary() -> Optional[Path]:
    """`ffmpeg.exe` under the configured FFmpeg tree, or None when absent."""
    try:
        from .config import get_video_config  # noqa: PLC0415

        ffdir = get_video_config().resolve_ffmpeg_dir()
        if ffdir is None:
            return None
        name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        candidate = ffdir / "bin" / name
        return candidate if candidate.is_file() else None
    except Exception:  # noqa: BLE001
        return None


__all__ = ["extract_video_poster"]
