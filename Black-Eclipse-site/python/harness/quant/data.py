"""Market-data adapter + point-in-time dataset for the quant engine.

The engine never talks to a provider. `MarketDataGateway` normalizes provider
payloads into `HistoricalPriceSeries`; this module turns those into the
engine's array-backed `BarSeries`/`MarketDataset` and enforces the data-quality
and point-in-time guarantees the backtester relies on:

  * timestamps are sorted ascending and de-duplicated (last write wins, warned),
  * every bar carries a `data_available_at` (its close time) — the engine only
    ever exposes a bar once its close has occurred,
  * gaps (missing bars) are recorded as warnings, never silently forward-filled,
  * higher-timeframe series are aligned to the primary timeline using *closed*
    bars only (the core anti-lookahead guarantee for multi-timeframe),
  * incomplete/duplicate/out-of-order rows are reported, not hidden.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from .errors import (
    CorruptDataset,
    InsufficientHistory,
    InvalidSymbol,
    MissingData,
    UnsupportedTimeframe,
)

# Interval string → seconds. The single source of truth for bar duration.
INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800, "1mo": 2592000,
}
# Bars per year, for annualizing metrics. Crypto (24/7) uses calendar days.
BARS_PER_YEAR: dict[str, float] = {
    "1m": 365 * 24 * 60, "5m": 365 * 24 * 12, "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2, "1h": 365 * 24, "4h": 365 * 6,
    "1d": 365, "1w": 52, "1mo": 12,
}


def interval_seconds(interval: str) -> int:
    if interval not in INTERVAL_SECONDS:
        raise UnsupportedTimeframe(f"unsupported interval {interval!r}",
                                   detail={"supported": sorted(INTERVAL_SECONDS)})
    return INTERVAL_SECONDS[interval]


def bars_per_year(interval: str) -> float:
    return BARS_PER_YEAR.get(interval, 365.0)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise CorruptDataset(f"unparseable timestamp {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class DataFinding:
    kind: str          # duplicate | out_of_order | gap | incomplete | missing_value | timezone
    severity: str      # info | warning | error
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "detail": self.detail}


@dataclass
class BarSeries:
    """One symbol's OHLCV history as aligned arrays. Timestamps ascending, UTC."""

    symbol: str
    interval: str
    timestamps: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    tz: str = "UTC"
    source: str = "unknown"
    exchange: Optional[str] = None
    asset_type: Optional[str] = None
    # Optional per-bar absolute bid/ask spread (price units). Present only when
    # the source supplied it; the execution simulator's `historical` spread model
    # uses it. None = not available (the engine then warns, never assumes zero).
    spread: Optional[np.ndarray] = None
    data_available_at: list[str] = field(default_factory=list)
    findings: list[DataFinding] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("open", "high", "low", "close", "volume"):
            arr = getattr(self, name)
            setattr(self, name, np.asarray(arr, dtype=float))
        if self.spread is not None:
            self.spread = np.asarray(self.spread, dtype=float)
        if not self.data_available_at:
            seconds = interval_seconds(self.interval)
            times = [_parse_ts(ts) for ts in self.timestamps]
            self.data_available_at = [
                _iso(dt.replace(microsecond=0) + _timedelta(seconds)) for dt in times
            ]

    @property
    def length(self) -> int:
        return len(self.timestamps)

    @property
    def interval_seconds(self) -> int:
        return interval_seconds(self.interval)

    def ohlcv(self) -> dict[str, np.ndarray]:
        return {
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
        }

    def available_mask(self) -> np.ndarray:
        """datetime64 array of each bar's availability (close) time."""
        return np.array([np.datetime64(_parse_ts(ts).replace(tzinfo=None))
                         for ts in self.data_available_at], dtype="datetime64[s]")

    def timestamps_dt(self) -> np.ndarray:
        return np.array([np.datetime64(_parse_ts(ts).replace(tzinfo=None))
                         for ts in self.timestamps], dtype="datetime64[s]")

    def to_dict(self, limit: Optional[int] = None) -> dict[str, Any]:
        n = self.length if limit is None else min(limit, self.length)
        return {
            "symbol": self.symbol, "interval": self.interval, "tz": self.tz,
            "source": self.source, "assetType": self.asset_type, "length": self.length,
            "start": self.timestamps[0] if self.length else None,
            "end": self.timestamps[-1] if self.length else None,
            "findings": [f.to_dict() for f in self.findings],
        }


def _timedelta(seconds: int):
    from datetime import timedelta

    return timedelta(seconds=seconds)


# ── Builders ─────────────────────────────────────────────────────────────────

def series_from_rows(
    symbol: str,
    interval: str,
    rows: list[dict[str, Any]],
    *,
    tz: str = "UTC",
    source: str = "unknown",
    exchange: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> BarSeries:
    """Normalize raw OHLCV rows into a clean, sorted, deduped BarSeries.

    Rows are dicts with `timestamp` (or `date`/`time`) and open/high/low/close/
    volume. Blank close rows are dropped with a warning; duplicate timestamps
    keep the last occurrence; out-of-order rows are sorted.
    """
    findings: list[DataFinding] = []
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        ts_raw = row.get("timestamp") or row.get("date") or row.get("time")
        if ts_raw is None:
            findings.append(DataFinding("incomplete", "warning", {"reason": "missing timestamp"}))
            continue
        try:
            dt = _parse_ts(ts_raw)
        except CorruptDataset as exc:
            findings.append(DataFinding("incomplete", "warning", {"reason": str(exc)}))
            continue
        close = row.get("close")
        if close is None:
            findings.append(DataFinding("missing_value", "warning",
                                        {"timestamp": _iso(dt), "field": "close"}))
            continue
        parsed.append((dt, row))

    if not parsed:
        raise MissingData(f"no usable bars for {symbol}")

    parsed.sort(key=lambda item: item[0])
    seen: dict[datetime, dict[str, Any]] = {}
    duplicates = 0
    for dt, row in parsed:
        if dt in seen:
            duplicates += 1
        seen[dt] = row
    if duplicates:
        findings.append(DataFinding("duplicate", "warning", {"count": duplicates}))

    ordered = sorted(seen.items(), key=lambda item: item[0])
    seconds = interval_seconds(interval)
    gap_count = 0
    prev: Optional[datetime] = None
    out_of_order = 0
    for dt, _ in parsed:
        if prev is not None and dt < prev:
            out_of_order += 1
        prev = dt
    if out_of_order:
        findings.append(DataFinding("out_of_order", "warning", {"count": out_of_order}))

    timestamps: list[str] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    spreads: list[float] = []
    available: list[str] = []
    prev = None
    for dt, row in ordered:
        if prev is not None and (dt - prev).total_seconds() > seconds * 1.5:
            gap_count += 1
        prev = dt
        close = float(row.get("close"))
        timestamps.append(_iso(dt))
        opens.append(float(row["open"]) if row.get("open") is not None else close)
        highs.append(float(row["high"]) if row.get("high") is not None else close)
        lows.append(float(row["low"]) if row.get("low") is not None else close)
        closes.append(close)
        volumes.append(float(row.get("volume") or 0.0))
        spread_raw = row.get("spread")
        spreads.append(float(spread_raw) if spread_raw is not None else float("nan"))
        available.append(_iso(dt + _timedelta(seconds)))
    if gap_count:
        findings.append(DataFinding("gap", "warning", {"count": gap_count, "interval": interval}))

    spread_arr = np.array(spreads, dtype=float) if any(s == s for s in spreads) else None
    return BarSeries(
        symbol=symbol, interval=interval, timestamps=timestamps,
        open=np.array(opens), high=np.array(highs), low=np.array(lows),
        close=np.array(closes), volume=np.array(volumes), tz=tz, source=source,
        exchange=exchange, asset_type=asset_type, spread=spread_arr,
        data_available_at=available, findings=findings,
    )


def series_from_historical(payload: Any) -> BarSeries:
    """Adapt a gateway `HistoricalPriceSeries` (or its dict) into a BarSeries."""
    if isinstance(payload, dict):
        meta = payload.get("meta") or {}
        rows = payload.get("bars") or payload.get("series") or []
        interval = payload.get("interval") or "1d"
        symbol = meta.get("symbol") or payload.get("symbol") or "?"
        return series_from_rows(
            symbol, interval, rows, tz="UTC",
            source=meta.get("provider") or meta.get("source") or "gateway",
            exchange=meta.get("exchange"), asset_type=meta.get("asset_type"),
        )
    # pydantic HistoricalPriceSeries
    meta = getattr(payload, "meta", None)
    rows = [bar.model_dump() if hasattr(bar, "model_dump") else dict(bar)
            for bar in getattr(payload, "bars", [])]
    symbol = getattr(meta, "symbol", None) or "?"
    interval = getattr(payload, "interval", None) or "1d"
    return series_from_rows(
        symbol, interval, rows, tz="UTC",
        source=getattr(meta, "provider", None) or "gateway",
        exchange=getattr(meta, "exchange", None),
        asset_type=getattr(meta, "asset_type", None),
    )


@dataclass
class MarketDataset:
    """A multi-symbol, optionally multi-timeframe dataset for one backtest.

    `series` maps symbol → primary BarSeries. `higher` maps (symbol, tf) →
    BarSeries. The engine iterates the union of primary timestamps across all
    symbols and only exposes each bar when it has closed.
    """

    series: dict[str, BarSeries]
    higher: dict[tuple[str, str], BarSeries] = field(default_factory=dict)
    lower: dict[tuple[str, str], BarSeries] = field(default_factory=dict)

    def symbols(self) -> list[str]:
        return sorted(self.series.keys())

    def primary_interval(self) -> str:
        intervals = {s.interval for s in self.series.values()}
        if len(intervals) != 1:
            raise CorruptDataset("all primary series must share one interval",
                                 detail={"intervals": sorted(intervals)})
        return next(iter(intervals))

    def timeline(self) -> list[str]:
        """The merged, ascending union of all primary timestamps."""
        stamps: set[str] = set()
        for s in self.series.values():
            stamps.update(s.timestamps)
        return sorted(stamps)

    def findings(self) -> list[DataFinding]:
        out: list[DataFinding] = []
        for s in self.series.values():
            out.extend(s.findings)
        for s in self.higher.values():
            out.extend(s.findings)
        return out

    def slice_by_timestamps(self, start_ts: str, end_ts: str) -> "MarketDataset":
        """A new dataset restricted to primary bars in [start_ts, end_ts].

        Higher-timeframe series are filtered to the same time range (used by
        walk-forward so a training window never sees a test bar, and vice versa).
        """
        series: dict[str, BarSeries] = {}
        for sym, s in self.series.items():
            sliced = slice_series(s, start_ts, end_ts)
            if sliced is not None:
                series[sym] = sliced
        higher: dict[tuple[str, str], BarSeries] = {}
        for key, s in self.higher.items():
            sliced = slice_series(s, start_ts, end_ts)
            if sliced is not None:
                higher[key] = sliced
        return MarketDataset(series=series, higher=higher)

    def require_min_bars(self, minimum: int) -> None:
        for sym, s in self.series.items():
            if s.length < minimum:
                raise InsufficientHistory(
                    f"{sym} has {s.length} bars; at least {minimum} are required",
                    detail={"symbol": sym, "have": s.length, "need": minimum},
                )


def align_higher_to_primary(
    higher: BarSeries, primary_timestamps: list[str], primary_interval: str
) -> np.ndarray:
    """For each primary bar, the index of the last *closed* higher-TF bar.

    A higher-TF bar is available to a primary bar only when the higher bar's
    close (`data_available_at`) is at or before the primary bar's close. Returns
    an int array of length len(primary_timestamps); -1 means "not yet available".
    This is the single guard against multi-timeframe lookahead.
    """
    if higher.length == 0:
        return np.full(len(primary_timestamps), -1, dtype=int)
    seconds = interval_seconds(primary_interval)
    primary_close = np.array(
        [(np.datetime64(_parse_ts(ts).replace(tzinfo=None)) + np.timedelta64(seconds, "s"))
         for ts in primary_timestamps], dtype="datetime64[s]"
    )
    higher_avail = higher.available_mask()
    out = np.full(len(primary_timestamps), -1, dtype=int)
    for i, close_t in enumerate(primary_close):
        # last higher index whose availability <= primary close
        idx = int(np.searchsorted(higher_avail, close_t, side="right")) - 1
        out[i] = idx
    return out


def build_dataset(
    series: dict[str, BarSeries],
    higher: Optional[dict[tuple[str, str], BarSeries]] = None,
) -> MarketDataset:
    if not series:
        raise MissingData("a dataset needs at least one symbol")
    return MarketDataset(series=series, higher=higher or {})


def slice_series(series: BarSeries, start_ts: str, end_ts: str) -> Optional[BarSeries]:
    """Slice a BarSeries to timestamps in [start_ts, end_ts] (inclusive). None if empty."""
    keep = [i for i, ts in enumerate(series.timestamps) if start_ts <= ts <= end_ts]
    if not keep:
        return None
    timestamps = [series.timestamps[i] for i in keep]
    return BarSeries(
        symbol=series.symbol, interval=series.interval, timestamps=timestamps,
        open=series.open[keep], high=series.high[keep], low=series.low[keep],
        close=series.close[keep], volume=series.volume[keep], tz=series.tz,
        source=series.source, exchange=series.exchange, asset_type=series.asset_type,
        spread=None if series.spread is None else series.spread[keep],
        data_available_at=[series.data_available_at[i] for i in keep], findings=[],
    )


__all__ = [
    "BARS_PER_YEAR",
    "BarSeries",
    "DataFinding",
    "INTERVAL_SECONDS",
    "MarketDataset",
    "align_higher_to_primary",
    "bars_per_year",
    "build_dataset",
    "interval_seconds",
    "series_from_historical",
    "series_from_rows",
]
