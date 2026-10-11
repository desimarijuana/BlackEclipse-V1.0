"""detect_outliers — z-score, MAD, IQR and isolation-forest anomaly detection.

Returns scores, thresholds, flagged indices/timestamps and method settings.
Anomalies are never deleted or overwritten — the caller decides. A data-quality
caveat distinguishes a legitimate extreme market move from an obviously invalid
observation (e.g. a non-positive price).
"""

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
    "Anomaly detection: global/rolling z-score, robust modified z-score (MAD), "
    "IQR fences and an isolation forest. Returns scores, thresholds, flagged "
    "indices and timestamps, and never modifies the underlying observations."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {"type": "number"}},
        "method": {"type": "string",
                   "enum": ["zscore", "mad", "iqr", "isolation_forest"], "default": "zscore"},
        "threshold": {"type": "number", "description": "z / modified-z threshold (default 3)."},
        "window": {"type": "integer", "minimum": 2, "description": "Rolling z-score window."},
        "contamination": {"type": "number", "default": 0.05,
                          "description": "Isolation-forest expected outlier fraction."},
        "seed": {"type": "integer", "default": 7},
        "timestamps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["values"],
}


class _IsolationTree:
    def __init__(self, idim: int):
        self.dim = idim
        self.left = self.right = None
        self.split_feature = -1
        self.split_value = 0.0
        self.size = 0
        self.is_leaf = True


def _build_tree(X: np.ndarray, depth: int, max_depth: int, rng) -> _IsolationTree:
    node = _IsolationTree(X.shape[1])
    node.size = X.shape[0]
    if depth >= max_depth or X.shape[0] <= 1:
        return node
    mins, maxs = X.min(axis=0), X.max(axis=0)
    ranges = maxs - mins
    if np.all(ranges <= 0):
        return node
    feat = int(rng.choice(np.where(ranges > 0)[0]))
    lo, hi = mins[feat], maxs[feat]
    if lo == hi:
        return node
    split = float(rng.uniform(lo, hi))
    node.is_leaf = False
    node.split_feature = feat
    node.split_value = split
    mask = X[:, feat] < split
    node.left = _build_tree(X[mask], depth + 1, max_depth, rng)
    node.right = _build_tree(X[~mask], depth + 1, max_depth, rng)
    return node


def _path_length(x: np.ndarray, node: _IsolationTree, depth: int = 0) -> float:
    while not node.is_leaf:
        if x[node.split_feature] < node.split_value:
            node = node.left
        else:
            node = node.right
        depth += 1
    return depth + _c(node.size)


def _c(n: int) -> float:
    if n <= 1:
        return 0.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - 2.0 * (n - 1) / n


def _isolation_forest(x: np.ndarray, contamination: float, seed: int) -> tuple[np.ndarray, float]:
    X = np.asarray(x, dtype=float).reshape(-1, 1)
    n = X.shape[0]
    rng = np.random.default_rng(seed)
    n_trees = 100
    psi = min(256, n)
    max_depth = int(math.ceil(math.log2(max(2, psi))))
    paths = np.zeros(n)
    for _ in range(n_trees):
        idx = rng.choice(n, size=psi, replace=False)
        tree = _build_tree(X[idx], 0, max_depth, rng)
        for i in range(n):
            paths[i] += _path_length(X[i], tree)
    avg_path = paths / n_trees
    denom = _c(psi) or 1.0
    scores = 2.0 ** (-avg_path / denom)
    k = max(1, int(round(contamination * n)))
    thresh = float(np.sort(scores)[::-1][k - 1]) if k <= n else float(scores.max())
    return scores, thresh


def run(args: dict) -> dict:
    x = to_float_array(args.get("values"), "values")
    require_min_length(x, 5, "values")
    method = get_str(args, "method", "zscore")
    timestamps = args.get("timestamps")
    warnings: list[str] = []

    if method == "zscore":
        thresh = get_float(args, "threshold", 3.0)
        window = args.get("window")
        if window:
            w = get_int(args, "window", 2, minimum=2)
            scores = np.full(x.size, np.nan)
            for i in range(w - 1, x.size):
                chunk = x[i - w + 1: i + 1]
                if np.isfinite(chunk).all():
                    s = chunk.std(ddof=0)
                    if s > 0:
                        scores[i] = (x[i] - chunk.mean()) / s
        else:
            m, s = np.nanmean(x), np.nanstd(x, ddof=0)
            scores = (x - m) / s if s > 0 else np.zeros_like(x)
        flags = np.abs(scores) > thresh

    elif method == "mad":
        thresh = get_float(args, "threshold", 3.5)
        med = np.nanmedian(x)
        mad = np.nanmedian(np.abs(x - med))
        if mad == 0:
            mad = 1e-12
        scores = 0.6745 * (x - med) / mad
        flags = np.abs(scores) > thresh
        thresh = thresh

    elif method == "iqr":
        q1, q3 = np.nanquantile(x, 0.25), np.nanquantile(x, 0.75)
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        scores = np.where(x < low, (x - low), np.where(x > high, x - high, 0.0))
        flags = (x < low) | (x > high)
        thresh = {"lower": float(low), "upper": float(high)}

    elif method == "isolation_forest":
        cont = get_float(args, "contamination", 0.05)
        if not 0.0 < cont < 0.5:
            raise StatsError(INVALID_INPUT, "contamination must be in (0, 0.5)")
        vals = x[np.isfinite(x)]
        if vals.size < 10:
            raise StatsError(INVALID_INPUT, "isolation forest needs at least 10 finite observations", 422)
        score_vals, thresh = _isolation_forest(vals, cont, get_int(args, "seed", 7, minimum=0))
        scores = np.full(x.size, np.nan)
        fin = np.isfinite(x)
        scores[fin] = score_vals
        flags = np.zeros(x.size, dtype=bool)
        flags[fin] = score_vals > thresh
    else:
        raise StatsError(INVALID_INPUT, f"unknown outlier method: {method}")

    flagged_idx = [int(i) for i in np.where(flags)[0]]
    results = {
        "scores": as_list(scores),
        "flaggedIndices": flagged_idx,
        "threshold": thresh if isinstance(thresh, dict) else float(thresh),
    }
    if timestamps and len(timestamps) == x.size:
        results["flaggedTimestamps"] = [timestamps[i] for i in flagged_idx]

    nonpositive = int(np.sum(np.isfinite(x) & (x <= 0)))
    if nonpositive:
        warnings.append(f"{nonpositive} non-positive observation(s) may indicate data-quality errors, not market events")

    return make_response(
        "detect_outliers",
        {"method": method, "contamination": args.get("contamination")},
        summary={"method": method, "flaggedCount": len(flagged_idx), "observations": int(x.size)},
        results=results,
        diagnostics={"dataQualityCaveat": "flagged points are not modified; inspect before removal"},
        warnings=warnings,
    )


__all__ = ["run", "DESCRIPTION", "INPUT_SCHEMA"]
