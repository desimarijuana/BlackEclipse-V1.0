"""Portfolio risk model: covariance, risk contributions and factor exposures.

Everything here is pure NumPy and deterministic. The estimators are explicit
about their assumptions:

* `sample` — the plain covariance of the supplied return rows;
* `ewma` — exponentially weighted, so recent observations carry more weight;
* `ledoit_wolf` — shrinks the sample covariance toward a scaled identity, which
  is the standard fix for a noisy/near-singular covariance matrix.

A covariance matrix that cannot be estimated (too few rows, a column with no
variance) raises `QuantError`; it is never silently replaced with an identity,
because a fabricated risk model is worse than no risk model.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from .errors import QuantError

PERIODS_PER_YEAR = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
    "1h": 8_760, "4h": 2_190, "1d": 252, "1w": 52, "1mo": 12,
}


def _matrix(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise QuantError("returns must be a 2-D array (rows x assets)")
    if arr.size == 0:
        raise QuantError("returns are empty")
    if not np.all(np.isfinite(arr)):
        raise QuantError("returns contain NaN/inf; clean or drop them explicitly first")
    return arr


def periods_per_year(interval: str) -> float:
    return float(PERIODS_PER_YEAR.get(str(interval), 252))


def correlation_matrix(cov: Any) -> np.ndarray:
    cov = _matrix(cov)
    d = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    if np.any(d <= 0):
        raise QuantError("a zero-variance asset has no correlation")
    corr = cov / np.outer(d, d)
    return np.clip(corr, -1.0, 1.0)


def _ledoit_wolf(returns: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf shrinkage toward a scaled identity.

    This is the analytically simple constant-correlation-free version: the
    target is `mu * I` where `mu = trace(S)/n`, and the shrinkage intensity is
    the ratio of estimated target noise to sample noise, clipped to [0, 1].
    """
    t, n = returns.shape
    if t < 2:
        raise QuantError("at least 2 return rows are required")
    centered = returns - returns.mean(axis=0)
    sample = (centered.T @ centered) / (t - 1)
    mu = float(np.trace(sample) / n)
    target = mu * np.eye(n)
    # Estimate the optimal intensity from the data (Ledoit-Wolf 2004, eq. 14
    # in its diagonal-target form).
    x2 = centered ** 2
    phi = float(np.sum(x2.T @ x2) / t - np.sum(sample ** 2) / t)
    gamma = float(np.sum((sample - target) ** 2))
    if gamma <= 0:
        return sample
    kappa = max(0.0, min(1.0, phi / gamma))
    shrunk = kappa * target + (1.0 - kappa) * sample
    return (shrunk + shrunk.T) / 2.0


def covariance_matrix(returns: Any, *, method: str = "sample",
                      annualize: bool = False, interval: str = "1d",
                      halflife: Optional[float] = None) -> dict[str, Any]:
    """Estimate a covariance matrix with an explicit method.

    Returns a payload with the matrix, labels, method, observations and (when
    annualized) the periods-per-year convention used.
    """
    arr = _matrix(returns)
    t, n = arr.shape
    if method == "sample":
        if t < 2:
            raise QuantError("sample covariance needs at least 2 rows")
        cov = np.cov(arr, rowvar=False, ddof=1)
    elif method == "ewma":
        if t < 2:
            raise QuantError("EWMA covariance needs at least 2 rows")
        hl = float(halflife or max(2.0, t / 4.0))
        decay = 0.5 ** (1.0 / hl)
        weights = decay ** np.arange(t - 1, -1, -1)
        weights = weights / weights.sum()
        mean = np.average(arr, axis=0, weights=weights)
        centered = arr - mean
        cov = (centered * weights[:, None]).T @ centered
        cov = (cov + cov.T) / 2.0
    elif method == "ledoit_wolf":
        if t < 3:
            raise QuantError("Ledoit-Wolf shrinkage needs at least 3 rows")
        cov = _ledoit_wolf(arr)
    else:
        raise QuantError(
            f"unknown covariance method {method!r}",
            detail={"methods": ["sample", "ewma", "ledoit_wolf"]},
        )
    return _payload(cov, arr, method=method, annualize=annualize, interval=interval,
                    observations=t, halflife=halflife)


def _payload(cov: np.ndarray, returns: np.ndarray, *, method: str,
             annualize: bool, interval: str, observations: int,
             halflife: Optional[float]) -> dict[str, Any]:
    n = cov.shape[0]
    # A covariance matrix with a non-positive diagonal is not a covariance.
    diag = np.diag(cov)
    if np.any(diag < -1e-12) or not np.all(np.isfinite(cov)):
        raise QuantError("estimated covariance is not positive semi-definite")
    ppy = periods_per_year(interval) if annualize else 1.0
    scaled = cov * ppy
    return {
        "method": method,
        "observations": observations,
        "assets": n,
        "covariance": scaled.tolist(),
        "volatility": np.sqrt(np.clip(np.diag(scaled), 0.0, None)).tolist(),
        "correlation": correlation_matrix(scaled).tolist(),
        "annualized": bool(annualize),
        "periodsPerYear": ppy,
        "halflife": halflife,
        "conditionNumber": float(np.linalg.cond(scaled)) if n else None,
        "assumptions": {
            "estimator": method,
            "annualization": "per-period covariance x periods-per-year" if annualize else "none",
        },
    }


def portfolio_volatility(weights: Sequence[float], cov: Any) -> float:
    w = np.asarray(weights, dtype=float)
    c = _matrix(cov)
    if w.shape[0] != c.shape[0]:
        raise QuantError("weights and covariance dimensions differ")
    var = float(w @ c @ w)
    return float(np.sqrt(max(0.0, var)))


def risk_contributions(weights: Sequence[float], cov: Any) -> dict[str, Any]:
    """Marginal and component risk contributions (Euler decomposition).

    `component[i]` sums to portfolio volatility for a fully invested book. The
    percentage share is component / volatility.
    """
    w = np.asarray(weights, dtype=float)
    c = _matrix(cov)
    if w.shape[0] != c.shape[0]:
        raise QuantError("weights and covariance dimensions differ")
    vol = portfolio_volatility(w, c)
    if vol <= 0:
        return {"volatility": 0.0, "marginal": [0.0] * len(w),
                "component": [0.0] * len(w), "share": [0.0] * len(w)}
    marginal = (c @ w) / vol
    component = w * marginal
    share = component / vol
    return {
        "volatility": vol,
        "marginal": marginal.tolist(),
        "component": component.tolist(),
        "share": share.tolist(),
    }


def factor_exposures(asset_returns: Any, factor_returns: Any, *,
                     add_intercept: bool = True) -> dict[str, Any]:
    """OLS betas of each asset on the supplied factor returns.

    Returns betas, annualized alpha, R², residuals and standard errors. A design
    matrix that is rank-deficient is refused rather than pseudo-inverted.
    """
    y = _matrix(asset_returns)
    x = _matrix(factor_returns)
    if y.shape[0] != x.shape[0]:
        raise QuantError("asset and factor rows differ")
    if add_intercept:
        x = np.column_stack([np.ones(x.shape[0]), x])
    xtx = x.T @ x
    if np.linalg.matrix_rank(xtx) < xtx.shape[0]:
        raise QuantError("factor design matrix is rank-deficient")
    beta = np.linalg.solve(xtx, x.T @ y)
    resid = y - x @ beta
    dof = max(1, x.shape[0] - x.shape[1])
    sigma2 = (resid ** 2).sum(axis=0) / dof
    try:
        cov_beta = sigma2[None, :] * np.linalg.inv(xtx)[:, :, None]
        se = np.sqrt(np.clip(np.diagonal(cov_beta, axis1=0, axis2=1), 0.0, None))
    except Exception:  # noqa: BLE001
        se = np.full_like(beta, np.nan)
    ss_tot = ((y - y.mean(axis=0)) ** 2).sum(axis=0)
    ss_res = (resid ** 2).sum(axis=0)
    r2 = 1.0 - ss_res / np.where(ss_tot == 0, np.nan, ss_tot)
    intercept = beta[0] if add_intercept else np.zeros(y.shape[1])
    loadings = beta[1:] if add_intercept else beta
    return {
        "alpha": intercept.tolist(),
        "betas": loadings.T.tolist(),          # asset -> factor loadings
        "standardErrors": se.T.tolist(),
        "r2": np.nan_to_num(r2, nan=0.0).tolist(),
        "residuals": resid.tolist(),
        "observations": int(y.shape[0]),
        "factors": int(loadings.shape[0]),
        "assets": int(y.shape[1]),
    }


def tracking_error(active_returns: Any, *, annualize: bool = True,
                   interval: str = "1d") -> dict[str, Any]:
    arr = np.asarray(active_returns, dtype=float).ravel()
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return {"available": False, "reason": "fewer than 2 active-return observations"}
    std = float(arr.std(ddof=1))
    ppy = periods_per_year(interval) if annualize else 1.0
    return {
        "available": True, "trackingError": std * float(np.sqrt(ppy)),
        "perPeriod": std, "observations": int(arr.size),
        "annualized": bool(annualize), "periodsPerYear": ppy,
    }


def portfolio_beta(weights: Sequence[float], asset_betas: Any) -> float:
    w = np.asarray(weights, dtype=float)
    b = np.asarray(asset_betas, dtype=float).ravel()
    if w.shape[0] != b.shape[0]:
        raise QuantError("weights and betas dimensions differ")
    return float(w @ b)


__all__ = [
    "PERIODS_PER_YEAR",
    "correlation_matrix",
    "covariance_matrix",
    "factor_exposures",
    "periods_per_year",
    "portfolio_beta",
    "portfolio_volatility",
    "risk_contributions",
    "tracking_error",
]
