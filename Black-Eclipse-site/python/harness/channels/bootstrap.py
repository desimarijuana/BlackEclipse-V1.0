"""Install the Channel Gateway into the process-wide `AgenticService`.

`install_channel_layer(service)` constructs the ONE `ChannelService` and attaches
it as `service.channels`. `start_channels`/`stop_channels` drive its provider
pollers from the FastAPI lifespan. Best-effort and additive: if the channel store
cannot be opened the rest of the harness still boots, and `/health` reports the
channel surface honestly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import ChannelService

log = logging.getLogger("harness.channels.bootstrap")


def install_channel_layer(service: Any) -> Optional[ChannelService]:
    existing = getattr(service, "channels", None)
    if existing is not None:
        return existing
    try:
        channel_service = ChannelService(service)
    except Exception:  # noqa: BLE001 - channels must never block boot
        log.warning("channel gateway failed to install", exc_info=True)
        return None
    service.channels = channel_service
    return channel_service


def channel_service(service: Any) -> Optional[ChannelService]:
    return getattr(service, "channels", None)


async def start_channels(service: Any) -> None:
    """Start enabled local pollers (Telegram long-poll). Never a boot blocker."""
    svc = channel_service(service) or install_channel_layer(service)
    if svc is None:
        return
    try:
        svc.start()
        log.info("channel gateway started (pollers=%s)", sorted(svc._tasks))  # noqa: SLF001
    except Exception:  # noqa: BLE001 - channels must never block boot
        log.warning("channel gateway failed to start", exc_info=True)


async def stop_channels(service: Any) -> None:
    svc = channel_service(service)
    if svc is None:
        return
    try:
        await svc.stop()
    except Exception:  # noqa: BLE001
        log.warning("channel gateway shutdown failed", exc_info=True)


__all__ = ["channel_service", "install_channel_layer", "start_channels", "stop_channels"]
