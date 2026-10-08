"""Process-wide event publisher for subsystems that have no bus handle.

A subsystem deep in the runtime (portfolio, quant, memory, market, the workspace
watcher) should not have to thread an `EventBus` through its constructors just to
announce that something happened. This module holds a reference to the ONE
`EventSystem` (and its loop) set at boot, and `publish_event(...)` schedules a
canonical publish.

It is loop-aware: an async caller schedules onto the running loop; a background
thread (e.g. the filesystem watcher) uses `run_coroutine_threadsafe` onto the
captured main loop. If no Event System is installed (unit tests, CLI) it is a
harmless no-op, so library code stays import-clean and side-effect-free by
default.

Use it as:

    from ..event_system.emit import publish_event
    publish_event("portfolio.position.added", {"portfolioId": pid, "symbol": sym},
                  source="portfolio", correlation_id=corr)
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

_SYSTEM: Optional[Any] = None
_LOOP: Optional[asyncio.AbstractEventLoop] = None


def set_event_system(system: Optional[Any]) -> None:
    global _SYSTEM
    _SYSTEM = system


def set_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Record the main event loop so a background thread can publish safely."""
    global _LOOP
    _LOOP = loop


def get_event_system() -> Optional[Any]:
    return _SYSTEM


def publish_event(
    type: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    source: str = "harness",
    **kwargs: Any,
) -> None:
    """Best-effort canonical publish from a sync, async or threaded seam."""
    system = _SYSTEM
    if system is None:
        return
    body = payload or {}
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        try:
            running.create_task(system.publish(type, body, source=source, **kwargs))
        except Exception:  # noqa: BLE001 - an advisory event must never break the caller
            pass
        return
    loop = _LOOP
    if loop is None or not loop.is_running():
        return
    try:
        asyncio.run_coroutine_threadsafe(system.publish(type, body, source=source, **kwargs), loop)
    except Exception:  # noqa: BLE001 - a failed schedule must never break the caller
        pass


__all__ = ["get_event_system", "publish_event", "set_event_system", "set_loop"]
