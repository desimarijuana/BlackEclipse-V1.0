"""calculate_regime — volatility regimes, trend/range, change points, HMM."""

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

DESCRIPTION = (
    "Regime and change-point analysis. Methods: volatility quantile regimes, "
    "rule-based trend/range classification, variance change-point detection "
    "(binary segmentation), and a two-state Gaussian hidden Markov model "
    "(Baum–Welch). Returns regime labels, model settings and transition "
    "diagnostics. Classification is retrospective unless expanding thresholds "
    "are requested — a fitted threshold is never presented as a real-time signal."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"},
                   "description": "Price series (returns are computed internally)."},
        "inputType": {"type": "string", "enum": ["prices", "returns"], "default": "prices"},
        "method": {"type": "string",
                   "enum": ["volatility", "trend_range", "changepoint", "hmm"],
                   "default": "volatility"},
        "window": {"type": "integer", "minimum": 2, "default": 20},
        "nRegimes": {"type": "integer", "minimum": 2, "maximum": 5, "default": 2},
        "seed": {"type": "integer", "default": 7},
        "expandingThresholds": {"type": "boolean", "default": False},
    },
    "required": ["values"],
}


def _returns(values: np.ndarray, input_type: str) -> np.ndarray:
    if input_type == "returns":
        return values
    with np.errstate(divide="ignore", invalid="ignore"):
        return values[1:] / values[:-1] - 1.0


def _rolling_vol(r: np.ndarray, window: int) -> np.ndarray:
    out = np.full(r.size, np.nan)
    for i in range(window - 1, r.size):
        chunk = r[i - window + 1: i + 1]
        if np.isfinite(chunk).all():
            out[i] = float(np.std(chunk, ddof=1))
    return out


def _volatility_regimes(r: np.ndarray, window: int, n: int, expanding: bool) -> dict:
    vol = _rolling_vol(r, window)
    finite = vol[np.isfinite(vol)]
    if finite.size < n:
        raise StatsError(INVALID_INPUT, "not enough volatility observations", 422)
    labels = np.full(r.size, -1, dtype=int)
    if expanding:
        for i in range(r.size):
            hist = vol[: i + 1]
            hist = hist[np.isfinite(hist)]
            if hist.size < window:
                continue
            qs = np.quantile(hist, np.linspace(0, 1, n + 1)[1:-1])
            labels[i] = int(np.searchsorted(qs, vol[i]))
        thresholds = None
    else:
        qs = np.quantile(finite, np.linspace(0, 1, n + 1)[1:-1])
        thresholds = [float(q) for q in qs]
        for i in range(r.size):
            if np.isfinite(vol[i]):
                labels[i] = int(np.searchsorted(qs, vol[i]))
    return {"labels": labels, "volatility": vol, "thresholds": thresholds, "window": window}


def _trend_range(r: np.ndarray, window: int) -> dict:
    labels = np.full(r.size, -1, dtype=int)
    for i in range(window - 1, r.size):
        chunk = r[i - window + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        slope = float(np.polyfit(np.arange(window), chunk, 1)[0])
        vol = float(np.std(chunk, ddof=1)) or 1e-12
        # trend when the per-period slope dominates noise (t-like ratio)
        ratio = slope / vol
        labels[i] = 0 if abs(ratio) < 0.15 else (1 if ratio > 0 else 2)
    return {"labels": labels, "regimeNames": ["range", "uptrend", "downtrend"], "window": window}


def _changepoint(r: np.ndarray, max_cps: int = 5, min_size: int = 5) -> dict:
    x = np.nan_to_num(r, nan=0.0)

    def cost(a: np.ndarray) -> float:
        if a.size < 2:
            return 0.0
        return float(a.var() * a.size)

    def best_split(a: np.ndarray) -> tuple[int, float]:
        base = cost(a)
        best_i, best_gain = -1, 0.0
        for i in range(min_size, a.size - min_size + 1):
            gain = base - cost(a[:i]) - cost(a[i:])
            if gain > best_gain:
                best_gain, best_i = gain, i
        return best_i, best_gain

    cps: list[int] = []
    segments = [(0, x.size)]
    for _ in range(max_cps):
        best = None
        for idx, (s, e) in enumerate(segments):
            i, gain = best_split(x[s:e])
            if i > 0 and (best is None or gain > best[0]):
                best = (gain, idx, s + i)
        if best is None or best[0] <= 0:
            break
        gain, idx, split = best
        s, e = segments[idx]
        cps.append(split)
        segments[idx] = (s, split)
        segments.append((split, e))
    labels = np.zeros(x.size, dtype=int)
    for k, cp in enumerate(sorted(cps)):
        labels[cp:] = k + 1
    return {"labels": labels, "changePoints": sorted(cps), "nSegments": len(cps) + 1}


def _hmm(r: np.ndarray, n_states: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    x = np.nan_to_num(r, nan=0.0)
    n = x.size
    if n < n_states * 10:
        raise StatsError(INVALID_INPUT, "HMM needs more observations", 422)
    # init: split by quantiles of x
    order = np.argsort(x)
    chunks = np.array_split(order, n_states)
    mu = np.array([x[c].mean() for c in chunks])
    var = np.array([max(x[c].var(), 1e-8) for c in chunks])
    A = np.full((n_states, n_states), 1.0 / n_states)
    pi = np.full(n_states, 1.0 / n_states)

    def gauss_pdf(xv: np.ndarray) -> np.ndarray:
        return np.exp(-0.5 * (xv[:, None] - mu[None, :]) ** 2 / var[None, :]) / np.sqrt(
            2 * math.pi * var[None, :]
        )

    prev_ll = -np.inf
    for _ in range(100):
        B = gauss_pdf(x)
        B = np.clip(B, 1e-300, None)
        alpha = np.zeros((n, n_states))
        scale = np.zeros(n)
        alpha[0] = pi * B[0]
        scale[0] = alpha[0].sum()
        alpha[0] /= scale[0] if scale[0] > 0 else 1.0
        for t in range(1, n):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            scale[t] = alpha[t].sum()
            alpha[t] /= scale[t] if scale[t] > 0 else 1.0
        beta = np.zeros((n, n_states))
        beta[-1] = 1.0
        for t in range(n - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / (scale[t + 1] if scale[t + 1] > 0 else 1.0)
        gamma = alpha * beta
        gamma /= np.clip(gamma.sum(axis=1, keepdims=True), 1e-300, None)
        xi_sum = np.zeros((n_states, n_states))
        for t in range(n - 1):
            xi = (alpha[t][:, None] * A) * (B[t + 1] * beta[t + 1])[None, :]
            s = xi.sum()
            if s > 0:
                xi_sum += xi / s
        pi = gamma[0] / gamma[0].sum()
        A = xi_sum / np.clip(xi_sum.sum(axis=1, keepdims=True), 1e-300, None)
        for k in range(n_states):
            w = gamma[:, k]
            wsum = w.sum()
            if wsum > 0:
                mu[k] = float((w * x).sum() / wsum)
                var[k] = float(max((w * (x - mu[k]) ** 2).sum() / wsum, 1e-8))
        ll = float(np.sum(np.log(scale + 1e-300)))
        if abs(ll - prev_ll) < 1e-6:
            break
        prev_ll = ll

    # Viterbi
    delta = np.zeros((n, n_states))
    psi = np.zeros((n, n_states), dtype=int)
    B = np.clip(gauss_pdf(x), 1e-300, None)
    delta[0] = np.log(pi + 1e-300) + np.log(B[0])
    for t in range(1, n):
        for k in range(n_states):
            probs = delta[t - 1] + np.log(A[:, k] + 1e-300)
            psi[t, k] = int(np.argmax(probs))
            delta[t, k] = probs[psi[t, k]] + math.log(B[t, k])
    states = np.zeros(n, dtype=int)
    states[-1] = int(np.argmax(delta[-1]))
    for t in range(n - 2, -1, -1):
        states[t] = psi[t + 1, states[t + 1]]

    # order states by mean
    order = np.argsort(mu)
    remap = {int(old): int(new) for new, old in enumerate(order)}
    states = np.array([remap[int(s)] for s in states])
    return {
        "labels": states,
        "means": [float(mu[o]) for o in order],
        "variances": [float(var[o]) for o in order],
        "transitionMatrix": [[float(A[order[i], order[j]]) for j in range(n_states)] for i in range(n_states)],
        "logLikelihood": float(prev_ll),
    }


def run(args: dict) -> dict:
    values = to_float_array(args.get("values"), "values")
    require_min_length(values, 10, "values")
    input_type = get_str(args, "inputType", "prices")
    method = get_str(args, "method", "volatility")
    r = _returns(values, input_type)
    r = np.where(np.isfinite(r), r, np.nan)
    window = get_int(args, "window", 20, minimum=2)
    n_regimes = get_int(args, "nRegimes", 2, minimum=2)
    expanding = bool(args.get("expandingThresholds", False))
    warnings: list[str] = []

    if method == "volatility":
        info = _volatility_regimes(r, window, n_regimes, expanding)
        names = [f"vol_q{i + 1}" for i in range(n_regimes)]
    elif method == "trend_range":
        info = _trend_range(r, window)
        names = info["regimeNames"]
    elif method == "changepoint":
        info = _changepoint(r)
        names = [f"segment_{i}" for i in range(info["nSegments"])]
    elif method == "hmm":
        info = _hmm(r, n_regimes, get_int(args, "seed", 7, minimum=0))
        names = [f"state_{i}" for i in range(n_regimes)]
    else:
        raise StatsError(INVALID_INPUT, f"unknown regime method: {method}")

    if not expanding and method in ("volatility", "changepoint"):
        warnings.append(
            "regime thresholds/model were fitted on the full sample and are "
            "retrospective; do not treat labels as a real-time signal"
        )

    labels = info["labels"]
    counts = {names[i]: int((labels == i).sum()) for i in range(len(names))}
    diagnostics = {"counts": counts}
    for key in ("thresholds", "changePoints", "transitionMatrix", "means", "variances", "logLikelihood"):
        if key in info:
            diagnostics[key] = info[key]

    return make_response(
        "calculate_regime",
        {"method": method, "window": window, "nRegimes": n_regimes, "expandingThresholds": expanding},
        summary={"method": method, "regimeNames": names, "observations": int(r.size)},
        results={"regimeLabels": [int(x) for x in labels], "regimeNames": names,
                 "volatility": as_list(info.get("volatility")) if "volatility" in info else None},
        diagnostics=diagnostics, warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
