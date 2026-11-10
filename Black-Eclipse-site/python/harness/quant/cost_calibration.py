"""Calibrate execution assumptions from real fills.

A backtest that guesses 1 bp of slippage is not evidence. This module computes
the observed spread/slippage/commission from a fill set and returns explicit
assumptions a backtest can use.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def calibrate(fills: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [f for f in fills or [] if isinstance(f, dict)]
    slips: list[float] = []
    commissions: list[float] = []
    per_lot: list[float] = []
    adverse = 0
    for fill in rows:
        side = str(fill.get("side") or "").lower()
        price = _num(fill.get("price") or fill.get("avgPrice"))
        arrival = _num(fill.get("arrivalPrice") or fill.get("openPrice"))
        if price > 0 and arrival > 0:
            slip = (price - arrival) if side == "buy" else (arrival - price)
            bps = slip / arrival * 10_000.0
            slips.append(bps)
            if bps > 0:
                adverse += 1
        commission = _num(fill.get("commission"))
        volume = abs(_num(fill.get("volume")))
        if commission:
            commissions.append(commission)
            if volume > 0:
                per_lot.append(commission / volume)

    def pct(values: list[float], q: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return ordered[idx]

    mean_slip = statistics.fmean(slips) if slips else 0.0
    mean_commission = statistics.fmean(per_lot) if per_lot else 0.0
    return {
        "status": "OK" if rows else "UNAVAILABLE",
        "fills": len(rows),
        "pricedFills": len(slips),
        "slippageBps": {
            "mean": round(mean_slip, 4),
            "median": round(statistics.median(slips), 4) if slips else None,
            "p95": round(pct(slips, 0.95), 4) if slips else None,
            "worst": round(max(slips), 4) if slips else None,
            "adverseRate": round(adverse / len(slips), 4) if slips else 0.0,
        },
        "commission": {
            "meanPerLot": round(mean_commission, 4),
            "total": round(sum(commissions), 4),
        },
        "assumptions": {
            "slippage": {"type": "percentage", "value": round(abs(mean_slip) / 100.0, 6)},
            "commission": {"type": "percentage", "value": 0.0},
            "note": "Commission is broker-specific; use the observed per-lot value "
                    "when the engine supports a per-lot model.",
        },
        "note": "A fill set with no arrival price cannot measure slippage.",
    }


__all__ = ["calibrate"]
