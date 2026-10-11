"""Portfolio risk engine (§23–§26): risk contributions and scenario/stress tests.

All math is deterministic and returns plain JSON-serializable dicts. Risk
contributions use the Euler decomposition:
    MRCᵢ = (Σw)ᵢ / σp ;  RCᵢ = wᵢ · MRCᵢ = wᵢ(Σw)ᵢ / σp
so Σ RCᵢ = σp exactly. Contributions preserve the sign of short positions; a
negative contribution is reported, never silently discarded.

Stress testing supports three modes:
  * `hypothetical` — a symbol or factor shock map applied linearly.
  * `historical`   — replay a supplied window of per-symbol returns (the caller
                     supplies point-in-time returns; no future data is inferred).
  * `monte_carlo`  — a seeded simulation from N(0, Σ) with a documented horizon.
Each result names its assumptions and limitations.
"""

from __future__ import annotations

import math
import random
from typing import Any, Optional, Sequence

from .risk import TRADING_DAYS, _norm_ppf


def _vol(weights: Sequence[float], cov: Sequence[Sequence[float]]) -> float:
    n = len(weights)
    var = sum(weights[i] * cov[i][j] * weights[j] for i in range(n) for j in range(n))
    return math.sqrt(max(var, 0.0))


def risk_contributions(
    weights: dict[str, float], covariance: Sequence[Sequence[float]],
    *, names: Optional[Sequence[str]] = None, groups: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Asset-level (and optional group-level) Euler risk contributions."""
    labels = list(names) if names is not None else list(weights)
    w = [float(weights.get(s, 0.0)) for s in labels]
    n = len(w)
    cov = [list(map(float, row)) for row in covariance]
    if len(cov) != n or any(len(row) != n for row in cov):
        return {"available": False, "reason": "covariance must be square and match weights"}
    vol = _vol(w, cov)
    if vol <= 0:
        return {"available": False, "reason": "portfolio volatility is zero; decomposition undefined"}
    sigma_w = [sum(cov[i][j] * w[j] for j in range(n)) for i in range(n)]
    mrc = [sigma_w[i] / vol for i in range(n)]
    variance_contrib = [w[i] * sigma_w[i] for i in range(n)]
    component = [w[i] * mrc[i] for i in range(n)]
    variance = vol * vol
    assets = {
        labels[i]: {
            "marginal": round(mrc[i], 10),
            "component": round(component[i], 10),
            "varianceContribution": round(variance_contrib[i], 12),
            "shareOfVariance": round(variance_contrib[i] / variance, 10) if variance else None,
        }
        for i in range(n)
    }
    result: dict[str, Any] = {
        "available": True,
        "portfolioVolatility": round(vol, 10),
        "riskContributions": assets,
        "reconciliation": {
            "sumOfComponents": round(sum(component), 10),
            "portfolioVolatility": round(vol, 10),
            "reconciles": abs(sum(component) - vol) <= 1e-8 * max(1.0, vol),
        },
    }
    if groups:
        bucket: dict[str, float] = {}
        for i in range(n):
            bucket[groups.get(labels[i], "UNCLASSIFIED")] = \
                bucket.get(groups.get(labels[i], "UNCLASSIFIED"), 0.0) + component[i]
        result["groupContributions"] = {k: round(v, 10) for k, v in sorted(bucket.items())}
    return result


def hypothetical_impact(weights: dict[str, float], shocks: dict[str, float]) -> dict[str, Any]:
    """Apply a linear shock map (symbol → fractional return) to the portfolio."""
    if not shocks:
        return {"available": False, "reason": "no shocks supplied"}
    contributions = {
        s: {"weight": weights.get(s, 0.0), "shock": float(shocks[s]),
            "contribution": weights.get(s, 0.0) * float(shocks[s])}
        for s in shocks
    }
    total = sum(c["contribution"] for c in contributions.values())
    return {
        "available": True, "type": "hypothetical", "portfolioReturn": round(total, 10),
        "contributions": {k: {kk: round(vv, 10) for kk, vv in v.items()}
                          for k, v in contributions.items()},
        "assumptions": ["linear impact", "no nonlinear payoffs, liquidity or gap risk represented"],
    }


def factor_shock_impact(
    weights: dict[str, float], loadings: dict[str, dict[str, float]],
    factor_shocks: dict[str, float],
) -> dict[str, Any]:
    """Translate factor shocks to symbol shocks via loadings, then apply them."""
    if not factor_shocks:
        return {"available": False, "reason": "no factor shocks supplied"}
    shocks: dict[str, float] = {}
    for symbol in weights:
        load = loadings.get(symbol) or {}
        shocks[symbol] = sum(float(factor_shocks[f]) * float(load.get(f, 0.0)) for f in factor_shocks)
    out = hypothetical_impact(weights, shocks)
    out["type"] = "hypothetical_factor"
    out["factorShocks"] = factor_shocks
    return out


def historical_replay(
    weights: dict[str, float], returns: dict[str, Sequence[float]],
) -> dict[str, Any]:
    """Replay a supplied window of per-symbol returns (already point-in-time).

    Returns are aligned by truncating to the shortest common length. A missing
    series for a weighted holding makes the result unavailable — never zeroed.
    """
    used = [s for s, w in weights.items() if abs(w) > 0 and returns.get(s)]
    missing = [s for s, w in weights.items() if abs(w) > 0 and not returns.get(s)]
    if missing:
        return {"available": False, "reason": f"missing return history for {missing}"}
    if not used:
        return {"available": False, "reason": "no weighted holding has return history"}
    length = min(len(returns[s]) for s in used)
    path: list[float] = []
    cumulative = 0.0
    for t in range(length):
        r = sum(weights[s] * float(returns[s][t]) for s in used)
        cumulative += r
        path.append(cumulative)
    peak = -math.inf
    max_dd = 0.0
    for value in path:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return {
        "available": True, "type": "historical", "observations": length,
        "cumulativeReturn": round(cumulative, 10),
        "worstSinglePeriod": round(min(path), 10) if path else None,
        "maxDrawdownOfCumulative": round(max_dd, 10),
        "path": [round(p, 8) for p in path],
        "assumptions": ["linear portfolio return", "caller-supplied point-in-time window"],
    }


def monte_carlo(
    weights: dict[str, float], covariance: Sequence[Sequence[float]],
    *, simulations: int = 10_000, horizon: int = 1, seed: int = 12345,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Seeded Monte-Carlo of the portfolio return under N(0, Σ)."""
    labels = list(weights)
    n = len(labels)
    if simulations <= 0:
        return {"available": False, "reason": "simulations must be positive"}
    w = [float(weights[s]) for s in labels]
    cov = [list(map(float, row)) for row in covariance]
    if len(cov) != n or any(len(row) != n for row in cov):
        return {"available": False, "reason": "covariance must be square and match weights"}
    # Cholesky with a documented fallback to the diagonal.
    L = _cholesky(cov)
    if L is None:
        return {"available": False, "reason": "covariance is not positive definite; cannot simulate"}
    rng = random.Random(seed)
    outcomes: list[float] = []
    for _ in range(simulations):
        portfolio = 0.0
        for _ in range(max(1, horizon)):
            z = [rng.gauss(0.0, 1.0) for _ in range(n)]
            shock = [sum(L[i][j] * z[j] for j in range(i + 1)) for i in range(n)]
            portfolio += sum(w[i] * shock[i] for i in range(n))
        outcomes.append(portfolio)
    outcomes.sort()
    idx = max(0, min(len(outcomes) - 1, int(math.floor((1 - confidence) * len(outcomes)))))
    var = outcomes[idx]
    tail = outcomes[: idx + 1] or [var]
    cvar = sum(tail) / len(tail)
    return {
        "available": True, "type": "monte_carlo", "simulations": simulations, "seed": seed,
        "horizon": horizon, "confidence": confidence,
        "var": round(var, 10), "cvar": round(cvar, 10),
        "mean": round(sum(outcomes) / len(outcomes), 10),
        "assumptions": ["multivariate normal (zero mean)", "Gaussian copula via Cholesky",
                        "linear portfolio return"],
    }


def _cholesky(cov: Sequence[Sequence[float]]) -> Optional[list[list[float]]]:
    n = len(cov)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = cov[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0:
                    return None
                L[i][j] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    return L


def stress_test(
    weights: dict[str, float], *, scenarios: Sequence[dict[str, Any]],
    covariance: Optional[Sequence[Sequence[float]]] = None,
) -> dict[str, Any]:
    """Run a list of named scenarios and return each result."""
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        kind = scenario.get("type", "hypothetical")
        name = scenario.get("name") or kind
        if kind == "hypothetical":
            res = hypothetical_impact(weights, scenario.get("shocks") or {})
        elif kind == "hypothetical_factor":
            res = factor_shock_impact(weights, scenario.get("loadings") or {},
                                      scenario.get("factorShocks") or {})
        elif kind == "historical":
            res = historical_replay(weights, scenario.get("returns") or {})
        elif kind == "monte_carlo":
            if covariance is None:
                res = {"available": False, "reason": "monte_carlo requires a covariance"}
            else:
                res = monte_carlo(weights, covariance,
                                  simulations=int(scenario.get("simulations", 10_000)),
                                  horizon=int(scenario.get("horizon", 1)),
                                  seed=int(scenario.get("seed", 12345)),
                                  confidence=float(scenario.get("confidence", 0.95)))
        else:
            res = {"available": False, "reason": f"unknown scenario type {kind!r}"}
        res["name"] = name
        results.append(res)
    return {"available": any(r.get("available") for r in results), "scenarios": results}


def parametric_tail(volatility: float, confidence: float = 0.95) -> Optional[float]:
    """Normal parametric VaR as a negative loss number for a given volatility."""
    if volatility <= 0:
        return None
    return round(_norm_ppf(1 - confidence) * volatility, 10)


__all__ = [
    "risk_contributions", "hypothetical_impact", "factor_shock_impact",
    "historical_replay", "monte_carlo", "stress_test", "parametric_tail", "TRADING_DAYS",
]
