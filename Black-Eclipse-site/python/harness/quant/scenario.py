"""Portfolio stress testing and scenario analysis.

Three complementary views, all deterministic:

* **parametric** — variance-covariance VaR/ES and component VaR, with the
  normal assumptions stated (they are assumptions, not facts);
* **historical** — empirical VaR/ES and the worst historical windows, which
  keeps fat tails and clustering instead of assuming them away;
* **scenario** — explicit asset or factor shocks ("rates +100bp", "equities
  -20%"), including a reverse stress test that finds the shock which breaches a
  loss threshold.

Every result names the method and its assumptions. A scenario with no supplied
shock for a held asset reports the uncovered weight; it does not assume zero.
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Any, Iterable, Optional, Sequence

import numpy as np

from .errors import QuantError
from .risk_model import _matrix, portfolio_volatility

_NORMAL = NormalDist()


def _weights(weights: Sequence[float], n: int) -> np.ndarray:
    w = np.asarray(weights, dtype=float).ravel()
    if w.size != n:
        raise QuantError(f"weights must have {n} entries")
    if not np.all(np.isfinite(w)):
        raise QuantError("weights contain NaN/inf")
    return w


def _portfolio_value(value: float) -> float:
    if value is None or value <= 0:
        raise QuantError("portfolio value must be positive")
    return float(value)


def _horizon_scale(horizon_days: float, periods_per_year: float) -> float:
    if horizon_days is None or horizon_days <= 0:
        raise QuantError("horizon must be positive")
    return float(np.sqrt(float(horizon_days) / (periods_per_year / 252.0)))


def parametric_risk(weights: Sequence[float], covariance: Any, *,
                    confidence: float = 0.95, horizon_days: float = 1.0,
                    portfolio_value: float = 1.0,
                    periods_per_year: float = 252.0) -> dict[str, Any]:
    cov = _matrix(covariance)
    n = cov.shape[0]
    w = _weights(weights, n)
    if not 0 < confidence < 1:
        raise QuantError("confidence must be in (0, 1)")
    pv = _portfolio_value(portfolio_value)
    sigma = portfolio_volatility(w, cov) * _horizon_scale(horizon_days, periods_per_year)
    z = _NORMAL.inv_cdf(confidence)
    var = z * sigma
    es = sigma * _NORMAL.pdf(z) / (1.0 - confidence)
    marginal = (cov @ w) / sigma if sigma > 0 else np.zeros(n)
    component = w * marginal * _horizon_scale(horizon_days, periods_per_year) * z
    return {
        "method": "parametric-normal",
        "confidence": confidence,
        "horizonDays": horizon_days,
        "portfolioValue": pv,
        "volatility": sigma,
        "varPct": var,
        "varAmount": var * pv,
        "expectedShortfallPct": es,
        "expectedShortfallAmount": es * pv,
        "componentVarAmount": (component * pv).tolist(),
        "componentVarShare": (component / var).tolist() if var > 0 else [0.0] * n,
        "assumptions": {
            "distribution": "normal (zero mean)",
            "linear": "positions are linear in the risk factors",
        },
    }


def historical_risk(returns: Any, weights: Sequence[float], *,
                    confidence: float = 0.95, window: Optional[int] = None,
                    portfolio_value: float = 1.0) -> dict[str, Any]:
    arr = np.asarray(returns, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2 or arr.size == 0:
        raise QuantError("returns must be a non-empty 2-D array")
    n = arr.shape[1]
    w = _weights(weights, n)
    if not 0 < confidence < 1:
        raise QuantError("confidence must be in (0, 1)")
    pv = _portfolio_value(portfolio_value)
    series = arr @ w
    if window:
        series = series[-int(window):]
    if series.size < 2:
        return {"available": False, "reason": "fewer than 2 return observations"}
    ordered = np.sort(series)
    idx = max(0, int(np.floor((1.0 - confidence) * ordered.size)) - 1)
    var = float(-ordered[idx])
    tail = ordered[: max(1, idx + 1)]
    es = float(-tail.mean())
    # Worst rolling windows preserve the order and clustering of the data.
    worst = []
    if series.size >= 5:
        for size in {5, 10, 20}:
            if series.size < size:
                continue
            sums = np.convolve(series, np.ones(size), mode="valid")
            j = int(np.argmin(sums))
            worst.append({"window": size, "return": float(sums[j]),
                          "startIndex": j, "endIndex": j + size - 1})
    return {
        "available": True,
        "method": "historical-empirical",
        "confidence": confidence,
        "observations": int(series.size),
        "varPct": var,
        "varAmount": var * pv,
        "expectedShortfallPct": es,
        "expectedShortfallAmount": es * pv,
        "worstWindows": worst,
        "meanReturn": float(series.mean()),
        "volatility": float(series.std(ddof=1)),
    }


def scenario_pnl(weights: Sequence[float], scenarios: dict[str, Any], *,
                 symbols: Optional[Sequence[str]] = None,
                 portfolio_value: float = 1.0) -> dict[str, Any]:
    """Apply explicit asset shocks.

    `scenarios` maps a scenario name to either:
      * a mapping ``{symbol: shock}`` where shock is a decimal return (e.g. -0.2);
      * a list of shocks aligned to `weights`.
    """
    w = np.asarray(weights, dtype=float).ravel()
    n = w.size
    pv = _portfolio_value(portfolio_value)
    labels = [str(s) for s in symbols] if symbols is not None else [str(i) for i in range(n)]
    if len(labels) != n:
        raise QuantError("symbols must align with weights")
    results = []
    for name, spec in (scenarios or {}).items():
        if isinstance(spec, dict):
            shocks = np.array([float(spec.get(sym, np.nan)) for sym in labels])
        else:
            shocks = np.asarray(spec, dtype=float).ravel()
            if shocks.size != n:
                raise QuantError(f"scenario {name!r} has {shocks.size} shocks for {n} assets")
        covered = np.isfinite(shocks)
        uncovered = [labels[i] for i in range(n) if not covered[i] and abs(w[i]) > 1e-12]
        applied = np.where(covered, shocks, 0.0)
        pnl = float(np.sum(w * applied))
        results.append({
            "name": name,
            "pnlPct": pnl,
            "pnlAmount": pnl * pv,
            "uncoveredSymbols": uncovered,
            "coveredWeight": float(np.sum(np.abs(w[covered]))),
            "assumptions": "asset shocks applied linearly to current weights",
        })
    worst = min(results, key=lambda r: r["pnlPct"]) if results else None
    return {"scenarios": results, "worst": worst, "portfolioValue": pv}


def factor_scenario_pnl(exposures: Any, factor_shocks: dict[str, float], *,
                        portfolio_value: float = 1.0,
                        idiosyncratic: Optional[dict[str, float]] = None,
                        factors: Optional[Sequence[str]] = None) -> dict[str, Any]:
    """Apply factor shocks through a beta/exposure matrix.

    `exposures` is assets x factors (or a mapping asset -> {factor: beta}).
    """
    pv = _portfolio_value(portfolio_value)
    if isinstance(exposures, dict):
        assets = list(exposures)
        factor_names = factors or sorted({k for row in exposures.values() for k in row})
        B = np.array([[float(exposures[a].get(f, 0.0)) for f in factor_names] for a in assets])
    else:
        B = np.asarray(exposures, dtype=float)
        if B.ndim == 1:
            B = B.reshape(-1, 1)
        factor_names = list(factors) if factors is not None else [f"f{i}" for i in range(B.shape[1])]
    if len(factor_names) != B.shape[1]:
        raise QuantError("factor names must align with the exposure matrix")
    shocks = np.array([float(factor_shocks.get(f, 0.0)) for f in factor_names])
    asset_returns = B @ shocks
    idio = np.asarray([float((idiosyncratic or {}).get(a, 0.0)) for a in (exposures.keys() if isinstance(exposures, dict) else range(B.shape[0]))])
    total = asset_returns + idio
    return {
        "factorShocks": dict(zip(factor_names, shocks.tolist())),
        "assetReturns": total.tolist(),
        "pnlPct": float(total.sum()) if not isinstance(exposures, dict) else float(total.mean()),
        "pnlAmount": (float(total.sum()) if not isinstance(exposures, dict) else float(total.mean())) * pv,
        "note": "factor betas are linear sensitivities; nonlinear instruments need a full revaluation",
    }


def reverse_stress(weights: Sequence[float], covariance: Any, *,
                   loss_threshold: float, confidence: float = 0.95,
                   portfolio_value: float = 1.0) -> dict[str, Any]:
    """Find the parallel shock magnitude that breaches `loss_threshold`.

    The threshold is a decimal loss (0.10 = a 10% loss). The answer is the
    shock that would produce it under the parametric model, not a prediction.
    """
    if loss_threshold <= 0:
        raise QuantError("loss threshold must be positive")
    base = parametric_risk(weights, covariance, confidence=confidence,
                           portfolio_value=portfolio_value)
    vol = base["volatility"]
    if vol <= 0:
        return {"available": False, "reason": "zero portfolio volatility"}
    z = _NORMAL.inv_cdf(confidence)
    shock = loss_threshold / (z * vol)
    return {
        "available": True,
        "lossThresholdPct": loss_threshold,
        "parallelShockPct": shock,
        "note": "a parallel shock to every asset; not a forecast of direction",
        "volatility": vol,
        "confidence": confidence,
    }


def stress_suite(weights: Sequence[float], covariance: Any, *,
                 scenarios: Optional[dict[str, Any]] = None,
                 confidence: float = 0.95, portfolio_value: float = 1.0,
                 symbols: Optional[Sequence[str]] = None) -> dict[str, Any]:
    """One envelope with parametric + explicit scenarios, for a UI/tool."""
    out: dict[str, Any] = {
        "parametric": parametric_risk(
            weights, covariance, confidence=confidence, portfolio_value=portfolio_value
        )
    }
    if scenarios:
        out["scenario"] = scenario_pnl(
            weights, scenarios, symbols=symbols, portfolio_value=portfolio_value
        )
    return out


__all__ = [
    "factor_scenario_pnl",
    "historical_risk",
    "parametric_risk",
    "reverse_stress",
    "scenario_pnl",
    "stress_suite",
]
