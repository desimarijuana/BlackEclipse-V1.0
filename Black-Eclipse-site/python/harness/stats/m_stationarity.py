"""calculate_stationarity — Augmented Dickey–Fuller and KPSS tests.

Unit-root and stationarity inference. Because the engine avoids SciPy, p-values
are obtained from published MacKinnon / Kwiatkowski critical-value tables and
are labelled as approximations (``pValueApprox``); the test statistics themselves
are exact. ADF and KPSS test opposite nulls, so when they disagree the response
says so rather than forcing a conclusion.
"""

from __future__ import annotations

import math

import numpy as np

from .base import (
    StatsError,
    INVALID_INPUT,
    get_int,
    get_str,
    make_response,
    require_min_length,
    to_float_array,
)
from .linreg import ols

DESCRIPTION = (
    "Stationarity / unit-root tests: Augmented Dickey–Fuller (ADF, with "
    "constant/trend/none deterministic terms and AIC/ BIC lag selection) and "
    "KPSS (level or trend stationarity). Returns test statistics, critical "
    "values, approximate p-values, the explicit null hypothesis, and a plain "
    "interpretation that flags ADF/KPSS disagreement."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"}},
        "test": {"type": "string", "enum": ["adf", "kpss", "both"], "default": "both"},
        "regression": {"type": "string", "enum": ["c", "ct", "n"], "default": "c",
                       "description": "c=constant, ct=constant+trend, n=none."},
        "maxLags": {"type": "integer", "minimum": 0},
        "autolag": {"type": "string", "enum": ["aic", "bic", "none"], "default": "aic"},
        "kpssType": {"type": "string", "enum": ["level", "trend"], "default": "level"},
    },
    "required": ["values"],
}

# MacKinnon (1994) asymptotic critical values, layout: regression -> pct -> value
_ADF_CRIT = {
    "c": {1: -3.430, 5: -2.862, 10: -2.567},
    "ct": {1: -3.958, 5: -3.410, 10: -3.127},
    "n": {1: -2.567, 5: -1.941, 10: -1.616},
}
_KPSS_CRIT = {
    "level": {1: 0.739, 5: 0.463, 10: 0.347},
    "trend": {1: 0.216, 5: 0.146, 10: 0.119},
}


def _approx_pvalue(stat: float, crit: dict[int, float], *, lower_rejects: bool) -> float:
    """Piecewise-linear p-value approximation from a critical-value table.

    ``lower_rejects=True``  — a *more negative* statistic rejects the null (ADF/EG).
    ``lower_rejects=False`` — a *larger* statistic rejects the null (KPSS).
    """
    # (critical_value, p) pairs sorted by p ascending
    pairs = sorted(((v, k / 100.0) for k, v in crit.items()), key=lambda kv: kv[1])
    xs = [p[0] for p in pairs]        # critical values (ascending)
    ps = [p[1] for p in pairs]        # matching p (ascending)
    if lower_rejects:
        # more negative than the 1% critical value -> p below 1%
        if stat <= xs[0]:
            return max(1e-4, ps[0] * max(0.05, abs(xs[0]) / max(1e-9, abs(stat))))
        # positive / above the 10% critical value -> do not reject
        if stat >= xs[-1]:
            return min(0.99, 0.10 + (stat - xs[-1]) * 0.5)
        return float(np.interp(stat, xs, ps))
    # upper-tail (KPSS): larger statistic -> smaller p
    if stat >= xs[-1]:
        return max(1e-4, ps[-1] * xs[-1] / max(1e-9, stat))
    if stat <= xs[0]:
        return min(0.99, 0.10 + (xs[0] - stat) * 0.5)
    return float(np.interp(stat, xs, ps))


def _adf(x: np.ndarray, regression: str, max_lags: int, autolag: str) -> dict:
    n = x.size
    dy = np.diff(x)
    p_max = max_lags if max_lags > 0 else max(1, int(math.floor(12 * (n / 100.0) ** 0.25)))
    p_max = min(p_max, (n // 2) - 2)

    def design(p: int):
        start = p
        rows_y = dy[start:]
        cols = [x[start: n - 1]]  # lagged level (y_{t-1})
        if regression in ("c", "ct"):
            cols.append(np.ones_like(rows_y))
        if regression == "ct":
            cols.append(np.arange(start, n - 1, dtype=float))
        for lag in range(1, p + 1):
            cols.append(dy[start - lag: n - 1 - lag])
        return rows_y, np.column_stack(cols)

    best = None
    if autolag == "none":
        candidates = {p_max}
    else:
        candidates = range(0, p_max + 1)
    for p in candidates:
        yy, XX = design(p)
        if yy.size <= XX.shape[1] + 1:
            continue
        try:
            fit = ols(yy, XX)
        except StatsError:
            continue
        k = XX.shape[1]
        ll = -0.5 * yy.size * (math.log(2 * math.pi) + math.log(max(fit.sigma2, 1e-300)) + 1)
        ic = -2 * ll + (2 * k if autolag == "aic" else math.log(yy.size) * k)
        if best is None or ic < best[0]:
            best = (ic, p, fit, yy, XX, k)
    if best is None:
        raise StatsError(INVALID_INPUT, "ADF regression could not be estimated (series too short)", 422)
    _, p, fit, yy, XX, k = best
    stat = fit.t_stats[0]
    return {
        "statistic": float(stat),
        "pValueApprox": float(_approx_pvalue(stat, _ADF_CRIT[regression], lower_rejects=True)),
        "criticalValues": _ADF_CRIT[regression],
        "usedLag": p,
        "nobs": int(yy.size),
        "regression": regression,
        "null": "series has a unit root (non-stationary)",
    }


def _kpss(x: np.ndarray, kpss_type: str) -> dict:
    n = x.size
    t = np.arange(n, dtype=float)
    if kpss_type == "trend":
        X = np.column_stack([np.ones(n), t])
    else:
        X = np.ones((n, 1))
    fit = ols(x, X)
    resid = np.array(fit.residuals)
    S = np.cumsum(resid)
    s2 = float(np.sum(resid ** 2)) / n
    # Newey–West long-run variance with Bartlett weights
    lags = int(4 * (n / 100.0) ** 0.25)
    lr = s2
    for l in range(1, lags + 1):
        w = 1.0 - l / (lags + 1.0)
        lr += 2 * w * float(np.sum(resid[l:] * resid[:-l])) / n
    if lr <= 0:
        lr = s2 if s2 > 0 else 1e-300
    stat = float(np.sum(S ** 2) / (n ** 2 * lr))
    return {
        "statistic": stat,
        "pValueApprox": float(_approx_pvalue(stat, _KPSS_CRIT[kpss_type], lower_rejects=False)),
        "criticalValues": _KPSS_CRIT[kpss_type],
        "lags": lags,
        "nobs": n,
        "type": kpss_type,
        "null": "series is level-stationary" if kpss_type == "level" else "series is trend-stationary",
    }


def run(args: dict) -> dict:
    x = to_float_array(args.get("values"), "values")
    require_min_length(x, 8, "values")
    x = x[np.isfinite(x)]
    test = get_str(args, "test", "both")
    if test not in ("adf", "kpss", "both"):
        raise StatsError(INVALID_INPUT, "test must be adf, kpss or both")
    regression = get_str(args, "regression", "c")
    if regression not in _ADF_CRIT:
        raise StatsError(INVALID_INPUT, "regression must be c, ct or n")
    autolag = get_str(args, "autolag", "aic")
    max_lags = get_int(args, "maxLags", 0, minimum=0)
    kpss_type = get_str(args, "kpssType", "level")
    if kpss_type not in _KPSS_CRIT:
        raise StatsError(INVALID_INPUT, "kpssType must be level or trend")

    results: dict = {}
    warnings: list[str] = []
    if test in ("adf", "both"):
        results["adf"] = _adf(x, regression, max_lags, autolag)
    if test in ("kpss", "both"):
        results["kpss"] = _kpss(x, kpss_type)

    interpretation = None
    if test == "both":
        adf_stationary = results["adf"]["pValueApprox"] < 0.05
        kpss_stationary = results["kpss"]["pValueApprox"] > 0.05
        if adf_stationary and kpss_stationary:
            interpretation = "Both tests indicate stationarity."
        elif not adf_stationary and not kpss_stationary:
            interpretation = "Both tests indicate non-stationarity (unit root)."
        else:
            interpretation = (
                "ADF and KPSS disagree — treat the stationarity conclusion as "
                "fragile; inspect the graph and consider differencing."
            )
            warnings.append("ADF and KPSS disagree on stationarity")
    results["interpretation"] = interpretation

    return make_response(
        "calculate_stationarity",
        {"test": test, "regression": regression, "autolag": autolag, "kpssType": kpss_type},
        summary={"observations": int(x.size), "interpretation": interpretation},
        results=results,
        diagnostics={"note": "p-values are table-interpolated approximations; test statistics are exact"},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
