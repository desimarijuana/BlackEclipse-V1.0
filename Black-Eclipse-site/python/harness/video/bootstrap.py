"""Video pipeline boot wiring.

Installs the `VideoService` (projects + job API) on the live service and
publishes it for the Fabric worker handler. Best-effort: never blocks boot.
The Artifact Center is resolved lazily (it may be installed after this layer),
so final renders register correctly regardless of wiring order.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.video")


def install_video_layer(service: Any) -> None:
    try:
        from .config import get_video_config

        cfg = get_video_config()
        if not cfg.enabled:
            return
        from .projects import VideoProjectStore
        from .runner import VideoRunner
        from .service import VideoService, set_video_service
        from .tools import register_video_tools

        register_video_tools(service.registry)
        video = VideoService(
            config=cfg,
            runner=VideoRunner(cfg),
            projects=VideoProjectStore(cfg.resolve_video_root() / "projects"),
            artifact_provider=lambda: getattr(service, "artifacts", None),
        )
        service.video = video
        set_video_service(video)
    except Exception:  # noqa: BLE001 - the video pipeline must never block boot
        log.warning("video pipeline unavailable", exc_info=True)


__all__ = ["install_video_layer"]
