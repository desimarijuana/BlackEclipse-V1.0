"""Deterministic time-series transformations for research datasets.

Two operations, both pure and dependency-free, operating on a canonical row
shape (`{"timestamp", "open", "high", "low", "close", "volume"}`):

  * `resample_rows`   — convert OHLCV between intervals with documented,
                        deterministic aggregation semantics.
  * `align_rows`      — align one or more instruments onto a common timestamp
                        axis with an explicit join + an explicit (never implicit)
                        missing-value policy.

Design rules:
  * Open  = first valid observation in the bucket (by time).
  * High  = maximum valid high; Low = minimum valid low.
  * Close = last valid observation in the bucket (by time).
  * Volume= sum of valid volumes (None volumes are ignored, not zero-filled).
  * A bucket whose member count is below the expected count (derivable when both
    intervals are known) is marked `partial` — never silently treated as a full
    bar. Partial bars are how a resampled 1d bar built from 20 of 24 hours is kept
    honest.
  * Intraday prices are NEVER manufactured from daily data (a wider target than
    the source is rejected).
  * `align_rows` never forward-fills implicitly: the caller must pass
    `fill="ffill"`, a scalar, or omit it (missing stays None and is reported).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}
# Monthly is calendar-based; a single number of seconds is an approximation used
# only for the expected-member-count heuristic, never for bucketing.
_MONTH_APPROX_S = 30 * 86400


class TransformError(ValueError):
    """A transformation could not be applied safely (bad input, illegal widening)."""


def interval_seconds(interval: str) -> int:
    key = (interval or "").strip().lower()
    if key == "1mo":
        return _MONTH_APPROX_S
    secs = _INTERVAL_SECONDS.get(key)
    if secs is None:
        raise TransformError(f"unknown interval {interval!r}")
    return secs


def _parse_ts(ts: Any) -> _dt.datetime:
    text = str(ts).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise TransformError(f"unparseable timestamp {ts!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _bucket_start(dt: _dt.datetime, target: str) -> _dt.datetime:
    target = (target or "").strip().lower()
    if target == "1mo":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if target == "1w":
        # ISO week, Monday-anchored.
        monday = dt - _dt.timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    secs = interval_seconds(target)
    epoch = int(dt.timestamp())
    floored = (epoch // secs) * secs
    return _dt.datetime.fromtimestamp(floored, tz=_dt.timezone.utc)


def _iso(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def resample_rows(
    rows: list[dict[str, Any]],
    target_interval: str,
    *,
    source_interval: Optional[str] = None,
) -> dict[str, Any]:
    """Aggregate OHLCV rows into `target_interval` buckets.

    Returns `{"rows": [...], "metadata": {...}}`. Raises `TransformError` if the
    source interval is known and the target is finer (which would require
    manufacturing prices).
    """
    target = (target_interval or "").strip().lower()
    interval_seconds(target)  # validate

    if source_interval:
        src_s = interval_seconds(source_interval)
        tgt_s = interval_seconds(target)
        if tgt_s < src_s:
            raise TransformError(
                f"cannot resample {source_interval} -> {target}: intraday bars cannot "
                "be manufactured from a coarser source"
            )

    parsed: list[tuple[_dt.datetime, dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("timestamp") is None:
            continue
        parsed.append((_parse_ts(row["timestamp"]), row))
    parsed.sort(key=lambda pair: pair[0])

    buckets: dict[str, dict[str, Any]] = {}
    for dt, row in parsed:
        key = _iso(_bucket_start(dt, target))
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {"timestamp": key, "open": None, "high": None, "low": None,
                      "close": None, "volume": None, "count": 0}
            buckets[key] = bucket
        o, h, low, c, v = (_num(row.get("open")), _num(row.get("high")),
                           _num(row.get("low")), _num(row.get("close")),
                           _num(row.get("volume")))
        if bucket["open"] is None and o is not None:
            bucket["open"] = o
        if bucket["close"] is None or c is not None:
            if c is not None:
                bucket["close"] = c
        if h is not None:
            bucket["high"] = h if bucket["high"] is None else max(bucket["high"], h)
        if low is not None:
            bucket["low"] = low if bucket["low"] is None else min(bucket["low"], low)
        if v is not None:
            bucket["volume"] = v if bucket["volume"] is None else bucket["volume"] + v
        bucket["count"] += 1

    expected: Optional[int] = None
    if source_interval:
        src_s = interval_seconds(source_interval)
        tgt_s = interval_seconds(target)
        expected = max(1, tgt_s // src_s) if tgt_s >= src_s else 1

    out_rows: list[dict[str, Any]] = []
    for key in sorted(buckets):
        bucket = buckets[key]
        partial = False
        if expected is not None and bucket["count"] < expected:
            partial = True
        out_rows.append({
            "timestamp": bucket["timestamp"],
            "open": bucket["open"], "high": bucket["high"], "low": bucket["low"],
            "close": bucket["close"], "volume": bucket["volume"],
            "bars": bucket["count"], "partial": partial,
        })

    metadata = {
        "sourceInterval": source_interval,
        "targetInterval": target,
        "inputBars": len(parsed),
        "outputBars": len(out_rows),
        "expectedBarsPerBucket": expected,
        "partialBuckets": sum(1 for r in out_rows if r["partial"]),
        "aggregation": "open=first, high=max, low=min, close=last, volume=sum",
        "timezone": "UTC",
    }
    return {"rows": out_rows, "metadata": metadata}


def align_rows(
    series: dict[str, list[dict[str, Any]]],
    *,
    join: str = "inner",
    column: str = "close",
    fill: Optional[Any] = None,
) -> dict[str, Any]:
    """Align instruments onto a common timestamp axis.

    `join` is `inner` (timestamps present in every series) or `outer` (the union).
    `fill` controls missing values: `None` (default — missing stays null and is
    counted), `"ffill"` (carry the previous value forward), or a scalar numeric
    fill. An explicit `"ffill"` is the ONLY way forward-filling happens; the
    caller opts in.
    """
    join = (join or "inner").strip().lower()
    if join not in ("inner", "outer"):
        raise TransformError(f"align join must be 'inner' or 'outer', got {join!r}")
    if fill not in (None, "ffill") and not isinstance(fill, (int, float)):
        raise TransformError("align fill must be None, 'ffill', or a number")

    maps: dict[str, dict[str, Optional[float]]] = {}
    for symbol, rows in series.items():
        m: dict[str, Optional[float]] = {}
        for row in rows or []:
            if not isinstance(row, dict) or row.get("timestamp") is None:
                continue
            m[_iso(_parse_ts(row["timestamp"]))] = _num(row.get(column))
        maps[symbol] = m

    symbols = list(maps.keys())
    if not symbols:
        return {"timestamps": [], "series": {}, "missing": {}, "join": join, "column": column}

    sets = [set(maps[s].keys()) for s in symbols]
    axis: set[str] = set.intersection(*sets) if join == "inner" else set.union(*sets)
    timestamps = sorted(axis)

    aligned: dict[str, list[Optional[float]]] = {}
    missing: dict[str, int] = {}
    for symbol in symbols:
        values: list[Optional[float]] = []
        last: Optional[float] = fill if isinstance(fill, (int, float)) else None
        miss = 0
        for ts in timestamps:
            val = maps[symbol].get(ts)
            if val is None:
                if fill == "ffill":
                    val = last
                elif isinstance(fill, (int, float)):
                    val = float(fill)
                if val is None:
                    miss += 1
            else:
                last = val
            values.append(val)
        aligned[symbol] = values
        missing[symbol] = miss

    return {
        "timestamps": timestamps,
        "series": aligned,
        "missing": missing,
        "join": join,
        "column": column,
        "fill": fill if fill == "ffill" else (float(fill) if isinstance(fill, (int, float)) else None),
        "imputed": fill is not None,
    }


__all__ = ["TransformError", "align_rows", "interval_seconds", "resample_rows"]
