"""The authoritative factor-research quantitative engine (pure NumPy).

Every factor metric the Lab reports is computed here — never in TypeScript and
never duplicated elsewhere. Conventions are stated in docstrings and covered by
`python/tests/test_factors_engine.py` against hand-computed values.

Panel convention: a panel is a 2-D ``np.ndarray`` of shape ``(T, N)`` — rows are
timestamps (date-major), columns are instruments. ``np.nan`` marks a missing or
invalid observation and is never silently replaced with zero.

Timing convention: ``factor[t]`` is known at the close of ``t``; a forward-return
panel ``ret[t]`` is the return realised over the period ``t -> t+1``. A portfolio
formed from ``factor[t]`` earns ``ret[t]``. This makes look-ahead impossible by
construction.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import numpy as np

from ..stats.base import INSUFFICIENT_DATA, INVALID_INPUT, STATS_VERSION, StatsError
from ..stats.dist import t_two_sided_p

# Bump when a convention changes so stored results stay interpretable.
FACTOR_ENGINE_VERSION = "1.0.0"

# Reuse the statistical engine's structured error so the shared HTTP handler and
# callers already understand it.
FactorError = StatsError


# ── small numeric helpers ────────────────────────────────────────────────────

def _panel(values: Any, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 2:
        raise StatsError(INVALID_INPUT, f"{name} must be a 2-D (date x instrument) panel")
    if arr.shape[0] == 0 or arr.shape[1] == 0:
        raise StatsError(INSUFFICIENT_DATA, f"{name} is empty", 422)
    return np.where(np.isfinite(arr), arr, np.nan)


def _finite_1d(values: Any, name: str = "series") -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    return arr[np.isfinite(arr)]


def _rank1d(a: np.ndarray) -> np.ndarray:
    """Average (fractional) ranks, 1-based; NaN preserved. Handles ties."""
    out = np.full(a.shape, np.nan, dtype=float)
    mask = np.isfinite(a)
    v = a[mask]
    n = v.size
    if n == 0:
        return out
    order = np.argsort(v, kind="mergesort")
    sv = v[order]
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    out[mask] = ranks[np.argsort(order, kind="mergesort")]
    return out


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 2:
        return math.nan
    x = a[mask] - a[mask].mean()
    y = b[mask] - b[mask].mean()
    denom = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
    if denom <= 0.0:
        return math.nan
    return float((x * y).sum() / denom)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _rank1d(a), _rank1d(b)
    return _pearson(ra, rb)


def _rank_panel(panel: np.ndarray) -> np.ndarray:
    return np.vstack([_rank1d(row) for row in panel])


# ── cross-sectional normalization (applied per timestamp, within the universe) ─

def percentile_rank(panel: Any) -> np.ndarray:
    """Cross-sectional percentile rank in [0, 1] per row; NaN preserved."""
    arr = _panel(panel, "panel")
    out = np.full(arr.shape, np.nan)
    for t, row in enumerate(arr):
        r = _rank1d(row)
        m = np.isfinite(r)
        c = int(m.sum())
        if c == 1:
            out[t, m] = 0.5
        elif c > 1:
            out[t, m] = (r[m] - 1.0) / (c - 1.0)
    return out


def zscore(panel: Any, *, robust: bool = False) -> np.ndarray:
    """Cross-sectional z-score per row. ``robust`` uses median/MAD (1.4826·MAD)."""
    arr = _panel(panel, "panel")
    out = np.full(arr.shape, np.nan)
    for t, row in enumerate(arr):
        m = np.isfinite(row)
        if m.sum() < 2:
            continue
        v = row[m]
        if robust:
            center = float(np.median(v))
            mad = float(np.median(np.abs(v - center)))
            scale = 1.4826 * mad
        else:
            center = float(v.mean())
            scale = float(v.std(ddof=1))
        if scale <= 0.0:
            out[t, m] = 0.0
        else:
            out[t, m] = (v - center) / scale
    return out


def winsorize(panel: Any, *, limits: tuple[float, float] = (0.01, 0.01)) -> np.ndarray:
    """Cross-sectional winsorization per row at the given tail quantiles."""
    arr = _panel(panel, "panel")
    lo, hi = limits
    if not (0.0 <= lo < 1.0 and 0.0 <= hi < 1.0):
        raise StatsError(INVALID_INPUT, "winsorize limits must be in [0, 1)")
    out = arr.copy()
    for t, row in enumerate(arr):
        m = np.isfinite(row)
        if m.sum() < 3:
            continue
        v = row[m]
        q_lo = float(np.quantile(v, lo)) if lo > 0 else -np.inf
        q_hi = float(np.quantile(v, 1.0 - hi)) if hi > 0 else np.inf
        out[t, m] = np.clip(v, q_lo, q_hi)
    return out


def demean_by_group(panel: Any, groups: Sequence[Any]) -> np.ndarray:
    """Subtract, per row, the mean within each instrument's group label."""
    arr = _panel(panel, "panel")
    labels = np.asarray(list(groups), dtype=object)
    if labels.size != arr.shape[1]:
        raise StatsError(INVALID_INPUT, "groups must have one label per instrument")
    out = arr.copy()
    for t, row in enumerate(arr):
        for g in np.unique(labels):
            m = (labels == g) & np.isfinite(row)
            if m.sum() > 0:
                out[t, m] = row[m] - float(row[m].mean())
    return out


def neutralize(panel: Any, exposures: Any) -> np.ndarray:
    """Per-row OLS residual of the panel on a set of exposure panels.

    ``exposures`` is an ``(T, N)`` panel or a list of them. The intercept is
    always included, so a neutralized factor is mean-zero by construction.
    """
    arr = _panel(panel, "panel")
    exp_list = exposures if isinstance(exposures, (list, tuple)) else [exposures]
    exp_panels = [_panel(e, "exposure") for e in exp_list]
    for e in exp_panels:
        if e.shape != arr.shape:
            raise StatsError(INVALID_INPUT, "exposure panels must match the factor panel")
    out = np.full(arr.shape, np.nan)
    for t in range(arr.shape[0]):
        y = arr[t]
        cols = [e[t] for e in exp_panels]
        mask = np.isfinite(y)
        for c in cols:
            mask &= np.isfinite(c)
        if int(mask.sum()) <= len(cols) + 1:
            continue
        X = np.column_stack([np.ones(int(mask.sum()))] + [c[mask] for c in cols])
        beta, *_ = np.linalg.lstsq(X, y[mask], rcond=None)
        out[t, mask] = y[mask] - X @ beta
    return out


# ── forward returns ──────────────────────────────────────────────────────────

def forward_returns(prices: Any, horizon: int, *, log: bool = False) -> np.ndarray:
    """R(i,t,h) = P(i,t+h)/P(i,t) − 1 (or the log equivalent). Last h rows are NaN."""
    if horizon < 1:
        raise StatsError(INVALID_INPUT, "horizon must be >= 1")
    px = _panel(prices, "prices")
    T, N = px.shape
    out = np.full((T, N), np.nan)
    if horizon >= T:
        return out
    p0 = px[: T - horizon]
    p1 = px[horizon:]
    with np.errstate(divide="ignore", invalid="ignore"):
        if log:
            out[: T - horizon] = np.log(p1 / p0)
        else:
            out[: T - horizon] = p1 / p0 - 1.0
    return out


# ── information coefficient ──────────────────────────────────────────────────

def cross_sectional_ic(
    factor: Any, forward: Any, *, method: str = "pearson", min_obs: int = 5
) -> tuple[np.ndarray, np.ndarray]:
    """Return (ic_series, counts): the per-date cross-sectional IC and sample size."""
    f = _panel(factor, "factor")
    r = _panel(forward, "forward")
    if f.shape != r.shape:
        raise StatsError(INVALID_INPUT, "factor and forward-return panels must match")
    method = (method or "pearson").lower()
    if method not in ("pearson", "spearman"):
        raise StatsError(INVALID_INPUT, f"unsupported IC method: {method}")
    fn = _pearson if method == "pearson" else _spearman
    ic = np.full(f.shape[0], np.nan)
    counts = np.zeros(f.shape[0], dtype=int)
    for t in range(f.shape[0]):
        mask = np.isfinite(f[t]) & np.isfinite(r[t])
        c = int(mask.sum())
        counts[t] = c
        if c >= max(2, min_obs):
            ic[t] = fn(f[t][mask], r[t][mask])
    return ic, counts


def newey_west_mean(series: Any, *, lag: Optional[int] = None) -> dict[str, Any]:
    """Newey–West HAC inference for the mean of a serially-dependent series."""
    x = _finite_1d(series)
    n = x.size
    if n < 3:
        return {"available": False, "reason": "fewer than 3 observations", "n": n}
    mean = float(x.mean())
    dev = x - mean
    gamma0 = float(dev @ dev) / n
    if lag is None:
        lag = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
    var = gamma0
    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)
        cov = float(dev[l:] @ dev[:-l]) / n
        var += 2.0 * w * cov
    se = math.sqrt(max(var, 0.0) / n)
    t = mean / se if se > 0 else math.nan
    p = t_two_sided_p(t, n - 1) if math.isfinite(t) else math.nan
    return {
        "available": True, "mean": mean, "standardError": se, "tStatistic": None if not math.isfinite(t) else t,
        "pValue": None if not math.isfinite(p) else p, "lag": lag, "n": n,
    }


def ic_summary(ic: Any, counts: Any = None, *, periods_per_year: Optional[int] = None) -> dict[str, Any]:
    """Summarise an IC series. IR is periodic unless periods_per_year is given."""
    series = np.asarray(ic, dtype=float)
    valid = series[np.isfinite(series)]
    n = valid.size
    out: dict[str, Any] = {
        "meanIC": None, "stdIC": None, "informationRatio": None,
        "annualizedInformationRatio": None, "hitRate": None,
        "periods": int(series.size), "validPeriods": int(n),
    }
    if n < 2:
        out["available"] = False
        out["reason"] = "fewer than 2 valid IC periods"
        return out
    mean = float(valid.mean())
    std = float(valid.std(ddof=1))
    out.update({
        "available": True, "meanIC": mean, "stdIC": std,
        "informationRatio": (mean / std) if std > 0 else None,
        "hitRate": float((valid > 0).mean()),
    })
    if periods_per_year:
        out["annualizedInformationRatio"] = (
            (mean / std) * math.sqrt(periods_per_year) if std > 0 else None
        )
    if counts is not None:
        c = np.asarray(counts, dtype=float)
        c = c[np.isfinite(c)]
        out["averageCrossSectionSize"] = float(c.mean()) if c.size else None
    out["hac"] = newey_west_mean(valid)
    return out


def factor_decay(
    factor: Any, prices: Any, horizons: Sequence[int], *, method: str = "pearson",
    min_obs: int = 5, periods_per_year: Optional[int] = None,
) -> dict[str, Any]:
    """Mean IC (and Rank IC) as a function of forward horizon."""
    curve: list[dict[str, Any]] = []
    for h in horizons:
        fwd = forward_returns(prices, int(h))
        ic, counts = cross_sectional_ic(factor, fwd, method=method, min_obs=min_obs)
        summ = ic_summary(ic, counts, periods_per_year=periods_per_year)
        curve.append({
            "horizon": int(h),
            "meanIC": summ.get("meanIC"),
            "informationRatio": summ.get("informationRatio"),
            "hitRate": summ.get("hitRate"),
            "validPeriods": summ.get("validPeriods"),
            "averageCrossSectionSize": summ.get("averageCrossSectionSize"),
        })
    means = [c["meanIC"] for c in curve if c["meanIC"] is not None]
    hs = [c["horizon"] for c in curve if c["meanIC"] is not None]
    slope = None
    if len(hs) >= 2:
        slope = float(np.polyfit(hs, means, 1)[0])
    return {"method": method, "curve": curve, "decaySlope": slope}


def rolling_mean_ic(ic: Any, window: int) -> np.ndarray:
    series = np.asarray(ic, dtype=float)
    out = np.full(series.shape, np.nan)
    if window < 1:
        raise StatsError(INVALID_INPUT, "window must be >= 1")
    for t in range(window - 1, series.size):
        window_vals = series[t - window + 1: t + 1]
        v = window_vals[np.isfinite(window_vals)]
        if v.size:
            out[t] = float(v.mean())
    return out


def group_ic(
    factor: Any, forward: Any, groups: Sequence[Any], *, method: str = "pearson", min_obs: int = 5
) -> dict[str, Any]:
    """IC computed independently per instrument group (sector/region/asset class)."""
    labels = np.asarray(list(groups), dtype=object)
    f = _panel(factor, "factor")
    if labels.size != f.shape[1]:
        raise StatsError(INVALID_INPUT, "groups must have one label per instrument")
    out: dict[str, Any] = {}
    for g in np.unique(labels):
        idx = np.where(labels == g)[0]
        if idx.size < 2:
            out[str(g)] = {"available": False, "reason": "fewer than 2 instruments"}
            continue
        sub = f[:, idx]
        r = _panel(forward, "forward")[:, idx]
        ic, counts = cross_sectional_ic(sub, r, method=method, min_obs=min_obs)
        summ = ic_summary(ic, counts)
        summ["instruments"] = int(idx.size)
        out[str(g)] = summ
    return out


def classify_regimes(values: Any, *, n_regimes: int = 2, method: str = "quantile") -> np.ndarray:
    """Label each timestamp by a scalar regime driver into quantile buckets.

    The driver is any per-date series (realised market volatility, a benchmark's
    rolling vol, a trend oscillator, …). Labels are ``R1`` (lowest) … ``Rn``;
    NaN/missing driver values are labelled ``unknown`` and never assigned to a
    bucket. This is the pluggable regime provider — callers supply the driver.
    """
    if n_regimes < 2:
        raise StatsError(INVALID_INPUT, "n_regimes must be >= 2")
    if method != "quantile":
        raise StatsError(INVALID_INPUT, f"unsupported regime method: {method}")
    x = np.asarray(values, dtype=float).ravel()
    labels = np.array(["unknown"] * x.size, dtype=object)
    idx = np.where(np.isfinite(x))[0]
    if idx.size < n_regimes:
        return labels
    edges = np.quantile(x[idx], np.linspace(0.0, 1.0, n_regimes + 1)[1:-1])
    buckets = np.digitize(x[idx], edges)
    for pos, label_i in zip(idx, buckets):
        labels[pos] = f"R{int(label_i) + 1}"
    return labels


def regime_ic(factor: Any, forward: Any, regime_labels: Sequence[Any], *, method: str = "pearson",
              min_obs: int = 5) -> dict[str, Any]:
    """IC split by a per-date regime label supplied by the caller (e.g. vol regime)."""
    labels = np.asarray(list(regime_labels), dtype=object)
    ic, counts = cross_sectional_ic(factor, forward, method=method, min_obs=min_obs)
    if labels.size != ic.size:
        raise StatsError(INVALID_INPUT, "regime labels must have one value per date")
    out: dict[str, Any] = {}
    for g in np.unique(labels):
        idx = np.where(labels == g)[0]
        summ = ic_summary(ic[idx], counts[idx])
        summ["periods"] = int(idx.size)
        out[str(g)] = summ
    return out


# ── quantile portfolios ──────────────────────────────────────────────────────

def _trailing_vol(returns: np.ndarray, t: int, window: int) -> np.ndarray:
    start = max(0, t - window)
    if t - start < 2:
        return np.full(returns.shape[1], np.nan)
    block = returns[start:t]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nanstd(block, axis=0, ddof=1)


def _weights_for(scores: np.ndarray, idx: np.ndarray, weighting: str,
                 vol_row: np.ndarray) -> np.ndarray:
    w = np.zeros(scores.shape[0])
    if idx.size == 0:
        return w
    if weighting == "equal":
        w[idx] = 1.0 / idx.size
    elif weighting == "score":
        s = scores[idx]
        lo, hi = float(s.min()), float(s.max())
        raw = (s - lo) / (hi - lo) if hi > lo else np.ones(idx.size)
        raw = raw + 1e-9
        w[idx] = raw / raw.sum()
    elif weighting == "vol_scaled":
        v = vol_row[idx]
        valid = np.isfinite(v) & (v > 0)
        if not valid.any():
            w[idx] = 1.0 / idx.size
        else:
            iv = np.where(valid, 1.0 / np.where(v > 0, v, np.nan), 0.0)
            iv = np.nan_to_num(iv)
            w[idx] = iv / iv.sum()
    else:
        raise StatsError(INVALID_INPUT, f"unsupported weighting: {weighting}")
    return w


def quantile_portfolio(
    factor: Any, returns: Any, *, quantiles: int = 5, weighting: str = "equal",
    long_short: bool = True, rebalance: int = 1, cost_bps: float = 0.0, min_obs: int = 5,
    periods_per_year: int = 252, risk_free: float = 0.0, vol_window: int = 60,
) -> dict[str, Any]:
    """Cross-sectional quantile portfolios with turnover and cost accounting.

    Returns per-quantile long-only equity curves plus (when ``long_short``) the
    top-minus-bottom spread, gross and net of a turnover-based cost. Turnover is
    one-way: ``½·Σ|w_new − w_prev|``; cost = ``turnover · cost_bps / 1e4``.
    """
    if quantiles < 2:
        raise StatsError(INVALID_INPUT, "quantiles must be >= 2")
    if rebalance < 1:
        raise StatsError(INVALID_INPUT, "rebalance must be >= 1")
    f = _panel(factor, "factor")
    r = _panel(returns, "returns")
    if f.shape != r.shape:
        raise StatsError(INVALID_INPUT, "factor and returns panels must match")
    T, N = f.shape

    q_ret = np.zeros((T, quantiles))
    q_books = np.zeros((quantiles, N))   # current weight vector per quantile
    ls_book = np.zeros(N)                # top - bottom book (long-short only)
    w_ls_prev = np.zeros(N)
    turnover = np.zeros(T)
    gross_ls = np.zeros(T)
    net_ls = np.zeros(T)
    last_weights: list[dict[str, Any]] = []

    for t in range(T):
        row = f[t]
        finite = np.isfinite(row)
        k = int(finite.sum())
        if t % rebalance == 0 and k >= max(quantiles, min_obs):
            ranks = _rank1d(row)
            # rank 1 = lowest factor -> Q1 ... rank k -> Qq
            edges = np.clip(np.ceil(ranks / k * quantiles).astype(int), 1, quantiles)
            vol_row = _trailing_vol(r, t, vol_window)
            q_books = np.zeros((quantiles, N))
            for qi in range(1, quantiles + 1):
                idx = np.where(finite & (edges == qi))[0]
                if idx.size:
                    q_books[qi - 1] = _weights_for(row, idx, weighting, vol_row)
            if long_short:
                ls_book = q_books[quantiles - 1] - q_books[0]
                turnover[t] = 0.5 * float(np.abs(ls_book - w_ls_prev).sum())
                w_ls_prev = ls_book
                last_weights = [
                    {"instrument": int(i), "weight": float(ls_book[i])}
                    for i in np.where(np.abs(ls_book) > 1e-12)[0]
                ]
            else:
                ls_book = q_books[quantiles - 1]

        ret_t = r[t]
        for qi in range(quantiles):
            q_ret[t, qi] = float(np.nansum(q_books[qi] * ret_t))
        gross_ls[t] = float(np.nansum(ls_book * ret_t))
        net_ls[t] = gross_ls[t] - turnover[t] * cost_bps / 1e4

    valid = np.isfinite(r).any(axis=1)
    ls_net = net_ls[valid]
    ls_gross = gross_ls[valid]
    turnover_valid = turnover[valid]
    quantile_metrics = {
        f"Q{qi + 1}": portfolio_metrics(q_ret[valid, qi], periods_per_year=periods_per_year,
                                        risk_free=risk_free)
        for qi in range(quantiles)
    }
    result: dict[str, Any] = {
        "quantiles": quantiles, "weighting": weighting, "rebalance": rebalance,
        "longShort": long_short, "costBps": cost_bps, "periodsPerYear": periods_per_year,
        "turnover": {
            "average": float(turnover_valid.mean()) if turnover_valid.size else None,
            "annualized": float(turnover_valid.mean() * periods_per_year) if turnover_valid.size else None,
            "series": _list(turnover),
        },
        "cost": {
            "costBps": cost_bps,
            "totalCost": float(float(turnover_valid.sum()) * cost_bps / 1e4) if turnover_valid.size else 0.0,
        },
        "quantileMetrics": quantile_metrics,
        "finalWeights": last_weights,
        "observations": int(valid.sum()),
    }
    if long_short:
        result["longShortMetrics"] = portfolio_metrics(ls_net, periods_per_year=periods_per_year,
                                                       risk_free=risk_free)
        result["grossLongShortMetrics"] = portfolio_metrics(ls_gross, periods_per_year=periods_per_year,
                                                            risk_free=risk_free)
        # The aligned net/gross long-short return series (needed for deflated
        # Sharpe / overfitting diagnostics without recomputing the simulation).
        result["longShortReturns"] = _list(ls_net)
        result["grossLongShortReturns"] = _list(ls_gross)
    return result


def portfolio_metrics(returns: Any, *, periods_per_year: int, risk_free: float = 0.0) -> dict[str, Any]:
    """Performance metrics for a periodic return series. Honest about degeneracy."""
    r = _finite_1d(returns, "returns")
    n = r.size
    out: dict[str, Any] = {"available": False, "periods": int(n)}
    if n < 2:
        out["reason"] = "fewer than 2 return periods"
        return out
    equity = np.cumprod(1.0 + r)
    total = float(equity[-1] - 1.0)
    years = n / periods_per_year
    ann_return = float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 and total > -1 else None
    std = float(r.std(ddof=1))
    ann_vol = std * math.sqrt(periods_per_year)
    rf_per = risk_free / periods_per_year
    excess = r - rf_per
    sharpe = float(excess.mean() / std * math.sqrt(periods_per_year)) if std > 0 else None
    downside = r[r < rf_per] - rf_per
    dd = float(math.sqrt((downside @ downside) / n)) if downside.size else 0.0
    sortino = float(excess.mean() / dd * math.sqrt(periods_per_year)) if dd > 0 else None
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    mdd = float(drawdown.min()) if drawdown.size else 0.0
    out.update({
        "available": True, "totalReturn": total, "annualizedReturn": ann_return,
        "annualizedVolatility": ann_vol, "sharpe": sharpe, "sortino": sortino,
        "maxDrawdown": mdd, "hitRate": float((r > 0).mean()),
        "averagePeriodReturn": float(r.mean()),
    })
    return out


def _list(a: Any) -> list[Optional[float]]:
    return [None if not math.isfinite(float(v)) else float(v) for v in np.asarray(a, dtype=float).ravel()]


# ── factor combination (alpha composer) ──────────────────────────────────────

def combine_factors(
    panels: Sequence[Any], *, method: str = "equal_zscore",
    weights: Optional[Sequence[float]] = None, forward: Any = None,
    training_rows: Optional[int] = None,
) -> dict[str, Any]:
    """Combine normalised factor panels into one composite score panel.

    Methods: ``equal_zscore``, ``equal_rank``, ``user_weights``,
    ``ic_weighted`` (needs ``forward``), ``regression`` (needs ``forward``).
    Fitting methods use only the first ``training_rows`` rows (the training
    window) — the final holdout is never used to fit weights.
    """
    if not panels:
        raise StatsError(INVALID_INPUT, "at least one factor panel is required")
    zs = [zscore(p) for p in panels]
    shape = zs[0].shape
    for p in zs:
        if p.shape != shape:
            raise StatsError(INVALID_INPUT, "all factor panels must share a shape")
    k = len(zs)
    T = shape[0]
    fit_rows = T if training_rows is None else max(1, int(training_rows))

    if method == "equal_zscore":
        w = np.ones(k) / k
    elif method == "equal_rank":
        zs = [zscore(_rank_panel(_panel(p, "factor"))) for p in panels]
        w = np.ones(k) / k
    elif method == "user_weights":
        if weights is None or len(weights) != k:
            raise StatsError(INVALID_INPUT, "user_weights requires one weight per factor")
        w = np.asarray(weights, dtype=float)
        w = w / w.sum() if w.sum() != 0 else np.ones(k) / k
    elif method in ("ic_weighted", "regression"):
        if forward is None:
            raise StatsError(INVALID_INPUT, f"{method} requires forward returns")
        fwd_panel = _panel(forward, "forward")
        if method == "ic_weighted":
            ics = []
            for p in panels:
                ic, _ = cross_sectional_ic(_panel(p, "factor")[:fit_rows], fwd_panel[:fit_rows], min_obs=3)
                valid = ic[np.isfinite(ic)]
                ics.append(float(valid.mean()) if valid.size else 0.0)
            w = np.asarray(ics, dtype=float)
            if np.all(w == 0):
                w = np.ones(k) / k
            else:
                w = w / np.abs(w).sum()
        else:  # regression on pooled standardised rows (training window only)
            X_rows, y_rows = [], []
            for t in range(fit_rows):
                cols = [z[t] for z in zs]
                mask = np.isfinite(fwd_panel[t])
                for c in cols:
                    mask &= np.isfinite(c)
                if mask.sum() >= 2:
                    X_rows.append(np.column_stack([c[mask] for c in cols]))
                    y_rows.append(fwd_panel[t][mask])
            if not X_rows:
                raise StatsError(INSUFFICIENT_DATA, "no usable training rows for regression", 422)
            X = np.vstack(X_rows)
            y = np.concatenate(y_rows)
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            w = beta
    else:
        raise StatsError(INVALID_INPUT, f"unsupported combine method: {method}")

    composite = sum(wi * zi for wi, zi in zip(w, zs))
    composites = sum(abs(wi) for wi in w) or 1.0
    composite = composite / composites
    contributions = {
        f"f{i}": float(abs(w[i]) / (float(np.abs(w).sum()) or 1.0)) for i in range(k)
    }
    return {
        "method": method, "weights": _list(w), "trainingRows": fit_rows,
        "composite": composite, "contributions": contributions,
    }


def factor_correlation(panels: Sequence[Any]) -> dict[str, Any]:
    """Pairwise pooled cross-sectional correlation between factor value panels."""
    zs = [_panel(p, "factor") for p in panels]
    k = len(zs)
    matrix = np.full((k, k), np.nan)
    for i in range(k):
        for j in range(k):
            a = zs[i].ravel()
            b = zs[j].ravel()
            matrix[i, j] = _pearson(a, b)
    return {"matrix": [[None if not math.isfinite(float(v)) else float(v) for v in row] for row in matrix]}


def detect_redundancy(panels: Sequence[Any], *, threshold: float = 0.9) -> dict[str, Any]:
    """Flag factor pairs whose |correlation| exceeds ``threshold``."""
    corr = factor_correlation(panels)
    m = corr["matrix"]
    pairs = []
    for i in range(len(m)):
        for j in range(i + 1, len(m)):
            c = m[i][j]
            if c is not None and abs(c) >= threshold:
                pairs.append({"i": i, "j": j, "correlation": c})
    return {"threshold": threshold, "pairs": pairs, "matrix": m}


# ── validation gate ──────────────────────────────────────────────────────────

def validation_gate(
    *, ic_mean: Optional[float], ic_pvalue: Optional[float], expected_direction: Optional[str],
    average_cross_section: Optional[float], net_cumulative: Optional[float],
    average_turnover: Optional[float], quantile_returns: Optional[Sequence[float]],
    min_cross_section: int = 20, max_turnover: float = 1.0, alpha: float = 0.05,
    deflated_sharpe: Optional[float] = None, dsr_threshold: float = 0.95,
    pbo: Optional[float] = None, pbo_threshold: float = 0.5,
) -> dict[str, Any]:
    """The structured research-validation gate. Failures are never downgraded.

    ``deflated_sharpe`` (probability the true Sharpe exceeds the best-of-N) and
    ``pbo`` (probability of backtest overfitting) are OPTIONAL selection-bias
    controls: when supplied they are enforced; when omitted the check is
    ``not_evaluated`` (never silently passed).
    """
    checks: list[dict[str, Any]] = []

    def add(name, status, method, params, result, failure=None, severity="high"):
        checks.append({
            "name": name, "status": status, "method": method, "parameters": params,
            "result": result, "failureReason": failure, "severity": severity,
        })

    if ic_mean is None or ic_pvalue is None:
        add("ic_significance", "not_evaluated", "Newey-West HAC t-test",
            {"alpha": alpha}, None, "IC statistics unavailable", "high")
    else:
        passed = ic_pvalue < alpha
        add("ic_significance", "passed" if passed else "failed", "Newey-West HAC t-test",
            {"alpha": alpha}, {"meanIC": ic_mean, "pValue": ic_pvalue},
            None if passed else f"mean IC not significant at {alpha}", "high")

    if expected_direction and ic_mean is not None:
        ok = (expected_direction == "positive" and ic_mean > 0) or \
             (expected_direction == "negative" and ic_mean < 0)
        add("ic_direction", "passed" if ok else "failed", "sign of mean IC",
            {"expected": expected_direction}, {"meanIC": ic_mean},
            None if ok else "mean IC sign contradicts the expected direction", "medium")

    if average_cross_section is None:
        add("sample_sufficiency", "not_evaluated", "average cross-section size",
            {"minimum": min_cross_section}, None, "cross-section size unavailable", "medium")
    else:
        ok = average_cross_section >= min_cross_section
        add("sample_sufficiency", "passed" if ok else "warning", "average cross-section size",
            {"minimum": min_cross_section}, {"average": average_cross_section},
            None if ok else "thin cross-sections; results may be unstable", "medium")

    if average_turnover is not None:
        ok = average_turnover <= max_turnover
        add("turnover", "passed" if ok else "warning", "average one-way turnover",
            {"maximum": max_turnover}, {"average": average_turnover},
            None if ok else "turnover high; net edge may not survive costs", "medium")

    if net_cumulative is None:
        add("net_profitability", "not_evaluated", "cumulative net long-short return",
            {}, None, "portfolio result unavailable", "high")
    else:
        add("net_profitability", "passed" if net_cumulative > 0 else "failed",
            "cumulative net long-short return", {}, {"netCumulative": net_cumulative},
            None if net_cumulative > 0 else "net long-short return is not positive", "high")

    if quantile_returns and len(quantile_returns) >= 3:
        seq = [v for v in quantile_returns if v is not None]
        mono = all(seq[i + 1] >= seq[i] for i in range(len(seq) - 1)) or \
               all(seq[i + 1] <= seq[i] for i in range(len(seq) - 1))
        add("quantile_monotonicity", "passed" if mono else "warning",
            "monotonicity of quantile mean returns", {}, {"means": seq},
            None if mono else "quantile returns are not monotonic", "medium")

    if deflated_sharpe is None:
        add("multiple_testing_deflated_sharpe", "not_evaluated",
            "Deflated Sharpe Ratio (Bailey & López de Prado 2014)", {"threshold": dsr_threshold},
            None, "trial count / Sharpe variance not supplied", "high")
    else:
        ok = deflated_sharpe >= dsr_threshold
        add("multiple_testing_deflated_sharpe", "passed" if ok else "failed",
            "Deflated Sharpe Ratio (Bailey & López de Prado 2014)",
            {"threshold": dsr_threshold}, {"deflatedSharpe": deflated_sharpe},
            None if ok else "performance is not distinguishable from selection luck after "
                            "multiple-testing deflation", "high")

    if pbo is None:
        add("multiple_testing_pbo", "not_evaluated",
            "Probability of Backtest Overfitting (CSCV)", {"threshold": pbo_threshold},
            None, "candidate return matrix not supplied", "high")
    else:
        ok = pbo <= pbo_threshold
        add("multiple_testing_pbo", "passed" if ok else "failed",
            "Probability of Backtest Overfitting (CSCV)", {"threshold": pbo_threshold},
            {"probabilityOfBacktestOverfitting": pbo},
            None if ok else "high overfitting probability: the in-sample best does not "
                            "generalise out-of-sample", "high")

    statuses = {c["status"] for c in checks}
    critical_failed = any(c["status"] == "failed" and c["severity"] == "high" for c in checks)
    outcome = "failed" if critical_failed else ("warning" if "warning" in statuses else "passed")
    return {
        "outcome": outcome,
        "validated": outcome == "passed",
        "checks": checks,
        "note": "A passing gate means the configured checks completed with these outcomes; "
                "it does not imply profitability.",
    }


__all__ = [
    "FACTOR_ENGINE_VERSION", "FactorError", "forward_returns", "cross_sectional_ic",
    "ic_summary", "newey_west_mean", "factor_decay", "rolling_mean_ic", "group_ic",
    "regime_ic", "classify_regimes", "percentile_rank", "zscore", "winsorize", "demean_by_group",
    "neutralize", "quantile_portfolio", "portfolio_metrics", "combine_factors",
    "factor_correlation", "detect_redundancy", "validation_gate",
]
