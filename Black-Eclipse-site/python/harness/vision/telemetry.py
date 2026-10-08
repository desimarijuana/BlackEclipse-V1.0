"""Vision telemetry.

Every vision operation emits a structured event on the SAME harness event path
the rest of the runtime uses (`RunEmitter` → persisted `HarnessEvent` → bus →
SSE). There is no disconnected telemetry system: when no run emitter is attached
(e.g. a direct tool call in a test), events are simply dropped, never invented.

Fields tracked: provider, model, task/mode, latency, input/output size, token
usage, cost, cache status, failure class, retry count, confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Event vocabulary (spec §30).
EVENT_REQUEST = "vision.request"
EVENT_PREPROCESS = "vision.preprocess"
EVENT_SECURITY = "vision.security"
EVENT_ROUTE = "vision.route"
EVENT_PROVIDER_CALL = "vision.provider_call"
EVENT_CACHE_HIT = "vision.cache_hit"
EVENT_CACHE_MISS = "vision.cache_miss"
EVENT_OCR = "vision.ocr"
EVENT_GROUNDING = "vision.grounding"
EVENT_CHART = "vision.chart_analysis"
EVENT_DOCUMENT = "vision.document_analysis"
EVENT_COMPARE = "vision.compare"
EVENT_ERROR = "vision.error"


@dataclass
class VisionTelemetry:
    """Emits vision events through an optional run emitter."""

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
            # The emitter path is async in the graph; a sync seam is used here
            # (like tools._warn_deprecated) so telemetry can never stall a call.
            emit_sync = getattr(self.emitter, "emit_sync", None)
            if callable(emit_sync):
                emit_sync(event_type, payload)
                return
            emit = getattr(self.emitter, "emit", None)
            if callable(emit):
                import asyncio  # noqa: PLC0415

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


def usage_fields(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    return {
        "inputTokens": getattr(usage, "input_tokens", 0),
        "outputTokens": getattr(usage, "output_tokens", 0),
        "totalTokens": getattr(usage, "total_tokens", 0),
        "cost": getattr(usage, "cost", None),
        "tokensEstimated": getattr(usage, "estimated", False),
    }


__all__ = [
    "VisionTelemetry", "usage_fields",
    "EVENT_REQUEST", "EVENT_PREPROCESS", "EVENT_ROUTE", "EVENT_PROVIDER_CALL",
    "EVENT_CACHE_HIT", "EVENT_CACHE_MISS", "EVENT_OCR", "EVENT_GROUNDING",
    "EVENT_CHART", "EVENT_DOCUMENT", "EVENT_COMPARE", "EVENT_ERROR",
]
