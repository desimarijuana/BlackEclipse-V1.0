"""Evaluation metrics for the ML Research Lab.

Pure NumPy, deterministic, independently testable. Metrics are split into three
families and NEVER mixed: predictive metrics (classification/regression/ranking)
are reported separately from linked strategy performance, which lives in the
shared backtester.

Design rules:
  * A metric that cannot be computed honestly returns ``None`` (with a reason in
    ``unavailable``) — it never invents a number.
  * Every function is dependency-free so it can be unit-tested against known
    closed-form examples.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks, 1-based, ties share the mean rank. Mirrors scipy.stats.rankdata."""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=float)
    sorted_a = a[order]
    i = 0
    while i < a.size:
        j = i
        while j + 1 < a.size and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def _finite_pairs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.isfinite(a) & np.isfinite(b)


def roc_auc(y_true: np.ndarray, scores: np.ndarray) -> Optional[float]:
    """ROC-AUC via the Mann–Whitney U statistic (handles ties correctly)."""
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    mask = _finite_pairs(y, s)
    y, s = y[mask], s[mask]
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _rankdata(s)
    auc = (ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def average_precision(y_true: np.ndarray, scores: np.ndarray) -> Optional[float]:
    """Average precision (area under the precision-recall curve, step rule)."""
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    mask = _finite_pairs(y, s)
    y, s = y[mask], s[mask]
    if y.size == 0 or y.sum() == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    precision = tp / (np.arange(y.size) + 1)
    recall = tp / y.sum()
    ap = 0.0
    prev_recall = 0.0
    for p, r in zip(precision, recall):
        ap += p * (r - prev_recall)
        prev_recall = r
    return float(ap)


def log_loss(y_true: np.ndarray, proba: np.ndarray, *, eps: float = 1e-15) -> Optional[float]:
    """Binary log loss. ``proba`` is P(y=1)."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(proba, dtype=float)
    mask = _finite_pairs(y, p)
    y, p = y[mask], p[mask]
    if y.size == 0:
        return None
    p = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier_score(y_true: np.ndarray, proba: np.ndarray) -> Optional[float]:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(proba, dtype=float)
    mask = _finite_pairs(y, p)
    if not mask.any():
        return None
    return float(np.mean((p[mask] - y[mask]) ** 2))


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    """Fraction of correctly signed predictions (both non-zero)."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = _finite_pairs(y, p) & (y != 0) & (p != 0)
    if not mask.any():
        return None
    return float(np.mean(np.sign(y[mask]) == np.sign(p[mask])))


def spearman_ic(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Spearman rank correlation (information coefficient)."""
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    mask = _finite_pairs(a, b)
    if mask.sum() < 3:
        return None
    ra, rb = _rankdata(a[mask]), _rankdata(b[mask])
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    if denom == 0.0:
        return None
    return float(float((ra * rb).sum()) / denom)


def pearson_ic(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    mask = _finite_pairs(a, b)
    if mask.sum() < 3:
        return None
    a, b = a[mask], b[mask]
    a = a - a.mean()
    b = b - b.mean()
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    if denom == 0.0:
        return None
    return float(float((a * b).sum()) / denom)


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> list[list[int]]:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    cm = [[0] * n_classes for _ in range(n_classes)]
    for t, pr in zip(y, p):
        if 0 <= t < n_classes and 0 <= pr < n_classes:
            cm[t][pr] += 1
    return cm


def _binary_prf(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Optional[float]]:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    tp = float(((y == 1) & (p == 1)).sum())
    fp = float(((y == 0) & (p == 1)).sum())
    fn = float(((y == 1) & (p == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_classification(
    y_true: np.ndarray, y_pred: np.ndarray, proba: Optional[np.ndarray], n_classes: int
) -> dict[str, Any]:
    """Classification metrics. ``proba`` is (n, n_classes) when available."""
    y = np.asarray(y_true)
    p = np.asarray(y_pred)
    out: dict[str, Any] = {
        "n": int(y.size),
        "accuracy": float(np.mean(y == p)) if y.size else None,
        "balancedAccuracy": None,
        "macroF1": None,
        "confusionMatrix": confusion_matrix(y, p, n_classes),
        "perClass": {},
        "rocAuc": None,
        "prAuc": None,
        "logLoss": None,
        "brier": None,
    }
    # per-class precision/recall/f1
    f1s = []
    recalls = []
    for c in range(n_classes):
        yc = (y == c).astype(int)
        pc = (p == c).astype(int)
        prf = _binary_prf(yc, pc)
        out["perClass"][str(c)] = prf
        if prf["f1"] is not None:
            f1s.append(prf["f1"])
        if prf["recall"] is not None:
            recalls.append(prf["recall"])
    if f1s:
        out["macroF1"] = float(np.mean(f1s))
    if recalls:
        out["balancedAccuracy"] = float(np.mean(recalls))
    if proba is not None and n_classes == 2:
        pos = np.asarray(proba, dtype=float)[:, 1]
        yb = (y == 1).astype(float)
        out["rocAuc"] = roc_auc(yb, pos)
        out["prAuc"] = average_precision(yb, pos)
        out["logLoss"] = log_loss(yb, pos)
        out["brier"] = brier_score(yb, pos)
    return out


def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = _finite_pairs(y, p)
    y, p = y[mask], p[mask]
    out: dict[str, Any] = {"n": int(y.size), "mae": None, "rmse": None, "r2": None,
                           "directionalAccuracy": None, "spearmanIc": None, "pearsonIc": None}
    if y.size == 0:
        return out
    err = p - y
    out["mae"] = float(np.mean(np.abs(err)))
    out["rmse"] = float(math.sqrt(float(np.mean(err * err))))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot > 0:
        out["r2"] = float(1.0 - float((err * err).sum()) / ss_tot)
    out["directionalAccuracy"] = directional_accuracy(y, p)
    out["spearmanIc"] = spearman_ic(p, y)
    out["pearsonIc"] = pearson_ic(p, y)
    return out


def evaluate_ranking(
    y_true: np.ndarray, scores: np.ndarray, *, top_fraction: float = 0.2
) -> dict[str, Any]:
    """Cross-sectional ranking metrics. ``y_true``/``scores`` are one period's
    aligned vectors (the caller groups by date)."""
    out: dict[str, Any] = {"n": int(np.size(y_true)), "spearmanIc": None, "topBottomSpread": None}
    out["spearmanIc"] = spearman_ic(scores, y_true)
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    mask = _finite_pairs(y, s)
    y, s = y[mask], s[mask]
    k = max(1, int(round(y.size * top_fraction)))
    if y.size >= 2 * k:
        order = np.argsort(-s, kind="mergesort")
        top = y[order[:k]].mean()
        bottom = y[order[-k:]].mean()
        out["topBottomSpread"] = float(top - bottom)
    return out


def silhouette(X: np.ndarray, labels: np.ndarray, *, max_points: int = 4000) -> Optional[float]:
    """Mean silhouette coefficient, or ``None`` when it is not defined.

    Undefined is an honest answer: fewer than two clusters, or any cluster with a
    single member, has no within-cluster distance to compare against. Pairwise
    distances are O(n^2), so a deterministic stride-subsample is used above
    ``max_points`` — never a random sample, so the same data gives the same value.
    """
    X = np.asarray(X, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if X.ndim != 2 or X.shape[0] != labels.size or X.shape[0] < 3:
        return None
    finite = np.isfinite(labels) & np.isfinite(X).all(axis=1)
    X, labels = X[finite], labels[finite]
    uniq = np.unique(labels)
    if uniq.size < 2 or X.shape[0] < 3:
        return None
    if X.shape[0] > max_points:
        step = int(np.ceil(X.shape[0] / max_points))
        X, labels = X[::step], labels[::step]
        uniq = np.unique(labels)
        if uniq.size < 2:
            return None
    # One distance block at a time keeps peak memory O(n) rather than O(n^2).
    scores: list[float] = []
    for i in range(X.shape[0]):
        d = np.sqrt(((X - X[i]) ** 2).sum(axis=1))
        same = labels == labels[i]
        same[i] = False
        if not same.any():          # a singleton cluster has no silhouette
            continue
        a = float(d[same].mean())
        b = min(float(d[labels == other].mean())
                for other in uniq if other != labels[i])
        denom = max(a, b)
        if denom > 0:
            scores.append((b - a) / denom)
    return float(np.mean(scores)) if scores else None


def evaluate_clustering(X: np.ndarray, labels: np.ndarray, centers: Optional[np.ndarray] = None) -> dict[str, Any]:
    """Unsupervised clustering quality. No label is required and none is invented."""
    labels = np.asarray(labels, dtype=float)
    uniq, counts = np.unique(labels[np.isfinite(labels)], return_counts=True)
    inertia = None
    if centers is not None and np.asarray(centers).ndim == 2 and uniq.size:
        X = np.asarray(X, dtype=float)
        centers = np.asarray(centers, dtype=float)
        total = 0.0
        for i, label in enumerate(uniq):
            if i < centers.shape[0]:
                rows = X[labels == label]
                total += float(((rows - centers[i]) ** 2).sum())
        inertia = total
    return {
        "silhouette": silhouette(X, labels),
        "inertia": inertia,
        "nClusters": int(uniq.size),
        "clusterSizes": [int(c) for c in counts],
    }


def evaluate_anomaly(scores: np.ndarray, flags: np.ndarray, *, contamination: float = 0.0) -> dict[str, Any]:
    """Anomaly-detector output summary. There is no ground truth, so no accuracy is claimed."""
    scores = np.asarray(scores, dtype=float)
    flags = np.asarray(flags, dtype=float)
    ok = np.isfinite(scores)
    if not ok.any():
        return {"anomalyRate": None, "flagged": 0, "scoreMean": None, "scoreP95": None,
                "targetRate": float(contamination) or None}
    finite_scores = scores[ok]
    flagged = int(np.nansum(flags == 1.0))
    valid_flags = int(np.isfinite(flags).sum())
    return {
        "anomalyRate": (flagged / valid_flags) if valid_flags else None,
        "flagged": flagged,
        "scoreMean": float(np.mean(finite_scores)),
        "scoreP95": float(np.quantile(finite_scores, 0.95)),
        "targetRate": float(contamination) or None,
    }


CLASSIFICATION_METRIC_KEYS = ("accuracy", "balancedAccuracy", "macroF1", "rocAuc", "prAuc", "logLoss", "brier")
REGRESSION_METRIC_KEYS = ("mae", "rmse", "r2", "directionalAccuracy", "spearmanIc", "pearsonIc")
CLUSTERING_METRIC_KEYS = ("silhouette", "inertia")
ANOMALY_METRIC_KEYS = ("anomalyRate", "scoreMean", "scoreP95")


def metric_keys(task: str) -> tuple[str, ...]:
    if task == "classification":
        return CLASSIFICATION_METRIC_KEYS
    if task == "clustering":
        return CLUSTERING_METRIC_KEYS
    if task == "anomaly":
        return ANOMALY_METRIC_KEYS
    return REGRESSION_METRIC_KEYS


def metric_vector(task: str, block: dict[str, Any]) -> dict[str, Any]:
    """Extract the scalar metric keys for an experiment's task (for aggregation)."""
    return {k: block.get(k) for k in metric_keys(task)}


__all__ = [
    "roc_auc",
    "average_precision",
    "log_loss",
    "brier_score",
    "directional_accuracy",
    "spearman_ic",
    "pearson_ic",
    "confusion_matrix",
    "evaluate_classification",
    "evaluate_regression",
    "evaluate_ranking",
    "evaluate_clustering",
    "evaluate_anomaly",
    "silhouette",
    "metric_vector",
    "metric_keys",
    "CLASSIFICATION_METRIC_KEYS",
    "REGRESSION_METRIC_KEYS",
    "CLUSTERING_METRIC_KEYS",
    "ANOMALY_METRIC_KEYS",
]
