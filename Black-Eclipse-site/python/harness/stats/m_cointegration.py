"""calculate_cointegration — Engle–Granger and Johansen trace tests."""

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
from .linreg import ols
from .m_stationarity import _adf, _approx_pvalue

DESCRIPTION = (
    "Cointegration testing. Engle–Granger: regress one series on the other(s), "
    "ADF-test the residual using cointegration-specific critical values, and "
    "return the cointegrating vector and spread. Johansen: eigenvalue-based "
    "trace test for the cointegration rank of a multivariate system. Integration "
    "order diagnostics and model caveats are reported; correlation alone is not "
    "treated as cointegration."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "series": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                   "description": "Two or more co-moving series."},
        "method": {"type": "string", "enum": ["engle_granger", "johansen", "both"],
                   "default": "both"},
        "detOrder": {"type": "string", "enum": ["c", "n"], "default": "c"},
        "maxLags": {"type": "integer", "minimum": 1, "default": 1},
    },
    "required": ["series"],
}

# MacKinnon critical values for the Engle–Granger residual test, by number of
# variables N (constant case). N=2 is the classic pair.
_EG_CRIT = {
    2: {1: -3.90, 5: -3.34, 10: -3.04},
    3: {1: -4.29, 5: -3.74, 10: -3.45},
    4: {1: -4.64, 5: -4.10, 10: -3.81},
    5: {1: -4.96, 5: -4.42, 10: -4.13},
}
# Johansen trace-test 95% critical values (no deterministic trend in the data,
# constant in the cointegrating space) — Osterwald–Lenum (1992).
_JOHANSEN_95 = {
    1: [3.76],
    2: [15.41, 3.76],
    3: [29.68, 15.41, 3.76],
    4: [47.21, 29.68, 15.41, 3.76],
}


def _engle_granger(arrays: list[np.ndarray], det_order: str, max_lags: int, warnings: list[str]) -> dict:
    y = arrays[0]
    X = np.column_stack(arrays[1:])
    n = y.size
    if det_order == "c":
        design = np.column_stack([np.ones(n), X])
    else:
        design = X
    fit = ols(y, design)
    resid = np.array(fit.residuals)
    # residual unit-root test (no constant: the regression already demeaned)
    adf = _adf(resid, "n", max_lags, "aic")
    n_vars = len(arrays)
    crit = _EG_CRIT.get(min(n_vars, 5), _EG_CRIT[5])
    stat = adf["statistic"]
    p = float(_approx_pvalue(stat, crit, lower_rejects=True))
    vector = fit.coefficients[1:] if det_order == "c" else fit.coefficients
    cointegrated = p < 0.05
    if not cointegrated:
        warnings.append("Engle–Granger: residuals do not reject a unit root; no cointegration evidence")
    return {
        "test": "engle_granger",
        "statistic": float(stat),
        "pValueApprox": p,
        "criticalValues": crit,
        "cointegratingVector": [float(1.0), *[float(v) for v in vector]],
        "intercept": float(fit.coefficients[0]) if det_order == "c" else 0.0,
        "spread": as_list(resid),
        "usedLag": adf["usedLag"],
        "nobs": n,
        "cointegrated": bool(cointegrated),
        "null": "series are not cointegrated (residual has a unit root)",
    }


def _johansen(arrays: list[np.ndarray], det_order: str, n_lags_diff: int) -> dict:
    Y = np.column_stack(arrays)
    p = Y.shape[1]
    T = Y.shape[0]
    dY = np.diff(Y, axis=0)
    if n_lags_diff > 0:
        # build lagged differences
        dy_lags = []
        for l in range(1, n_lags_diff + 1):
            dy_lags.append(dY[n_lags_diff - l: T - 1 - l])
        Z0 = dY[n_lags_diff:]
        Ylag = Y[n_lags_diff: T - 1]
        W = np.column_stack(dy_lags) if dy_lags else np.empty((Z0.shape[0], 0))
    else:
        Z0 = dY
        Ylag = Y[:-1]
        W = np.empty((Z0.shape[0], 0))

    def resid(target: np.ndarray) -> np.ndarray:
        cols = [np.ones((target.shape[0], 1))] if det_order == "c" else []
        if W.size:
            cols.append(W)
        if cols:
            D = np.column_stack(cols)
            beta = np.linalg.lstsq(D, target, rcond=None)[0]
            return target - D @ beta
        return target - target.mean(axis=0) if det_order == "c" else target

    R0 = resid(Z0)
    R1 = resid(Ylag)
    Tt = R0.shape[0]
    S00 = R0.T @ R0 / Tt
    S11 = R1.T @ R1 / Tt
    S01 = R0.T @ R1 / Tt
    S10 = S01.T
    try:
        S11_inv = np.linalg.inv(S11)
    except np.linalg.LinAlgError as exc:
        raise StatsError(INVALID_INPUT, "Johansen: singular S11 (collinear series)") from exc
    M = S11_inv @ S10 @ np.linalg.inv(S00) @ S01
    eigvals = np.linalg.eigvals(M)
    eigvals = np.sort(np.real(eigvals))[::-1]
    eigvals = np.clip(eigvals, 0.0, 1.0 - 1e-12)

    trace = [float(-Tt * np.sum(np.log(1.0 - eigvals[r:]))) for r in range(p)]
    crit = _JOHANSEN_95.get(p, _JOHANSEN_95[4])
    rank = 0
    for r in range(p):
        if trace[r] > crit[r]:
            rank = r + 1
        else:
            break
    return {
        "test": "johansen",
        "eigenvalues": [float(e) for e in eigvals],
        "traceStatistic": trace,
        "criticalValues95": crit[:p],
        "rank": int(rank),
        "null": "cointegration rank <= r",
        "nobs": int(Tt),
    }


def run(args: dict) -> dict:
    series_arg = args.get("series")
    if not series_arg or len(series_arg) < 2:
        raise StatsError(INVALID_INPUT, "cointegration requires at least two series")
    arrays = [to_float_array(s, f"series[{i}]") for i, s in enumerate(series_arg)]
    lengths = {a.size for a in arrays}
    if len(lengths) != 1:
        raise StatsError(INVALID_INPUT, "all series must have equal length")
    if arrays[0].size < 20:
        raise StatsError(INVALID_INPUT, "cointegration tests need at least 20 observations", 422)
    if any(not np.isfinite(a).all() for a in arrays):
        raise StatsError(INVALID_INPUT, "cointegration requires complete series (no missing values)")

    method = get_str(args, "method", "both")
    det_order = get_str(args, "detOrder", "c")
    max_lags = get_int(args, "maxLags", 1, minimum=1)
    warnings: list[str] = []
    results: dict = {}

    if method in ("engle_granger", "both"):
        results["engleGranger"] = _engle_granger(arrays, det_order, max_lags, warnings)
    if method in ("johansen", "both"):
        results["johansen"] = _johansen(arrays, det_order, max_lags)
        n_vars = len(arrays)
        if n_vars > 4:
            warnings.append("Johansen critical values are provided only up to 4 variables")
        if arrays[0].size < 50:
            warnings.append("small sample for Johansen; trace-test size may be distorted")

    return make_response(
        "calculate_cointegration",
        {"method": method, "detOrder": det_order, "maxLags": max_lags},
        summary={"variables": len(arrays), "observations": arrays[0].size, "method": method},
        results=results,
        diagnostics={"note": "critical values from standard published tables; p-values approximate"},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
