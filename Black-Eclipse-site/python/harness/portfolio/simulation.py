"""Point-in-time rebalancing / walk-forward simulation (§30).

A rebalancing simulation that uses ONLY information available at each decision
timestamp: at every rebalance date the covariance (and optionally expected
returns) is re-estimated from the trailing window of returns up to (and
including) that date — never from future data. Holdings drift between
rebalances, turnover and transaction costs are charged at each rebalance, and
the resulting net equity curve is reported with risk metrics.

This is deliberately not a market-timing engine: it runs a deterministic,
reproducible construction method on a schedule and reports what would have
happened, including when a rebalance could not be built (infeasible).
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import numpy as np

from . import construction as C
from .estimation import estimate_covariance
from .risk import annualized_volatility, max_drawdown, sharpe, TRADING_DAYS

SCHEDULES = {"monthly": 21, "quarterly": 63, "semiannual": 126, "annual": 252}


def _align(price_series: dict[str, Sequence[dict[str, Any]]]) -> tuple[list[str], list[str], np.ndarray]:
    prepared: dict[str, dict[str, float]] = {}
    for symbol, rows in price_series.items():
        values = {}
        for row in rows or []:
            date = row.get("date") or row.get("timestamp")
            close = row.get("close", row.get("value"))
            if date is not None and close is not None:
                try:
                    price = float(close)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    values[str(date)] = price
        if values:
            prepared[symbol] = values
    symbols = sorted(prepared)
    if not symbols:
        return [], [], np.empty((0, 0))
    common = set(prepared[symbols[0]])
    for s in symbols:
        common &= set(prepared[s])
    dates = sorted(common)
    if len(dates) < 3:
        return symbols, [], np.empty((0, 0))
    matrix = np.array([[prepared[s][d] for s in symbols] for d in dates], dtype=float)
    return symbols, dates, matrix


def rebalancing_simulation(
    price_series: dict[str, Sequence[dict[str, Any]]],
    *,
    schedule: str = "quarterly",
    method: str = "risk_parity",
    constraints_payload: Optional[dict[str, Any]] = None,
    lookback: int = 252,
    initial_capital: float = 1.0,
    cost_rate: float = 0.0,
    expected_returns_by_step: Optional[dict[int, dict[str, float]]] = None,
    cancel_event: Any = None,
    progress: Optional[Any] = None,
    time_budget_s: Optional[float] = None,
) -> dict[str, Any]:
    """Simulate scheduled rebalancing with point-in-time estimation.

    `cancel_event` / `progress` / `time_budget_s` let the Execution Fabric run
    this as a cancellable, bounded background job without changing the result.
    """
    import time as _time

    started = _time.monotonic()
    if schedule not in SCHEDULES:
        return {"available": False, "reason": f"unknown schedule {schedule!r}; use {list(SCHEDULES)}"}
    symbols, dates, prices = _align(price_series)
    if not symbols:
        return {"available": False, "reason": "no usable price series"}
    n, n_symbols = prices.shape[0], len(symbols)
    if n < 2:
        return {"available": False, "reason": "fewer than two common price dates"}
    step = SCHEDULES[schedule]
    returns = prices[1:] / prices[:-1] - 1.0  # (T, N); return t uses dates[t]->dates[t+1]
    t_len = returns.shape[0]
    window = min(lookback, max(20, t_len // 2))
    if t_len <= window:
        return {"available": False, "reason": "history is too short for the requested lookback",
                "observations": t_len, "lookback": window}

    constraints_payload = dict(constraints_payload or {})
    decision_indices = set(range(window, t_len, step))
    nav = float(initial_capital)
    equity = [nav]
    events: list[dict[str, Any]] = []
    period_returns: list[float] = []
    current_weights: Optional[np.ndarray] = None

    def build_target(t: int) -> Optional[np.ndarray]:
        # Only returns STRICTLY BEFORE t are used: no look-ahead.
        hist = {symbols[i]: returns[:t, i].tolist() for i in range(n_symbols)}
        cov = estimate_covariance(hist, method="sample")
        if not cov.get("available"):
            return None
        er = None
        if expected_returns_by_step and t in expected_returns_by_step:
            mapping = expected_returns_by_step[t]
            er = [mapping.get(s) for s in symbols]
            if any(v is None for v in er):
                er = None
        result = C.construct(
            symbols=symbols, method=method, covariance=cov["covariance"],
            constraints_payload={**constraints_payload,
                                 "current_weights": {symbols[i]: float(current_weights[i])
                                                     for i in range(n_symbols)}
                                 if current_weights is not None else None},
            expected_returns=er, risk_aversion=1.0)
        if not result.get("weights"):
            return None
        return np.array([float(result["weights"][s]) for s in symbols])

    total_steps = max(1, t_len - window)
    for t in range(window, t_len):
        if cancel_event is not None and cancel_event.is_set():
            return {"available": False, "status": "cancelled", "reason": "cancelled"}
        if time_budget_s is not None and (_time.monotonic() - started) > time_budget_s:
            return {"available": False, "status": "timed_out", "reason": "time budget exceeded"}
        if progress is not None and t % 20 == 0:
            try:
                progress((t - window) / total_steps, "simulating rebalances")
            except Exception:  # noqa: BLE001
                pass
        prev_nav = nav
        # 1) Rebalance at time t using ONLY information available at t, BEFORE the
        #    t→t+1 return is earned (so the new weights earn the next period).
        if current_weights is None or t in decision_indices:
            target = build_target(t)
            if target is not None:
                if current_weights is None:
                    turnover = gross_traded = 1.0
                else:
                    turnover = 0.5 * float(np.abs(target - current_weights).sum())
                    gross_traded = float(np.abs(target - current_weights).sum())
                cost = cost_rate * gross_traded * nav
                nav -= cost
                current_weights = target
                events.append({"date": dates[t], "step": t, "turnover": round(turnover, 8),
                               "grossTraded": round(gross_traded, 8), "cost": round(cost, 10)})
        # 2) Earn the return from date t to t+1 and let holdings drift.
        if current_weights is not None:
            gross = float((current_weights * (1 + returns[t])).sum())
            if gross > 0:
                nav *= gross
                current_weights = current_weights * (1 + returns[t]) / gross
        period_returns.append(nav / prev_nav - 1.0 if prev_nav > 0 else 0.0)
        equity.append(nav)

    eq = np.array(equity, dtype=float)
    rets = list(np.diff(eq) / eq[:-1]) if len(eq) > 1 else []
    return {
        "available": True,
        "schedule": schedule,
        "method": method,
        "lookback": window,
        "rebalances": len(events),
        "initialCapital": initial_capital,
        "finalValue": round(float(eq[-1]), 10),
        "totalReturn": round(float(eq[-1] / eq[0] - 1.0), 10),
        "annualizedVolatility": _r(annualized_volatility(rets)),
        "sharpe": _r(sharpe(rets)),
        "maxDrawdown": _r(max_drawdown(eq.tolist())),
        "totalTurnover": round(sum(e["turnover"] for e in events), 8),
        "totalCostFraction": round(sum(e["cost"] for e in events), 10),
        "events": events,
        "equityCurve": [round(float(x), 8) for x in eq],
        "methodology": {
            "estimation": "sample covariance of the trailing window at each decision date",
            "noLookAhead": True,
            "drift": "holdings drift with realized returns between rebalances",
            "costs": f"{cost_rate} × gross traded notional per rebalance",
        },
    }


def _r(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 8)


__all__ = ["rebalancing_simulation", "SCHEDULES"]
