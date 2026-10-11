"""analyze_lead_lag — cross-correlation, lagged regression and Granger tests.

Lag convention: a positive lag k means the predictor at t−k is related to the
target at t (the predictor LEADS the target by k periods). Every result states
this convention explicitly. Predictive association is reported as association,
never as proven economic causation.
"""

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
from .dist import f_sf
from .linreg import ols

DESCRIPTION = (
    "Lead–lag analysis between two series: cross-correlation over a configurable "
    "lag range, a lagged regression, and optional Granger-causality F-tests with "
    "Bonferroni multiple-testing control. Convention: positive lag k means the "
    "predictor leads the target by k periods."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "predictor": {"type": "array", "items": {"type": "number"}},
        "target": {"type": "array", "items": {"type": "number"}},
        "maxLag": {"type": "integer", "minimum": 1, "default": 10},
        "method": {"type": "string",
                   "enum": ["cross_correlation", "lagged_regression", "granger", "all"],
                   "default": "all"},
        "significance": {"type": "number", "default": 0.05},
    },
    "required": ["predictor", "target"],
}


def _cross_corr(x: np.ndarray, y: np.ndarray, max_lag: int) -> dict:
    out = []
    for k in range(-max_lag, max_lag + 1):
        if k >= 0:
            a, b = x[: x.size - k] if k else x, y[k:]
        else:
            a, b = x[-k:], y[: y.size + k]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
            out.append({"lag": k, "correlation": None, "observations": int(m.sum())})
            continue
        r = float(np.corrcoef(a[m], b[m])[0, 1])
        out.append({"lag": k, "correlation": r, "observations": int(m.sum())})
    valid = [o for o in out if o["correlation"] is not None]
    best = max(valid, key=lambda o: abs(o["correlation"])) if valid else None
    return {"crossCorrelation": out, "peak": best}


def _granger(x: np.ndarray, y: np.ndarray, p: int) -> dict:
    n = y.size
    if n < 3 * p + 5:
        raise StatsError(INVALID_INPUT, f"not enough observations for Granger lag {p}", 422)
    start = p
    Y = y[start:]
    rows = Y.size
    ylags = np.column_stack([y[start - i: n - i] for i in range(1, p + 1)])
    xlags = np.column_stack([x[start - i: n - i] for i in range(1, p + 1)])
    R = np.column_stack([np.ones(rows), ylags])
    U = np.column_stack([np.ones(rows), ylags, xlags])
    fit_r = ols(Y, R)
    fit_u = ols(Y, U)
    rss_r = float(np.sum(np.array(fit_r.residuals) ** 2))
    rss_u = float(np.sum(np.array(fit_u.residuals) ** 2))
    df_num = p
    df_den = rows - U.shape[1]
    if rss_u <= 0 or df_den <= 0:
        return {"lag": p, "fStatistic": None, "pValue": None}
    f = ((rss_r - rss_u) / df_num) / (rss_u / df_den)
    return {"lag": p, "fStatistic": float(f), "pValue": float(f_sf(f, df_num, df_den)),
            "nobs": int(rows)}


def run(args: dict) -> dict:
    x = to_float_array(args.get("predictor"), "predictor")
    y = to_float_array(args.get("target"), "target")
    if x.size != y.size:
        raise StatsError(INVALID_INPUT, "predictor and target must have equal length")
    require_min_length(x, 20, "predictor")
    max_lag = get_int(args, "maxLag", 10, minimum=1)
    max_lag = min(max_lag, x.size // 4)
    method = get_str(args, "method", "all")
    alpha = get_float(args, "significance", 0.05)
    warnings: list[str] = []

    results: dict = {}
    summary: dict = {"convention": "positive lag k: predictor leads target by k periods"}

    if method in ("cross_correlation", "all"):
        cc = _cross_corr(x, y, max_lag)
        results["crossCorrelation"] = cc["crossCorrelation"]
        if cc["peak"]:
            summary["peakLag"] = cc["peak"]["lag"]
            summary["peakCorrelation"] = cc["peak"]["correlation"]

    if method in ("lagged_regression", "all"):
        rows = x.size - max_lag
        Y = y[max_lag:]
        cols = [np.ones(rows)]
        names = ["intercept"]
        for i in range(max_lag):
            cols.append(x[max_lag - i - 1: x.size - i - 1])
            names.append(f"predictor_lag{i + 1}")
        fit = ols(Y, np.column_stack(cols), names=names)
        results["laggedRegression"] = fit.to_dict()

    if method in ("granger", "all"):
        tests = []
        for p in range(1, max_lag + 1):
            try:
                tests.append(_granger(x, y, p))
            except StatsError:
                continue
        n_tests = len(tests)
        for t in tests:
            t["significantBonferroni"] = bool(
                t["pValue"] is not None and t["pValue"] < alpha / max(1, n_tests)
            )
        results["granger"] = tests
        summary["grangerRejectsXtoY"] = any(t.get("significantBonferroni") for t in tests)
        if n_tests:
            warnings.append(f"Granger: {n_tests} lag tests; Bonferroni-corrected at {alpha / n_tests:.4g}")
        warnings.append("Granger causality is predictive association under a linear model, not economic causality")

    return make_response(
        "analyze_lead_lag",
        {"maxLag": max_lag, "method": method, "significance": alpha},
        summary=summary, results=results, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
