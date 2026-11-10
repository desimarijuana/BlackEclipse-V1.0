"""Capital allocation across strategies.

Allocation is by risk, not by equal notional. A strategy with higher volatility
gets less capital for the same risk budget. A cap prevents one strategy from
dominating the book.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else default
    except (TypeError, ValueError):
        return default


def risk_budget_weights(
    strategies: Iterable[dict[str, Any]], *,
    max_weight: float = 0.40, total_risk: float = 1.0,
) -> dict[str, Any]:
    rows = [dict(s) for s in strategies or []]
    if not rows:
        return {"available": False, "reason": "no strategies", "weights": {}}
    if not 0 < max_weight <= 1:
        raise ValueError("max_weight must be in (0, 1]")
    inverse: list[float] = []
    for strategy in rows:
        vol = _num(strategy.get("volatility"), 0.0)
        if vol <= 0:
            vol = 0.01
        inverse.append(1.0 / vol)
    total = sum(inverse)
    weights = [w / total for w in inverse]

    # Iterative cap + redistribute. Never returns more than max_weight.
    for _ in range(len(weights) * 4):
        overflow = sum(max(0.0, w - max_weight) for w in weights)
        if overflow <= 1e-12:
            break
        weights = [min(w, max_weight) for w in weights]
        room = [i for i, w in enumerate(weights) if w < max_weight - 1e-12]
        if not room:
            break
        base = sum(weights[i] for i in room)
        for i in room:
            weights[i] += overflow * (weights[i] / base if base else 1.0 / len(room))
    weights = [round(w, 8) for w in weights]
    return {
        "available": True,
        "weights": {str(r.get("strategyId") or r.get("id")): weights[i]
                    for i, r in enumerate(rows)},
        "totalRisk": total_risk,
        "maxWeight": max_weight,
        "sum": round(sum(weights), 8),
        "method": "inverse-volatility risk budgeting with a hard weight cap",
    }


def capital_for(equity: float, weights: dict[str, float],
                *, reserve_pct: float = 0.20) -> dict[str, Any]:
    if equity <= 0:
        return {"available": False, "reason": "equity must be positive", "capital": {}}
    if not 0 <= reserve_pct < 1:
        raise ValueError("reserve_pct must be in [0, 1)")
    investable = equity * (1.0 - reserve_pct)
    return {
        "available": True,
        "equity": equity,
        "reserve": equity * reserve_pct,
        "investable": investable,
        "capital": {name: round(investable * weight, 2)
                    for name, weight in weights.items()},
    }


def check_portfolio(weights: dict[str, float], *,
                    max_weight: float = 0.40, max_gross: float = 1.0) -> dict[str, Any]:
    values = [float(v) for v in weights.values()]
    gross = sum(abs(v) for v in values)
    largest = max(values) if values else 0.0
    checks = [
        {"check": "sum", "passed": abs(sum(values) - 1.0) <= 1e-6,
         "detail": f"sum={sum(values):.6f}"},
        {"check": "max_weight", "passed": largest <= max_weight + 1e-9,
         "detail": f"largest={largest:.4f} max={max_weight:g}"},
        {"check": "gross", "passed": gross <= max_gross + 1e-9,
         "detail": f"gross={gross:.4f} max={max_gross:g}"},
    ]
    failed = [c for c in checks if not c["passed"]]
    return {"allowed": not failed, "checks": checks,
            "reasons": [f"{c['check']}: {c['detail']}" for c in failed]}


__all__ = ["capital_for", "check_portfolio", "risk_budget_weights"]
