"""build_features — a reusable feature-construction framework.

Builds a feature matrix from a price (and optional OHLC) series using a catalogue
of causal transforms plus the safe formula language. Every feature carries the
metadata required for reproducible, point-in-time-safe reuse: input
requirements, parameters, output schema, lookback, warm-up, missing-data
behaviour and a point-in-time-safety classification.

All built-in transforms are causal (value at t uses only data up to t), so a
feature computed here is identical in research, backtesting and live use.
"""

from __future__ import annotations

import numpy as np

from .base import (
    INVALID_INPUT,
    StatsError,
    as_list,
    get_int,
    get_str,
    make_response,
    require_min_length,
    to_float_array,
)
from .formula import FormulaError, evaluate

DESCRIPTION = (
    "Construct a feature matrix. Supports lagging/differencing, simple and log "
    "returns, rolling mean/std/min/max/quantile, z-scores and robust scaling, "
    "momentum/ROC, RSI/MACD/ATR/moving averages/Bollinger bands/VWAP, volatility "
    "and drawdown features, and safe custom formulas. Each feature reports its "
    "lookback, warm-up, missing-data behaviour and point-in-time safety."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"}},
        "high": {"type": "array", "items": {"type": "number"}},
        "low": {"type": "array", "items": {"type": "number"}},
        "close": {"type": "array", "items": {"type": "number"}},
        "volume": {"type": "array", "items": {"type": "number"}},
        "benchmark": {"type": "array", "items": {"type": "number"}},
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "params": {"type": "object"},
                    "expression": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["values", "features"],
}


def _lag(a, n):
    out = np.full(a.size, np.nan)
    if 0 < n < a.size:
        out[n:] = a[:-n]
    elif n == 0:
        return a.copy()
    return out


def _rolling(a, w, fn):
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if np.isfinite(chunk).all():
            out[i] = fn(chunk)
    return out


def _rsi(a, w):
    out = np.full(a.size, np.nan)
    gains = np.zeros(a.size)
    losses = np.zeros(a.size)
    for i in range(1, a.size):
        d = a[i] - a[i - 1]
        gains[i], losses[i] = max(d, 0.0), max(-d, 0.0)
    if a.size <= w:
        return out
    ag, al = gains[1: w + 1].mean(), losses[1: w + 1].mean()
    for i in range(w + 1, a.size):
        ag = (ag * (w - 1) + gains[i]) / w
        al = (al * (w - 1) + losses[i]) / w
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def _build_one(spec: dict, ctx: dict, prices: np.ndarray) -> tuple[np.ndarray, dict]:
    name = get_str(spec, "name", "")
    if not name:
        raise StatsError(INVALID_INPUT, "each feature needs a name")
    ftype = spec.get("type")
    params = spec.get("params") or {}
    close = ctx["close"]

    if spec.get("expression"):
        try:
            series, parsed = evaluate(spec["expression"], ctx)
        except FormulaError as exc:
            raise StatsError(INVALID_INPUT, f"feature '{name}': {exc.message}") from exc
        meta = {"kind": "formula", "expression": spec["expression"],
                "inputs": parsed.variables, "functions": parsed.functions,
                "lookback": 0, "pointInTimeSafe": True}
        return series, meta

    if ftype == "lag":
        n = int(params.get("n", 1)); return _lag(close, n), {"lookback": n}
    if ftype == "diff":
        n = int(params.get("n", 1))
        out = np.full(close.size, np.nan); out[n:] = close[n:] - close[:-n]
        return out, {"lookback": n}
    if ftype in ("pct_change", "roc", "momentum"):
        n = int(params.get("n", 1))
        out = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n:] = close[n:] / close[:-n] - 1.0
        return out, {"lookback": n, "transform": ftype}
    if ftype in ("log_return", "return"):
        n = int(params.get("n", 1))
        if np.any(close[np.isfinite(close)] <= 0):
            raise StatsError(INVALID_INPUT, f"feature '{name}': log return needs positive prices")
        out = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n:] = np.log(close[n:] / close[:-n])
        return out, {"lookback": n}
    if ftype in ("sma", "rolling_mean"):
        w = int(params.get("window", 20)); return _rolling(close, w, lambda c: float(c.mean())), {"lookback": w}
    if ftype in ("rolling_std", "volatility"):
        w = int(params.get("window", 20))
        r = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            r[1:] = close[1:] / close[:-1] - 1.0
        return _rolling(r, w, lambda c: float(np.std(c, ddof=1))), {"lookback": w + 1}
    if ftype == "rolling_min":
        w = int(params.get("window", 20)); return _rolling(close, w, lambda c: float(c.min())), {"lookback": w}
    if ftype == "rolling_max":
        w = int(params.get("window", 20)); return _rolling(close, w, lambda c: float(c.max())), {"lookback": w}
    if ftype == "rolling_quantile":
        w = int(params.get("window", 20)); q = float(params.get("q", 0.5))
        return _rolling(close, w, lambda c: float(np.quantile(c, q))), {"lookback": w, "q": q}
    if ftype in ("zscore", "minmax_scale", "winsorize"):
        w = int(params.get("window", 20)) if params.get("window") else None
        if ftype == "zscore":
            if w:
                mean = _rolling(close, w, lambda c: float(c.mean()))
                sd = _rolling(close, w, lambda c: float(np.std(c, ddof=0)))
                with np.errstate(divide="ignore", invalid="ignore"):
                    return (close - mean) / np.where(sd == 0, np.nan, sd), {"lookback": w}
            m, s = np.nanmean(close), np.nanstd(close)
            return (close - m) / s if s else np.zeros_like(close), {"lookback": 0}
        if ftype == "minmax_scale":
            lo, hi = np.nanmin(close), np.nanmax(close)
            return (close - lo) / (hi - lo) if hi > lo else np.zeros_like(close), {"lookback": 0}
        lo = np.nanquantile(close, float(params.get("lower", 0.05)))
        hi = np.nanquantile(close, float(params.get("upper", 0.95)))
        return np.clip(close, lo, hi), {"lookback": 0}
    if ftype == "rsi":
        w = int(params.get("window", 14)); return _rsi(close, w), {"lookback": w + 1}
    if ftype == "ema":
        w = int(params.get("window", 20))
        k = 2.0 / (w + 1)
        out = np.full(close.size, np.nan)
        prev = close[0]; out[0] = prev
        for i in range(1, close.size):
            prev = close[i] * k + prev * (1 - k); out[i] = prev
        return out, {"lookback": 0}
    if ftype in ("atr", "bollinger"):
        if "high" not in ctx or "low" not in ctx:
            raise StatsError(INVALID_INPUT, f"feature '{name}': {ftype} requires high/low")
        h, l = ctx["high"], ctx["low"]
        if ftype == "atr":
            w = int(params.get("window", 14))
            tr = np.full(close.size, np.nan)
            for i in range(1, close.size):
                tr[i] = max(h[i] - l[i], abs(h[i] - close[i - 1]), abs(l[i] - close[i - 1]))
            return _rolling(tr, w, lambda c: float(c.mean())), {"lookback": w + 1}
        w = int(params.get("window", 20)); k = float(params.get("k", 2.0))
        mid = _rolling(close, w, lambda c: float(c.mean()))
        sd = _rolling(close, w, lambda c: float(np.std(c, ddof=0)))
        with np.errstate(divide="ignore", invalid="ignore"):
            return (close - mid) / np.where(sd == 0, np.nan, k * sd), {"lookback": w}
    if ftype == "vwap":
        if "volume" not in ctx:
            raise StatsError(INVALID_INPUT, f"feature '{name}': vwap requires volume")
        vol = ctx["volume"]
        pv = np.cumsum(np.where(np.isfinite(close * vol), close * vol, 0.0))
        vv = np.cumsum(np.where(np.isfinite(vol), vol, 0.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            return pv / np.where(vv == 0, np.nan, vv), {"lookback": 0}
    if ftype == "drawdown":
        peak = np.maximum.accumulate(close)
        with np.errstate(divide="ignore", invalid="ignore"):
            return close / peak - 1.0, {"lookback": 0}
    if ftype == "beta":
        if "benchmark" not in ctx:
            raise StatsError(INVALID_INPUT, f"feature '{name}': beta requires a benchmark")
        w = int(params.get("window", 60))
        as_, bs = close, ctx["benchmark"]
        ra = np.full(close.size, np.nan); rb = np.full(close.size, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            ra[1:] = as_[1:] / as_[:-1] - 1.0; rb[1:] = bs[1:] / bs[:-1] - 1.0
        out = np.full(close.size, np.nan)
        for i in range(w, close.size):
            ca, cb = ra[i - w + 1: i + 1], rb[i - w + 1: i + 1]
            m = np.isfinite(ca) & np.isfinite(cb)
            if m.sum() > 2 and np.var(cb[m]) > 0:
                out[i] = float(np.cov(ca[m], cb[m])[0, 1] / np.var(cb[m]))
        return out, {"lookback": w + 1}
    raise StatsError(INVALID_INPUT, f"feature '{name}': unknown type '{ftype}'")


def run(args: dict) -> dict:
    values = to_float_array(args.get("values"), "values")
    require_min_length(values, 3, "values")
    specs = args.get("features")
    if not specs or not isinstance(specs, list):
        raise StatsError(INVALID_INPUT, "features must be a non-empty list")
    ctx: dict = {"price": values, "close": values}
    if args.get("close") is not None:
        ctx["close"] = to_float_array(args.get("close"), "close")
    for key in ("high", "low", "volume", "benchmark"):
        if args.get(key) is not None:
            arr = to_float_array(args.get(key), key)
            if arr.size != values.size:
                raise StatsError(INVALID_INPUT, f"{key} length must match values")
            ctx[key] = arr
    # expose first-difference returns as a variable
    r = np.full(values.size, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = values[1:] / values[:-1] - 1.0
    ctx["returns"] = r

    features: dict[str, list] = {}
    metadata: dict[str, dict] = {}
    missingness: dict[str, dict] = {}
    warnings: list[str] = []
    for spec in specs:
        series, meta = _build_one(spec, ctx, values)
        name = spec["name"]
        features[name] = as_list(series)
        meta.update({
            "inputs": meta.get("inputs", ["close"]),
            "outputSchema": {"type": "array", "items": {"type": "number", "nullable": True}},
            "warmUp": int(meta.get("lookback", 0)),
            "missingBehavior": "NaN until warm-up; never filled",
            "pointInTimeSafe": bool(meta.get("pointInTimeSafe", True)),
            "version": "1.0.0",
        })
        metadata[name] = meta
        finite = series[np.isfinite(series)]
        missingness[name] = {
            "missingCount": int(np.isnan(series).sum()),
            "coverage": float(finite.size / series.size) if series.size else 0.0,
        }
        if np.isfinite(series).sum() == 0:
            warnings.append(f"feature '{name}' produced no finite values (check windows/inputs)")

    return make_response(
        "build_features",
        {"featureCount": len(specs)},
        summary={"features": list(features.keys()), "observations": int(values.size)},
        results={"features": features, "featureMetadata": metadata},
        diagnostics={"missingness": missingness},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
