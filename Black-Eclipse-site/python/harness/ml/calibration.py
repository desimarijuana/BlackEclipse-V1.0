"""Probability calibration — fit on OUT-OF-FOLD predictions, never on the holdout.

A classifier's scores are not probabilities. Platt scaling (a one-dimensional
logistic fit on the logit of the score) and isotonic regression (a monotone
step function) both learn a correction from `(score, outcome)` pairs.

The pairs here are the pooled out-of-fold predictions of the training run: every
row was predicted by a model that had never seen it, so the correction is fitted
on genuinely held-out data. The final holdout is used only to REPORT the effect,
never to fit it. Binary classification only — a multiclass calibration needs a
per-class design that this phase does not claim.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .models import MLError

_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(np.asarray(z, dtype=float), -700.0, 700.0)
    return 1.0 / (1.0 + np.exp(-z))


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - y) ** 2))


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    clipped = np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped)))


def _fit_platt(scores: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Fit `p = sigmoid(a * logit(score) + b)` by Newton steps. Pure NumPy."""
    z = _logit(scores)
    a, b = 1.0, 0.0
    for _ in range(100):
        p = _sigmoid(a * z + b)
        w = np.clip(p * (1.0 - p), 1e-12, None)
        grad = np.array([np.sum((p - y) * z), np.sum(p - y)])
        hess = np.array([
            [np.sum(w * z * z), np.sum(w * z)],
            [np.sum(w * z), np.sum(w)],
        ])
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            break
        a -= step[0]
        b -= step[1]
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return {"a": float(a), "b": float(b)}


def _fit_isotonic(scores: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Pool-adjacent-violators on the score order, returned as step points."""
    order = np.argsort(scores, kind="mergesort")
    xs = np.asarray(scores, dtype=float)[order]
    ys = np.asarray(y, dtype=float)[order]
    # blocks of (weight, mean) merged while the means decrease
    blocks: list[list[float]] = []          # [sum_y, count, max_x]
    for x, target in zip(xs, ys):
        blocks.append([float(target), 1.0, float(x)])
        while len(blocks) >= 2 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            sy, n, mx = blocks.pop()
            blocks[-1][0] += sy
            blocks[-1][1] += n
            blocks[-1][2] = mx
    points = []
    for sy, n, mx in blocks:
        points.append({"x": float(mx), "y": float(np.clip(sy / n, 0.0, 1.0))})
    return {"points": points}


def fit_calibration(
    probabilities: np.ndarray,
    y: np.ndarray,
    *,
    method: str = "platt",
    min_rows: int = 50,
) -> Optional[dict[str, Any]]:
    """Fit a binary calibration curve on out-of-fold probabilities.

    Returns ``None`` (with the reason the caller can report) when the method is
    "none", the data is too small, or the labels are not binary — never a
    silently-identity "calibration".
    """
    if method in (None, "", "none"):
        return None
    if method not in ("platt", "isotonic"):
        raise MLError("INVALID_INPUT", f"unknown calibration method {method!r}")
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(p) & np.isfinite(y)
    p, y = p[finite], y[finite]
    if p.size < min_rows:
        return None
    if set(np.unique(y).tolist()) != {0.0, 1.0}:
        return None

    params = _fit_platt(p, y) if method == "platt" else _fit_isotonic(p, y)
    calibrated = apply_calibration({"method": method, **params}, p)
    return {
        "method": method,
        "fittedOn": "out-of-fold",
        "rows": int(p.size),
        **params,
        "brierBefore": _brier(y, p),
        "brierAfter": _brier(y, calibrated),
        "logLossBefore": _log_loss(y, p),
        "logLossAfter": _log_loss(y, calibrated),
    }


def apply_calibration(state: dict[str, Any], probabilities: np.ndarray) -> np.ndarray:
    """Apply a fitted calibration to probabilities (identity when absent)."""
    p = np.asarray(probabilities, dtype=float)
    if not state:
        return p
    method = state.get("method")
    if method == "platt":
        return _sigmoid(float(state.get("a", 1.0)) * _logit(p) + float(state.get("b", 0.0)))
    if method == "isotonic":
        points = state.get("points") or []
        if not points:
            return p
        xs = np.asarray([pt["x"] for pt in points], dtype=float)
        ys = np.asarray([pt["y"] for pt in points], dtype=float)
        # step function: the value of the last block whose upper bound is <= p
        idx = np.searchsorted(xs, p, side="left")
        return ys[np.clip(idx, 0, len(ys) - 1)]
    return p


__all__ = ["apply_calibration", "fit_calibration"]
