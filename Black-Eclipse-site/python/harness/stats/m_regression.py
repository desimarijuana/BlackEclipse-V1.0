"""calculate_regression — OLS/WLS/HC3/HAC + ridge/lasso + chronological validation."""

from __future__ import annotations

import math

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
from .dist import chi2_sf
from .linreg import ols

DESCRIPTION = (
    "Linear regression: ordinary and weighted least squares, heteroskedasticity-"
    "consistent (HC0/HC1/HC3) and Newey–West (HAC) standard errors, ridge and "
    "lasso regularization, coefficient tables with confidence intervals, "
    "residual diagnostics (Durbin–Watson, normality, heteroskedasticity) and "
    "chronological out-of-sample evaluation. Time order is never shuffled."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "y": {"type": "array", "items": {"type": "number"}},
        "x": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
              "description": "Design matrix, rows = observations, columns = features."},
        "featureNames": {"type": "array", "items": {"type": "string"}},
        "intercept": {"type": "boolean", "default": True},
        "method": {"type": "string", "enum": ["ols", "wls", "ridge", "lasso"], "default": "ols"},
        "alpha": {"type": "number", "default": 1.0, "description": "Ridge/lasso penalty."},
        "weights": {"type": "array", "items": {"type": "number"}},
        "covType": {"type": "string", "enum": ["classical", "HC0", "HC1", "HC3", "HAC"],
                    "default": "classical"},
        "trainFraction": {"type": "number", "description": "Chronological train split (e.g. 0.7)."},
        "confidence": {"type": "number", "default": 0.95},
    },
    "required": ["y", "x"],
}


def _ridge(X: np.ndarray, y: np.ndarray, alpha: float, intercept: bool) -> np.ndarray:
    k = X.shape[1]
    pen = np.eye(k) * alpha
    if intercept:
        pen[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + pen, X.T @ y)


def _lasso(X: np.ndarray, y: np.ndarray, alpha: float, intercept: bool, max_iter: int = 500) -> np.ndarray:
    n, k = X.shape
    if intercept:
        Xc = X.copy()
        Xc[:, 0] = 1.0
    beta = np.zeros(k)
    # center y for the intercept handling
    if intercept:
        y_mean = y.mean()
        yc = y - y_mean
    else:
        yc = y
    Xn = Xc if intercept else X
    col_sq = (Xn ** 2).sum(axis=0)
    for _ in range(max_iter):
        beta_old = beta.copy()
        for j in range(k):
            if intercept and j == 0:
                continue
            r = yc - Xn @ beta + Xn[:, j] * beta[j]
            rho = float(Xn[:, j] @ r)
            if col_sq[j] == 0:
                beta[j] = 0.0
                continue
            # soft threshold
            beta[j] = np.sign(rho) * max(0.0, abs(rho) - alpha * n / 2.0) / col_sq[j]
        if intercept:
            beta[0] = y_mean - float(Xn[:, 1:].mean(axis=0) @ beta[1:])
        if np.max(np.abs(beta - beta_old)) < 1e-8:
            break
    return beta


def _durbin_watson(resid: np.ndarray) -> float:
    num = float(np.sum(np.diff(resid) ** 2))
    den = float(np.sum(resid ** 2))
    return num / den if den > 0 else float("nan")


def _jarque_bera(resid: np.ndarray) -> dict:
    n = resid.size
    if n < 8:
        return {"statistic": None, "pValue": None}
    m = resid.mean()
    s = resid.std(ddof=0)
    if s == 0:
        return {"statistic": None, "pValue": None}
    z = (resid - m) / s
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))
    jb = n / 6.0 * (skew ** 2 + (kurt - 3.0) ** 2 / 4.0)
    return {"statistic": float(jb), "pValue": float(chi2_sf(jb, 2)), "skew": skew, "kurtosis": kurt}


def run(args: dict) -> dict:
    y = to_float_array(args.get("y"), "y")
    x_raw = args.get("x")
    if not x_raw:
        raise StatsError(INVALID_INPUT, "x (design matrix) is required")
    X = np.asarray(x_raw, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    if X.shape[0] != y.size:
        raise StatsError(INVALID_INPUT, f"x has {X.shape[0]} rows but y has {y.size}")
    X = np.where(np.isfinite(X), X, np.nan)
    mask = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[mask], X[mask]
    require_min_length(y, 4, "y")

    method = get_str(args, "method", "ols")
    intercept = bool(args.get("intercept", True))
    alpha = get_float(args, "alpha", 1.0)
    cov_type = get_str(args, "covType", "classical")
    confidence = float(args.get("confidence", 0.95))
    names = args.get("featureNames") or [f"x{i}" for i in range(X.shape[1])]
    if intercept:
        names = ["intercept", *names]
        Xd = np.column_stack([np.ones(X.shape[0]), X])
    else:
        Xd = X
    warnings: list[str] = []

    if method in ("ols", "wls"):
        weights = None
        if method == "wls":
            w = args.get("weights")
            if not w:
                raise StatsError(INVALID_INPUT, "wls requires weights")
            weights = to_float_array(w, "weights")
            if weights.size != y.size:
                raise StatsError(INVALID_INPUT, "weights length must match y")
        fit = ols(y, Xd, names=names, weights=weights, cov=cov_type, confidence=confidence)
        coef = fit.coefficients
        resid = np.array(fit.residuals)
        fitted = np.array(fit.fitted)
        coef_table = fit.to_dict()
    else:
        coef = _ridge(Xd, y, alpha, intercept) if method == "ridge" else _lasso(Xd, y, alpha, intercept)
        fitted = Xd @ coef
        resid = y - fitted
        tss = float(((y - y.mean()) ** 2).sum())
        rss = float((resid ** 2).sum())
        r2 = 1.0 - rss / tss if tss > 0 else 0.0
        coef_table = {
            "names": names,
            "coefficients": [float(c) for c in coef],
            "rSquared": float(r2),
            "adjRSquared": None,
            "method": method,
            "alpha": alpha,
        }
        if cov_type != "classical":
            warnings.append("robust/HAC standard errors are reported only for OLS/WLS, not regularized fits")

    diagnostics = {
        "durbinWatson": _durbin_watson(resid),
        "jarqueBera": _jarque_bera(resid),
        "residualMean": float(resid.mean()),
        "residualStd": float(resid.std(ddof=1)) if resid.size > 1 else None,
    }

    results = {
        "coefficients": coef_table,
        "residuals": as_list(resid),
        "fitted": as_list(fitted),
        "diagnostics": diagnostics,
    }

    train_fraction = args.get("trainFraction")
    if train_fraction:
        tf = float(train_fraction)
        if not 0.2 <= tf < 1.0:
            raise StatsError(INVALID_INPUT, "trainFraction must be in [0.2, 1.0)")
        split = int(y.size * tf)
        if split < Xd.shape[1] + 1 or y.size - split < 2:
            raise StatsError(INVALID_INPUT, "insufficient data for the requested train/test split", 422)
        fit_tr = ols(y[:split], Xd[:split], names=names, cov=cov_type)
        pred = Xd[split:] @ np.array(fit_tr.coefficients)
        actual = y[split:]
        ss_res = float(((actual - pred) ** 2).sum())
        ss_tot = float(((actual - actual.mean()) ** 2).sum())
        oos_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        results["outOfSample"] = {
            "trainSize": split, "testSize": int(y.size - split),
            "rmse": math.sqrt(ss_res / actual.size), "rSquared": oos_r2,
            "actual": as_list(actual), "predicted": as_list(pred),
        }

    return make_response(
        "calculate_regression",
        {"method": method, "intercept": intercept, "covType": cov_type, "alpha": alpha},
        summary={"observations": int(y.size), "features": int(X.shape[1]), "method": method,
                 "rSquared": coef_table.get("rSquared")},
        results=results, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
