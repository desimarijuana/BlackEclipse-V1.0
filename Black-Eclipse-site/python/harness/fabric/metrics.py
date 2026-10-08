"""In-process observability counters for the Execution Fabric.

This is not a second logging system: it is a small, deterministic counter set the
admin API and the health surface read. Queue depth and worker state come from the
durable store (the source of truth); this holds only cheap process-local rates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

_COUNTERS = (
    "submitted", "direct", "queued", "succeeded", "failed", "retried",
    "timed_out", "cancelled", "dlq", "replayed", "deduplicated", "rate_limited",
)


@dataclass
class FabricMetrics:
    started_at: float = field(default_factory=time.time)
    counters: dict[str, int] = field(default_factory=lambda: {name: 0 for name in _COUNTERS})
    # rolling latency observations (bounded)
    latency_samples_ms: list[int] = field(default_factory=list)
    max_samples: int = 500

    def incr(self, name: str, amount: int = 1) -> None:
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += int(amount)

    def observe_latency(self, duration_ms: int) -> None:
        self.latency_samples_ms.append(int(duration_ms))
        if len(self.latency_samples_ms) > self.max_samples:
            del self.latency_samples_ms[: len(self.latency_samples_ms) - self.max_samples]

    def snapshot(self) -> dict[str, Any]:
        samples = sorted(self.latency_samples_ms)
        count = len(samples)
        p50 = samples[count // 2] if count else 0
        p95 = samples[min(count - 1, int(count * 0.95))] if count else 0
        return {
            "uptimeSeconds": round(time.time() - self.started_at, 1),
            "counters": dict(self.counters),
            "latency": {
                "samples": count,
                "p50Ms": p50,
                "p95Ms": p95,
                "maxMs": samples[-1] if samples else 0,
            },
        }


__all__ = ["FabricMetrics"]
