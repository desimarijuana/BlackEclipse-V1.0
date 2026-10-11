"""Deterministic estimation layer (§9–§10) for portfolio construction.

Expected returns and covariance are the two inputs every optimizer is most
sensitive to, so they are computed here from explicit, documented estimators —
never invented by the model. Nothing in this module returns a fabricated zero:
when an input is insufficient the estimate is `None` with a reason.

Units convention: `returns` are per-period simple (or log) returns; `periods` is
the assumed number of periods per year used only for annualization. Covariance
is returned in the same per-period units unless `annualize=True`.

Estimators
----------
Expected returns (`estimate_expected_returns`):
  * ``arithmetic`` — sample mean (the unbiased estimator of the arithmetic mean).
  * ``geometric``  — geometric mean of gross returns (compounded growth), which is
                     NOT interchangeable with the arithmetic mean in a
                     mean-variance objective; recorded so callers cannot conflate.
  * ``ewma``       — exponentially weighted mean (half-life in periods).
  * ``shrinkage``  — shrinks the arithmetic mean toward the grand mean, the
                     standard remedy for estimation error in μ.
  * ``user``       — caller-supplied (validated for length/finiteness only).

Covariance (`estimate_covariance`):
  * ``sample``     — the sample covariance matrix (ddof configurable).
  * ``ewma``       — exponentially weighted covariance.
  * ``shrinkage``  — shrinks the sample covariance toward a diagonal target
                     (``auto`` intensity ``min(1, N/T)`` or an explicit δ).
  * ``diagonal``   — sample variances with zero off-diagonal (independence).

Every covariance result carries a `diagnostics` block: symmetry, finiteness,
positive-semidefiniteness (min eigenvalue), condition number, and whether a
documented regularization was applied. An invalid matrix is reported, never
silently replaced.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import numpy as np

TRADING_DAYS = 252

RETURN_METHODS = ("arithmetic", "geometric", "ewma", "shrinkage", "user")
COV_METHODS = ("sample", "ewma", "shrinkage", "diagonal")


# ── Alignment ─────────────────────────────────────────────────────────────────

def align_returns(
    series: dict[str, Sequence[dict[str, Any]]],
    *,
    log: bool = False,
    frequency: int = TRADING_DAYS,
) -> dict[str, Any]:
    """Date-align per-symbol price series on their common dates and return
    per-symbol return lists. Missing dates are dropped, never forward-filled to
    zero (which would fabricate a zero return).

    Each series entry is a dict with a date/timestamp key (``date`` or
    ``timestamp``) and a close/value key (``close`` or ``value``). Symbols with
    fewer than two usable observations on the common calendar are excluded with
    a reason. `diagnostics` records coverage so an exclusion is never silent.
    """
    prepared: dict[str, dict[str, float]] = {}
    excluded: dict[str, str] = {}
    for symbol, rows in series.items():
        values: dict[str, float] = {}
        for row in rows or []:
            date = row.get("date") or row.get("timestamp")
            raw = row.get("close", row.get("value"))
            if date is None or raw is None:
                continue
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            if price > 0:
                values[str(date)] = price
        if len(values) < 2:
            excluded[symbol] = "fewer than two usable price observations"
            continue
        prepared[symbol] = values

    if not prepared:
        return {"available": False, "reason": "no symbol has usable price history",
                "returns": {}, "symbols": [], "excluded": excluded}

    common = set(next(iter(prepared.values())))
    for values in prepared.values():
        common &= set(values)
    dates = sorted(common)
    if len(dates) < 3:
        return {"available": False, "reason": "fewer than three common dates across the universe",
                "returns": {}, "symbols": [], "excluded": excluded, "commonDates": len(dates)}

    returns: dict[str, list[float]] = {}
    for symbol, values in prepared.items():
        out: list[float] = []
        for i in range(1, len(dates)):
            prev, cur = values[dates[i - 1]], values[dates[i]]
            ratio = cur / prev
            out.append(math.log(ratio) if log else ratio - 1.0)
        returns[symbol] = out
    return {
        "available": True,
        "symbols": sorted(returns),
        "returns": returns,
        "commonDates": len(dates),
        "observations": len(dates) - 1,
        "frequency": frequency,
        "returnType": "log" if log else "simple",
        "excluded": excluded,
    }


# ── Expected returns ──────────────────────────────────────────────────────────

def estimate_expected_returns(
    returns: dict[str, Sequence[float]],
    *,
    method: str = "arithmetic",
    half_life: float = 60.0,
    shrinkage: Optional[float] = None,
    user: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Estimate per-period expected returns for every symbol. Returns
    `available: False` with a reason when the method cannot be applied."""
    symbols = sorted(returns)
    if not symbols:
        return {"available": False, "reason": "no return series supplied", "expectedReturns": {}}
    series = {s: [float(x) for x in returns[s]] for s in symbols}
    lengths = {s: len(series[s]) for s in symbols}
    if any(lengths[s] < 2 for s in symbols):
        short = [s for s in symbols if lengths[s] < 2]
        return {"available": False, "reason": f"insufficient observations for {short}",
                "expectedReturns": {}}

    meta: dict[str, Any] = {"method": method}
    if method == "user":
        if user is None:
            return {"available": False, "reason": "method 'user' requires explicit expected returns",
                    "expectedReturns": {}}
        mu = {s: float(user.get(s)) for s in symbols if user.get(s) is not None}
        if len(mu) != len(symbols):
            missing = [s for s in symbols if s not in mu]
            return {"available": False, "reason": f"user expected returns missing for {missing}",
                    "expectedReturns": {}}
        out = mu
    elif method == "arithmetic":
        out = {s: sum(series[s]) / len(series[s]) for s in symbols}
    elif method == "geometric":
        out = {s: _geometric_mean(series[s]) for s in symbols}
        meta["note"] = ("geometric (compounded) mean — not interchangeable with arithmetic in a "
                        "mean-variance objective")
    elif method == "ewma":
        out = {s: _ewma_mean(series[s], half_life) for s in symbols}
        meta["halfLife"] = half_life
    elif method == "shrinkage":
        grand = sum(sum(series[s]) / len(series[s]) for s in symbols) / len(symbols)
        if shrinkage is None:
            # James–Stein style auto-intensity: with N assets and average sample
            # length T̄, use δ = N / T̄ (matching the covariance shrinkage
            # heuristic), not N / (N·T̄) — the latter is ~N× too weak.
            total = sum(len(series[s]) for s in symbols)
            mean_len = max(total / max(len(symbols), 1), 1.0)
            delta = min(0.9, max(0.05, len(symbols) / mean_len))
        else:
            delta = min(1.0, max(0.0, float(shrinkage)))
        out = {}
        for s in symbols:
            sample = sum(series[s]) / len(series[s])
            out[s] = (1 - delta) * sample + delta * grand
        meta["shrinkage"] = round(delta, 6)
        meta["target"] = "grand mean"
    else:
        return {"available": False, "reason": f"unknown expected-return method {method!r}",
                "expectedReturns": {}}

    if any(not math.isfinite(v) for v in out.values()):
        return {"available": False, "reason": "non-finite expected return produced",
                "expectedReturns": {}}
    meta["observations"] = {s: lengths[s] for s in symbols}
    return {
        "available": True,
        "method": method,
        "symbols": symbols,
        "expectedReturns": {s: round(out[s], 10) for s in symbols},
        "meta": meta,
    }


def estimate_factor_loadings(
    asset_returns: dict[str, Sequence[float]],
    factor_returns: dict[str, Sequence[float]],
    *, intercept: bool = True,
) -> dict[str, Any]:
    """Estimate per-asset factor loadings by OLS (asset returns on factor returns).

    Returns `loadings` (symbol → factor → beta), the intercept (`alpha`), the
    residual variance and R² per asset. All series are truncated to their common
    length; a singular factor set is solved with a pseudo-inverse. This is the
    estimator behind factor-constrained optimization when loadings are not
    supplied by the caller.
    """
    assets = sorted(asset_returns)
    factors = sorted(factor_returns)
    if not assets or not factors:
        return {"available": False, "reason": "asset and factor returns are both required"}
    length = min([len(asset_returns[a]) for a in assets] + [len(factor_returns[f]) for f in factors])
    if length < len(factors) + (1 if intercept else 0) + 1:
        return {"available": False, "reason": "not enough observations for the factor model",
                "observations": length}
    x_cols = [np.array(list(map(float, factor_returns[f]))[-length:], dtype=float) for f in factors]
    design = np.column_stack(([np.ones(length)] if intercept else []) + x_cols)
    loadings: dict[str, dict[str, float]] = {}
    alpha: dict[str, float] = {}
    resid: dict[str, float] = {}
    r2: dict[str, float] = {}
    for a in assets:
        y = np.array(list(map(float, asset_returns[a]))[-length:], dtype=float)
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        fitted = design @ beta
        residual = y - fitted
        ss_res = float(residual @ residual)
        ss_tot = float(((y - y.mean()) ** 2).sum())
        offset = 1 if intercept else 0
        loadings[a] = {factors[i]: round(float(beta[offset + i]), 10) for i in range(len(factors))}
        if intercept:
            alpha[a] = round(float(beta[0]), 10)
        resid[a] = round(ss_res / max(length - design.shape[1], 1), 12)
        r2[a] = round(1.0 - ss_res / ss_tot, 10) if ss_tot > 0 else None
    return {
        "available": True, "factors": factors, "loadings": loadings, "alpha": alpha or None,
        "residualVariance": resid, "r2": r2, "observations": length, "method": "ols",
    }


def estimate_factor_covariance(
    asset_returns: dict[str, Sequence[float]],
    factor_returns: dict[str, Sequence[float]],
    *, annualize: bool = False, frequency: int = TRADING_DAYS,
    psd_tolerance: float = 1e-10, regularize: bool = True,
) -> dict[str, Any]:
    """Build a factor covariance model Σ = B·F·Bᵀ + D.

    `B` are the OLS factor loadings, `F` the sample covariance of the factors and
    `D` the diagonal idiosyncratic (residual) variances. This is a genuine factor
    risk model: it separates systematic and idiosyncratic risk and avoids
    double-counting them (the systematic part comes only from B·F·Bᵀ; the residual
    variances are the OLS residuals, which are orthogonal to the factors).
    """
    loadings = estimate_factor_loadings(asset_returns, factor_returns)
    if not loadings.get("available"):
        return {"available": False, "reason": loadings.get("reason", "factor model unavailable")}
    symbols = sorted(asset_returns)
    factors = loadings["factors"]
    n, k = len(symbols), len(factors)
    B = np.array([[loadings["loadings"][s][f] for f in factors] for s in symbols], dtype=float)
    # The loadings/residuals were fit on the last `observations` rows of each
    # asset series. The factor covariance MUST use the same trailing window,
    # otherwise Σ = B·F·Bᵀ mixes a short-window B with a full-history F.
    window = loadings["observations"]
    factor_window = {f: list(map(float, factor_returns[f]))[-window:] for f in factors}
    fcov = np.array(_sample_covariance(factors, factor_window, 1), dtype=float)
    idio = np.array([max(loadings["residualVariance"][s], 0.0) for s in symbols], dtype=float)
    systematic = B @ fcov @ B.T
    covariance = systematic + np.diag(idio)
    if annualize:
        covariance = covariance * frequency
        fcov = fcov * frequency
        idio = idio * frequency
        systematic = systematic * frequency
    diagnostics = _covariance_diagnostics(covariance.tolist(), psd_tolerance)
    warnings: list[str] = []
    if not diagnostics["positiveSemidefinite"]:
        if regularize:
            repaired, shift = _nearest_psd(covariance.tolist())
            covariance = np.array(repaired, dtype=float)
            diagnostics["regularized"] = True
            warnings.append(f"factor covariance regularized (+{round(shift, 10)} floor)")
            diagnostics.update(_covariance_diagnostics(covariance.tolist(), psd_tolerance))
        else:
            warnings.append("factor covariance is not positive semidefinite")
    return {
        "available": True,
        "model": "factor",
        "symbols": symbols,
        "factors": factors,
        "loadings": loadings["loadings"],
        "alpha": loadings.get("alpha"),
        "r2": loadings.get("r2"),
        "factorCovariance": [[round(float(fcov[i][j]), 14) for j in range(k)] for i in range(k)],
        "idiosyncraticVariance": {symbols[i]: round(float(idio[i]), 14) for i in range(n)},
        "systematicVariance": {symbols[i]: round(float(systematic[i][i]), 14) for i in range(n)},
        "covariance": [[round(float(covariance[i][j]), 14) for j in range(n)] for i in range(n)],
        "annualized": annualize,
        "observations": loadings["observations"],
        "diagnostics": diagnostics,
        "warnings": warnings,
    }


def _geometric_mean(xs: Sequence[float]) -> float:
    log_sum = 0.0
    for x in xs:
        if 1.0 + x <= 0:
            return float("nan")
        log_sum += math.log(1.0 + x)
    return math.expm1(log_sum / len(xs))


def _ewma_mean(xs: Sequence[float], half_life: float) -> float:
    lam = 0.5 ** (1.0 / max(half_life, 1e-9))
    weight_sum = 0.0
    total = 0.0
    w = 1.0
    for x in reversed(xs):
        total += w * x
        weight_sum += w
        w *= lam
    return total / weight_sum if weight_sum else float("nan")


# ── Covariance ────────────────────────────────────────────────────────────────

def estimate_covariance(
    returns: dict[str, Sequence[float]],
    *,
    method: str = "sample",
    half_life: float = 60.0,
    shrinkage: Optional[float] = None,
    ddof: int = 1,
    annualize: bool = False,
    frequency: int = TRADING_DAYS,
    psd_tolerance: float = 1e-10,
    regularize: bool = True,
) -> dict[str, Any]:
    """Estimate the covariance matrix aligned to `sorted(returns)`."""
    symbols = sorted(returns)
    n = len(symbols)
    if n == 0:
        return {"available": False, "reason": "no return series supplied",
                "symbols": [], "covariance": []}
    lengths = {s: len(returns[s]) for s in symbols}
    if any(lengths[s] < 2 for s in symbols):
        return {"available": False, "reason": "every series needs >= 2 observations",
                "symbols": symbols, "covariance": []}

    if method == "ewma":
        matrix, used = _ewma_covariance(symbols, returns, half_life), min(lengths.values())
    elif method == "sample":
        matrix, used = _sample_covariance(symbols, returns, ddof), min(lengths.values())
    elif method == "diagonal":
        sample = _sample_covariance(symbols, returns, ddof)
        matrix = [[sample[i][i] if i == j else 0.0 for j in range(n)] for i in range(n)]
        used = min(lengths.values())
    elif method == "shrinkage":
        sample = _sample_covariance(symbols, returns, ddof)
        total = sum(lengths.values())
        delta = min(0.9, max(0.05, n / max(total // n, 1))) if shrinkage is None else \
            min(1.0, max(0.0, float(shrinkage)))
        matrix = _shrink_diagonal(sample, delta)
        used = min(lengths.values())
    else:
        return {"available": False, "reason": f"unknown covariance method {method!r}",
                "symbols": symbols, "covariance": []}

    if annualize:
        matrix = [[matrix[i][j] * frequency for j in range(n)] for i in range(n)]

    diagnostics = _covariance_diagnostics(matrix, psd_tolerance)
    warnings: list[str] = []
    if not diagnostics["symmetric"]:
        warnings.append("covariance matrix is not symmetric")
    if not diagnostics["finite"]:
        warnings.append("covariance matrix contains non-finite values")
    if not diagnostics["positiveSemidefinite"]:
        if regularize and diagnostics["finite"] and diagnostics["symmetric"]:
            matrix, shift = _nearest_psd(matrix)
            diagnostics["regularized"] = True
            diagnostics["eigenvalueShift"] = round(shift, 12)
            warnings.append(
                f"covariance was not positive semidefinite; regularized by a "
                f"documented eigenvalue floor (+{round(shift, 8)}); original min eigenvalue "
                f"{diagnostics['minEigenvalue']}")
            diagnostics.update(_covariance_diagnostics(matrix, psd_tolerance))
        else:
            warnings.append("covariance is not positive semidefinite and was not regularized")

    return {
        "available": diagnostics["finite"] and diagnostics["symmetric"],
        "method": method,
        "symbols": symbols,
        "covariance": [[round(matrix[i][j], 14) for j in range(n)] for i in range(n)],
        "volatilities": [round(math.sqrt(max(matrix[i][i], 0.0)), 10) for i in range(n)],
        "annualized": annualize,
        "observations": used,
        "diagnostics": diagnostics,
        "warnings": warnings,
    }


def _sample_covariance(
    symbols: Sequence[str], returns: dict[str, Sequence[float]], ddof: int,
) -> list[list[float]]:
    n = len(symbols)
    # Truncate to the shortest common window so unequal-length series stay
    # aligned instead of building a ragged (object) array.
    length = min(len(returns[s]) for s in symbols)
    data = np.array([list(map(float, returns[s]))[-length:] for s in symbols], dtype=float)
    cov = np.cov(data, ddof=ddof, bias=(ddof == 0))
    if n == 1:
        cov = np.array([[float(np.var(data[0], ddof=ddof))]])
    return np.asarray(cov, dtype=float).tolist()


def _ewma_covariance(
    symbols: Sequence[str], returns: dict[str, Sequence[float]], half_life: float,
) -> list[list[float]]:
    n = len(symbols)
    length = min(len(returns[s]) for s in symbols)
    lam = 0.5 ** (1.0 / max(half_life, 1e-9))
    data = np.array([list(map(float, returns[s]))[-length:] for s in symbols], dtype=float)
    mean = data.mean(axis=1, keepdims=True)
    centered = data - mean
    weights = np.array([lam ** (length - 1 - t) for t in range(length)], dtype=float)
    wsum = float(weights.sum())
    cov = np.zeros((n, n))
    for t in range(length):
        cov += weights[t] * np.outer(centered[:, t], centered[:, t])
    cov /= max(wsum, 1e-12)
    return cov.tolist()


def _shrink_diagonal(sample: list[list[float]], delta: float) -> list[list[float]]:
    n = len(sample)
    return [
        [(1 - delta) * sample[i][j] + (delta * sample[i][i] if i == j else 0.0) for j in range(n)]
        for i in range(n)
    ]


def _covariance_diagnostics(matrix: list[list[float]], tol: float) -> dict[str, Any]:
    n = len(matrix)
    finite = all(math.isfinite(matrix[i][j]) for i in range(n) for j in range(n))
    symmetric = all(abs(matrix[i][j] - matrix[j][i]) <= 1e-12 for i in range(n) for j in range(n))
    out: dict[str, Any] = {
        "size": n, "finite": finite, "symmetric": symmetric,
        "positiveSemidefinite": False, "minEigenvalue": None, "conditionNumber": None,
        "regularized": False,
    }
    if not (finite and symmetric and n > 0):
        return out
    eig = np.linalg.eigvalsh(np.array(matrix, dtype=float))
    min_eig = float(eig.min())
    max_eig = float(eig.max())
    out["minEigenvalue"] = round(min_eig, 12)
    out["conditionNumber"] = round(max_eig / min_eig, 6) if min_eig > 1e-15 else None
    out["positiveSemidefinite"] = min_eig >= -tol
    return out


def _nearest_psd(matrix: list[list[float]], floor: float = 1e-10) -> tuple[list[list[float]], float]:
    """Project a symmetric matrix onto the PSD cone by flooring eigenvalues."""
    arr = np.array(matrix, dtype=float)
    arr = (arr + arr.T) / 2.0
    vals, vecs = np.linalg.eigh(arr)
    shift = 0.0
    if vals.min() < floor:
        shift = floor - vals.min()
        vals = vals + shift
    repaired = vecs @ np.diag(vals) @ vecs.T
    return ((repaired + repaired.T) / 2.0).tolist(), shift


__all__ = [
    "align_returns",
    "estimate_expected_returns",
    "estimate_covariance",
    "estimate_factor_loadings",
    "estimate_factor_covariance",
    "TRADING_DAYS",
    "RETURN_METHODS",
    "COV_METHODS",
]
