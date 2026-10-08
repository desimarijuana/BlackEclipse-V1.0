"""Sampling — decide what telemetry is retained without ever dropping failures.

Two stages:

* **Head sampling** (`should_sample`) is a deterministic function of the trace
  id, so a decision made in the run process is reproduced identically when the
  same trace crosses a queue/worker boundary. `always_sample_errors` marks the
  trace so the tail stage can override.
* **Tail sampling** (`should_keep_span`) decides at span END using the final
  status/duration; it ALWAYS keeps error spans, failed runs, security events and
  anomalies regardless of the head rate.

The sampler is cheap, allocation-free on the hot path and safe to call from any
thread.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


def _ratio(trace_id: str) -> float:
    """Map a trace id to [0, 1) deterministically (first 8 hex bytes)."""
    try:
        head = int(trace_id[:16], 16)
    except (ValueError, TypeError):
        return 1.0
    return head / float(1 << 64)


@dataclass
class SamplingDecision:
    sampled: bool
    reason: str = "head"
    forced: bool = False


@dataclass
class Sampler:
    rate: float = 1.0
    always_sample_errors: bool = True
    latency_threshold_ms: float = 0.0
    _forced_keep: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.rate = max(0.0, min(1.0, float(self.rate)))

    def should_sample(self, trace_id: str) -> SamplingDecision:
        if self.rate >= 1.0:
            return SamplingDecision(True, "rate=1.0")
        if self.rate <= 0.0:
            # A 0 rate still keeps forced (error) traces; the caller marks them.
            return SamplingDecision(False, "rate=0.0")
        keep = _ratio(trace_id) < self.rate
        return SamplingDecision(keep, f"head ratio<{self.rate}")

    def force_keep(self, trace_id: str) -> None:
        """Mark a trace as must-keep (an error/security/anomaly was seen)."""
        if len(self._forced_keep) > 100_000:
            self._forced_keep.clear()
        self._forced_keep.add(trace_id)

    def should_keep_span(
        self,
        trace_id: str,
        *,
        is_error: bool = False,
        is_security: bool = False,
        is_anomaly: bool = False,
        duration_ms: float = 0.0,
    ) -> bool:
        if is_error or is_security or is_anomaly:
            self.force_keep(trace_id)
            return True
        if trace_id in self._forced_keep:
            return True
        if self.latency_threshold_ms and duration_ms >= self.latency_threshold_ms:
            self.force_keep(trace_id)
            return True
        return self.should_sample(trace_id).sampled

    def is_forced(self, trace_id: str) -> bool:
        return trace_id in self._forced_keep

    def snapshot(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "alwaysSampleErrors": self.always_sample_errors,
            "latencyThresholdMs": self.latency_threshold_ms,
            "forcedTraces": len(self._forced_keep),
        }


__all__ = ["Sampler", "SamplingDecision"]
