"""Anomaly & loop detection — statistical, rule-based, extensible.

Two detectors the hub runs on every completed operation:

* `LoopDetector` — counts identical operation signatures (tool + canonical args,
  or model+step shape) in a sliding window. N repeats mark a loop, which the hub
  emits as `onLoopDetected` so Eclipse's Recovery Engine can act.
* `AnomalyDetector` — maintains rolling mean/stddev per metric and flags values
  beyond `z_threshold` sigmas (with a warmup and an absolute floor so a tiny
  variance does not produce false positives). Errors, latency and cost spikes
  are all covered.

Neither detector mutates runtime state; they only return verdicts the hub maps
to hook events. The design leaves room for an ML detector behind the same
`Detector` interface.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


class Detector(Protocol):
    name: str

    def reset(self) -> None: ...


@dataclass
class LoopVerdict:
    detected: bool
    signature: str
    count: int
    window: int


class LoopDetector:
    name = "loop"

    def __init__(self, *, threshold: int = 3, window: int = 8) -> None:
        self.threshold = max(2, threshold)
        self.window = max(self.threshold, window)
        self._signatures: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=self.window))
        self._counts: dict[str, int] = defaultdict(int)

    def observe(self, signature: str) -> LoopVerdict:
        buffer = self._signatures[signature]
        buffer.append(signature)
        count = sum(1 for s in buffer if s == signature)
        detected = count >= self.threshold
        if detected:
            self._counts[signature] += 1
        return LoopVerdict(detected=detected, signature=signature, count=count, window=self.window)

    def reset(self) -> None:
        self._signatures.clear()
        self._counts.clear()

    def snapshot(self) -> dict[str, Any]:
        return {"threshold": self.threshold, "window": self.window, "trackedSignatures": len(self._signatures)}


@dataclass
class _Stats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def stddev(self) -> float:
        return math.sqrt(self.m2 / self.count) if self.count > 1 else 0.0


@dataclass
class AnomalyVerdict:
    detected: bool
    metric: str
    value: float
    mean: float
    stddev: float
    zscore: float
    reason: str = ""


class AnomalyDetector:
    name = "anomaly"

    def __init__(
        self,
        *,
        z_threshold: float = 4.0,
        min_samples: int = 20,
        absolute_floor: Optional[dict[str, float]] = None,
        window: int = 500,
    ) -> None:
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self.absolute_floor = absolute_floor or {}
        self.window = window
        self._rolling: dict[str, _Stats] = defaultdict(_Stats)
        self._recent: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._flagged: int = 0

    def observe(self, metric: str, value: float, *, floor: Optional[float] = None) -> AnomalyVerdict:
        stats = self._rolling[metric]
        verdict = AnomalyVerdict(
            detected=False, metric=metric, value=value, mean=stats.mean,
            stddev=stats.stddev, zscore=0.0,
        )
        effective_floor = floor if floor is not None else self.absolute_floor.get(metric, 0.0)
        if value < effective_floor:
            stats.observe(value)
            self._recent[metric].append(value)
            return verdict
        if stats.count >= self.min_samples and stats.stddev > 0:
            z = (value - stats.mean) / stats.stddev
            verdict.zscore = z
            if abs(z) >= self.z_threshold:
                verdict.detected = True
                verdict.reason = f"{metric} z={z:.1f} >= {self.z_threshold}"
                self._flagged += 1
        stats.observe(value)
        self._recent[metric].append(value)
        return verdict

    def percentile(self, metric: str, q: float) -> float:
        samples = sorted(self._recent.get(metric, []))
        if not samples:
            return 0.0
        idx = min(len(samples) - 1, max(0, int(q * (len(samples) - 1) + 0.5)))
        return samples[idx]

    def reset(self) -> None:
        self._rolling.clear()
        self._recent.clear()
        self._flagged = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "zThreshold": self.z_threshold,
            "minSamples": self.min_samples,
            "metrics": {
                metric: {
                    "count": stats.count,
                    "mean": round(stats.mean, 3),
                    "stddev": round(stats.stddev, 3),
                }
                for metric, stats in self._rolling.items()
            },
            "flagged": self._flagged,
        }


__all__ = ["LoopDetector", "AnomalyDetector", "LoopVerdict", "AnomalyVerdict", "Detector"]
