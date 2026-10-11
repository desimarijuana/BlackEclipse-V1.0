"""calculate_volatility — rolling / EWMA / annualized / OHLC / GARCH(1,1)."""

from __future__ import annotations

import math

import numpy as np

from .base import (
    INVALID_INPUT,
    INSUFFICIENT_DATA,
    StatsError,
    as_list,
    get_float,
    get_int,
    get_str,
    make_response,
    require_min_length,
    to_float_array,
)
from .optim import nelder_mead

DESCRIPTION = (
    "Estimate volatility: rolling standard deviation/variance, annualized "
    "volatility, EWMA (RiskMetrics) volatility, Parkinson and Garman–Klass "
    "range estimators from OHLC bars, and a Gaussian GARCH(1,1) maximum-"
    "likelihood fit with a one-step variance forecast. Annualization is "
    "frequency-aware."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"}},
        "inputType": {"type": "string", "enum": ["prices", "returns"], "default": "prices"},
        "returnMethod": {"type": "string", "enum": ["simple", "log"], "default": "simple"},
        "method": {"type": "string",
                   "enum": ["rolling_std", "rolling_var", "ewma", "garch11",
                            "parkinson", "garman_klass"],
                   "default": "rolling_std"},
        "window": {"type": "integer", "minimum": 2, "default": 20},
        "periodsPerYear": {"type": "integer", "minimum": 1, "default": 252},
        "decay": {"type": "number", "description": "EWMA lambda (default 0.94)."},
        "annualize": {"type": "boolean", "default": True},
        "high": {"type": "array", "items": {"type": "number"}},
        "low": {"type": "array", "items": {"type": "number"}},
        "open": {"type": "array", "items": {"type": "number"}},
        "close": {"type": "array", "items": {"type": "number"}},
    },
    "required": ["values"],
}


def _to_returns(prices: np.ndarray, method: str) -> np.ndarray:
    if method == "log":
        if np.any(prices[np.isfinite(prices)] <= 0):
            raise StatsError(INVALID_INPUT, "log returns require strictly positive prices")
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.log(prices[1:] / prices[:-1])
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            r = prices[1:] / prices[:-1] - 1.0
    return np.where(np.isfinite(r), r, np.nan)


def _parkinson(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        rng = np.log(high / low)
    var = rng ** 2 / (4.0 * math.log(2.0))
    return np.where(np.isfinite(var), var, np.nan)


def _garman_klass(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        hl = 0.5 * np.log(high / low) ** 2
        co = (2.0 * math.log(2.0) - 1.0) * np.log(close / open_) ** 2
    var = hl - co
    return np.where((var > 0) & np.isfinite(var), var, np.nan)


def _garch11(returns: np.ndarray) -> dict:
    r = returns[np.isfinite(returns)]
    if r.size < 20:
        raise StatsError(INSUFFICIENT_DATA, "GARCH(1,1) needs at least 20 observations", 422)
    var0 = float(np.var(r, ddof=1))

    def negloglik(theta: list[float]) -> float:
        o, a, b = theta
        omega = math.exp(o)
        alpha = 1.0 / (1.0 + math.exp(-a))
        beta = (1.0 - alpha) / (1.0 + math.exp(-b))
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1.0:
            return 1e12
        variance = var0
        nll = 0.0
        for x in r:
            nll += 0.5 * (math.log(variance) + x * x / variance)
            variance = omega + alpha * x * x + beta * variance
        return nll

    x0 = [math.log(var0 * (1.0 - 0.1 - 0.8) + 1e-12), 0.0, 1.0]
    best, fval, converged = nelder_mead(negloglik, x0, step=0.3, max_iter=1500)
    omega = math.exp(best[0])
    alpha = 1.0 / (1.0 + math.exp(-best[1]))
    beta = (1.0 - alpha) / (1.0 + math.exp(-best[2]))
    # final variance recursion + one-step forecast
    variance = var0
    for x in r[:-1]:
        variance = omega + alpha * x * x + beta * variance
    forecast = omega + alpha * r[-1] ** 2 + beta * variance
    return {
        "omega": float(omega), "alpha": float(alpha), "beta": float(beta),
        "persistence": float(alpha + beta), "logLikelihood": float(-fval),
        "forecastVariance": float(forecast), "converged": bool(converged),
    }


def run(args: dict) -> dict:
    values = to_float_array(args.get("values"), "values")
    require_min_length(values, 3, "values")
    input_type = get_str(args, "inputType", "prices")
    method = get_str(args, "method", "rolling_std")
    window = get_int(args, "window", 20, minimum=2)
    periods = get_int(args, "periodsPerYear", 252, minimum=1)
    annualize = bool(args.get("annualize", True))
    warnings: list[str] = []

    if input_type == "returns":
        rets = values
        prices = None
    else:
        prices = values
        rets = _to_returns(values, get_str(args, "returnMethod", "simple"))

    ann = math.sqrt(periods) if annualize else 1.0
    results: dict = {}
    summary: dict = {"method": method, "periodsPerYear": periods, "annualized": annualize}

    if method in ("rolling_std", "rolling_var"):
        if window > rets.size:
            raise StatsError(INSUFFICIENT_DATA, f"window {window} exceeds series length {rets.size}", 422)
        series = np.full(rets.size, np.nan)
        for i in range(window - 1, rets.size):
            chunk = rets[i - window + 1: i + 1]
            if np.isnan(chunk).any():
                continue
            v = float(np.var(chunk, ddof=1))
            series[i] = math.sqrt(v) if method == "rolling_std" else v
        scale = ann if method == "rolling_std" else (periods if annualize else 1.0)
        results["rollingSeries"] = as_list(series * scale)
        valid = series[np.isfinite(series)]
        summary["latest"] = float(valid[-1] * scale) if valid.size else None
        summary["mean"] = float(valid.mean() * scale) if valid.size else None
        summary["unit"] = "annualized" if annualize else "per-period"

    elif method == "ewma":
        lam = get_float(args, "decay", 0.94)
        if not 0.0 < lam < 1.0:
            raise StatsError(INVALID_INPUT, "decay must be in (0, 1)")
        r = rets[np.isfinite(rets)]
        if r.size < 2:
            raise StatsError(INSUFFICIENT_DATA, "EWMA needs at least 2 returns", 422)
        variances = np.full(r.size, np.nan)
        v = float(np.var(r[: min(r.size, 20)], ddof=1))
        for i in range(1, r.size):
            v = lam * v + (1.0 - lam) * r[i - 1] ** 2
            variances[i] = v
        results["ewmaVarianceSeries"] = as_list(variances * (periods if annualize else 1.0))
        results["ewmaVolSeries"] = as_list(np.sqrt(variances) * ann)
        summary["latest"] = float(math.sqrt(variances[-1]) * ann)
        summary["decay"] = lam
        summary["unit"] = "annualized" if annualize else "per-period"

    elif method == "garch11":
        fit = _garch11(rets)
        results["garch"] = fit
        summary.update({
            "alpha": fit["alpha"], "beta": fit["beta"], "omega": fit["omega"],
            "persistence": fit["persistence"],
            "forecastVolatility": float(math.sqrt(fit["forecastVariance"]) * ann),
        })
        if not fit["converged"]:
            warnings.append("GARCH(1,1) optimizer did not fully converge; treat parameters as provisional")
        if fit["persistence"] >= 0.999:
            warnings.append("near-integrated GARCH (persistence ~ 1); long-run variance undefined")

    elif method in ("parkinson", "garman_klass"):
        high = to_float_array(args.get("high"), "high")
        low = to_float_array(args.get("low"), "low")
        if high.size != values.size or low.size != values.size:
            raise StatsError(INVALID_INPUT, "high/low must match values length")
        if method == "parkinson":
            var_full = _parkinson(high, low)
        else:
            open_ = to_float_array(args.get("open"), "open")
            close = to_float_array(args.get("close"), "close")
            if open_.size != values.size or close.size != values.size:
                raise StatsError(INVALID_INPUT, "open/close must match values length")
            var_full = _garman_klass(open_, high, low, close)
        series = np.full(var_full.size, np.nan)
        for i in range(window - 1, var_full.size):
            chunk = var_full[i - window + 1: i + 1]
            if np.isnan(chunk).any():
                continue
            series[i] = math.sqrt(float(np.nanmean(chunk)))
        results["rangeVolSeries"] = as_list(series * ann)
        valid = series[np.isfinite(series)]
        summary["latest"] = float(valid[-1] * ann) if valid.size else None
        summary["estimator"] = method
        summary["unit"] = "annualized" if annualize else "per-period"

    else:
        raise StatsError(INVALID_INPUT, f"unknown volatility method: {method}")

    return make_response(
        "calculate_volatility",
        {"method": method, "window": window, "periodsPerYear": periods, "annualize": annualize},
        summary=summary, results=results, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
