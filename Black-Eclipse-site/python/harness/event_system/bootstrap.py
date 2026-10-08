"""Install the Event System into the process-wide `AgenticService`.

`install_event_system(service)` constructs the facade exactly once and attaches
it as `service.events`. `start_events`/`stop_events` on the service drive the
lifespan. Best-effort and additive: if the event store cannot be opened the rest
of the harness still boots (the runtime reports the events surface as stopped).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .config import EventConfig
from .service import EventSystem

log = logging.getLogger("harness.events.bootstrap")


def install_event_system(
    service: Any,
    *,
    config: Optional[EventConfig] = None,
    max_concurrency: Optional[int] = None,
    echo_legacy: Optional[bool] = None,
) -> EventSystem:
    existing = getattr(service, "_event_system", None)
    if existing is not None:
        return existing
    system = EventSystem(
        service, config=config or EventConfig.from_env(),
        max_concurrency=max_concurrency, echo_legacy=echo_legacy,
    )
    service._event_system = system  # noqa: SLF001 - the one process-wide attach point
    from .emit import set_event_system  # noqa: PLC0415

    set_event_system(system)
    return system


def event_system(service: Any) -> EventSystem:
    """The process-wide Event System, constructed lazily on first use."""
    return install_event_system(service)


async def start_events(service: Any) -> None:
    """Start the Event System + its built-in consumers. Never a boot blocker."""
    system = event_system(service)
    if not system.config.bus_enabled:
        log.info("event system disabled (EVENT_BUS_ENABLED=0)")
        return
    try:
        await system.start()
    except Exception:  # noqa: BLE001 - the event layer must never block boot
        log.warning("event system failed to start", exc_info=True)


async def stop_events(service: Any) -> None:
    system = getattr(service, "_event_system", None)
    if system is None:
        return
    try:
        await system.stop()
    except Exception:  # noqa: BLE001
        log.warning("event system shutdown failed", exc_info=True)


__all__ = ["event_system", "install_event_system", "start_events", "stop_events"]
