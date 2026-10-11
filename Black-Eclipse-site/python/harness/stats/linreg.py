"""Ordinary / weighted least squares with robust covariance estimators.

Shared by `calculate_beta`, `calculate_regression`, `analyze_lead_lag` and the
regime/cointegration modules. Standard errors support classical, HC0/HC1/HC3
(heteroskedasticity-consistent) and Newey–West (HAC) inference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .base import INVALID_INPUT, SINGULAR_MATRIX, StatsError
from .dist import t_two_sided_p, t_ppf


@dataclass
class OLSResult:
    names: list[str]
    coefficients: list[float]
    std_errors: list[float]
    t_stats: list[float]
    p_values: list[float]
    ci_lower: list[float]
    ci_upper: list[float]
    r_squared: float
    adj_r_squared: float
    f_stat: Optional[float]
    f_pvalue: Optional[float]
    n: int
    df_resid: int
    sigma2: float
    residuals: list[float] = field(default_factory=list)
    fitted: list[float] = field(default_factory=list)
    cov_type: str = "classical"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "names": self.names,
            "coefficients": self.coefficients,
            "stdErrors": self.std_errors,
            "tStats": self.t_stats,
            "pValues": self.p_values,
            "ciLower": self.ci_lower,
            "ciUpper": self.ci_upper,
            "rSquared": self.r_squared,
            "adjRSquared": self.adj_r_squared,
            "fStatistic": self.f_stat,
            "fPValue": self.f_pvalue,
            "n": self.n,
            "dfResid": self.df_resid,
            "sigma2": self.sigma2,
            "covType": self.cov_type,
            "warnings": self.warnings,
        }


def _covariance(X: np.ndarray, resid: np.ndarray, xtx_inv: np.ndarray, kind: str, lags: int) -> np.ndarray:
    n, k = X.shape
    if kind == "classical":
        s2 = float(resid @ resid) / (n - k)
        return s2 * xtx_inv
    if kind in ("HC0", "HC1", "HC3"):
        if kind == "HC0":
            w = resid ** 2
        elif kind == "HC1":
            w = resid ** 2 * (n / (n - k))
        else:  # HC3
            h = np.einsum("ij,jk,ik->i", X, xtx_inv, X)
            w = (resid / np.clip(1.0 - h, 1e-8, None)) ** 2
        meat = (X * w[:, None]).T @ X
        return xtx_inv @ meat @ xtx_inv
    if kind == "HAC":
        u = X * resid[:, None]
        s = u.T @ u
        for l in range(1, lags + 1):
            weight = 1.0 - l / (lags + 1.0)
            gamma = u[l:].T @ u[:-l]
            s += weight * (gamma + gamma.T)
        return xtx_inv @ s @ xtx_inv
    raise StatsError(INVALID_INPUT, f"unknown covariance type: {kind}")


def ols(
    y: np.ndarray,
    X: np.ndarray,
    *,
    names: Optional[list[str]] = None,
    weights: Optional[np.ndarray] = None,
    cov: str = "classical",
    hac_lags: Optional[int] = None,
    confidence: float = 0.95,
) -> OLSResult:
    """Fit y = X beta. `X` must already include any intercept column."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    n, k = X.shape
    if y.size != n:
        raise StatsError(INVALID_INPUT, "y and X must have the same number of rows")
    if n <= k:
        raise StatsError(INVALID_INPUT, f"need more observations ({n}) than parameters ({k})")

    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if np.any(w <= 0):
        raise StatsError(INVALID_INPUT, "weights must be positive")
    sw = np.sqrt(w)
    Xw, yw = X * sw[:, None], y * sw
    try:
        xtx_inv = np.linalg.inv(Xw.T @ Xw)
    except np.linalg.LinAlgError as exc:
        raise StatsError(SINGULAR_MATRIX, "design matrix is singular (collinear regressors)") from exc
    beta = xtx_inv @ (Xw.T @ yw)
    fitted = X @ beta
    resid = y - fitted
    df_resid = n - k
    sigma2 = float(resid @ resid) / df_resid if df_resid > 0 else float("nan")
    tss = float(((y - y.mean()) ** 2).sum())
    rss = float((resid ** 2).sum())
    r2 = 1.0 - rss / tss if tss > 0 else 0.0
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / df_resid if df_resid > 0 and tss > 0 else 0.0

    kind = cov
    if cov == "HAC" and hac_lags is None:
        hac_lags = max(1, int(round(4 * (n / 100.0) ** (2.0 / 9.0))))
    covm = _covariance(Xw, resid * sw, xtx_inv, kind, hac_lags or 0)
    se = np.sqrt(np.clip(np.diag(covm), 0.0, None))
    warnings: list[str] = []
    with np.errstate(divide="ignore", invalid="ignore"):
        tstats = beta / se
    pvals = np.array([t_two_sided_p(float(t), df_resid) if np.isfinite(t) else float("nan") for t in tstats])
    crit = t_ppf(1.0 - (1.0 - confidence) / 2.0, df_resid)
    ci_lo = beta - crit * se
    ci_hi = beta + crit * se

    f_stat = f_p = None
    if k > 1 and df_resid > 0 and tss > 0:
        r2_clamped = min(max(r2, 0.0), 1.0)
        if r2_clamped < 1.0:
            f_stat = (r2_clamped / (k - 1)) / ((1.0 - r2_clamped) / df_resid)
            from .dist import f_sf  # noqa: PLC0415

            f_p = float(f_sf(f_stat, k - 1, df_resid))
    if se.min() == 0:
        warnings.append("zero standard error on at least one coefficient (perfect fit or collinearity)")

    return OLSResult(
        names=names or [f"x{i}" for i in range(k)],
        coefficients=[float(b) for b in beta],
        std_errors=[float(s) for s in se],
        t_stats=[float(t) for t in tstats],
        p_values=[float(p) for p in pvals],
        ci_lower=[float(x) for x in ci_lo],
        ci_upper=[float(x) for x in ci_hi],
        r_squared=float(r2), adj_r_squared=float(adj_r2),
        f_stat=float(f_stat) if f_stat is not None else None,
        f_pvalue=f_p,
        n=n, df_resid=df_resid, sigma2=float(sigma2),
        residuals=[float(r) for r in resid], fitted=[float(f) for f in fitted],
        cov_type=cov, warnings=warnings,
    )


__all__ = ["OLSResult", "ols"]
