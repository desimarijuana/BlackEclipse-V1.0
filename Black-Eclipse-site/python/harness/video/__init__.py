"""Native video generation: the fframes Rust worker behind an Execution-Fabric
job layer (draft renders, final renders, frame inspection, artifact
registration).

Phase 2 scope: the job layer only — agent tools, routes and the storyboard
schema arrive in later phases (see `docs/video-pipeline.md`).
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
