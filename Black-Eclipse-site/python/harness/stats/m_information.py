"""calculate_information_coefficient — cross-sectional and time-series IC."""

from __future__ import annotations

import math

import numpy as np

from .base import (
    INVALID_INPUT,
    StatsError,
    as_list,
    get_int,
    get_str,
    make_response,
    to_float_array,
)
from .dist import norm_sf, t_two_sided_p

DESCRIPTION = (
    "Information coefficient analysis. Cross-sectional IC (per-date rank/linear "
    "correlation of a factor with forward returns, averaged across dates) and "
    "time-series IC. Returns mean IC, its standard deviation, the IC information "
    "ratio, hit rate, coverage, a t-statistic/p-value, and IC decay across "
    "forward horizons when a price series is supplied. Forward targets are built "
    "from t to t+horizon with no look-ahead into the factor."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "factor": {"type": "array", "description": "1-D factor series, or 2-D (dates x assets)."},
        "forwardReturns": {"type": "array", "description": "Aligned forward returns (same shape as factor)."},
        "prices": {"type": "array", "items": {"type": "number"},
                   "description": "Price series to build forward returns (time-series mode)."},
        "horizon": {"type": "integer", "minimum": 1, "default": 1},
        "method": {"type": "string", "enum": ["pearson", "spearman"], "default": "spearman"},
        "decayHorizons": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["factor"],
}


def _rank(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a)
    ranks = np.empty(a.size)
    ranks[order] = np.arange(a.size)
    return ranks


def _corr(a: np.ndarray, b: np.ndarray, method: str) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    av, bv = a[m], b[m]
    if method == "spearman":
        av, bv = _rank(av), _rank(bv)
    if np.std(av) == 0 or np.std(bv) == 0:
        return float("nan")
    return float(np.corrcoef(av, bv)[0, 1])


def _forward_returns(prices: np.ndarray, h: int) -> np.ndarray:
    out = np.full(prices.size, np.nan)
    if h < prices.size:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[: prices.size - h] = prices[h:] / prices[: prices.size - h] - 1.0
    return out


def _ic_stats(ics: np.ndarray, alpha: float = 0.05) -> dict:
    good = ics[np.isfinite(ics)]
    T = good.size
    if T == 0:
        return {"meanIC": None, "observations": 0}
    mean = float(good.mean())
    std = float(good.std(ddof=1)) if T > 1 else None
    ir = mean / std if std else None
    hit = float((good > 0).mean())
    t_stat = mean / (std / math.sqrt(T)) if std else None
    p = t_two_sided_p(t_stat, T - 1) if t_stat is not None else None
    return {
        "meanIC": mean, "stdIC": std, "informationRatio": ir, "hitRate": hit,
        "observations": T, "tStatistic": t_stat, "pValue": p,
        "significant": bool(p < alpha) if p is not None else None,
        "series": as_list(ics),
    }


def run(args: dict) -> dict:
    factor = np.asarray(args.get("factor"), dtype=float)
    if factor.size == 0:
        raise StatsError(INVALID_INPUT, "factor is required")
    method = get_str(args, "method", "spearman")
    if method not in ("pearson", "spearman"):
        raise StatsError(INVALID_INPUT, "method must be pearson or spearman")
    horizon = get_int(args, "horizon", 1, minimum=1)
    warnings: list[str] = []
    results: dict = {}

    # ── cross-sectional mode (2-D factor) ────────────────────────────────────
    if factor.ndim == 2:
        fwd = args.get("forwardReturns")
        if fwd is None:
            raise StatsError(INVALID_INPUT, "cross-sectional IC requires forwardReturns")
        fwd = np.asarray(fwd, dtype=float)
        if fwd.shape != factor.shape:
            raise StatsError(INVALID_INPUT, "forwardReturns must match factor shape")
        ics = np.array([_corr(factor[i], fwd[i], method) for i in range(factor.shape[0])])
        stats = _ic_stats(ics)
        coverage = float(np.isfinite(factor).sum() / factor.size)
        results["crossSectional"] = stats
        results["factorCoverage"] = coverage
        summary = {"mode": "cross_sectional", "method": method,
                   "meanIC": stats.get("meanIC"), "informationRatio": stats.get("informationRatio"),
                   "dates": factor.shape[0]}
        warnings.append("cross-sectional IC evaluated in-sample; out-of-sample validation is separate")
        return make_response(
            "calculate_information_coefficient",
            {"method": method, "horizon": horizon},
            summary=summary, results=results, warnings=warnings,
        )

    # ── time-series mode (1-D factor) ────────────────────────────────────────
    if args.get("forwardReturns") is not None:
        fwd = to_float_array(args.get("forwardReturns"), "forwardReturns")
        if fwd.size != factor.size:
            raise StatsError(INVALID_INPUT, "forwardReturns must match factor length")
    elif args.get("prices") is not None:
        prices = to_float_array(args.get("prices"), "prices")
        if prices.size != factor.size:
            raise StatsError(INVALID_INPUT, "prices must match factor length")
        fwd = _forward_returns(prices, horizon)
    else:
        raise StatsError(INVALID_INPUT, "provide forwardReturns or prices for time-series IC")

    ic = _corr(factor, fwd, method)
    n = int((np.isfinite(factor) & np.isfinite(fwd)).sum())
    summary = {"mode": "time_series", "method": method, "horizon": horizon,
               "ic": ic, "observations": n}
    results["timeSeries"] = {"ic": ic, "observations": n}

    # IC decay across horizons
    if args.get("prices") is not None and args.get("decayHorizons"):
        prices = to_float_array(args.get("prices"), "prices")
        decay = []
        for h in args["decayHorizons"]:
            fh = _forward_returns(prices, int(h))
            decay.append({"horizon": int(h), "ic": _corr(factor, fh, method)})
        results["icDecay"] = decay

    warnings.append("a calculated IC is not evidence of out-of-sample predictive value")
    return make_response(
        "calculate_information_coefficient",
        {"method": method, "horizon": horizon},
        summary=summary, results=results,
        diagnostics={"note": "factor known at t; forward return spans t..t+h"},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
