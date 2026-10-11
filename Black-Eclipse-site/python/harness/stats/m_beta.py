"""calculate_beta — market-model beta/alpha with robust and HAC inference."""

from __future__ import annotations

import math

import numpy as np

from .base import (
    INVALID_INPUT,
    StatsError,
    align_series,
    as_list,
    get_int,
    get_str,
    make_response,
    require_min_length,
    to_float_array,
)
from .linreg import ols

DESCRIPTION = (
    "Estimate a market-model regression of asset returns on a benchmark: OLS "
    "beta, alpha (per-period and annualized), R-squared, robust (HC0/HC1/HC3) or "
    "Newey-West (HAC) standard errors, confidence intervals, and a rolling beta "
    "series. Asset and benchmark are aligned by timestamp/position."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "asset": {"type": "array", "items": {"type": "number"}},
        "benchmark": {"type": "array", "items": {"type": "number"}},
        "inputType": {"type": "string", "enum": ["prices", "returns"], "default": "returns"},
        "returnMethod": {"type": "string", "enum": ["simple", "log"], "default": "simple"},
        "covType": {"type": "string", "enum": ["classical", "HC0", "HC1", "HC3", "HAC"],
                    "default": "classical"},
        "window": {"type": "integer", "minimum": 3, "description": "Rolling beta window."},
        "periodsPerYear": {"type": "integer", "minimum": 1, "default": 252},
        "annualizeAlpha": {"type": "boolean", "default": True},
        "confidence": {"type": "number", "default": 0.95},
    },
    "required": ["asset", "benchmark"],
}


def _to_returns(series: np.ndarray, method: str) -> np.ndarray:
    if method == "log":
        if np.any(series[np.isfinite(series)] <= 0):
            raise StatsError(INVALID_INPUT, "log returns require strictly positive prices")
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(series[1:] / series[:-1])
    with np.errstate(divide="ignore", invalid="ignore"):
        return series[1:] / series[:-1] - 1.0


def run(args: dict) -> dict:
    asset = to_float_array(args.get("asset"), "asset")
    bench = to_float_array(args.get("benchmark"), "benchmark")
    if asset.size != bench.size:
        raise StatsError(INVALID_INPUT, f"asset length {asset.size} != benchmark length {bench.size}")
    require_min_length(asset, 4, "asset")
    input_type = get_str(args, "inputType", "returns")
    if input_type == "prices":
        method = get_str(args, "returnMethod", "simple")
        asset, bench = _to_returns(asset, method), _to_returns(bench, method)
    a, b = align_series(asset, bench, "asset", "benchmark", "pairwise")
    if a.size < 4:
        raise StatsError(INVALID_INPUT, f"only {a.size} overlapping observations; need at least 4", 422)

    cov_type = get_str(args, "covType", "classical")
    periods = get_int(args, "periodsPerYear", 252, minimum=1)
    annualize_alpha = bool(args.get("annualizeAlpha", True))
    confidence = float(args.get("confidence", 0.95))
    warnings: list[str] = []

    X = np.column_stack([np.ones(a.size), b])
    fit = ols(a, X, names=["alpha", "beta"], cov=cov_type, confidence=confidence)
    alpha_per = fit.coefficients[0]
    beta = fit.coefficients[1]
    summary = {
        "beta": beta,
        "alphaPerPeriod": alpha_per,
        "alphaAnnualized": alpha_per * periods if annualize_alpha else None,
        "rSquared": fit.r_squared,
        "observations": int(a.size),
        "covType": cov_type,
    }
    if fit.p_values[1] is not None:
        summary["betaPValue"] = fit.p_values[1]
    results = {
        "beta": beta,
        "alpha": alpha_per,
        "alphaAnnualized": alpha_per * periods if annualize_alpha else None,
        "coefficients": fit.to_dict(),
        "rSquared": fit.r_squared,
        "residuals": fit.residuals,
        "fitted": fit.fitted,
    }

    window = args.get("window")
    if window:
        w = get_int(args, "window", 3, minimum=3)
        rolling = np.full(a.size, np.nan)
        for i in range(w - 1, a.size):
            ca, cb = a[i - w + 1: i + 1], b[i - w + 1: i + 1]
            if cb.std() == 0:
                continue
            rolling[i] = float(np.cov(ca, cb, ddof=0)[0, 1] / np.var(cb))
        results["rollingBeta"] = as_list(rolling)
        summary["rollingWindow"] = w

    if beta < 0:
        warnings.append("negative beta: asset moved opposite to the benchmark over the window")
    return make_response(
        "calculate_beta",
        {"covType": cov_type, "window": window, "periodsPerYear": periods},
        summary=summary, results=results, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
