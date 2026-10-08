"""Event System observability — counters + latency percentiles.

Self-contained and lock-protected so it can be read from any thread while the
bus updates it from the event loop. Not a second monitoring stack: the same
values are exposed through the `/events/metrics` route and folded into the run
observability surfaces. Percentiles use a bounded reservoir, so memory stays flat
under an event storm.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Optional

_MAX_RESERVOIR = 4096


class EventMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {
            "published": 0,
            "persisted": 0,
            "validationFailed": 0,
            "processed": 0,
            "delivered": 0,
            "failed": 0,
            "retried": 0,
            "deadLettered": 0,
            "deduplicated": 0,
            "droppedBackpressure": 0,
            "replayed": 0,
        }
        self._by_type: dict[str, int] = {}
        self._processing_ms: deque[float] = deque(maxlen=_MAX_RESERVOIR)
        self._queue_ms: deque[float] = deque(maxlen=_MAX_RESERVOIR)
        self._subscribers = 0

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount

    def observe_type(self, event_type: str) -> None:
        with self._lock:
            self._by_type[event_type] = self._by_type.get(event_type, 0) + 1

    def observe_processing(self, ms: float) -> None:
        with self._lock:
            self._processing_ms.append(max(0.0, ms))

    def observe_queue(self, ms: float) -> None:
        with self._lock:
            self._queue_ms.append(max(0.0, ms))

    def set_subscribers(self, count: int) -> None:
        with self._lock:
            self._subscribers = count

    @staticmethod
    def _percentile(values: list[float], pct: float) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
        return round(ordered[idx], 3)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            processing = list(self._processing_ms)
            queue = list(self._queue_ms)
            return {
                **self._counters,
                "byType": dict(sorted(self._by_type.items(), key=lambda kv: kv[1], reverse=True)[:50]),
                "subscribers": self._subscribers,
                "processingLatencyMs": {
                    "p50": self._percentile(processing, 50),
                    "p95": self._percentile(processing, 95),
                    "p99": self._percentile(processing, 99),
                    "samples": len(processing),
                },
                "queueLatencyMs": {
                    "p50": self._percentile(queue, 50),
                    "p95": self._percentile(queue, 95),
                    "p99": self._percentile(queue, 99),
                    "samples": len(queue),
                },
            }


__all__ = ["EventMetrics"]
