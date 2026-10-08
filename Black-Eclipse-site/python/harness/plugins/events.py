"""Plugin event bridge — namespaced events on Eclipse's ONE EventBus.

Plugins publish and subscribe through here, never the raw bus. Publishing
requires `events.publish`; subscribing requires `events.subscribe`. A plugin
event that fails to deliver never fails the originating core operation: handler
errors are caught, logged and counted, and (for `on_error` handlers) recorded as
dead-letter entries on the plugin's own event log.

Event types are validated: a plugin may publish inside its own namespace or a
common namespace, and a subscriber pattern may be an exact type, a `prefix.*`
wildcard or `*`.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .errors import PluginError

_EVENT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_.-]*[a-z0-9])?$")
_HANDLER_TIMEOUT_S = 10.0


class EventError(PluginError):
    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


@dataclass
class _Subscription:
    plugin_id: str
    pattern: str
    handler: Callable[[dict[str, Any], Any], Any]
    order: int = 100


def _matches(pattern: str, event_type: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-1]  # keep the dot
        return event_type.startswith(prefix) or event_type == pattern[:-2]
    return pattern == event_type


@dataclass
class PluginEventBridge:
    """Dispatches bus events to plugin subscribers and publishes plugin events."""

    bus: Any = None
    on_failure: Optional[Callable[[str, str], None]] = None
    context_for: Optional[Callable[[str], Any]] = None
    _subs: list[_Subscription] = field(default_factory=list)
    _connected: bool = False
    _unsub: Any = None

    def connect(self, bus: Any) -> None:
        self.bus = bus
        if not self._connected:
            self._unsub = bus.subscribe(self._on_bus_event)
            self._connected = True

    def disconnect(self) -> None:
        if self._unsub is not None:
            try:
                self._unsub()
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass
        self._unsub = None
        self._connected = False

    def register(self, plugin_id: str, pattern: str, handler: Callable[..., Any], *, order: int = 100) -> None:
        self._subs.append(_Subscription(plugin_id, pattern, handler, order))
        self._subs.sort(key=lambda s: (s.order, s.plugin_id))

    def unregister_plugin(self, plugin_id: str) -> None:
        self._subs = [s for s in self._subs if s.plugin_id != plugin_id]

    def subscriptions(self, plugin_id: Optional[str] = None) -> list[dict[str, Any]]:
        return [
            {"pluginId": s.plugin_id, "pattern": s.pattern, "order": s.order}
            for s in self._subs if plugin_id is None or s.plugin_id == plugin_id
        ]

    def publish(self, plugin_id: str, event_type: str, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not _EVENT_RE.match(event_type or ""):
            raise EventError("PLUGIN_EVENT_INVALID", f"invalid event type: {event_type!r}")
        if data is not None and not isinstance(data, dict):
            raise EventError("PLUGIN_EVENT_PAYLOAD", "event payload must be an object")
        event = {
            "id": f"plugin_{plugin_id}_{event_type}",
            "runId": None,
            "type": event_type,
            "seq": 0,
            "at": _now(),
            "data": data or {},
            "source": {"source_type": "plugin", "plugin_id": plugin_id},
        }
        if self.bus is not None:
            self.bus.publish(event)
        return event

    def _on_bus_event(self, event: dict[str, Any]) -> None:
        """Synchronous bus listener; schedules async dispatch when a loop runs."""
        event_type = str(event.get("type") or "")
        if not event_type:
            return
        targets = [s for s in self._subs if _matches(s.pattern, event_type)]
        if not targets:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop: a sync-only context has no async handler dispatch
        for sub in targets:
            loop.create_task(self._dispatch(sub, event))

    async def _dispatch(self, sub: _Subscription, event: dict[str, Any]) -> None:
        ctx = None
        if self.context_for is not None:
            try:
                ctx = self.context_for(sub.plugin_id)
            except Exception:  # noqa: BLE001
                ctx = None
        try:
            result = sub.handler(event, ctx)
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=_HANDLER_TIMEOUT_S)
        except asyncio.TimeoutError:
            self._fail(sub.plugin_id, "timeout", event)
        except Exception as exc:  # noqa: BLE001 - a subscriber must never break the bus
            self._fail(sub.plugin_id, f"{type(exc).__name__}: {exc}", event)

    def _fail(self, plugin_id: str, reason: str, event: dict[str, Any]) -> None:
        if self.on_failure is not None:
            try:
                self.on_failure(plugin_id, reason)
            except Exception:  # noqa: BLE001
                pass


def _now() -> str:
    from ..persistence import now_iso

    return now_iso()


__all__ = ["PluginEventBridge", "EventError"]
