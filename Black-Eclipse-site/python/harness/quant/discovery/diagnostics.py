"""Market-structure diagnostics — what kind of process does this series look like?

These are descriptive statistics, not a prediction. They are the bridge between
"here is a price series" and "here is a method worth testing":

* variance ratios and a Hurst estimate separate trend from mean reversion;
* AR(1) half-life says how fast a dislocation decays;
* absolute-return autocorrelation measures volatility clustering;
* weekday/month buckets test calendar effects (and are multiple-testing-prone);
* breakout frequency measures how often a channel is exceeded.

Everything is computed on a chronological in-sample window and optionally
repeated on a held-out tail, so a structure that only exists in-sample is named
as such rather than sold as an edge.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np

from ..errors import QuantError


def _arrays(rows: Any) -> dict[str, np.ndarray]:
    if isinstance(rows, dict):
        try:
            data = {k: np.asarray(rows[k], dtype=float) for k in
                    ("open", "high", "low", "close", "volume") if k in rows}
        except Exception as exc:  # noqa: BLE001
            raise QuantError("coloured arrays are malformed") from exc
        timestamps = list(rows.get("timestamp") or [])
        if "close" not in data:
            raise QuantError("diagnostics need a close series")
        if "high" not in data:
            data["high"] = data["close"]
        if "low" not in data:
            data["low"] = data["close"]
        if "open" not in data:
            data["open"] = data["close"]
        if "volume" not in data:
            data["volume"] = np.zeros_like(data["close"])
        return {**data, "timestamp": np.asarray(timestamps, dtype=object)}
    if not isinstance(rows, Iterable):
        raise QuantError("diagnostics need rows or arrays")
    items = list(rows)
    if not items:
        raise QuantError("the series is empty")
    out: dict[str, list[Any]] = {k: [] for k in
                                 ("open", "high", "low", "close", "volume", "timestamp")}
    for item in items:
        try:
            close = float(item["close"])
        except (KeyError, TypeError, ValueError) as exc:
            raise QuantError("every row needs a numeric close") from exc
        out["close"].append(close)
        out["open"].append(float(item.get("open", close)))
        out["high"].append(float(item.get("high", close)))
        out["low"].append(float(item.get("low", close)))
        out["volume"].append(float(item.get("volume", 0.0)))
        out["timestamp"].append(item.get("timestamp"))
    return {k: np.asarray(v, dtype=object if k == "timestamp" else float)
            for k, v in out.items()}


def _autocorr(x: np.ndarray, lag: int) -> Optional[float]:
    if x.size <= lag + 2:
        return None
    a = x[:-lag]
    b = x[lag:]
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _variance_ratio(returns: np.ndarray, q: int) -> Optional[float]:
    if returns.size < q + 2:
        return None
    var1 = float(np.var(returns, ddof=1))
    if var1 <= 0:
        return None
    agg = np.convolve(returns, np.ones(q), mode="valid")
    varq = float(np.var(agg, ddof=1))
    return varq / (q * var1)


def _hurst_from_vr(returns: np.ndarray) -> Optional[float]:
    estimates = []
    for q in (2, 4, 8, 16):
        vr = _variance_ratio(returns, q)
        if vr is not None and vr > 0:
            estimates.append(0.5 + 0.5 * np.log(vr) / np.log(q))
    if not estimates:
        return None
    return float(np.median(estimates))


def _half_life(log_price: np.ndarray) -> Optional[float]:
    if log_price.size < 20:
        return None
    x = log_price[:-1]
    y = np.diff(log_price)
    xm, ym = x - x.mean(), y - y.mean()
    denom = float(xm @ xm)
    if denom <= 0:
        return None
    b = float(xm @ ym) / denom
    if b >= -1e-9 or b <= -1.0:
        return None
    return float(-np.log(2.0) / np.log(1.0 + b))


def _weekday(timestamps: np.ndarray) -> np.ndarray:
    out = np.full(timestamps.size, -1, dtype=int)
    for i, ts in enumerate(timestamps):
        text = str(ts or "")[:10]
        try:
            from datetime import date
            out[i] = date.fromisoformat(text).weekday()
        except ValueError:
            out[i] = -1
    return out


def _seasonality(returns: np.ndarray, timestamps: np.ndarray) -> dict[str, Any]:
    # Returns are first differences; tolerate a caller passing bar timestamps.
    if timestamps.size == returns.size + 1:
        timestamps = timestamps[1:]
    if timestamps.size != returns.size:
        return {"available": False, "reason": "timestamps do not align with returns"}
    days = _weekday(timestamps)
    if np.sum(days >= 0) < max(30, returns.size // 2):
        return {"available": False, "reason": "timestamps are missing or unparseable"}
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    buckets = []
    for d, name in enumerate(names):
        vals = returns[days == d]
        if vals.size < 3:
            continue
        mean = float(vals.mean())
        se = float(vals.std(ddof=1) / np.sqrt(vals.size))
        buckets.append({"day": name, "mean": mean, "n": int(vals.size),
                        "tStat": (mean / se) if se > 0 else None})
    if not buckets:
        return {"available": False, "reason": "not enough observations per weekday"}
    means = [b["mean"] for b in buckets]
    strongest = max(buckets, key=lambda b: abs(b["mean"]))
    return {
        "available": True,
        "byWeekday": buckets,
        "spread": float(max(means) - min(means)),
        "strongest": strongest,
        "warning": "calendar effects are multiple-testing-prone; require long "
                   "out-of-sample confirmation and costs",
    }


def _structure_metrics(arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    close = np.asarray(arrays["close"], dtype=float)
    if close.size < 30:
        raise QuantError("at least 30 bars are required for structure diagnostics")
    if not np.all(np.isfinite(close)) or np.any(close <= 0):
        raise QuantError("close must be finite and positive")
    returns = np.diff(np.log(close))
    log_price = np.log(close)
    n = returns.size

    lags = {f"lag{k}": _autocorr(returns, k) for k in (1, 2, 3, 5, 10)}
    abs_ac = {f"lag{k}": _autocorr(np.abs(returns), k) for k in (1, 2, 5, 10)}
    vrs = {f"q{q}": _variance_ratio(returns, q) for q in (2, 4, 8, 16)}
    hurst = _hurst_from_vr(returns)

    t = np.arange(close.size, dtype=float)
    slope, intercept = np.polyfit(t, log_price, 1)
    fitted = slope * t + intercept
    ss_tot = float(((log_price - log_price.mean()) ** 2).sum())
    r2 = 1.0 - float(((log_price - fitted) ** 2).sum()) / ss_tot if ss_tot > 0 else 0.0

    sma200 = np.convolve(close, np.ones(200) / 200, mode="valid") if close.size >= 200 else None
    above = None
    if sma200 is not None and sma200.size:
        above = float(np.mean(close[-sma200.size:] > sma200))

    breakout = None
    look = 20
    if close.size > look + 5:
        prior_high = np.array([close[i - look:i].max() for i in range(look, close.size)])
        breakout = float(np.mean(close[look:] > prior_high))

    realized = returns[-60:] if returns.size >= 60 else returns
    vol = float(realized.std(ddof=1) * np.sqrt(252.0)) if realized.size > 2 else None
    drift_signal = (float(slope * 252.0) / vol) if vol and vol > 0 else None

    return {
        "observations": int(close.size),
        "returnObservations": int(n),
        "returnAutocorrelation": lags,
        "absReturnAutocorrelation": abs_ac,
        "varianceRatio": vrs,
        "hurstExponent": hurst,
        "meanReversionHalfLifeBars": _half_life(log_price),
        "trendR2": float(r2),
        "annualizedSlope": float(slope * 252.0),
        "driftSignal": drift_signal,
        "fractionAboveSma200": above,
        "breakoutFrequency20": breakout,
        "annualizedVolatility": vol,
        "totalReturn": float(close[-1] / close[0] - 1.0),
    }


def _classify(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    hurst = metrics.get("hurstExponent")
    vrs = metrics.get("varianceRatio") or {}
    vr_med = float(np.median([v for v in vrs.values() if v is not None])) if any(
        v is not None for v in vrs.values()) else None
    trend_r2 = float(metrics.get("trendR2") or 0.0)
    abs_ac = metrics.get("absReturnAutocorrelation") or {}
    vol_cluster = max((v for v in abs_ac.values() if v is not None), default=0.0)
    drift_signal = metrics.get("driftSignal")
    reasons: list[str] = []

    # A strong sample-wide drift is a different phenomenon from short-horizon
    # persistence. Judge it first: a random walk can also show a high R², so the
    # drift is only called material when it is large relative to volatility.
    if drift_signal is not None and abs(float(drift_signal)) >= 2.0 and trend_r2 >= 0.6:
        reasons.append(f"sample drift is {drift_signal:.2f}× volatility (R² {trend_r2:.2f})")
        return ("drifting" if hurst is not None and hurst < 0.55 else "trending"), reasons

    if hurst is not None and hurst >= 0.55 and (vr_med is None or vr_med >= 1.0):
        reasons.append(f"Hurst {hurst:.3f} and variance ratio {vr_med or float('nan'):.2f} "
                       "lean persistent")
        if trend_r2 >= 0.25:
            reasons.append(f"log price trend R² {trend_r2:.2f}")
        if vol_cluster >= 0.1:
            reasons.append(f"volatility clusters (abs-return autocorr {vol_cluster:.2f})")
        return "trending", reasons
    if hurst is not None and hurst <= 0.45 and vr_med is not None and vr_med <= 0.95:
        hl = metrics.get("meanReversionHalfLifeBars")
        reasons.append(f"Hurst {hurst:.3f}, variance ratio {vr_med:.2f} lean mean-reverting")
        if hl:
            reasons.append(f"AR(1) half-life ≈ {hl:.0f} bars")
        return "mean_reverting", reasons
    if vol_cluster >= 0.15:
        reasons.append(f"volatility clustering dominates (abs-return autocorr {vol_cluster:.2f})")
        return "volatility_clustered", reasons
    if trend_r2 >= 0.5:
        reasons.append(f"a strong sample-wide drift (R² {trend_r2:.2f}) but weak "
                       "short-horizon persistence")
        return "drifting", reasons
    reasons.append("variance ratio near 1 and Hurst near 0.5: close to a random walk")
    return "random", reasons


def _candidate_families(structure: str, metrics: dict[str, Any],
                        seasonality: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def add(method_id: str, score: float, reason: str) -> None:
        candidates.append({"methodId": method_id, "score": round(score, 3),
                           "reason": reason})

    if structure == "trending":
        add("trend_ema_cross", 0.9, "persistent structure in the sample")
        add("trend_donchian_breakout", 0.8, "breakout frequency supports channel entries")
        add("momentum_cross_sectional", 0.5, "if a universe is available")
    elif structure == "mean_reverting":
        add("mean_reversion_bollinger", 0.9, "negative autocorrelation / low variance ratio")
        add("mean_reversion_rsi", 0.7, "exhaustion entries fit a reverting series")
        add("pairs_cointegration", 0.5, "if a linked asset exists")
    elif structure == "volatility_clustered":
        add("volatility_breakout", 0.9, "volatility clusters; trade the expansion")
        add("trend_ema_cross", 0.5, "expansions often have direction")
    elif structure == "drifting":
        add("trend_ema_cross", 0.6, "sample-wide drift, but verify persistence")
        add("low_volatility", 0.4, "if this is a cross-section")
    else:
        add("trend_ema_cross", 0.3, "weak prior; test, do not assume")
        add("mean_reversion_bollinger", 0.3, "weak prior; test, do not assume")

    if seasonality.get("available") and abs(
            (seasonality.get("strongest") or {}).get("mean", 0.0)) > 0:
        add("seasonality_calendar", 0.4, "calendar buckets differ; multiple-testing risk")
    return sorted(candidates, key=lambda c: -c["score"])


def _oos_stability(arrays: dict[str, np.ndarray], oos_fraction: float) -> dict[str, Any]:
    close = np.asarray(arrays["close"], dtype=float)
    n = close.size
    cut = max(30, int(n * (1.0 - oos_fraction)))
    if cut >= n - 10:
        return {"available": False, "reason": "not enough out-of-sample bars"}
    base = _structure_metrics({"close": close[:cut], "high": arrays["high"][:cut],
                               "low": arrays["low"][:cut], "open": arrays["open"][:cut],
                               "volume": arrays["volume"][:cut]})
    oos = _structure_metrics({"close": close[cut:], "high": arrays["high"][cut:],
                              "low": arrays["low"][cut:], "open": arrays["open"][cut:],
                              "volume": arrays["volume"][cut:]})
    structure_is, _ = _classify(base)
    structure_oos, _ = _classify(oos)
    return {
        "available": True,
        "inSampleStructure": structure_is,
        "outOfSampleStructure": structure_oos,
        "stable": structure_is == structure_oos,
        "inSample": {k: base.get(k) for k in
                     ("hurstExponent", "trendR2", "meanReversionHalfLifeBars",
                      "annualizedVolatility")},
        "outOfSample": {k: oos.get(k) for k in
                        ("hurstExponent", "trendR2", "meanReversionHalfLifeBars",
                         "annualizedVolatility")},
        "warning": "a structure that changes out-of-sample is not a tradable edge",
    }


def analyze_structure(rows: Any, *, interval: str = "1d",
                      oos_fraction: float = 0.3) -> dict[str, Any]:
    arrays = _arrays(rows)
    metrics = _structure_metrics(arrays)
    structure, reasons = _classify(metrics)
    season = _seasonality(
        np.diff(np.log(arrays["close"])),
        arrays["timestamp"][1:] if arrays["timestamp"].size else arrays["timestamp"],
    )
    stability = _oos_stability(arrays, oos_fraction) if 0 < oos_fraction < 1 else {
        "available": False, "reason": "oos split disabled"}
    candidates = _candidate_families(structure, metrics, season)
    insights = list(reasons)
    if season.get("available"):
        strongest = season["strongest"]
        insights.append(f"strongest weekday mean is {strongest['day']} "
                        f"({strongest['mean'] * 100:.3f}%/bar)")
    if stability.get("available"):
        insights.append(
            "structure is stable out-of-sample" if stability["stable"]
            else "structure changes out-of-sample: treat any edge with suspicion"
        )
    return {
        "interval": interval,
        "structure": structure,
        "insights": insights,
        "metrics": metrics,
        "seasonality": season,
        "outOfSampleStability": stability,
        "candidateMethods": candidates,
        "note": "descriptive structure, not a signal; candidate methods still "
                "require a full validation cycle",
    }


__all__ = ["analyze_structure"]
