"""Live monitoring: signal parity, drift and P&L attribution.

These are measurements, not verdicts. They tell an operator where the live
result differs from the expected result and which condition carried the P&L.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def signal_parity(
    backtest_signals: Iterable[dict[str, Any]],
    live_signals: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Compare signal timelines by bar timestamp and signal name."""
    def index(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in rows or []:
            ts = str(row.get("ts") or row.get("bar") or row.get("barTs") or "")
            if ts:
                out[ts] = str(row.get("signal") or row.get("action") or "none")
        return out

    expected, actual = index(backtest_signals), index(live_signals)
    common = sorted(set(expected) & set(actual))
    mismatched = [{"ts": ts, "expected": expected[ts], "actual": actual[ts]}
                  for ts in common if expected[ts] != actual[ts]]
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    matched = len(common) - len(mismatched)
    return {
        "expectedBars": len(expected),
        "liveBars": len(actual),
        "overlap": len(common),
        "matched": matched,
        "mismatched": mismatched[:50],
        "missingInLive": missing[:50],
        "extraInLive": extra[:50],
        "parity": matched / len(expected) if expected else 0.0,
        "note": "A missing live signal is not a failed trade; it is a parity gap.",
    }


def drift(
    baseline: dict[str, Any], recent: dict[str, Any],
    *, tolerances: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Measure recent metrics against a baseline with explicit tolerances."""
    tol = {
        "sharpe": 0.5, "winRate": 0.15, "expectancy": 0.3,
        "tradeCount": 0.5, "costBps": 5.0,
        **(tolerances or {}),
    }
    rows: list[dict[str, Any]] = []
    flags: list[str] = []
    for name, limit in tol.items():
        before = _num(baseline.get(name))
        after = _num(recent.get(name))
        delta = after - before
        relative = abs(delta) / abs(before) if before else (0.0 if after == 0 else 1.0)
        breached = abs(delta) > limit
        rows.append({"metric": name, "baseline": before, "recent": after,
                     "delta": delta, "relative": relative, "tolerance": limit,
                     "breached": breached})
        if breached:
            flags.append(f"{name} moved {delta:+.3f} (tolerance {limit:g})")
    return {
        "status": "DRIFT" if flags else "OK",
        "metrics": rows,
        "flags": flags,
        "note": "A drift flag is a reason to review, not an automatic stop.",
    }


def attribution(trades: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """P&L by symbol, side and regime, with concentration."""
    rows = list(trades or [])
    total = sum(_num(t.get("pnl") or t.get("netPnl") or t.get("profit")) for t in rows)

    def group(key: str) -> dict[str, Any]:
        out: dict[str, dict[str, Any]] = {}
        for trade in rows:
            name = str(trade.get(key) or "unclassified")
            bucket = out.setdefault(name, {"trades": 0, "pnl": 0.0, "wins": 0})
            bucket["trades"] += 1
            pnl = _num(trade.get("pnl") or trade.get("netPnl") or trade.get("profit"))
            bucket["pnl"] += pnl
            bucket["wins"] += 1 if pnl > 0 else 0
        for bucket in out.values():
            bucket["pnl"] = round(bucket["pnl"], 6)
            bucket["winRate"] = bucket["wins"] / bucket["trades"] if bucket["trades"] else 0.0
        return out

    positive = sorted((abs(_num(t.get("pnl") or t.get("netPnl") or t.get("profit")))
                       for t in rows if _num(t.get("pnl") or t.get("netPnl")
                                             or t.get("profit")) > 0), reverse=True)
    top_share = (sum(positive[:3]) / sum(positive)) if positive else 0.0
    return {
        "trades": len(rows),
        "totalPnl": round(total, 6),
        "bySymbol": group("symbol"),
        "bySide": group("side"),
        "byRegime": group("regime"),
        "top3PositiveShare": top_share,
        "concentrated": top_share > 0.6,
        "note": "A concentrated P&L can be a streak, not an edge.",
    }


__all__ = ["attribution", "drift", "signal_parity"]
