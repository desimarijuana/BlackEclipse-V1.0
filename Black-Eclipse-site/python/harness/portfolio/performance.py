"""Performance analytics — TWR, MWR/IRR, CAGR, cumulative and benchmark (§25).

Returns are dimensionless statistics computed in float; the money that feeds
them comes from the exact Decimal ledger. A metric that cannot be computed is
returned as None with a reason, never a substituted zero.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

from .risk import returns_from_prices, _stdev, TRADING_DAYS


def cumulative_return(nav: Sequence[float]) -> Optional[float]:
    if len(nav) < 2 or nav[0] == 0:
        return None
    return nav[-1] / nav[0] - 1.0


def cagr(begin: float, end: float, years: float) -> Optional[float]:
    if begin <= 0 or years <= 0:
        return None
    return (end / begin) ** (1.0 / years) - 1.0


def time_weighted_return(values: Sequence[float], flows: Sequence[float]) -> Optional[float]:
    """TWR from an end-of-period value series and external net cash flows.

    `values[i]` is the portfolio value at the end of period i; `flows[i]` is the
    net external contribution at that point (deposits +, withdrawals −). The
    period return removes the flow so the manager's return is not distorted by
    the investor's funding decisions.
    """
    if len(values) < 2:
        return None
    twr = 1.0
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev <= 0:
            return None
        flow = flows[i] if i < len(flows) else 0.0
        sub = (values[i] - flow) / prev - 1.0
        twr *= (1.0 + sub)
    return twr - 1.0


def _npv(rate: float, flows: Sequence[float]) -> float:
    return sum(f / ((1.0 + rate) ** i) for i, f in enumerate(flows))


def irr(flows: Sequence[float], *, period_years: float = 1.0) -> Optional[float]:
    """Money-weighted periodic IRR by bisection. `flows[0]` is typically negative.

    `period_years` converts the per-period rate to an annualized rate.
    """
    if len(flows) < 2:
        return None
    if all(f >= 0 for f in flows) or all(f <= 0 for f in flows):
        return None
    lo, hi = -0.9999, 10.0
    f_lo, f_hi = _npv(lo, flows), _npv(hi, flows)
    if f_lo * f_hi > 0:
        # No sign change in the bracket: the true IRR lies outside the search.
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, flows)
        if abs(f_mid) < 1e-9:
            lo = hi = mid
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    per_period = (lo + hi) / 2.0
    if period_years == 1.0:
        return per_period
    return (1.0 + per_period) ** (1.0 / period_years) - 1.0


def money_weighted_return(nav: Sequence[float], flows: Sequence[float],
                          *, periods_per_year: int = TRADING_DAYS) -> Optional[float]:
    """MWR (IRR) from a NAV series and the external flows that occurred."""
    if len(nav) < 2:
        return None
    cash_flows = [-nav[0]]
    for i in range(1, len(nav)):
        flow = flows[i] if i < len(flows) else 0.0
        # A withdrawal is a positive return to the investor; a contribution negative.
        cash_flows.append(-flow)
        if i == len(nav) - 1:
            cash_flows[-1] += nav[i]
    return irr(cash_flows, period_years=1.0 / periods_per_year)


def tracking_error(portfolio_returns: Sequence[float], benchmark_returns: Sequence[float],
                   periods: int = TRADING_DAYS) -> Optional[float]:
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 2:
        return None
    active = [portfolio_returns[i] - benchmark_returns[i] for i in range(n)]
    sd = _stdev(active)
    return None if sd is None else sd * math.sqrt(periods)


def information_ratio(portfolio_returns: Sequence[float], benchmark_returns: Sequence[float],
                      periods: int = TRADING_DAYS) -> Optional[float]:
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 2:
        return None
    active = [portfolio_returns[i] - benchmark_returns[i] for i in range(n)]
    sd = _stdev(active)
    mean = sum(active) / n
    if sd is None or sd == 0:
        return None
    return (mean * periods) / (sd * math.sqrt(periods))


def benchmark_compare(portfolio_nav: Sequence[float], benchmark_nav: Sequence[float],
                      periods: int = TRADING_DAYS) -> dict[str, Any]:
    if len(portfolio_nav) < 2 or len(benchmark_nav) < 2:
        return {"available": False, "reason": "insufficient NAV series"}
    pr = returns_from_prices(portfolio_nav)
    br = returns_from_prices(benchmark_nav)
    n = min(len(pr), len(br))
    return {
        "available": True,
        "portfolioReturn": cumulative_return(portfolio_nav),
        "benchmarkReturn": cumulative_return(benchmark_nav),
        "excessReturn": (
            (cumulative_return(portfolio_nav) or 0.0) - (cumulative_return(benchmark_nav) or 0.0)
        ),
        "trackingError": tracking_error(pr[:n], br[:n], periods),
        "informationRatio": information_ratio(pr[:n], br[:n], periods),
        "observations": n,
    }


def compute_performance(
    *,
    nav: Sequence[float],
    flows: Optional[Sequence[float]] = None,
    benchmark_nav: Optional[Sequence[float]] = None,
    years: Optional[float] = None,
    periods: int = TRADING_DAYS,
) -> dict[str, Any]:
    nav = list(nav)
    if len(nav) < 2:
        return {
            "status": "UNAVAILABLE",
            "reason": "need at least two portfolio snapshots to compute performance",
            "metrics": {},
        }
    flows = list(flows or [0.0] * len(nav))
    returns = returns_from_prices(nav)
    metrics: dict[str, Any] = {
        "cumulativeReturn": cumulative_return(nav),
        "dailyReturns": [round(r, 8) for r in returns],
        "timeWeightedReturn": time_weighted_return(nav, flows),
        "moneyWeightedReturn": money_weighted_return(nav, flows, periods_per_year=periods),
    }
    if years and years > 0:
        metrics["cagr"] = cagr(nav[0], nav[-1], years)
    else:
        metrics["cagr"] = cagr(nav[0], nav[-1], len(nav) / periods) if len(nav) > 1 else None
    if benchmark_nav:
        metrics["benchmark"] = benchmark_compare(nav, benchmark_nav, periods)
    return {"status": "OK", "metrics": metrics, "observations": len(nav)}


__all__ = [
    "compute_performance",
    "cumulative_return",
    "cagr",
    "irr",
    "time_weighted_return",
    "money_weighted_return",
    "benchmark_compare",
    "tracking_error",
    "information_ratio",
]
