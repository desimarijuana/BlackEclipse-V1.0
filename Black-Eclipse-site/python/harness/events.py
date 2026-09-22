"""Harness event emission — the Python runtime owns the event model.

Events are assigned a monotonic per-run sequence and timestamp here, persisted
to the agent-memory database, then published on an in-process bus for live
subscribers. The TS side is no longer involved in event creation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from .persistence import AgentMemoryStore, now_iso

log = logging.getLogger("harness.events")

Listener = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        # Live per-run queues for SSE consumers. A queue (not a callback) so a
        # slow HTTP client can never stall the agent loop.
        self._streams: dict[str, list[asyncio.Queue[Optional[dict[str, Any]]]]] = {}

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def publish(self, event: dict[str, Any]) -> None:
        run_id = event.get("runId")
        if run_id:
            for queue in list(self._streams.get(run_id, [])):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # a slow client drops live deltas; the run is unaffected
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # noqa: BLE001 - a broken subscriber must not break a run
                log.warning("event subscriber failed", exc_info=True)

    def open_stream(self, run_id: str) -> asyncio.Queue[Optional[dict[str, Any]]]:
        """Register a live queue for one run. Caller must `close_stream`."""
        queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue(maxsize=1000)
        self._streams.setdefault(run_id, []).append(queue)
        return queue

    def close_stream(self, run_id: str, queue: asyncio.Queue[Optional[dict[str, Any]]]) -> None:
        queues = self._streams.get(run_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._streams.pop(run_id, None)

    def end_stream(self, run_id: str) -> None:
        """Signal all live consumers that a run is finished (sentinel None)."""
        for queue in list(self._streams.get(run_id, [])):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass


class RunEmitter:
    """Per-run emitter: sequence numbers, persistence, bus fan-out."""

    def __init__(self, run_id: str, store: AgentMemoryStore, bus: Optional[EventBus] = None) -> None:
        self.run_id = run_id
        self._store = store
        self._bus = bus
        self._seq = 0

    async def emit(self, event_type: str, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._seq += 1
        event = {
            "id": f"evt_{self.run_id}_{self._seq}",
            "runId": self.run_id,
            "type": event_type,
            "seq": self._seq,
            "at": now_iso(),
            "data": data or {},
        }
        try:
            self._store.append_event(self.run_id, event_type, event["seq"], event["data"])
        except Exception:  # noqa: BLE001 - losing an event must not kill the run
            log.error("failed to persist event %s", event_type, exc_info=True)
        if self._bus:
            self._bus.publish(event)
        return event

    def emit_transient(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        """Publish a live-only event (no persistence, no sequence).

        Token deltas are high-frequency and worthless after the run ends; writing
        every one to SQLite would bloat the trace and slow the run. They ride the
        bus to live subscribers only — the final message is still persisted by
        `model.completed`.
        """
        self._seq += 1
        event = {
            "id": f"evt_{self.run_id}_{self._seq}",
            "runId": self.run_id,
            "type": event_type,
            "seq": self._seq,
            "at": now_iso(),
            "data": data or {},
            "transient": True,
        }
        if self._bus:
            self._bus.publish(event)


__all__ = ["EventBus", "RunEmitter"]
