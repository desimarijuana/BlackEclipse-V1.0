"""Per-run latency marks — one durable summary of where an answer's time went.

The chat feels "stuck" in three different places, and they need different fixes:

* **setup** — everything the runtime does before the first model call
  (memory, profile, surface, prompt blocks). Measured `run.started` →
  first `model.requested`.
* **time to first token** — the provider's own latency. Measured
  `model.requested` → `model.first_token` (the same number the model stream
  already reports as `ttftMs`).
* **cadence** — whether tokens arrive smoothly or in bursts. Measured as the
  gaps between `model.delta` events.

`RunTimings` is a pure in-memory recorder. `RunEmitter` feeds it every event it
sees and, on the run's terminal event, writes ONE `run.timings` event so the
numbers survive the run without adding a row per token. Recording is total: a
malformed event or a missing mark yields an absent field, never an error.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

__all__ = ["TERMINAL_EVENT_TYPES", "RunTimings", "percentile"]

# The event types that end a run. `run.timings` itself is deliberately NOT in
# this set (it is written BY the terminal event, not at it).
TERMINAL_EVENT_TYPES = frozenset(
    {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}
)

# Token deltas can be numerous. The gap sample is bounded so a very long answer
# cannot make this record grow without limit; the count is always exact.
_MAX_GAPS = 2_000


def percentile(values: list[float], pct: float) -> Optional[float]:
    """The `pct` percentile of `values` (linear interpolation), or None."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _ms(seconds: Optional[float]) -> Optional[int]:
    if seconds is None:
        return None
    return max(0, int(round(seconds * 1000.0)))


class RunTimings:
    """Latency marks for one run. Cheap, sync, and never raises."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.started_at: Optional[float] = None
        self.first_request_at: Optional[float] = None
        self.first_token_at: Optional[float] = None
        self.first_delta_at: Optional[float] = None
        self.reported_ttft_s: Optional[float] = None
        self.delta_count = 0
        self.delta_chars = 0
        self.model_calls = 0
        self._last_delta_at: Optional[float] = None
        self._gaps: list[float] = []

    def observe(self, event_type: str, data: Optional[dict[str, Any]], at: Optional[float] = None) -> None:
        """Record one emitted event. Unknown types are ignored."""
        now = self._clock() if at is None else at
        try:
            if event_type in ("run.created", "run.started"):
                if self.started_at is None:
                    self.started_at = now
            elif event_type == "model.requested":
                self.model_calls += 1
                if self.first_request_at is None:
                    self.first_request_at = now
            elif event_type == "model.first_token":
                if self.first_token_at is None:
                    self.first_token_at = now
                raw = (data or {}).get("ttftMs")
                if self.reported_ttft_s is None and isinstance(raw, (int, float)) and raw >= 0:
                    self.reported_ttft_s = float(raw) / 1000.0
            elif event_type == "model.delta":
                text = (data or {}).get("text")
                self.delta_count += 1
                if isinstance(text, str):
                    self.delta_chars += len(text)
                if self.first_delta_at is None:
                    self.first_delta_at = now
                if self._last_delta_at is not None and len(self._gaps) < _MAX_GAPS:
                    self._gaps.append(max(0.0, now - self._last_delta_at))
                self._last_delta_at = now
        except Exception:  # noqa: BLE001 - measurement must never break a run
            return

    def summary(self, *, at: Optional[float] = None) -> dict[str, Any]:
        """A compact, JSON-safe summary. Absent marks are omitted, never faked."""
        now = self._clock() if at is None else at
        out: dict[str, Any] = {
            "deltaCount": self.delta_count,
            "streamedChars": self.delta_chars,
            "modelCalls": self.model_calls,
        }
        if self.started_at is not None:
            out["totalMs"] = _ms(max(0.0, now - self.started_at))
            if self.first_request_at is not None:
                out["setupMs"] = _ms(max(0.0, self.first_request_at - self.started_at))
            if self.first_delta_at is not None:
                out["firstDeltaMs"] = _ms(max(0.0, self.first_delta_at - self.started_at))
        ttft = None
        if self.reported_ttft_s is not None:
            ttft = self.reported_ttft_s
        elif self.first_request_at is not None and self.first_token_at is not None:
            ttft = max(0.0, self.first_token_at - self.first_request_at)
        if ttft is not None:
            out["ttftMs"] = _ms(ttft)
        if self._gaps:
            out["deltaGapP50Ms"] = _ms(percentile(self._gaps, 50))
            out["deltaGapP95Ms"] = _ms(percentile(self._gaps, 95))
            out["deltaGapMaxMs"] = _ms(max(self._gaps))
        return out
