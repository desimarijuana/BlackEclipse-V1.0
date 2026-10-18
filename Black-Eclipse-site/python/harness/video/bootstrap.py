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

        def _market_provider() -> Any:
            """A `MarketGatewayProvider` over the EXISTING Market Data Gateway,
            or None when that layer is absent (bound scenes then fail honestly)."""
            if getattr(service, "market_gateway", None) is None:
                return None
            from .market_provider import MarketGatewayProvider  # noqa: PLC0415

            def _gateway_factory() -> Any:
                from ..market.gateway import MarketDataGateway  # noqa: PLC0415

                return MarketDataGateway(
                    service.server_bridge(),
                    cache=getattr(service, "market_cache", None),
                    router=getattr(service, "market_router", None),
                )

            return MarketGatewayProvider(_gateway_factory)

        register_video_tools(service.registry)
        video = VideoService(
            config=cfg,
            runner=VideoRunner(cfg),
            projects=VideoProjectStore(cfg.resolve_video_root() / "projects"),
            artifact_provider=lambda: getattr(service, "artifacts", None),
            data_provider=_market_provider,
        )
        service.video = video
        set_video_service(video)

        # Poster frames for video artifact thumbnails: the artifacts preview
        # engine has no video import by design, so this is the seam — a final
        # render's MP4 gets a REAL frame as its thumbnail (or an honest
        # UNSUPPORTED when the FFmpeg tree is absent).
        from ..artifacts.preview import set_video_poster_extractor  # noqa: PLC0415
        from .poster import extract_video_poster  # noqa: PLC0415

        set_video_poster_extractor(extract_video_poster)
    except Exception:  # noqa: BLE001 - the video pipeline must never block boot
        log.warning("video pipeline unavailable", exc_info=True)


__all__ = ["install_video_layer"]
