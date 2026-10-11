"""Deterministic portfolio risk calculators (§24).

Every metric is a real, documented computation. When an input is insufficient
(fewer than two observations, no benchmark, no history) the metric is `None`
with a reason — never a fabricated zero. Returns/volatility/ratios are
dimensionless statistics, so float is appropriate; money never appears here.

Methods:
  * volatility    — sample stdev of returns × √periods (annualized)
  * Sharpe        — (mean excess return) / volatility, annualized
  * Sortino       — (mean excess return) / downside deviation
  * max drawdown  — peak-to-trough on the NAV curve
  * VaR / CVaR    — historical (empirical) and parametric (normal), plus a
                    seeded Monte Carlo simulation (reproducible, not fake)
  * beta / correlation — vs a benchmark series
  * concentration — Herfindahl-Hirschman index + top-N weight
"""

from __future__ import annotations

import math
import random
from typing import Any, Optional, Sequence

TRADING_DAYS = 252


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _stdev(xs: Sequence[float], ddof: int = 1) -> Optional[float]:
    n = len(xs)
    if n <= ddof:
        return None
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - ddof)
    return math.sqrt(var)


def returns_from_prices(prices: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            out.append(prices[i] / prices[i - 1] - 1.0)
    return out


def annualized_volatility(returns: Sequence[float], periods: int = TRADING_DAYS) -> Optional[float]:
    sd = _stdev(returns)
    return None if sd is None else sd * math.sqrt(periods)


def sharpe(returns: Sequence[float], risk_free: float = 0.0, periods: int = TRADING_DAYS) -> Optional[float]:
    sd = _stdev(returns)
    mean = _mean(returns)
    if sd is None or mean is None or sd == 0:
        return None
    annual_ret = mean * periods
    annual_vol = sd * math.sqrt(periods)
    return (annual_ret - risk_free) / annual_vol if annual_vol else None


def sortino(returns: Sequence[float], risk_free: float = 0.0, periods: int = TRADING_DAYS) -> Optional[float]:
    if len(returns) < 2:
        return None
    mean = _mean(returns)
    if mean is None:
        return None
    target = risk_free / periods
    downside = [min(0.0, r - target) ** 2 for r in returns]
    # Sample downside deviation (n-1), matching the frequency-aware convention in
    # `quant/metrics.py` so the same named metric agrees across modules.
    dd = math.sqrt(sum(downside) / (len(returns) - 1))
    if dd == 0:
        return None
    annual_ret = mean * periods
    annual_dd = dd * math.sqrt(periods)
    return (annual_ret - risk_free) / annual_dd if annual_dd else None


def max_drawdown(nav: Sequence[float]) -> Optional[float]:
    if len(nav) < 2:
        return None
    peak = nav[0]
    mdd = 0.0
    for value in nav:
        if value > peak:
            peak = value
        if peak > 0:
            dd = value / peak - 1.0
            if dd < mdd:
                mdd = dd
    return mdd


def historic_var(returns: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    if len(returns) < 2:
        return None
    ordered = sorted(returns)
    idx = max(0, min(len(ordered) - 1, int(math.floor((1 - confidence) * len(ordered)))))
    return ordered[idx]


def cvar(returns: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    if len(returns) < 2:
        return None
    var = historic_var(returns, confidence)
    if var is None:
        return None
    tail = [r for r in returns if r <= var]
    return sum(tail) / len(tail) if tail else var


def parametric_var(returns: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    mean = _mean(returns)
    sd = _stdev(returns)
    if mean is None or sd is None or sd == 0:
        return None
    z = _norm_ppf(1 - confidence)
    return mean + z * sd


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def monte_carlo_var(
    returns: Sequence[float], confidence: float = 0.95, *, simulations: int = 10_000,
    horizon: int = 1, seed: int = 12345,
) -> Optional[float]:
    """A genuine seeded simulation drawing from N(mean, sd) of daily returns.

    Deterministic for a fixed seed, so results are reproducible and auditable.
    """
    mean = _mean(returns)
    sd = _stdev(returns)
    if mean is None or sd is None or sd == 0 or simulations <= 0:
        return None
    rng = random.Random(seed)
    simulated: list[float] = []
    for _ in range(simulations):
        cum = 0.0
        for _ in range(max(1, horizon)):
            cum += rng.gauss(mean, sd)
        simulated.append(cum)
    simulated.sort()
    idx = max(0, min(len(simulated) - 1, int(math.floor((1 - confidence) * len(simulated)))))
    return simulated[idx]


def beta(asset_returns: Sequence[float], bench_returns: Sequence[float]) -> Optional[float]:
    n = min(len(asset_returns), len(bench_returns))
    if n < 2:
        return None
    a = asset_returns[:n]
    b = bench_returns[:n]
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    varb = sum((b[i] - mb) ** 2 for i in range(n)) / (n - 1)
    if varb == 0:
        return None
    return cov / varb


def correlation(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    n = min(len(a), len(b))
    if n < 2:
        return None
    ma = sum(a[:n]) / n
    mb = sum(b[:n]) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n)))
    vb = math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
    if va == 0 or vb == 0:
        return None
    return cov / (va * vb)


def concentration(weights: Sequence[float]) -> dict[str, Any]:
    """HHI on the weights (fractions summing to 1) + top holding share."""
    w = [x for x in weights if x > 0]
    total = sum(w)
    if total <= 0:
        return {"hhi": None, "topWeight": None, "effectiveN": None}
    fracs = [x / total for x in w]
    hhi = sum(f * f for f in fracs)
    return {
        "hhi": round(hhi, 6),
        "topWeight": round(max(fracs), 6),
        "effectiveN": round(1 / hhi, 4) if hhi > 0 else None,
    }


def factor_exposure(weights: dict[str, float],
                    loadings: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Portfolio exposure to named factors = Σ weightᵢ × loadingᵢ,factor.

    `loadings` is caller-supplied (e.g. each symbol's beta to a market/style
    factor). Without loadings the report is unavailable — never invented.
    """
    factors = sorted({f for m in loadings.values() for f in m})
    if not factors:
        return {"available": False, "reason": "no factor loadings supplied", "exposures": {}}
    exposures = {
        f: round(sum(weights.get(s, 0.0) * loadings.get(s, {}).get(f, 0.0) for s in weights), 8)
        for f in factors
    }
    return {"available": True, "exposures": exposures, "factors": factors}


def portfolio_nav(
    weights: dict[str, float], closes: dict[str, Sequence[float]]
) -> tuple[list[float], list[str]]:
    """Build a rebased NAV curve from per-symbol closes and weights."""
    used = [s for s, w in weights.items() if w > 0 and closes.get(s) and len(closes[s]) >= 2]
    if not used:
        return [], []
    length = min(len(closes[s]) for s in used)
    wsum = sum(weights[s] for s in used) or 1.0
    nav = []
    for t in range(length):
        value = 0.0
        for s in used:
            series = closes[s][-length:]
            value += (weights[s] / wsum) * (series[t] / series[0])
        nav.append(value)
    return nav, used


def compute_risk(
    *,
    weights: dict[str, float],
    closes: dict[str, Sequence[float]],
    benchmark_closes: Optional[Sequence[float]] = None,
    confidence: float = 0.95,
    risk_free: float = 0.0,
    periods: int = TRADING_DAYS,
) -> dict[str, Any]:
    """Assemble the risk report. Uncomputable metrics are None with reasons."""
    unavailable: list[str] = []
    nav, used = portfolio_nav(weights, closes)
    if not nav:
        return {
            "status": "UNAVAILABLE",
            "reason": "insufficient price history for any weighted holding",
            "metrics": {},
            "unavailable": ["volatility", "sharpe", "sortino", "maxDrawdown", "var", "cvar",
                            "beta", "correlation", "concentration"],
            "observations": 0,
        }
    rets = returns_from_prices(nav)
    if len(rets) < 2:
        unavailable.append("insufficient return observations for statistics")

    vol = annualized_volatility(rets, periods)
    sharpe_ratio = sharpe(rets, risk_free, periods)
    sortino_ratio = sortino(rets, risk_free, periods)
    mdd = max_drawdown(nav)
    hist = historic_var(rets, confidence)
    cvar_v = cvar(rets, confidence)
    pvar = parametric_var(rets, confidence)
    mcvar = monte_carlo_var(rets, confidence)

    bench_beta = None
    bench_corr = None
    if benchmark_closes and len(benchmark_closes) >= 2:
        br = returns_from_prices(benchmark_closes)
        bench_beta = beta(rets, br)
        bench_corr = correlation(rets, br)
    else:
        unavailable.append("no benchmark series supplied; beta/correlation omitted")

    conc = concentration(list(weights.values()))

    metrics = {
        "volatility": _r(vol),
        "sharpe": _r(sharpe_ratio),
        "sortino": _r(sortino_ratio),
        "maxDrawdown": _r(mdd),
        "varHistorical": _r(hist),
        "cvar": _r(cvar_v),
        "varParametric": _r(pvar),
        "varMonteCarlo": _r(mcvar),
        "beta": _r(bench_beta),
        "correlation": _r(bench_corr),
        "concentration": conc,
        "confidence": confidence,
        "observations": len(rets),
        "holdingsUsed": used,
    }
    return {
        "status": "OK" if len(rets) >= 2 else "PARTIAL",
        "methodology": {
            "volatility": "sample stdev of daily returns × √252 (annualized)",
            "sharpe": "annualized excess return / annualized volatility",
            "sortino": "annualized excess return / annualized downside deviation",
            "maxDrawdown": "peak-to-trough on the rebased NAV curve",
            "var": f"{confidence:.0%} empirical / normal / seeded Monte-Carlo",
            "beta": "cov(asset, benchmark)/var(benchmark) on aligned daily returns",
            "concentration": "Herfindahl-Hirschman index on position weights",
        },
        "metrics": metrics,
        "unavailable": unavailable,
    }


def _r(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 6)


__all__ = [
    "compute_risk",
    "annualized_volatility",
    "sharpe",
    "sortino",
    "max_drawdown",
    "historic_var",
    "parametric_var",
    "cvar",
    "monte_carlo_var",
    "beta",
    "correlation",
    "concentration",
    "factor_exposure",
    "portfolio_nav",
    "returns_from_prices",
    "TRADING_DAYS",
]
