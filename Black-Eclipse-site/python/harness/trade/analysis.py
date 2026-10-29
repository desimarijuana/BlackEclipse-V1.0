"""Deterministic bar statistics for a trade bracket.

These functions are pure and tiny on purpose: the model should not compute an
ATR in its head, and a stop placed on a guessed volatility is worse than no stop.
The broker's own bars are the input (`broker_bars`); nothing here invents a
series or extrapolates one.
"""

from __future__ import annotations

from typing import Any


def true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    """True range per bar (first bar uses high-low, as MT5 conventions go)."""
    out: list[float] = []
    previous: float | None = None
    for bar in bars:
        high = float(bar.get("high") or 0)
        low = float(bar.get("low") or 0)
        close = float(bar.get("close") or 0)
        if previous is None:
            out.append(max(high - low, 0.0))
        else:
            out.append(max(high - low, abs(high - previous), abs(low - previous)))
        previous = close
    return out


def atr(bars: list[dict[str, Any]], period: int = 14) -> float | None:
    """Simple average of the last `period` true ranges, or None if too short."""
    if not bars or period <= 0:
        return None
    ranges = true_ranges(bars)
    window = ranges[-period:]
    if len(window) < period:
        return None
    return sum(window) / period


def bar_summary(
    bars: list[dict[str, Any]], period: int = 14, lookback: int = 20,
) -> dict[str, Any]:
    """The handful of facts a bracket needs, computed from the series."""
    if not bars:
        return {}
    last = bars[-1]
    window = bars[-max(1, lookback):]
    highs = [float(bar.get("high") or 0) for bar in window]
    lows = [float(bar.get("low") or 0) for bar in window]
    closes = [float(bar.get("close") or 0) for bar in bars]
    change_pct = None
    if len(closes) >= 2 and closes[-2]:
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100.0
    return {
        "lastClose": float(last.get("close") or 0),
        "lastHigh": float(last.get("high") or 0),
        "lastLow": float(last.get("low") or 0),
        "changePct": round(change_pct, 4) if change_pct is not None else None,
        "atr": round(value, 6) if (value := atr(bars, period)) is not None else None,
        "atrPeriod": period,
        "lookbackHigh": max(highs) if highs else None,
        "lookbackLow": min(lows) if lows else None,
        "lookback": len(window),
    }


__all__ = ["atr", "bar_summary", "true_ranges"]
