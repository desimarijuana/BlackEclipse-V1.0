"""The process-wide terminal manager, and the event bridge to the run bus.

Both the agent tools and the HTTP router must reach the SAME `TerminalManager`
instance, so it lives here as one process-wide singleton (mirroring `deps.service`
for the runtime). The service installs it at boot; a test can install its own.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .manager import TerminalManager

_MANAGER: Optional[TerminalManager] = None


def set_terminal_manager(manager: Optional[TerminalManager]) -> None:
    global _MANAGER
    _MANAGER = manager


def get_terminal_manager() -> Optional[TerminalManager]:
    return _MANAGER


def build_terminal_manager(*, store: Optional[Any] = None, bus: Optional[Any] = None) -> TerminalManager:
    """Construct a manager whose events are published onto the harness bus.

    A background process event has no live per-run emitter (it fires from a pump
    thread), so it rides the process-wide `EventBus` with its `runId`; a run's SSE
    consumer filters by that id exactly as for a persisted event.
    """
    on_event: Optional[Callable[[str, dict[str, Any]], None]] = None
    if bus is not None:
        import time as _time

        def on_event(event_type: str, data: dict[str, Any]) -> None:  # noqa: ANN001
            bus.publish({
                "type": f"terminal.{event_type}",
                "runId": data.get("runId"),
                "data": data,
                "at": _time.time(),
            })

    return TerminalManager(store=store, on_event=on_event)


__all__ = ["build_terminal_manager", "get_terminal_manager", "set_terminal_manager"]
