"""Reproduction harness for established methods.

Reproduction is deliberately separate from a trading adaptation. This module
runs the *method*, records the observed estimates and compares them with a
published benchmark when one is supplied. It never turns a good estimate into a
trading claim, and it never invents a missing benchmark.

Only implementations Eclipse can actually run are listed in `_BUILTINS`. Any
other method returns `inconclusive` with a reason — an honest gap, not a faked
result. Paper-derived code, when added, must run in the existing isolated worker.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable, Iterable

from ..errors import QuantError
from .catalog import get_catalog_method

_BUILTINS: dict[str, str] = {
    "stats.ornstein_uhlenbeck": "ornstein_uhlenbeck",
    "volatility.ewma": "ewma_volatility",
    "volatility.realized": "realized_volatility",
    "volatility.garch_11": "garch_11",
    "volatility.gjr_garch": "gjr_garch",
    "volatility.egarch_11": "egarch",
    "volatility.har_rv": "har_rv",
    "statarb.cointegration": "engle_granger",
    "regime.hmm": "hmm",
    "risk.evt_gpd": "evt_gpd",
    "factor.capm": "capm",
    "factor.fama_french": "capm",
    "execution.almgren_chriss": "almgren_chriss",
}


def _rows(series: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in series or []:
        if isinstance(row, dict):
            out.append(row)
        elif hasattr(row, "close"):
            out.append({
                "ts": getattr(row, "timestamps", [None] * 1)[0] if hasattr(row, "timestamps") else None,
                "close": float(row.close),
            })
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _var(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = _mean(values)
    return sum((v - mu) ** 2 for v in values) / (len(values) - 1)


def _std(values: list[float]) -> float:
    return math.sqrt(max(0.0, _var(values)))


def _ols(y: list[float], x: list[float]) -> tuple[float, float, list[float]]:
    n = min(len(y), len(x))
    if n < 3:
        raise QuantError("at least three observations are required")
    y, x = y[:n], x[:n]
    mx, my = _mean(x), _mean(y)
    denom = sum((xi - mx) ** 2 for xi in x)
    if denom <= 0:
        raise QuantError("the explanatory series has no variation")
    slope = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / denom
    intercept = my - slope * mx
    residuals = [yi - (intercept + slope * xi) for xi, yi in zip(x, y)]
    return intercept, slope, residuals


def _r2(y: list[float], residuals: list[float]) -> float:
    total = sum((yi - _mean(y)) ** 2 for yi in y)
    if total <= 0:
        return 0.0
    return 1.0 - sum(r * r for r in residuals) / total


def _log_returns(rows: list[dict[str, Any]]) -> list[float]:
    closes = [float(r["close"]) for r in rows if r.get("close") is not None]
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


def _ou(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    transform = str(params.get("transform") or "raw").lower()
    values = [float(r["close"]) for r in rows if r.get("close") is not None]
    if transform == "log":
        values = [math.log(v) for v in values if v > 0]
    if len(values) < 30:
        raise QuantError("the OU estimate needs at least 30 observations")
    y, x = values[1:], values[:-1]
    intercept, slope, residuals = _ols(y, x)
    if not (0 < slope < 1):
        return {
            "status": "inconclusive",
            "reason": "the estimated AR(1) coefficient is outside (0,1); the series "
                      "is not mean-reverting over this window",
            "metrics": {"slope": slope, "intercept": intercept},
        }
    theta = -math.log(slope)
    mu = intercept / (1 - slope)
    sigma = _std(residuals)
    half_life = math.log(2) / theta if theta > 0 else None

    split = len(values) // 2
    stability = {}
    try:
        _, b1, _ = _ols(values[1:split], values[:split - 1])
        _, b2, _ = _ols(values[split + 1:], values[split:-1])
        hl1 = math.log(2) / -math.log(b1) if 0 < b1 < 1 else None
        hl2 = math.log(2) / -math.log(b2) if 0 < b2 < 1 else None
        if hl1 and hl2:
            stability = {"halfLifeFirstHalf": hl1, "halfLifeSecondHalf": hl2,
                         "relativeChange": abs(hl2 - hl1) / max(abs(hl1), 1e-9)}
    except QuantError:
        stability = {}

    train = len(values) * 7 // 10
    oos: dict[str, Any] = {}
    try:
        a_tr, b_tr, _ = _ols(values[1:train], values[:train - 1])
        test_y, test_x = values[train + 1:], values[train:-1]
        if test_y:
            mse = sum((y - (a_tr + b_tr * x)) ** 2 for y, x in zip(test_y, test_x)) / len(test_y)
            baseline = sum((y - _mean(values[:train])) ** 2 for y in test_y) / len(test_y)
            oos = {"testMse": mse, "baselineMse": baseline,
                   "skill": 1 - mse / baseline if baseline > 0 else None,
                   "testObservations": len(test_y)}
    except QuantError:
        oos = {}

    return {
        "status": "OK",
        "metrics": {
            "theta": theta, "mu": mu, "sigma": sigma, "halfLife": half_life,
            "ar1": slope, "rSquared": _r2(y, residuals), "observations": len(values),
            "parameterStability": stability, "outOfSample": oos,
            "transform": transform,
        },
    }


def _ewma(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    returns = _log_returns(rows)
    if len(returns) < 20:
        raise QuantError("EWMA needs at least 20 returns")
    lam = float(params.get("lambda") or params.get("decay") or 0.94)
    if not 0 < lam < 1:
        raise QuantError("lambda must be between 0 and 1")
    variance = _var(returns[:10]) or 1e-12
    series: list[float] = []
    for r in returns:
        variance = lam * variance + (1 - lam) * r * r
        series.append(math.sqrt(variance))
    last = series[-1]
    sensitivity = {}
    for delta in (-0.02, 0.02):
        alt = lam + delta
        if 0 < alt < 1:
            v = _var(returns[:10]) or 1e-12
            for r in returns:
                v = alt * v + (1 - alt) * r * r
            sensitivity[f"lambda{alt:.2f}"] = math.sqrt(v)
    return {
        "status": "OK",
        "metrics": {
            "lambda": lam, "lastVolatility": last,
            "meanVolatility": _mean(series), "observations": len(returns),
            "lambdaSensitivity": sensitivity,
        },
    }


def _realized(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    from collections import defaultdict

    bucket_field = str(params.get("dateField") or "")
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        close = row.get("close")
        if close is None:
            continue
        ts = str(row.get(bucket_field) if bucket_field else row.get("ts") or row.get("timestamp") or "")
        key = ts[:10] if ts else "all"
        buckets[key].append(float(close))
    rv: list[float] = []
    for key, closes in buckets.items():
        if len(closes) < 3:
            continue
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
                if closes[i - 1] > 0 and closes[i] > 0]
        rv.append(sum(r * r for r in rets))
    if not rv:
        raise QuantError("realized volatility needs intraday closes within at least one day")
    return {
        "status": "OK",
        "metrics": {
            "meanRealizedVariance": _mean(rv),
            "lastRealizedVariance": rv[-1],
            "observations": len(rv),
            "note": "RV is sensitive to the sampling frequency and to microstructure noise.",
        },
    }


def _garch_negloglik(returns: list[float], omega: float, alpha: float,
                     beta: float, floor: float) -> float:
    var = _var(returns) or 1e-12
    total = 0.0
    for r in returns:
        var = omega + alpha * r * r + beta * var
        var = max(var, floor)
        total += 0.5 * (math.log(2 * math.pi) + math.log(var) + r * r / var)
    return total


def _garch11(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    returns = _log_returns(rows)
    if len(returns) < 100:
        raise QuantError("GARCH(1,1) needs at least 100 returns for a stable estimate")
    unconditional = _var(returns) or 1e-12
    floor = unconditional * 1e-6
    best: tuple[float, float, float, float] | None = None
    for alpha in (0.02, 0.04, 0.06, 0.08, 0.10, 0.14):
        for beta in (0.70, 0.78, 0.84, 0.88, 0.92, 0.95):
            if alpha + beta >= 0.999:
                continue
            omega = unconditional * (1 - alpha - beta)
            if omega <= 0:
                continue
            nll = _garch_negloglik(returns, omega, alpha, beta, floor)
            if best is None or nll < best[0]:
                best = (nll, omega, alpha, beta)
    if best is None:
        raise QuantError("no admissible GARCH parameter set was found")
    nll, omega, alpha, beta = best
    return {
        "status": "OK",
        "metrics": {
            "omega": omega, "alpha": alpha, "beta": beta,
            "persistence": alpha + beta,
            "logLikelihood": -nll,
            "aic": 2 * 3 + 2 * nll,
            "observations": len(returns),
            "unconditionalVariance": unconditional,
            "note": "A coarse variance-targeting grid MLE; not a full optimiser.",
        },
    }


def _daily_rv(rows: list[dict[str, Any]]) -> list[float]:
    from collections import defaultdict

    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        close = row.get("close")
        if close is None:
            continue
        key = str(row.get("ts") or row.get("timestamp") or "all")[:10]
        buckets[key].append(float(close))
    out: list[float] = []
    for closes in buckets.values():
        if len(closes) < 3:
            continue
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
                if closes[i - 1] > 0 and closes[i] > 0]
        out.append(sum(r * r for r in rets))
    return out


def _ols_multi(y: list[float], columns: list[list[float]]) -> tuple[list[float], float, int]:
    import numpy as np

    n = len(y)
    X = np.column_stack([np.ones(n)] + [np.asarray(col, dtype=float) for col in columns])
    beta, *_ = np.linalg.lstsq(X, np.asarray(y, dtype=float), rcond=None)
    fitted = X @ beta
    resid = np.asarray(y, dtype=float) - fitted
    total = float(np.sum((np.asarray(y) - np.mean(y)) ** 2))
    r2 = 0.0 if total <= 0 else 1.0 - float(np.sum(resid ** 2)) / total
    return [float(b) for b in beta], r2, n


def _har_rv(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    rv = [float(r["rv"]) for r in rows if r.get("rv") is not None] or _daily_rv(rows)
    if len(rv) < 40:
        raise QuantError("HAR-RV needs at least 40 daily realized-variance observations")
    y, d, w, m = [], [], [], []
    for t in range(22, len(rv) - 1):
        y.append(rv[t + 1])
        d.append(rv[t])
        w.append(sum(rv[t - 4:t + 1]) / 5)
        m.append(sum(rv[t - 21:t + 1]) / 22)
    coef, r2, n = _ols_multi(y, [d, w, m])
    return {"status": "OK", "metrics": {
        "intercept": coef[0], "betaDaily": coef[1], "betaWeekly": coef[2],
        "betaMonthly": coef[3], "rSquared": r2, "observations": n,
        "note": "RV must come from intraday data; microstructure noise biases it.",
    }}


def _gjr_garch(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    returns = _log_returns(rows)
    if len(returns) < 100:
        raise QuantError("GJR-GARCH needs at least 100 returns")
    unconditional = _var(returns) or 1e-12
    floor = unconditional * 1e-6
    best = None
    for alpha in (0.02, 0.04, 0.06, 0.08, 0.10):
        for gamma in (0.02, 0.05, 0.08, 0.12):
            for beta in (0.70, 0.80, 0.88, 0.92):
                if alpha + gamma / 2 + beta >= 0.999:
                    continue
                omega = unconditional * (1 - alpha - gamma / 2 - beta)
                if omega <= 0:
                    continue
                var = unconditional
                nll = 0.0
                for r in returns:
                    shock = 1.0 if r < 0 else 0.0
                    var = omega + (alpha + gamma * shock) * r * r + beta * var
                    var = max(var, floor)
                    nll += 0.5 * (math.log(2 * math.pi) + math.log(var) + r * r / var)
                if best is None or nll < best[0]:
                    best = (nll, omega, alpha, gamma, beta)
    if best is None:
        raise QuantError("no admissible GJR-GARCH parameter set was found")
    nll, omega, alpha, gamma, beta = best
    return {"status": "OK", "metrics": {
        "omega": omega, "alpha": alpha, "gamma": gamma, "beta": beta,
        "persistence": alpha + gamma / 2 + beta, "logLikelihood": -nll,
        "observations": len(returns),
        "note": "A coarse variance-targeting grid MLE; not a full optimiser.",
    }}


def _egarch(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    returns = _log_returns(rows)
    if len(returns) < 100:
        raise QuantError("EGARCH needs at least 100 returns")
    unconditional = _var(returns) or 1e-12
    log_uncond = math.log(unconditional)
    best = None
    for alpha in (0.02, 0.05, 0.08, 0.12):
        for gamma in (-0.10, -0.05, 0.0, 0.05, 0.10):
            for beta in (0.80, 0.88, 0.94):
                omega = log_uncond * (1 - beta)
                logvar = log_uncond
                nll = 0.0
                for r in returns:
                    var = max(math.exp(logvar), unconditional * 1e-6)
                    z = r / math.sqrt(var)
                    nll += 0.5 * (math.log(2 * math.pi) + logvar + z * z)
                    logvar = omega + alpha * (abs(z) - math.sqrt(2 / math.pi)) + gamma * z + beta * logvar
                if best is None or nll < best[0]:
                    best = (nll, omega, alpha, gamma, beta)
    if best is None:
        raise QuantError("no admissible EGARCH parameter set was found")
    nll, omega, alpha, gamma, beta = best
    return {"status": "OK", "metrics": {
        "omega": omega, "alpha": alpha, "gamma": gamma, "beta": beta,
        "persistence": beta, "logLikelihood": -nll, "observations": len(returns),
        "note": "A coarse grid MLE; the leverage term is gamma.",
    }}


def _pairs(rows: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    ys, xs = [], []
    for row in rows:
        y = row.get("y", row.get("close_a", row.get("a")))
        x = row.get("x", row.get("close_b", row.get("b")))
        if y is not None and x is not None:
            ys.append(float(y))
            xs.append(float(x))
    return ys, xs


def _engle_granger(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    ys, xs = _pairs(rows)
    if len(ys) < 40:
        raise QuantError("Engle-Granger needs two aligned series with 40+ rows "
                         "(fields y/x or close_a/close_b)")
    intercept, beta, residuals = _ols(ys, xs)
    x, y = residuals[:-1], residuals[1:]
    mean_x = _mean(x)
    denom = sum((v - mean_x) ** 2 for v in x)
    slope = sum((xi - mean_x) * (yi - _mean(y)) for xi, yi in zip(x, y)) / denom if denom else 0.0
    fitted = [_mean(y) + slope * (xi - mean_x) for xi in x]
    resid = [yi - fi for yi, fi in zip(y, fitted)]
    se = math.sqrt(sum(r * r for r in resid) / max(len(resid) - 2, 1) / denom) if denom else 0.0
    t_stat = slope / se if se else 0.0
    half_life = math.log(2) / -math.log(slope) if 0 < slope < 1 else None
    return {"status": "OK", "metrics": {
        "alpha": intercept, "beta": beta, "residualAr1": slope,
        "adfTStat": t_stat, "halfLife": half_life,
        "rSquared": _r2(ys, residuals), "observations": len(ys),
        "stationaryAt5pct": bool(slope < 1 and t_stat < -2.86),
        "note": "A two-step Engle-Granger check, not a full Johansen test.",
    }}


def _hmm(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    returns = np.asarray(_log_returns(rows), dtype=float)
    if len(returns) < 120:
        raise QuantError("the HMM needs at least 120 returns")
    n_states = max(2, min(int(params.get("n_states") or 2), 4))
    mu = np.quantile(returns, np.linspace(0.2, 0.8, n_states))
    var = np.full(n_states, float(np.var(returns)) or 1e-8)
    A = np.full((n_states, n_states), 0.05 / max(n_states - 1, 1))
    np.fill_diagonal(A, 0.95)
    pi = np.full(n_states, 1.0 / n_states)
    loglik = -math.inf
    for _ in range(30):
        emit = np.zeros((len(returns), n_states))
        for k in range(n_states):
            v = max(var[k], 1e-12)
            emit[:, k] = np.exp(-0.5 * (returns - mu[k]) ** 2 / v) / math.sqrt(2 * math.pi * v)
        emit = np.clip(emit, 1e-300, None)
        alpha = np.zeros_like(emit)
        scale = np.zeros(len(returns))
        alpha[0] = pi * emit[0]
        scale[0] = alpha[0].sum()
        alpha[0] /= scale[0]
        for t in range(1, len(returns)):
            alpha[t] = (alpha[t - 1] @ A) * emit[t]
            scale[t] = alpha[t].sum()
            alpha[t] /= max(scale[t], 1e-300)
        beta = np.ones_like(emit)
        for t in range(len(returns) - 2, -1, -1):
            beta[t] = A @ (emit[t + 1] * beta[t + 1])
            beta[t] /= max(beta[t].sum(), 1e-300)
        gamma = alpha * beta
        gamma /= np.clip(gamma.sum(axis=1, keepdims=True), 1e-300, None)
        xi = np.zeros((n_states, n_states))
        for t in range(len(returns) - 1):
            num = (alpha[t][:, None] * A) * (emit[t + 1] * beta[t + 1])[None, :]
            xi += num / max(num.sum(), 1e-300)
        pi = gamma[0]
        A = xi / np.clip(xi.sum(axis=1, keepdims=True), 1e-300, None)
        for k in range(n_states):
            weight = gamma[:, k].sum()
            mu[k] = float((gamma[:, k] * returns).sum() / max(weight, 1e-300))
            var[k] = float((gamma[:, k] * (returns - mu[k]) ** 2).sum() / max(weight, 1e-300))
        loglik = float(np.log(np.clip(scale, 1e-300, None)).sum())
    labels = np.argmax(gamma, axis=1)
    state_vols = [math.sqrt(max(v, 1e-12)) for v in var]
    return {"status": "OK", "metrics": {
        "states": n_states,
        "means": [float(m) for m in mu],
        "volatilities": state_vols,
        "transition": A.round(6).tolist(),
        "lastStateProbabilities": [float(x) for x in gamma[-1]],
        "logLikelihood": loglik,
        "observations": len(returns),
        "note": "States are latent and exist only in this sample; label switching is possible.",
    }}


def _evt(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    returns = np.asarray(_log_returns(rows), dtype=float)
    losses = -returns
    if len(losses) < 100:
        raise QuantError("EVT needs at least 100 returns")
    fraction = float(params.get("tail_fraction") or 0.1)
    u = float(params.get("threshold") or np.quantile(losses, 1 - fraction))
    excess = np.sort(losses[losses > u] - u)
    if len(excess) < 10:
        raise QuantError("too few tail observations above the threshold")
    n, nu = len(losses), len(excess)
    mean_y = float(excess.mean())
    ranks = (np.arange(1, nu + 1) - 0.5) / nu
    a1 = float((excess * (1 - ranks)).mean())
    denom = mean_y - 2 * a1
    if abs(denom) < 1e-12:
        raise QuantError("the GPD fit is degenerate at this threshold")
    xi = 2 - mean_y / denom
    sigma = 2 * mean_y * a1 / denom
    if xi >= 1 or sigma <= 0:
        raise QuantError("the fitted GPD parameters are not admissible")

    def var_es(level: float) -> tuple[float | None, float | None]:
        q = (n / nu) * (1 - level)
        if q <= 0:
            return None, None
        var = u + (sigma / xi) * (q ** (-xi) - 1) if abs(xi) > 1e-9 else u - sigma * math.log(q)
        es = (var + sigma - xi * u) / (1 - xi)
        return var, es

    var99, es99 = var_es(0.99)
    return {"status": "OK", "metrics": {
        "threshold": u, "tailFraction": fraction, "excesses": nu,
        "xi": xi, "beta": sigma, "var99": var99, "expectedShortfall99": es99,
        "observations": n,
        "note": "Peaks-over-threshold with a probability-weighted-moment GPD fit.",
    }}


def _capm(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    ys, xs, smb, hml = [], [], [], []
    for row in rows:
        asset = row.get("asset", row.get("close"))
        market = row.get("market")
        if asset is None or market is None:
            continue
        ys.append(float(asset))
        xs.append(float(market))
        smb.append(float(row.get("smb") or 0.0))
        hml.append(float(row.get("hml") or 0.0))
    if len(ys) < 40:
        raise QuantError("the factor model needs at least 40 rows with `asset` and `market`")
    use_ff = any(abs(v) > 0 for v in smb) and any(abs(v) > 0 for v in hml)
    columns = [xs, smb, hml] if use_ff else [xs]
    coef, r2, n = _ols_multi(ys, columns)
    metrics = {"alpha": coef[0], "betaMarket": coef[1], "rSquared": r2,
               "observations": n, "model": "Fama-French 3-factor" if use_ff else "CAPM"}
    if use_ff:
        metrics["betaSMB"] = coef[2]
        metrics["betaHML"] = coef[3]
    metrics["note"] = "OLS on returns; factor definitions must match the data provider."
    return {"status": "OK", "metrics": metrics}


def _almgren_chriss(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    size = float(params.get("order_size") or params.get("size") or 1000.0)
    volatility = float(params.get("price_volatility") or params.get("volatility") or 0.02)
    risk_aversion = float(params.get("risk_aversion") or 1e-6)
    temp = float(params.get("temporary_impact") or 1e-6)
    perm = float(params.get("permanent_impact") or 1e-7)
    slices = max(1, min(int(params.get("slices") or 10), 200))
    schedule = [size / slices] * slices
    expected_cost = temp * size * size / (2 * slices) + perm * size * size / 2
    variance = (volatility ** 2) * (size ** 2) * sum((slices - i) / slices
                                                    for i in range(1, slices + 1)) / slices
    return {"status": "OK", "metrics": {
        "slices": slices, "schedule": schedule[:20],
        "expectedCost": expected_cost, "costVariance": variance,
        "riskAversion": risk_aversion,
        "note": "Linear-impact closed form; a schedule is not a fill guarantee.",
    }}


_BUILTIN_FUNCS: dict[str, Callable[[list[dict[str, Any]], dict[str, Any]], dict[str, Any]]] = {
    "ornstein_uhlenbeck": _ou,
    "ewma_volatility": _ewma,
    "realized_volatility": _realized,
    "garch_11": _garch11,
    "gjr_garch": _gjr_garch,
    "egarch": _egarch,
    "har_rv": _har_rv,
    "engle_granger": _engle_granger,
    "hmm": _hmm,
    "evt_gpd": _evt,
    "capm": _capm,
    "almgren_chriss": _almgren_chriss,
}


def _canon(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _compare(observed: dict[str, Any], benchmark: dict[str, Any],
             tolerance: float) -> dict[str, Any]:
    lookup = {_canon(k): v for k, v in observed.items()}
    rows: list[dict[str, Any]] = []
    for key, expected in benchmark.items():
        got = lookup.get(_canon(key))
        if not isinstance(expected, (int, float)) or not isinstance(got, (int, float)):
            rows.append({"metric": key, "expected": expected, "observed": got,
                         "status": "not_comparable"})
            continue
        if expected == 0:
            relative = 0.0 if got == 0 else None
        else:
            relative = abs(got - expected) / abs(expected)
        status = "match" if relative is not None and relative <= tolerance else "mismatch"
        rows.append({"metric": key, "expected": expected, "observed": got,
                     "relativeError": relative, "status": status})
    return {
        "tolerance": tolerance,
        "metrics": rows,
        "matched": sum(1 for r in rows if r["status"] == "match"),
        "mismatched": sum(1 for r in rows if r["status"] == "mismatch"),
        "notComparable": sum(1 for r in rows if r["status"] == "not_comparable"),
    }


def reproduce_method(
    store: Any,
    *,
    method_id: str,
    series: Iterable[Any],
    published_benchmark: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    dataset_id: str | None = None,
    dataset_version: str | None = None,
    tolerance: float = 0.25,
) -> dict[str, Any]:
    """Run a known method and record the result. Never claims a trading edge."""
    try:
        method = store.get_method_spec(method_id)
        spec = method.get("spec") or {}
    except QuantError:
        spec = get_catalog_method(method_id)
        if spec is None:
            raise QuantError(f"method {method_id!r} not found")
    key = _BUILTINS.get(method_id)
    rows = _rows(series)
    flat_params = {
        str(p.get("name")): p.get("default", p.get("value"))
        for p in (spec.get("parameters") or [])
        if isinstance(p, dict) and p.get("name")
    }
    flat_params.update(params or {})

    implementation = spec.get("implementation") or {}
    if key is None and isinstance(implementation, dict) and implementation.get("source"):
        from .implementation import run_implementation

        result = run_implementation(
            str(implementation["source"]), rows, flat_params,
            timeout_s=float(implementation.get("timeoutSeconds") or 30.0),
        )
    elif key is None:
        record = {
            "methodId": method_id,
            "status": "inconclusive",
            "observedMetrics": {},
            "publishedBenchmark": published_benchmark or {},
            "fidelity": {
                "note": "No runnable implementation is registered for this method. "
                        "A specification is not a reproduction.",
            },
            "datasetId": dataset_id,
            "datasetVersion": dataset_version,
        }
        return store.save_reproduction(record)
    else:
        try:
            result = _BUILTIN_FUNCS[key](rows, flat_params)
        except QuantError as exc:
            result = {"status": "failed", "metrics": {},
                      "reason": exc.message}

    observed = result.get("metrics") or {}
    benchmark = published_benchmark or {}
    if benchmark:
        fidelity = _compare(observed, benchmark, tolerance)
        status = "reproduced" if fidelity["mismatched"] == 0 and fidelity["matched"] > 0 else "partial"
    else:
        fidelity = {"note": "No published benchmark was supplied; the method was run "
                            "but the reproduction is not verified against the paper."}
        status = "partial"
    if result.get("status") != "OK":
        status = "inconclusive" if result.get("status") == "inconclusive" else "failed"
        fidelity["reason"] = result.get("reason") or result.get("error")

    record = {
        "methodId": method_id,
        "status": status,
        "observedMetrics": observed,
        "publishedBenchmark": benchmark,
        "fidelity": fidelity,
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
    }
    return store.save_reproduction(record)


def validate_reproduction(store: Any, reproduction_id: str) -> dict[str, Any]:
    """Apply the checks that are actually possible for this reproduction."""
    rep = store.get_reproduction(reproduction_id)
    observed = rep.get("observedMetrics") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str, evidence: Any = None) -> None:
        checks.append({"check": name, "status": status, "detail": detail,
                       "evidence": evidence})

    observations = int(observed.get("observations") or 0)
    add("data_integrity",
        "pass" if observations >= 100 else ("warn" if observations >= 30 else "fail"),
        f"{observations} observations in the reproduction window")

    method = None
    try:
        method = store.get_method_spec(rep["methodId"])
    except QuantError:
        method = None
    impl = ((method or {}).get("spec") or {}).get("implementationStatus")
    add("mathematical_correctness",
        "pass" if impl in ("builtin", "tested") else "warn",
        f"implementation status is {impl or 'unknown'}; the equation was not "
        "independently audited by this check")

    stability = observed.get("parameterStability") or {}
    change = stability.get("relativeChange")
    if change is None:
        add("parameter_stability", "not_checked",
            "this method does not expose a split-half parameter comparison")
    else:
        add("parameter_stability", "pass" if change <= 0.5 else "warn",
            f"relative parameter change across halves is {change:.2f}", stability)

    oos = observed.get("outOfSample") or {}
    if not oos:
        add("out_of_sample", "not_checked",
            "no out-of-sample evaluation is available for this method")
    else:
        skill = oos.get("skill")
        add("out_of_sample", "pass" if (skill is not None and skill > 0) else "warn",
            f"out-of-sample skill versus the baseline is {skill}", oos)

    add("reproducibility", "pass",
        "the estimator is deterministic for the same inputs and parameters")
    add("multiple_testing", "not_checked",
        "the number of methods compared in this research session must be supplied "
        "to the multiple-testing engine")
    add("cost_impact", "not_checked",
        "reproduction is an estimator test; trading costs belong to the adaptation")

    failures = [c for c in checks if c["status"] == "fail"]
    unchecked = [c for c in checks if c["status"] == "not_checked"]
    if failures:
        overall = "fail"
    elif unchecked:
        overall = "incomplete"
    else:
        overall = "pass"
    validation = {
        "reproductionId": reproduction_id,
        "methodId": rep["methodId"],
        "status": overall,
        "checks": checks,
        "note": "A pass is a statement about the checks performed, not a profit claim.",
    }
    saved = store.save_validation(reproduction_id, validation)
    return {"validation": validation, "reproduction": saved}


async def load_series(ctx: Any, *, symbol: str, interval: str = "1d",
                      start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    """Load bars through the existing dataset resolver (one data path)."""
    from ..datasets import dataset_from_strategy
    from ..strategy import parse_strategy
    from ...market.tools import _gateway as market_gateway

    spec = parse_strategy({
        "strategy": {"id": "research_probe", "name": "Research probe", "version": "1.0.0"},
        "universe": {"symbols": [symbol]},
        "timeframes": {"primary": interval},
    })
    dataset = await dataset_from_strategy(
        market_gateway(ctx), spec, start=start, end=end, symbols=[symbol]
    )
    series = dataset.series.get(symbol) or dataset.series.get(symbol.upper())
    if series is None:
        raise QuantError(f"no data for {symbol}", detail={"symbol": symbol})
    return [
        {"ts": series.timestamps[i], "open": float(series.open[i]),
         "high": float(series.high[i]), "low": float(series.low[i]),
         "close": float(series.close[i]), "volume": float(series.volume[i])}
        for i in range(series.length)
    ]


__all__ = ["load_series", "reproduce_method", "validate_reproduction"]
