"""Metrics — counters, gauges and histograms with a Prometheus exposition.

A small, thread-safe, dependency-free registry. The `MetricsRegistry` owns
metric families keyed by name+labels; the hub records into it from HookEvents.
`render_prometheus()` emits the text exposition format for scraping.

Histograms keep count/sum/min/max plus a bounded reservoir so P50/P95/P99 can be
computed without an unbounded memory cost. RED (Rate/Errors/Duration) and USE
(Utilization/Saturation/Errors) helpers build the standard families.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

_BUCKETS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000)
_RESERVOIR = 2048


def _key(labels: Optional[dict[str, str]]) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _fmt_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels)
    return "{" + inner + "}"


@dataclass
class _HistogramData:
    count: int = 0
    total: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf
    reservoir: list[float] = field(default_factory=list)
    buckets: dict[float, int] = field(default_factory=lambda: {b: 0 for b in _BUCKETS})

    def observe(self, value: float) -> None:
        value = float(value)
        self.count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        for b in _BUCKETS:
            if value <= b:
                self.buckets[b] += 1
        self.reservoir.append(value)
        if len(self.reservoir) > _RESERVOIR:
            del self.reservoir[: len(self.reservoir) - _RESERVOIR]

    def quantile(self, q: float) -> float:
        if not self.reservoir:
            return 0.0
        samples = sorted(self.reservoir)
        idx = min(len(samples) - 1, max(0, int(q * (len(samples) - 1) + 0.5)))
        return samples[idx]


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._histograms: dict[str, dict[tuple[tuple[str, str], ...], _HistogramData]] = defaultdict(dict)
        self._help: dict[str, str] = {}
        self._started = time.time()

    # ── record ──────────────────────────────────────────────────────────────
    def inc_counter(self, name: str, amount: float = 1.0, labels: Optional[dict[str, str]] = None, help_text: str = "") -> None:
        with self._lock:
            if help_text:
                self._help.setdefault(name, help_text)
            key = _key(labels)
            self._counters[name][key] = self._counters[name].get(key, 0.0) + float(amount)

    def set_gauge(self, name: str, value: float, labels: Optional[dict[str, str]] = None, help_text: str = "") -> None:
        with self._lock:
            if help_text:
                self._help.setdefault(name, help_text)
            self._gauges[name][_key(labels)] = float(value)

    def inc_gauge(self, name: str, amount: float = 1.0, labels: Optional[dict[str, str]] = None) -> None:
        with self._lock:
            key = _key(labels)
            self._gauges[name][key] = self._gauges[name].get(key, 0.0) + float(amount)

    def observe_histogram(self, name: str, value: float, labels: Optional[dict[str, str]] = None, help_text: str = "") -> None:
        with self._lock:
            if help_text:
                self._help.setdefault(name, help_text)
            key = _key(labels)
            bucket = self._histograms[name].get(key)
            if bucket is None:
                bucket = _HistogramData()
                self._histograms[name][key] = bucket
            bucket.observe(value)

    # ── RED / USE helpers ───────────────────────────────────────────────────
    def red(self, prefix: str, *, rate: float = 1.0, errors: float = 0.0, duration_ms: float = 0.0, labels: Optional[dict[str, str]] = None) -> None:
        self.inc_counter(f"{prefix}_requests_total", rate, labels)
        if errors:
            self.inc_counter(f"{prefix}_errors_total", errors, labels)
        if duration_ms:
            self.observe_histogram(f"{prefix}_duration_ms", duration_ms, labels)

    def use(self, prefix: str, *, utilization: float, saturation: float, errors: float = 0.0, labels: Optional[dict[str, str]] = None) -> None:
        self.set_gauge(f"{prefix}_utilization", utilization, labels)
        self.set_gauge(f"{prefix}_saturation", saturation, labels)
        if errors:
            self.inc_counter(f"{prefix}_errors_total", errors, labels)

    # ── read ────────────────────────────────────────────────────────────────
    def counter_value(self, name: str, labels: Optional[dict[str, str]] = None) -> float:
        with self._lock:
            if labels is None:
                return sum(self._counters.get(name, {}).values())
            return self._counters.get(name, {}).get(_key(labels), 0.0)

    def gauge_value(self, name: str, labels: Optional[dict[str, str]] = None) -> Optional[float]:
        with self._lock:
            series = self._gauges.get(name)
            if not series:
                return None
            if labels is None:
                return series.get((), 0.0) if () in series else sum(series.values())
            return series.get(_key(labels))

    def histogram_stats(self, name: str, labels: Optional[dict[str, str]] = None) -> dict[str, Any]:
        with self._lock:
            series = self._histograms.get(name)
            if not series:
                return {"count": 0, "p50Ms": 0, "p95Ms": 0, "p99Ms": 0, "avgMs": 0, "maxMs": 0}
            buckets = [_key(labels)] if labels is not None else list(series.keys())
            agg = _HistogramData()
            for key in buckets:
                data = series.get(key)
                if data is None:
                    continue
                agg.count += data.count
                agg.total += data.total
                agg.minimum = min(agg.minimum, data.minimum)
                agg.maximum = max(agg.maximum, data.maximum)
                agg.reservoir.extend(data.reservoir)
            if not agg.count:
                return {"count": 0, "p50Ms": 0, "p95Ms": 0, "p99Ms": 0, "avgMs": 0, "maxMs": 0}
            agg.reservoir = sorted(agg.reservoir)
            return {
                "count": agg.count,
                "p50Ms": round(agg.quantile(0.50), 2),
                "p95Ms": round(agg.quantile(0.95), 2),
                "p99Ms": round(agg.quantile(0.99), 2),
                "avgMs": round(agg.total / agg.count, 2),
                "maxMs": round(agg.maximum, 2) if agg.maximum != -math.inf else 0,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "uptimeSeconds": round(time.time() - self._started, 1),
                "counters": {
                    name: {_fmt_labels(k) or "": v for k, v in series.items()}
                    for name, series in self._counters.items()
                },
                "gauges": {
                    name: {_fmt_labels(k) or "": v for k, v in series.items()}
                    for name, series in self._gauges.items()
                },
                "histograms": {
                    name: {
                        _fmt_labels(k) or "": {
                            "count": d.count,
                            "avgMs": round(d.total / d.count, 2) if d.count else 0,
                            "p95Ms": round(d.quantile(0.95), 2),
                            "maxMs": round(d.maximum, 2) if d.count else 0,
                        }
                        for k, d in series.items()
                    }
                    for name, series in self._histograms.items()
                },
            }

    def names(self) -> dict[str, list[str]]:
        with self._lock:
            return {
                "counters": sorted(self._counters),
                "gauges": sorted(self._gauges),
                "histograms": sorted(self._histograms),
            }

    # ── Prometheus exposition ───────────────────────────────────────────────
    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                help_text = self._help.get(name, name)
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                for key, value in sorted(series.items()):
                    lines.append(f"{name}{_fmt_labels(key)} {_num(value)}")
            for name, series in sorted(self._gauges.items()):
                help_text = self._help.get(name, name)
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
                for key, value in sorted(series.items()):
                    lines.append(f"{name}{_fmt_labels(key)} {_num(value)}")
            for name, series in sorted(self._histograms.items()):
                help_text = self._help.get(name, name)
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} histogram")
                for key, data in sorted(series.items()):
                    for b in _BUCKETS:
                        lines.append(f'{name}_bucket{_merge(key, ("le", _num(b)))} {data.buckets[b]}')
                    lines.append(f'{name}_bucket{_merge(key, ("le", "+Inf"))} {data.count}')
                    lines.append(f"{name}_sum{_fmt_labels(key)} {_num(data.total)}")
                    lines.append(f"{name}_count{_fmt_labels(key)} {data.count}")
        return "\n".join(lines) + "\n"


def _num(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(float(value))


def _merge(key: tuple[tuple[str, str], ...], extra: tuple[str, str]) -> str:
    merged = tuple(sorted((*key, extra)))
    return "{" + ",".join(f'{k}="{v}"' for k, v in merged) + "}"


__all__ = ["MetricsRegistry"]
