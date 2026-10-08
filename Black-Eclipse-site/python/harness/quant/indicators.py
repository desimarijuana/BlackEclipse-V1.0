"""Deterministic technical indicators.

Every function is **causal**: the value at index `i` is computed only from
values at indices `<= i`. The warm-up region is `NaN` (never a fabricated 0) so
a strategy can never act on an indicator that has not "warmed up". This is the
foundation of lookahead-bias safety — the engine additionally only exposes bars
whose close has occurred.

Implemented with numpy for speed. A fresh copy is returned for every call, so a
caller may mutate the result freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np


class IndicatorError(ValueError):
    pass


@dataclass(frozen=True)
class IndicatorSpec:
    """A declared indicator: `type` + params, optionally a custom `id`."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    source: Optional[str] = None

    def resolved_id(self) -> str:
        if self.id:
            return self.id
        parts = [self.type]
        for key in sorted(self.params):
            parts.append(str(self.params[key]))
        return "_".join(parts)


# ── Primitive building blocks ────────────────────────────────────────────────

def sma(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    if period <= 0:
        raise IndicatorError("sma period must be > 0")
    out = np.full(values.shape, np.nan, dtype=float)
    if values.shape[0] < period:
        return out
    csum = np.cumsum(np.insert(values.astype(float), 0, 0.0))
    out[period - 1:] = (csum[period:] - csum[:-period]) / period
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    if period <= 0:
        raise IndicatorError("ema period must be > 0")
    out = np.full(values.shape, np.nan, dtype=float)
    n = values.shape[0]
    if n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed = float(np.mean(values[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def rma(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (used by RSI and ATR)."""
    period = int(period)
    out = np.full(values.shape, np.nan, dtype=float)
    n = values.shape[0]
    if n < period:
        return out
    alpha = 1.0 / period
    seed = float(np.mean(values[:period]))
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def wma(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    out = np.full(values.shape, np.nan, dtype=float)
    n = values.shape[0]
    if n < period:
        return out
    weights = np.arange(1, period + 1, dtype=float)
    wsum = weights.sum()
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1].astype(float)
        out[i] = float(np.dot(window, weights) / wsum)
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = high.shape[0]
    tr = np.full(n, np.nan, dtype=float)
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        prev_close = close[i - 1]
        tr[i] = max(high[i] - low[i], abs(high[i] - prev_close), abs(low[i] - prev_close))
    return tr


def rsi(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return out
    delta = np.diff(values.astype(float))
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = rma(gains, period)
    avg_loss = rma(losses, period)
    for i in range(period, n):
        g = avg_gain[i - 1]
        l = avg_loss[i - 1]
        if np.isnan(g) or np.isnan(l):
            continue
        if l == 0:
            out[i] = 100.0
        else:
            rs = g / l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    tr = true_range(high, low, close)
    out = rma(tr[1:], period) if tr.shape[0] > 1 else np.full(1, np.nan)
    padded = np.full(high.shape[0], np.nan, dtype=float)
    padded[1:] = out
    return padded


def stddev(values: np.ndarray, period: int, ddof: int = 0) -> np.ndarray:
    period = int(period)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1].astype(float)
        out[i] = float(np.std(window, ddof=ddof))
    return out


def roc(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=float)
    for i in range(period, n):
        base = values[i - period]
        if base != 0:
            out[i] = (values[i] - base) / base * 100.0
    return out


def rolling_max(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=float)
    for i in range(period - 1, n):
        out[i] = float(np.max(values[i - period + 1:i + 1]))
    return out


def rolling_min(values: np.ndarray, period: int) -> np.ndarray:
    period = int(period)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=float)
    for i in range(period - 1, n):
        out[i] = float(np.min(values[i - period + 1:i + 1]))
    return out


# ── Source resolution ────────────────────────────────────────────────────────

_PRICE_SOURCES = {"open", "high", "low", "close", "hl2", "hlc3", "ohlc4"}


def _source_array(source: str, ohlcv: dict[str, np.ndarray]) -> np.ndarray:
    s = (source or "close").lower()
    if s == "open":
        return ohlcv["open"]
    if s == "high":
        return ohlcv["high"]
    if s == "low":
        return ohlcv["low"]
    if s == "close":
        return ohlcv["close"]
    if s == "volume":
        return ohlcv["volume"]
    if s == "hl2":
        return (ohlcv["high"] + ohlcv["low"]) / 2.0
    if s == "hlc3":
        return (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3.0
    if s == "ohlc4":
        return (ohlcv["open"] + ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 4.0
    raise IndicatorError(f"unknown price source {source!r}")


# ── Catalog ──────────────────────────────────────────────────────────────────

# type → (required params, optional params). Used by strategy validation so an
# unknown indicator or a bad parameter is rejected before a run starts.
INDICATOR_CATALOG: dict[str, dict[str, Any]] = {
    "sma": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "ema": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "wma": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "rma": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "rsi": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "atr": {"required": ["period"], "optional": [], "outputs": ["{id}"]},
    "stddev": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "roc": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "highest": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "lowest": {"required": ["period"], "optional": ["source"], "outputs": ["{id}"]},
    "bollinger": {
        "required": ["period"], "optional": ["num_std", "source"],
        "outputs": ["{id}_upper", "{id}_middle", "{id}_lower"],
    },
    "macd": {
        "required": [], "optional": ["fast", "slow", "signal", "source"],
        "outputs": ["{id}", "{id}_signal", "{id}_hist"],
    },
    "vwap": {"required": ["period"], "optional": [], "outputs": ["{id}"]},
}


def resolve_spec(spec: IndicatorSpec) -> IndicatorSpec:
    """Fill defaults and normalize an IndicatorSpec (its id + source)."""
    t = spec.type.lower()
    if t not in INDICATOR_CATALOG:
        raise IndicatorError(f"unknown indicator type {spec.type!r}")
    meta = INDICATOR_CATALOG[t]
    for req in meta["required"]:
        if req not in spec.params and not (t == "macd"):
            raise IndicatorError(f"{t} requires parameter {req!r}")
    params = dict(spec.params)
    if t == "macd":
        params.setdefault("fast", 12)
        params.setdefault("slow", 26)
        params.setdefault("signal", 9)
    if t == "bollinger":
        params.setdefault("num_std", 2.0)
    source = spec.source or params.get("source")
    return IndicatorSpec(type=t, params=params, id=spec.id, source=source)


def compute_one(spec: IndicatorSpec, ohlcv: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Compute one indicator into a dict of output-key → array."""
    s = resolve_spec(spec)
    base = s.resolved_id()
    t = s.type
    p = s.params
    out: dict[str, np.ndarray] = {}
    if t == "sma":
        out[base] = sma(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "ema":
        out[base] = ema(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "wma":
        out[base] = wma(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "rma":
        out[base] = rma(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "rsi":
        out[base] = rsi(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "atr":
        out[base] = atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], p["period"])
    elif t == "stddev":
        out[base] = stddev(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "roc":
        out[base] = roc(_source_array(s.source or "close", ohlcv), p["period"])
    elif t == "highest":
        out[base] = rolling_max(_source_array(s.source or "high", ohlcv), p["period"])
    elif t == "lowest":
        out[base] = rolling_min(_source_array(s.source or "low", ohlcv), p["period"])
    elif t == "bollinger":
        src = _source_array(s.source or "close", ohlcv)
        mid = sma(src, p["period"])
        sd = stddev(src, p["period"])
        k = float(p.get("num_std", 2.0))
        out[f"{base}_middle"] = mid
        out[f"{base}_upper"] = mid + k * sd
        out[f"{base}_lower"] = mid - k * sd
    elif t == "macd":
        src = _source_array(s.source or "close", ohlcv)
        fast = ema(src, p["fast"])
        slow = ema(src, p["slow"])
        macd_line = fast - slow
        signal = ema(np.nan_to_num(macd_line, nan=0.0), p["signal"])
        signal = np.where(np.isnan(macd_line), np.nan, signal)
        out[base] = macd_line
        out[f"{base}_signal"] = signal
        out[f"{base}_hist"] = macd_line - signal
    elif t == "vwap":
        period = int(p["period"])
        tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3.0
        vol = ohlcv["volume"]
        n = tp.shape[0]
        out[base] = np.full(n, np.nan, dtype=float)
        for i in range(period - 1, n):
            v = vol[i - period + 1:i + 1]
            pv = tp[i - period + 1:i + 1]
            tot = float(np.sum(v))
            if tot > 0:
                out[base][i] = float(np.sum(pv * v) / tot)
            else:
                out[base][i] = float(np.mean(pv))
    else:  # pragma: no cover - resolve_spec already rejects unknown types
        raise IndicatorError(f"unhandled indicator {t!r}")
    return out


def compute_indicators(
    specs: list[IndicatorSpec], ohlcv: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """Compute every declared indicator; keys are the resolvable output names.

    A duplicate output key is an error (ambiguous reference) — rejected rather
    than silently overwritten.
    """
    result: dict[str, np.ndarray] = {}
    for spec in specs:
        for key, arr in compute_one(spec, ohlcv).items():
            if key in result:
                raise IndicatorError(f"duplicate indicator output {key!r}")
            result[key] = arr
    return result


def output_keys(spec: IndicatorSpec) -> list[str]:
    """The exact output keys an indicator will produce (for rule validation)."""
    s = resolve_spec(spec)
    base = s.resolved_id()
    return [tpl.format(id=base) for tpl in INDICATOR_CATALOG[s.type]["outputs"]]


__all__ = [
    "IndicatorError",
    "IndicatorSpec",
    "INDICATOR_CATALOG",
    "atr",
    "compute_indicators",
    "compute_one",
    "ema",
    "output_keys",
    "resolve_spec",
    "rma",
    "roc",
    "rolling_max",
    "rolling_min",
    "rsi",
    "sma",
    "stddev",
    "true_range",
    "wma",
]
