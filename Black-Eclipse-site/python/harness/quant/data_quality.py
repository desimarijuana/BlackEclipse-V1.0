"""Data quality gate for the quant system.

A backtest is only as good as its bars. This module classifies the problems a
quant must see before trusting a series:

- exact duplicates;
- conflicting duplicates (same timestamp, different values);
- non-positive prices;
- invalid OHLC relationships;
- missing bars against the inferred interval;
- weekend/session gaps (reported separately, not silently filled).

It never repairs data. It reports. The caller decides, and a critical finding
blocks promotion.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

_INTERVAL_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800,
}


def _ts(row: dict[str, Any]) -> Optional[datetime]:
    raw = row.get("ts") or row.get("timestamp") or row.get("date") or row.get("time")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value > 1e11:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(k) for k in ("open", "high", "low", "close", "volume"))


def inspect_bars(
    rows: Iterable[dict[str, Any]], *, interval: str = "1d",
    symbol: str = "",
) -> dict[str, Any]:
    """Return a deterministic quality report for one series."""
    data = [dict(row) for row in rows or [] if isinstance(row, dict)]
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    missing_ts = 0
    for row in data:
        when = _ts(row)
        if when is None:
            missing_ts += 1
            continue
        parsed.append((when, row))
    parsed.sort(key=lambda item: item[0])

    timestamps = [item[0] for item in parsed]
    exact_duplicates = 0
    conflicts: list[dict[str, Any]] = []
    seen: dict[datetime, dict[str, Any]] = {}
    for when, row in parsed:
        if when in seen:
            if _key(seen[when]) == _key(row):
                exact_duplicates += 1
            else:
                conflicts.append({
                    "ts": when.isoformat(),
                    "first": _key(seen[when]),
                    "second": _key(row),
                })
        else:
            seen[when] = row

    non_positive = 0
    invalid_ohlc = 0
    for row in data:
        o, h, l, c = (_num(row.get(k)) for k in ("open", "high", "low", "close"))
        if any(v is not None and v <= 0 for v in (o, h, l, c)):
            non_positive += 1
        if all(v is not None for v in (o, h, l, c)):
            if h < max(o, c, l) or l > min(o, c, h) or h < l:
                invalid_ohlc += 1

    gaps: list[dict[str, Any]] = []
    expected = _INTERVAL_SECONDS.get(interval)
    if expected and len(timestamps) > 2:
        deltas = [(timestamps[i] - timestamps[i - 1]).total_seconds()
                  for i in range(1, len(timestamps))]
        observed = sorted(d for d in deltas if d > 0)
        step = observed[len(observed) // 2] if observed else expected
        step = step or expected
        for i in range(1, len(timestamps)):
            delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if delta > step * 1.5:
                missing = max(0, int(round(delta / step)) - 1)
                weekend = False
                if interval in ("1d", "1w"):
                    weekday = timestamps[i - 1].weekday()
                    weekend = weekday == 4 and timestamps[i].weekday() == 0
                gaps.append({
                    "from": timestamps[i - 1].isoformat(),
                    "to": timestamps[i].isoformat(),
                    "missingBars": missing,
                    "classification": "weekend" if weekend else "market_or_provider_gap",
                })

    real_gaps = [g for g in gaps if g["classification"] != "weekend"]
    expected_bars = len(timestamps) + sum(g["missingBars"] for g in real_gaps)
    gap_ratio = (sum(g["missingBars"] for g in real_gaps) / expected_bars
                 if expected_bars else 0.0)
    critical: list[str] = []
    if exact_duplicates:
        critical.append(f"{exact_duplicates} exact duplicate bars")
    if conflicts:
        critical.append(f"{len(conflicts)} conflicting duplicate bars")
    if non_positive:
        critical.append(f"{non_positive} non-positive prices")
    if invalid_ohlc:
        critical.append(f"{invalid_ohlc} invalid OHLC bars")
    if missing_ts:
        critical.append(f"{missing_ts} bars without a timestamp")
    if gap_ratio > 0.02:
        critical.append(f"gap ratio {gap_ratio:.2%} is above 2%")

    canonical = json.dumps(
        [{"ts": t.isoformat(), "o": r.get("open"), "h": r.get("high"),
          "l": r.get("low"), "c": r.get("close"), "v": r.get("volume")}
         for t, r in parsed],
        sort_keys=True, default=str,
    )
    return {
        "status": "OK",
        "symbol": symbol,
        "interval": interval,
        "bars": len(data),
        "first": timestamps[0].isoformat() if timestamps else None,
        "last": timestamps[-1].isoformat() if timestamps else None,
        "exactDuplicates": exact_duplicates,
        "conflictingDuplicates": conflicts[:20],
        "gaps": gaps[:200],
        "gapRatio": round(gap_ratio, 6),
        "nonPositive": non_positive,
        "invalidOhlc": invalid_ohlc,
        "missingTimestamps": missing_ts,
        "critical": critical,
        "contentHash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "gate": {
            "allowed": not critical,
            "reasons": critical,
            "note": "Repair is a separate, explicit step. This report never edits data.",
        },
    }


def inspect_dataset(dataset: Any, *, symbols: Iterable[str] | None = None,
                    interval: str | None = None) -> dict[str, Any]:
    """Inspect every series in a `MarketDataset` and return one gated report."""
    reports: dict[str, Any] = {}
    selected = [str(s).upper() for s in (symbols or list(getattr(dataset, "series", {}) or {}))]
    for symbol in selected:
        series = getattr(dataset, "series", {}).get(symbol)
        if series is None:
            continue
        rows = []
        for i in range(getattr(series, "length", 0)):
            rows.append({
                "ts": series.timestamps[i],
                "open": float(series.open[i]), "high": float(series.high[i]),
                "low": float(series.low[i]), "close": float(series.close[i]),
                "volume": float(series.volume[i]),
            })
        reports[symbol] = inspect_bars(
            rows, interval=interval or getattr(series, "interval", "1d"),
            symbol=symbol,
        )
    critical = {symbol: report["critical"] for symbol, report in reports.items()
                if report.get("critical")}
    return {
        "status": "OK",
        "reports": reports,
        "critical": critical,
        "gate": {"allowed": not critical,
                 "reasons": [f"{s}: {', '.join(r)}" for s, r in critical.items()]},
    }


def repair_bars(rows: Iterable[dict[str, Any]], *, interval: str = "1d",
                symbol: str = "") -> dict[str, Any]:
    """Drop exact duplicates and keep the first row of a conflict.

    The repair is explicit and reported. It never invents a missing bar.
    """
    before = inspect_bars(rows, interval=interval, symbol=symbol)
    seen: dict[datetime, dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    removed_exact = 0
    conflicted = 0
    for row in rows or []:
        when = _ts(row)
        if when is None:
            continue
        if when in seen:
            if _key(seen[when]) == _key(row):
                removed_exact += 1
            else:
                conflicted += 1
            continue
        seen[when] = row
        kept.append(dict(row))
    kept.sort(key=lambda r: _ts(r))
    after = inspect_bars(kept, interval=interval, symbol=symbol)
    return {
        "status": "OK",
        "rows": kept,
        "removedExact": removed_exact,
        "conflictsKeptFirst": conflicted,
        "before": before,
        "after": after,
        "note": "Gaps are not filled. A conflict keeps the first row and is counted.",
    }


def require_clean(report: dict[str, Any]) -> None:
    """Raise a named error when the data cannot be trusted for promotion."""
    gate = report.get("gate") or {}
    if gate.get("allowed"):
        return
    from .errors import QuantError

    error = QuantError(
        "the dataset has critical findings; repair it or record an explicit override",
        detail={"reasons": gate.get("reasons") or []},
    )
    error.code = "DATA_QUALITY_BLOCKED"
    raise error


def compare_series(
    left: Iterable[dict[str, Any]], right: Iterable[dict[str, Any]],
    *, label: str = "broker parity",
) -> dict[str, Any]:
    """Compare two series by timestamp: overlap, price mismatch and skew."""
    def index(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            when = _ts(row)
            if when is not None:
                out[when.isoformat()] = row
        return out

    a, b = index(left), index(right)
    common = sorted(set(a) & set(b))
    mismatches: list[dict[str, Any]] = []
    for key in common:
        ca, cb = _num(a[key].get("close")), _num(b[key].get("close"))
        if ca is None or cb is None or cb == 0:
            continue
        diff = abs(ca - cb) / abs(cb)
        if diff > 1e-6:
            mismatches.append({"ts": key, "left": ca, "right": cb,
                               "relativeDiff": diff})
    return {
        "label": label,
        "leftBars": len(a),
        "rightBars": len(b),
        "overlapBars": len(common),
        "missingLeft": len(set(b) - set(a)),
        "missingRight": len(set(a) - set(b)),
        "priceMismatches": len(mismatches),
        "mismatches": mismatches[:20],
        "parity": (len(common) - len(mismatches)) / len(common) if common else 0.0,
    }


__all__ = ["compare_series", "inspect_bars", "inspect_dataset",
           "repair_bars", "require_clean"]
