"""Deterministic golden datasets for regression testing and offline research.

Every generator is seeded and reproducible: the same call yields byte-identical
OHLCV rows. They cover the regimes the spec names — bull, bear, sideways, gap,
high/low volatility, missing candle, duplicate candle, multiple symbols and
multiple timeframes (via `aggregate`).

These are *synthetic* fixtures for tests and demos. They are clearly not market
data and must never be presented as such: `source` is always `"synthetic"`.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _series(
    symbol: str,
    *,
    n: int,
    start: float,
    drift: float,
    vol: float,
    interval_min: int = 1440,
    seed: int = 7,
    start_time: Optional[datetime] = None,
) -> list[dict]:
    rng = random.Random(seed + sum(ord(c) for c in symbol))
    t0 = start_time or datetime(2023, 1, 1, tzinfo=timezone.utc)
    price = start
    rows: list[dict] = []
    for i in range(n):
        ts = t0 + timedelta(minutes=interval_min * i)
        ret = drift + rng.gauss(0.0, vol)
        o = price
        c = max(0.01, o * (1.0 + ret))
        hi = max(o, c) * (1.0 + abs(rng.gauss(0.0, vol / 2)))
        lo = min(o, c) * (1.0 - abs(rng.gauss(0.0, vol / 2)))
        v = 1000.0 + rng.uniform(0, 500)
        rows.append({
            "timestamp": _iso(ts), "open": round(o, 4), "high": round(hi, 4),
            "low": round(lo, 4), "close": round(c, 4), "volume": round(v, 2),
        })
        price = c
    return rows


def bull_market(symbol: str = "TESTUSDT", n: int = 300, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=0.003, vol=0.01, **kw)


def bear_market(symbol: str = "TESTUSDT", n: int = 300, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=-0.003, vol=0.012, **kw)


def sideways_market(symbol: str = "TESTUSDT", n: int = 300, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=0.0, vol=0.008, **kw)


def high_volatility(symbol: str = "TESTUSDT", n: int = 300, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=0.0, vol=0.05, **kw)


def low_volatility(symbol: str = "TESTUSDT", n: int = 300, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=0.0, vol=0.001, **kw)


def with_gap(symbol: str = "TESTUSDT", n: int = 300, *, gap_at: int = 150,
             gap_pct: float = 0.1, **kw) -> list[dict]:
    rows = bullish_flat(symbol, n=n, **kw)
    for row in rows[gap_at:]:
        factor = 1.0 + gap_pct
        for f in ("open", "high", "low", "close"):
            row[f] = round(row[f] * factor, 4)
    return rows


def bullish_flat(symbol: str, n: int, **kw) -> list[dict]:
    return _series(symbol, n=n, start=100.0, drift=0.001, vol=0.01, **kw)


def with_missing_candle(symbol: str = "TESTUSDT", n: int = 300, *, drop_at: int = 150) -> list[dict]:
    rows = _series(symbol, n=n, start=100.0, drift=0.001, vol=0.01)
    return rows[:drop_at] + rows[drop_at + 1:]


def with_duplicate_candle(symbol: str = "TESTUSDT", n: int = 300, *, dup_at: int = 150) -> list[dict]:
    rows = _series(symbol, n=n, start=100.0, drift=0.001, vol=0.01)
    return rows[:dup_at] + [dict(rows[dup_at])] + rows[dup_at:]


def multi_symbol(n: int = 300) -> dict[str, list[dict]]:
    return {
        "AAAUSDT": _series("AAAUSDT", n=n, start=50.0, drift=0.002, vol=0.012, seed=11),
        "BBBUSDT": _series("BBBUSDT", n=n, start=200.0, drift=-0.001, vol=0.02, seed=23),
    }


def aggregate(rows: list[dict], factor: int) -> list[dict]:
    """Aggregate `factor` consecutive bars into one (open/high/low/close/volume).

    Used to build a higher-timeframe series from a primary one in tests.
    """
    out: list[dict] = []
    for i in range(0, len(rows) - factor + 1, factor):
        chunk = rows[i:i + factor]
        out.append({
            "timestamp": chunk[0]["timestamp"],
            "open": chunk[0]["open"],
            "high": max(r["high"] for r in chunk),
            "low": min(r["low"] for r in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(r["volume"] for r in chunk),
        })
    return out


__all__ = [
    "aggregate",
    "bear_market",
    "bull_market",
    "bullish_flat",
    "high_volatility",
    "low_volatility",
    "multi_symbol",
    "sideways_market",
    "with_duplicate_candle",
    "with_gap",
    "with_missing_candle",
]
