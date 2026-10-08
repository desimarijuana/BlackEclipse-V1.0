"""Document intelligence telemetry (spec §38).

Every processing stage emits a structured event on the SAME harness event path
the rest of the runtime uses (`RunEmitter` → `HarnessEvent` → bus → SSE). No
disconnected monitoring. When no emitter is attached the event is dropped, never
invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

EVENT_REQUEST = "document.request"
EVENT_VALIDATE = "document.validate"
EVENT_PARSE = "document.parse"
EVENT_OCR = "document.ocr"
EVENT_RENDER = "document.render"
EVENT_VISION = "document.vision"
EVENT_INDEX = "document.index"
EVENT_STORE = "document.store"
EVENT_COMPARE = "document.compare"
EVENT_QUERY = "document.query"
EVENT_EVIDENCE = "document.evidence"
EVENT_CACHE_HIT = "document.cache_hit"
EVENT_CACHE_MISS = "document.cache_miss"
EVENT_ERROR = "document.error"
EVENT_STAGE = "document.stage"


@dataclass
class DocumentTelemetry:
    emitter: Any = None
    enabled: bool = True
    counters: dict[str, int] = field(default_factory=dict)

    def _bump(self, event_type: str) -> None:
        self.counters[event_type] = self.counters.get(event_type, 0) + 1

    def emit(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        self._bump(event_type)
        if not self.enabled or self.emitter is None:
            return
        payload = data or {}
        try:
            emit_sync = getattr(self.emitter, "emit_sync", None)
            if callable(emit_sync):
                emit_sync(event_type, payload)
                return
            emit = getattr(self.emitter, "emit", None)
            if callable(emit):
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.create_task(emit(event_type, payload))
                else:
                    asyncio.run(emit(event_type, payload))
        except Exception:  # noqa: BLE001 - observability must never break a call
            pass

    def summary(self) -> dict[str, int]:
        return dict(self.counters)


__all__ = [
    "DocumentTelemetry", "EVENT_REQUEST", "EVENT_VALIDATE", "EVENT_PARSE", "EVENT_OCR",
    "EVENT_RENDER", "EVENT_VISION", "EVENT_INDEX", "EVENT_STORE", "EVENT_COMPARE",
    "EVENT_QUERY", "EVENT_EVIDENCE", "EVENT_CACHE_HIT", "EVENT_CACHE_MISS", "EVENT_ERROR",
    "EVENT_STAGE",
]
