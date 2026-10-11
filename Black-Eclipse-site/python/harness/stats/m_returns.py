"""calculate_returns — simple, log, cumulative, rolling, lagged and excess returns."""

from __future__ import annotations

import numpy as np

from .base import (
    INVALID_INPUT,
    StatsError,
    as_list,
    get_float,
    get_int,
    get_str,
    make_response,
    require_min_length,
    to_float_array,
)

TOOL_VERSION = "1.0.0"

DESCRIPTION = (
    "Compute returns from a price series: simple, logarithmic, cumulative, "
    "rolling (n-period), lagged and excess (vs a benchmark / risk-free rate). "
    "Returns the per-period series plus summary statistics."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"},
                   "description": "Price series, oldest first."},
        "method": {"type": "string", "enum": ["simple", "log"], "default": "simple"},
        "rollingWindow": {"type": "integer", "minimum": 1,
                          "description": "n-period rolling return P[t]/P[t-n]-1."},
        "lag": {"type": "integer", "minimum": 0,
                "description": "Shift returns forward by n periods."},
        "benchmark": {"type": "array", "items": {"type": "number"},
                      "description": "Benchmark price series for excess returns."},
        "riskFree": {"type": "number", "default": 0.0,
                     "description": "Per-period risk-free rate (subtracted)."},
        "missingPolicy": {"type": "string", "enum": ["reject", "nan"],
                          "default": "nan"},
    },
    "required": ["values"],
}


def _summary(returns: np.ndarray) -> dict:
    finite = returns[np.isfinite(returns)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "mean": float(finite.mean()),
        "std": float(finite.std(ddof=1)) if finite.size > 1 else None,
        "min": float(finite.min()),
        "max": float(finite.max()),
        "sum": float(finite.sum()),
    }


def run(args: dict) -> dict:
    prices = to_float_array(args.get("values"), "values")
    require_min_length(prices, 2, "values")
    method = get_str(args, "method", "simple")
    if method not in ("simple", "log"):
        raise StatsError(INVALID_INPUT, "method must be 'simple' or 'log'")
    lag = get_int(args, "lag", 0, minimum=0)
    rolling = args.get("rollingWindow")
    rf = get_float(args, "riskFree", 0.0)
    reject = get_str(args, "missingPolicy", "nan") == "reject"

    warnings: list[str] = []
    n = prices.size

    if method == "log":
        nonpos = np.where(np.isfinite(prices) & (prices <= 0))[0]
        if nonpos.size:
            raise StatsError(
                INVALID_INPUT,
                f"log returns require strictly positive prices; found {nonpos.size} "
                f"non-positive value(s) (first at index {int(nonpos[0])})",
            )

    simple = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        prev = prices[:-1]
        if method == "simple":
            simple[1:] = prices[1:] / prev - 1.0
        else:
            simple[1:] = np.log(prices[1:] / prev)
    # positions where a prior price was missing or zero are unusable
    bad_prev = ~np.isfinite(np.concatenate([[1.0], prices[:-1]]))
    simple[bad_prev] = np.nan

    lagged = np.full(n, np.nan)
    if lag > 0:
        lagged[lag:] = simple[:-lag]
    else:
        lagged = simple.copy()

    if reject and np.isnan(simple[1:]).any():
        raise StatsError(INVALID_INPUT, "series contains missing prices; cannot form returns")

    excess = None
    if args.get("benchmark") is not None:
        bench = to_float_array(args.get("benchmark"), "benchmark")
        if bench.size != n:
            raise StatsError(INVALID_INPUT, f"benchmark length {bench.size} != values length {n}")
        with np.errstate(divide="ignore", invalid="ignore"):
            brets = np.full(n, np.nan)
            if method == "simple":
                brets[1:] = bench[1:] / bench[:-1] - 1.0
            else:
                brets[1:] = np.log(bench[1:] / bench[:-1])
        excess = simple - brets - rf
    elif rf:
        excess = simple - rf

    rolling_series = None
    if rolling is not None:
        w = int(rolling)
        if w < 1:
            raise StatsError(INVALID_INPUT, "rollingWindow must be >= 1")
        rolling_series = np.full(n, np.nan)
        if w < n:
            with np.errstate(divide="ignore", invalid="ignore"):
                if method == "simple":
                    rolling_series[w:] = prices[w:] / prices[: n - w] - 1.0
                else:
                    rolling_series[w:] = np.log(prices[w:] / prices[: n - w])
        else:
            warnings.append(f"rollingWindow {w} >= series length {n}; rolling series is empty")

    wealth = None
    if method == "simple":
        good = np.nan_to_num(simple, nan=0.0)
        wealth = np.cumprod(1.0 + good)
    else:
        wealth = np.exp(np.cumsum(np.nan_to_num(simple, nan=0.0)))

    results = {
        "returns": as_list(simple),
        "laggedReturns": as_list(lagged),
        "excessReturns": as_list(excess) if excess is not None else None,
        "rollingReturns": as_list(rolling_series) if rolling_series is not None else None,
        "cumulativeWealth": as_list(wealth),
    }
    summary = {"method": method, "observations": n, "returnSummary": _summary(simple)}
    if rolling:
        summary["rollingWindow"] = int(rolling)
    if method == "simple":
        summary["cumulativeReturn"] = float(wealth[-1] - 1.0)
    else:
        summary["cumulativeReturn"] = float(np.expm1(np.nansum(simple)))

    return make_response(
        "calculate_returns",
        {"method": method, "lag": lag, "rollingWindow": rolling, "riskFree": rf},
        summary=summary,
        results=results,
        diagnostics={"missingReturns": int(np.isnan(simple[1:]).sum())},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA", "TOOL_VERSION"]
