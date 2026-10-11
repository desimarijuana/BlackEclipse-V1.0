"""Leakage-safe feature selection for the ML Research Lab.

Selection is FITTED on the training fold only and then applied to validation /
test folds. Fitting on the full dataset before evaluation would leak held-out
labels into the feature choice, so the training pipeline never does it.

Supported methods (all pure NumPy): ``variance``, ``correlation`` (Pearson /
point-biserial), ``univariate`` (|correlation| ranked) and ``mutual_information``
(equal-frequency histogram estimator). ``none`` selects every feature.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .models import MLError, SELECTION_METHODS
from ..stats.base import INVALID_INPUT, INSUFFICIENT_DATA


def _finite_columns(X: np.ndarray) -> np.ndarray:
    return np.isfinite(X)


def _col_scores_correlation(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Absolute Pearson correlation of each column with the target (pairwise-complete)."""
    d = X.shape[1]
    scores = np.zeros(d)
    for j in range(d):
        mask = np.isfinite(X[:, j]) & np.isfinite(y)
        if mask.sum() < 3:
            continue
        a = X[mask, j] - X[mask, j].mean()
        b = y[mask] - y[mask].mean()
        denom = float(np.sqrt((a * a).sum()) * np.sqrt((b * b).sum()))
        scores[j] = abs(float((a * b).sum()) / denom) if denom > 0 else 0.0
    return scores


def _mutual_information(x: np.ndarray, y: np.ndarray, bins: int = 10,
                        discrete_y: bool = False) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < bins:
        return 0.0
    # equal-frequency bins for the feature
    edges = np.quantile(x, np.linspace(0, 1, bins + 1)[1:-1])
    xb = np.digitize(x, edges)
    if discrete_y:
        yv = y.astype(int)
        yv -= yv.min()
        yb = yv
        y_n = int(yv.max()) + 1
    else:
        yedges = np.quantile(y, np.linspace(0, 1, bins + 1)[1:-1])
        yb = np.digitize(y, yedges)
        y_n = bins
    x_n = bins
    joint = np.zeros((x_n, y_n))
    for a, b in zip(xb, yb):
        joint[a, b] += 1.0
    pxy = joint / joint.sum()
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    nz = pxy > 0
    mi = 0.0
    for a in range(x_n):
        for b in range(y_n):
            if nz[a, b]:
                mi += pxy[a, b] * float(np.log(pxy[a, b] / (px[a, 0] * py[0, b])))
    return float(mi)


def fit_selection(X: np.ndarray, y: np.ndarray, task: str, feature_names: list[str],
                  method: str = "none", *, top_k: int = 0, threshold: float = 0.0,
                  bins: int = 10) -> dict[str, Any]:
    """Fit a feature-selection rule on the TRAINING fold.

    Returns ``{method, selected, scores, featureNames, dropped}``. ``selected``
    is the list of kept column indices; ``dropped`` the complement.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2:
        raise MLError(INVALID_INPUT, "X must be a 2-D matrix")
    if X.shape[0] != y.shape[0]:
        raise MLError(INVALID_INPUT, "X and y must have the same number of rows")
    if X.shape[0] < 4:
        raise MLError(INSUFFICIENT_DATA, "need at least 4 training rows to select features", 422)
    d = X.shape[1]
    if len(feature_names) != d:
        feature_names = [f"f{j}" for j in range(d)]
    if method not in SELECTION_METHODS:
        raise MLError(INVALID_INPUT, f"unknown selection method {method!r}")

    if method == "none":
        scores = np.ones(d)
    elif method == "variance":
        scores = np.nanvar(np.where(np.isfinite(X), X, np.nan), axis=0)
        scores = np.nan_to_num(scores, nan=0.0)
    elif method in ("correlation", "univariate"):
        scores = _col_scores_correlation(X, y)
    elif method == "mutual_information":
        discrete_y = task == "classification"
        scores = np.array([_mutual_information(X[:, j], y, bins=bins, discrete_y=discrete_y)
                           for j in range(d)])
    else:  # pragma: no cover - guarded above
        scores = np.ones(d)

    order = np.argsort(-scores, kind="mergesort")
    if method == "none":
        selected = list(range(d))
    else:
        if top_k and top_k > 0:
            keep = order[: min(top_k, d)]
            selected = sorted(int(i) for i in keep if scores[i] >= threshold)
        else:
            selected = sorted(int(i) for i in range(d) if scores[i] >= threshold)
        if not selected:
            selected = [int(order[0])]  # never return zero features
    dropped = [int(i) for i in range(d) if i not in selected]

    return {
        "method": method,
        "selected": selected,
        "dropped": dropped,
        "scores": {feature_names[j]: float(scores[j]) for j in range(d)},
        "featureNames": list(feature_names),
    }


def apply_selection(X: np.ndarray, selected: list[int]) -> np.ndarray:
    return np.asarray(X, dtype=float)[:, list(selected)]


def correlation_matrix(X: np.ndarray) -> dict[str, Any]:
    """Pairwise Pearson correlations ignoring non-finite pairs (for the explorer)."""
    X = np.asarray(X, dtype=float)
    d = X.shape[1]
    out = [[None] * d for _ in range(d)]
    for i in range(d):
        for j in range(i, d):
            mask = np.isfinite(X[:, i]) & np.isfinite(X[:, j])
            if mask.sum() < 3:
                c = None
            else:
                a, b = X[mask, i], X[mask, j]
                a, b = a - a.mean(), b - b.mean()
                denom = float(np.sqrt((a * a).sum()) * np.sqrt((b * b).sum()))
                c = float((a * b).sum() / denom) if denom > 0 else None
            out[i][j] = out[j][i] = c
    return {"matrix": out}


__all__ = ["fit_selection", "apply_selection", "correlation_matrix"]
