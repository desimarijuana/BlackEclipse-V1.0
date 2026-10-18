"""Native video generation: the fframes Rust worker behind an Execution-Fabric
job layer (projects, versioned storyboards, evidence-bound market data, PNG
previews, draft/final renders, frame inspection, a bounded repair loop,
artifact registration).

Phases 1–6 are live; the chat artifact UI is Phase 7 and hardening is Phase 8
(see `docs/video-pipeline.md`).
"""

from __future__ import annotations

from .bootstrap import install_video_layer
from .config import VideoConfig, get_video_config
from .models import VideoError
from .service import VideoService, get_video_service, set_video_service

__all__ = [
    "VideoConfig",
    "VideoError",
    "VideoService",
    "get_video_config",
    "get_video_service",
    "install_video_layer",
    "set_video_service",
]
