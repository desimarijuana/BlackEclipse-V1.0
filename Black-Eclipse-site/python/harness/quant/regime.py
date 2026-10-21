"""Causal market-regime classification for the quant engine.

A *regime* is the state of the market at a point in time, described on two
independent axes:

  * **trend** — `up`, `down` or `flat`, measured as the distance between a fast
    and a slow exponential average **in ATR units**, so the measure is
    comparable across instruments and across volatility regimes;
  * **volatility** — `high`, `normal` or `low`, measured as realised volatility
    against its own trailing median.

Two properties are enforced here rather than assumed:

1. **Causality.** Every value at bar *i* is computed from bars *<= i* only. A
   regime label can therefore be attached to a trade that was taken at *i*
   without smuggling future information into it.
2. **Self-containment.** The regime comes from the same bars the backtest used
   — not a second vendor, not a separate macro series, not a hand-set label — so
   a regime attribution is reproducible from the stored artifact alone.

This module is deliberately separate from `robustness.py` and `montecarlo.py`:
those answer *how sensitive* the result is and *how uncertain* the distribution
is. This one answers **where the result came from** — which conditions carried
the edge and which conditions would have destroyed it.
"""

from __future__ import annotations

import math
import warnings as _warnings
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .errors import QuantError
from .indicators import atr as _atr
from .indicators import ema as _ema


class RegimeError(QuantError):
    code = "REGIME_ERROR"


TREND_LABELS: tuple[str, ...] = ("up", "down", "flat")
VOL_LABELS: tuple[str, ...] = ("high", "normal", "low")

UNKNOWN_REGIME = "unknown"


@dataclass(frozen=True)
class RegimeConfig:
    """Parameters of the classifier. Every one of them is a lookback."""

    fast: int = 20
    slow: int = 50
    atr_period: int = 14
    vol_period: int = 20
    vol_baseline: int = 100
    trend_threshold: float = 0.5      # ATR units
    high_vol_ratio: float = 1.5
    low_vol_ratio: float = 0.67

    def validate(self) -> None:
        if self.fast < 2:
            raise RegimeError(f"fast period must be >= 2, got {self.fast}")
        if self.slow <= self.fast:
            raise RegimeError(
                f"slow period ({self.slow}) must exceed fast period ({self.fast})")
        if self.atr_period < 2:
            raise RegimeError(f"atr_period must be >= 2, got {self.atr_period}")
        if self.vol_period < 2:
            raise RegimeError(f"vol_period must be >= 2, got {self.vol_period}")
        if self.vol_baseline < self.vol_period:
            raise RegimeError(
                f"vol_baseline ({self.vol_baseline}) must be >= vol_period "
                f"({self.vol_period})")
        if self.trend_threshold <= 0:
            raise RegimeError("trend_threshold must be > 0")
        if not (0.0 < self.low_vol_ratio < 1.0 < self.high_vol_ratio):
            raise RegimeError(
                "volatility ratios must satisfy 0 < low_vol_ratio < 1 < high_vol_ratio")

    @property
    def minimum_bars(self) -> int:
        return max(self.slow, self.atr_period + self.vol_period) + 1


@dataclass
class RegimeSeries:
    """Per-bar regime labels for one instrument."""

    symbol: str
    timestamps: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    trend: list[str] = field(default_factory=list)
    volatility: list[str] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)
    warmup_bars: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    def index_of(self, timestamp: Optional[str]) -> Optional[int]:
        """Exact timestamp lookup; `None` when the bar is not in this series."""
        if not timestamp:
            return None
        try:
            return self.timestamps.index(timestamp)
        except ValueError:
            return None

    def to_dict(self, *, include_series: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "symbol": self.symbol,
            "labels": self.labels,
            "trend": self.trend,
            "volatility": self.volatility,
            "confidence": [round(float(c), 4) for c in self.confidence],
            "warmupBars": self.warmup_bars,
            "counts": dict(self.counts),
            "axes": {"trend": list(TREND_LABELS), "volatility": list(VOL_LABELS)},
        }
        if include_series:
            data["timestamps"] = list(self.timestamps)
        return data


def _trailing_median(values: np.ndarray, window: int) -> np.ndarray:
    """Median of the trailing `window` observations ending at each index.

    NaN observations are ignored. A window with no finite observation yields
    NaN. The computation is chunked so a long series does not materialise the
    full sliding-window matrix at once.
    """
    n = int(values.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if n == 0 or window < 1:
        return out
    pad = np.concatenate([np.full(window - 1, np.nan), values.astype(float)])
    view = np.lib.stride_tricks.sliding_window_view(pad, window)
    chunk = max(1, 200_000 // max(1, window))
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", category=RuntimeWarning)
        for start in range(0, n, chunk):
            end = min(n, start + chunk)
            block = np.nanmedian(view[start:end], axis=1)
            out[start:end] = block
    return out


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Sample standard deviation over a trailing window (NaN before it fills)."""
    n = int(values.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if n < window or window < 2:
        return out
    sq = np.cumsum(values.astype(float) ** 2)
    sm = np.cumsum(values.astype(float))
    for i in range(window - 1, n):
        total = sq[i] - (sq[i - window] if i - window >= 0 else 0.0)
        total_sum = sm[i] - (sm[i - window] if i - window >= 0 else 0.0)
        var = (total - (total_sum ** 2) / window) / (window - 1)
        out[i] = float(math.sqrt(var)) if var > 0 else 0.0
    return out


def classify_series(
    symbol: str,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    timestamps: list[str],
    config: Optional[RegimeConfig] = None,
) -> RegimeSeries:
    """Classify every bar of one instrument into a trend/volatility regime."""
    cfg = config or RegimeConfig()
    cfg.validate()

    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    n = int(close.shape[0])
    if n < cfg.minimum_bars:
        raise RegimeError(
            f"{symbol}: need at least {cfg.minimum_bars} bars to classify a regime, "
            f"got {n}",
            detail={"symbol": symbol, "bars": n, "minimumBars": cfg.minimum_bars},
        )

    atr_arr = _atr(high, low, close, cfg.atr_period)
    ema_fast = _ema(close, cfg.fast)
    ema_slow = _ema(close, cfg.slow)

    log_returns = np.zeros(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = np.divide(close[1:], close[:-1], out=np.full(max(0, n - 1), np.nan),
                           where=close[:-1] != 0)
        log_returns[1:] = np.log(ratios)
    realised = _rolling_std(log_returns, cfg.vol_period)
    baseline = _trailing_median(realised, cfg.vol_baseline)

    trend: list[str] = []
    volatility: list[str] = []
    labels: list[str] = []
    confidence: list[float] = []
    counts: dict[str, int] = {}
    warmup = n

    for i in range(n):
        atr_i = float(atr_arr[i]) if i < atr_arr.size and np.isfinite(atr_arr[i]) else math.nan
        fast_i = float(ema_fast[i]) if np.isfinite(ema_fast[i]) else math.nan
        slow_i = float(ema_slow[i]) if np.isfinite(ema_slow[i]) else math.nan

        trend_label = "flat"
        trend_conf = 0.0
        if np.isfinite(atr_i) and atr_i > 0 and np.isfinite(fast_i) and np.isfinite(slow_i):
            score = (fast_i - slow_i) / atr_i
            if score > cfg.trend_threshold:
                trend_label = "up"
            elif score < -cfg.trend_threshold:
                trend_label = "down"
            trend_conf = min(1.0, abs(score) / cfg.trend_threshold)

        rv = float(realised[i]) if np.isfinite(realised[i]) else math.nan
        base = float(baseline[i]) if np.isfinite(baseline[i]) else math.nan
        vol_label = "normal"
        vol_conf = 0.0
        if np.isfinite(rv) and np.isfinite(base) and base > 0 and rv > 0:
            ratio = rv / base
            if ratio > cfg.high_vol_ratio:
                vol_label = "high"
            elif ratio < cfg.low_vol_ratio:
                vol_label = "low"
            vol_conf = min(1.0, abs(math.log(ratio)) / math.log(cfg.high_vol_ratio))

        label = f"{trend_label}_{vol_label}"
        trend.append(trend_label)
        volatility.append(vol_label)
        labels.append(label)
        confidence.append(round(0.6 * trend_conf + 0.4 * vol_conf, 4))
        counts[label] = counts.get(label, 0) + 1
        if warmup == n and trend_conf > 0.0 and np.isfinite(base):
            warmup = i

    return RegimeSeries(
        symbol=symbol,
        timestamps=[str(t) for t in timestamps[:n]],
        labels=labels,
        trend=trend,
        volatility=volatility,
        confidence=confidence,
        warmup_bars=warmup,
        counts=counts,
    )


def classify_dataset(dataset: Any, config: Optional[RegimeConfig] = None) -> dict[str, RegimeSeries]:
    """Classify every instrument of a dataset.

    An instrument whose series is too short is skipped rather than fatal: the
    caller decides what an unclassified instrument means.
    """
    out: dict[str, RegimeSeries] = {}
    series_map = getattr(dataset, "series", {}) or {}
    for symbol, series in series_map.items():
        try:
            out[symbol] = classify_series(
                symbol, series.high, series.low, series.close,
                list(series.timestamps), config)
        except RegimeError:
            continue
    return out


def label_trades(
    trades: list[dict[str, Any]],
    series_by_symbol: dict[str, RegimeSeries],
) -> tuple[list[Optional[str]], dict[str, Any]]:
    """Attach a regime label to each trade, using its entry bar.

    Returns the labels (aligned with `trades`; `None` where the trade could not
    be placed) and a placement report.
    """
    labels: list[Optional[str]] = []
    assigned = 0
    reasons: dict[str, int] = {}

    for trade in trades or []:
        symbol = str(trade.get("symbol") or "")
        series = series_by_symbol.get(symbol)
        if series is None:
            labels.append(None)
            reasons["symbol_not_classified"] = reasons.get("symbol_not_classified", 0) + 1
            continue
        entry_ts = trade.get("entryTs") or trade.get("entry_ts")
        index = series.index_of(entry_ts)
        if index is None:
            labels.append(None)
            reasons["entry_bar_not_found"] = reasons.get("entry_bar_not_found", 0) + 1
            continue
        labels.append(series.labels[index])
        assigned += 1

    report = {
        "assigned": assigned,
        "unassigned": len(labels) - assigned,
        "unassignedReasons": reasons,
        "instruments": sorted(series_by_symbol.keys()),
    }
    return labels, report


def attribute_regimes(
    trades: list[dict[str, Any]],
    labels: list[Optional[str]],
) -> dict[str, Any]:
    """Summarise realised P&L by regime.

    `pnlShare` is the regime's share of **gross positive** P&L, so a regime
    that only ever lost money cannot claim a positive share by accident.
    """
    buckets: dict[str, dict[str, Any]] = {}
    gross_positive = 0.0
    for trade, label in zip(trades or [], labels):
        if label is None:
            continue
        pnl = float(trade.get("netPnl") or trade.get("net_pnl") or 0.0)
        bucket = buckets.setdefault(label, {
            "trades": 0, "netPnl": 0.0, "wins": 0, "losses": 0,
            "grossPositive": 0.0, "best": None, "worst": None,
        })
        bucket["trades"] += 1
        bucket["netPnl"] += pnl
        if pnl > 0:
            bucket["wins"] += 1
            bucket["grossPositive"] += pnl
            gross_positive += pnl
        elif pnl < 0:
            bucket["losses"] += 1
        bucket["best"] = pnl if bucket["best"] is None else max(bucket["best"], pnl)
        bucket["worst"] = pnl if bucket["worst"] is None else min(bucket["worst"], pnl)

    out: dict[str, Any] = {}
    for label, bucket in sorted(buckets.items()):
        trades_n = int(bucket["trades"])
        net = float(bucket["netPnl"])
        gross_pos = float(bucket["grossPositive"])
        out[label] = {
            "trades": trades_n,
            "netPnl": round(net, 6),
            "avgPnl": round(net / trades_n, 6) if trades_n else None,
            "winRate": round(bucket["wins"] / trades_n * 100.0, 4) if trades_n else None,
            "grossPositivePnl": round(gross_pos, 6),
            "grossPositiveShare": round(
                gross_pos / gross_positive * 100.0, 4) if gross_positive > 0 else None,
            "best": bucket["best"],
            "worst": bucket["worst"],
        }
    return {
        "regimes": out,
        "grossPositivePnl": round(gross_positive, 6),
        "regimeCount": len(out),
    }


def regime_blocks(labels: list[Optional[str]]) -> list[list[int]]:
    """Split a labelled sequence into maximal runs of the same regime."""
    blocks: list[list[int]] = []
    current: list[int] = []
    current_label: Optional[str] = None
    for i, label in enumerate(labels):
        if label != current_label:
            if current:
                blocks.append(current)
            current = []
            current_label = label
        current.append(i)
    if current:
        blocks.append(current)
    return blocks


__all__ = [
    "RegimeConfig",
    "RegimeError",
    "RegimeSeries",
    "TREND_LABELS",
    "VOL_LABELS",
    "UNKNOWN_REGIME",
    "attribute_regimes",
    "classify_dataset",
    "classify_series",
    "label_trades",
    "regime_blocks",
]
