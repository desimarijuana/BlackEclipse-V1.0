"""Model-agnostic permutation importance — explain any family, no SHAP dependency.

Trees expose a split-based importance; a linear model, a k-means centroid set and
an optional torch MLP do not. Permutation importance works for all of them and
measures the same thing everywhere: how much the model's quality drops when one
feature's values are shuffled, which destroys that feature's information while
keeping its distribution.

Rules:

  * measured on the FINAL HOLDOUT rows only (never on rows the model was fitted on);
  * the metric is explicit (accuracy for classification, -RMSE for regression) and
    reported with the block it was measured on;
  * deterministic — the shuffle is seeded, and the same data gives the same numbers;
  * `None` when the holdout is too small to mean anything, rather than a confident
    number computed from a handful of rows.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

MIN_ROWS = 30


def _score(task: str, y: np.ndarray, pred: np.ndarray) -> float:
    if task == "classification":
        return float(np.mean(np.asarray(y) == np.asarray(pred)))
    return -float(np.sqrt(np.mean((np.asarray(y, dtype=float) - np.asarray(pred, dtype=float)) ** 2)))


def permutation_importance(
    predict: Callable[[np.ndarray], np.ndarray],
    X: np.ndarray,
    y: np.ndarray,
    *,
    task: str,
    seed: int = 42,
    n_repeats: int = 5,
    feature_names: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Drop in the holdout metric when each feature is shuffled.

    ``None`` when the holdout has fewer than ``MIN_ROWS`` rows or no features —
    an importance from a toy sample is noise wearing a number.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2 or X.shape[0] < MIN_ROWS or X.shape[1] == 0:
        return None
    names = feature_names or [f"f{i}" for i in range(X.shape[1])]
    if len(names) != X.shape[1]:
        names = [f"f{i}" for i in range(X.shape[1])]

    metric_name = "accuracy" if task == "classification" else "negativeRmse"
    baseline = _score(task, y, predict(X))
    rng = np.random.default_rng(seed)

    per_feature: dict[str, dict[str, float]] = {}
    for index, name in enumerate(names):
        drops = []
        for _ in range(max(1, int(n_repeats))):
            shuffled = X.copy()
            rng.shuffle(shuffled[:, index])
            drops.append(baseline - _score(task, y, predict(shuffled)))
        per_feature[name] = {"mean": float(np.mean(drops)), "std": float(np.std(drops, ddof=0))}

    ranked = sorted(per_feature.items(), key=lambda item: -item[1]["mean"])
    return {
        "method": "permutation",
        "metric": metric_name,
        "baseline": baseline,
        "rows": int(X.shape[0]),
        "nRepeats": int(max(1, int(n_repeats))),
        "features": dict(ranked),
    }


__all__ = ["MIN_ROWS", "permutation_importance"]
