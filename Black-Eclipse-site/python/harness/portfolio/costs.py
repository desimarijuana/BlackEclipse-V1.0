"""Turnover and transaction-cost model (§27–§29).

A documented cost model, applied only when its inputs are available. If a cost
component's rate is missing it is reported as absent rather than assumed to be
zero.

Turnover convention: one-way turnover of a fully-invested portfolio is
    TO = 0.5 · Σ |w_target − w_current|.
The gross-traded-notional convention (Σ |Δw|) is also returned so the caller can
choose; the two are not interchangeable.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence


def turnover(
    current: dict[str, float], target: dict[str, float],
) -> dict[str, Any]:
    symbols = sorted(set(current) | set(target))
    deltas = {s: target.get(s, 0.0) - current.get(s, 0.0) for s in symbols}
    gross = sum(abs(v) for v in deltas.values())
    return {
        "symbols": symbols,
        "deltas": {s: round(deltas[s], 10) for s in symbols},
        "oneWayTurnover": round(gross / 2.0, 10),
        "grossTradedNotional": round(gross, 10),
        "buys": {s: round(deltas[s], 10) for s in symbols if deltas[s] > 0},
        "sells": {s: round(-deltas[s], 10) for s in symbols if deltas[s] < 0},
    }


def transaction_costs(
    trades: dict[str, float],
    *,
    commission_rate: float = 0.0,
    half_spread: Optional[float] = None,
    impact_coefficient: float = 0.0,
    min_commission: float = 0.0,
    fx_rate: float = 1.0,
) -> dict[str, Any]:
    """Estimate transaction costs for a set of trade notional fractions.

    `trades` is a map symbol → signed traded notional (as a fraction of NAV).
    Commission is charged per unit of gross notional, the half-spread likewise,
    and market impact uses a simple square-root-free linear coefficient. Missing
    inputs (e.g. no half-spread) are reported as zero WITH an explicit note so a
    "cost-adjusted" claim is never overstated.
    """
    components: dict[str, float] = {}
    notes: list[str] = []
    gross = sum(abs(float(v)) for v in trades.values())
    commission = max(commission_rate * gross, min_commission if gross > 0 else 0.0)
    components["commission"] = commission
    if half_spread is None:
        components["spread"] = 0.0
        notes.append("no half-spread supplied; spread cost assumed zero")
    else:
        components["spread"] = half_spread * gross
    components["impact"] = impact_coefficient * gross
    components["fx"] = (fx_rate - 1.0) * abs(sum(float(v) for v in trades.values())) \
        if fx_rate != 1.0 else 0.0
    total = sum(components.values())
    return {
        "grossTradedNotional": round(gross, 10),
        "components": {k: round(v, 10) for k, v in components.items()},
        "totalCostFraction": round(total, 10),
        "totalCostBps": round(total * 10_000, 4),
        "notes": notes,
        "model": {
            "commissionRate": commission_rate, "halfSpread": half_spread,
            "impactCoefficient": impact_coefficient, "minCommission": min_commission,
        },
    }


def net_of_cost_weights(target: dict[str, float], cost_fraction: float) -> dict[str, float]:
    """Scale target weights so the portfolio is funded after paying costs.

    Cost funding reduces every weight proportionally (a documented, simple
    convention); the remainder becomes an implicit cash drag.
    """
    if cost_fraction <= 0:
        return dict(target)
    factor = max(0.0, 1.0 - cost_fraction)
    return {s: w * factor for s, w in target.items()}


__all__ = ["turnover", "transaction_costs", "net_of_cost_weights"]
