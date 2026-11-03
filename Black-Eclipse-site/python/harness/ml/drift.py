"""Feature drift between a model's training data and a newer dataset version.

A model is only as good as the world it was fitted on. This module compares the
feature matrix a model was trained on with a later dataset version and reports,
per feature, two standard, deterministic measures:

  * **PSI** (population stability index) — bin proportions under the reference's
    own quantiles; 0 means identical shape.
  * **KS** (two-sample Kolmogorov–Smirnov) — the maximum gap between the empirical
    CDFs, with its asymptotic p-value.

No model is called and nothing is extrapolated: missing values are counted per
feature (not imputed), and a feature that exists in only one of the two versions
is reported as a schema change rather than silently skipped.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

# Conventional PSI bands (Siddiqi). Stated here, not hidden in a caller.
PSI_WATCH = 0.10
PSI_DRIFT = 0.25


def psi(reference: np.ndarray, current: np.ndarray, *, bins: int = 10) -> Optional[float]:
    """Population stability index; ``None`` when a side has no finite values."""
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size == 0 or cur.size == 0:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0.0, 1.0, bins + 1)))
    if edges.size < 3:                 # a constant reference has no stable bins
        return None
    edges[0] = -np.inf
    edges[-1] = np.inf
    ref_counts = np.histogram(ref, bins=edges)[0] / ref.size
    cur_counts = np.histogram(cur, bins=edges)[0] / cur.size
    eps = 1e-6
    ref_p = np.clip(ref_counts, eps, None)
    cur_p = np.clip(cur_counts, eps, None)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def ks_statistic(reference: np.ndarray, current: np.ndarray) -> Optional[dict[str, float]]:
    """Two-sample KS: statistic + asymptotic p-value. Pure NumPy."""
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = np.sort(ref[np.isfinite(ref)])
    cur = np.sort(cur[np.isfinite(cur)])
    if ref.size == 0 or cur.size == 0:
        return None
    values = np.concatenate([ref, cur])
    cdf_ref = np.searchsorted(ref, values, side="right") / ref.size
    cdf_cur = np.searchsorted(cur, values, side="right") / cur.size
    d = float(np.max(np.abs(cdf_ref - cdf_cur)))
    ne = ref.size * cur.size / (ref.size + cur.size)
    lam = (math.sqrt(ne) + 0.12 + 0.11 / math.sqrt(ne)) * d
    if lam <= 0:
        return {"statistic": 0.0, "pValue": 1.0}
    total = 0.0
    for k in range(1, 101):
        term = 2.0 * (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
        total += term
        if abs(term) < 1e-12:
            break
    return {"statistic": d, "pValue": float(min(1.0, max(0.0, total)))}


def _verdict(psi_value: Optional[float], ks_value: Optional[float]) -> str:
    if psi_value is None:
        return "unmeasured"
    if psi_value >= PSI_DRIFT:
        return "drift"
    if psi_value >= PSI_WATCH:
        return "watch"
    if ks_value is not None and ks_value >= 0.2:
        return "watch"
    return "stable"


def compare_features(
    reference: dict[str, np.ndarray],
    current: dict[str, np.ndarray],
    *,
    feature_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Per-feature drift report between two feature matrices.

    ``reference``/``current`` are ``feature name → 1-D column`` maps. A feature
    present on only one side is a SCHEMA CHANGE — the drift verdict is then
    `unmeasured` for it, never 0.
    """
    names = feature_names or sorted(set(reference) | set(current))
    rows: list[dict[str, Any]] = []
    for name in names:
        ref = reference.get(name)
        cur = current.get(name)
        if ref is None or cur is None:
            rows.append({"feature": name, "verdict": "schema_change",
                         "psi": None, "ks": None, "pValue": None,
                         "missingReference": None, "missingCurrent": None})
            continue
        ref_arr = np.asarray(ref, dtype=float)
        cur_arr = np.asarray(cur, dtype=float)
        psi_value = psi(ref_arr, cur_arr)
        ks = ks_statistic(ref_arr, cur_arr)
        rows.append({
            "feature": name,
            "verdict": _verdict(psi_value, None if ks is None else ks["statistic"]),
            "psi": psi_value,
            "ks": None if ks is None else ks["statistic"],
            "pValue": None if ks is None else ks["pValue"],
            "missingReference": float(np.mean(~np.isfinite(ref_arr))),
            "missingCurrent": float(np.mean(~np.isfinite(cur_arr))),
        })

    order = {"drift": 0, "schema_change": 1, "watch": 2, "unmeasured": 3, "stable": 4}
    worst = min((row["verdict"] for row in rows), key=lambda v: order.get(v, 9), default="unmeasured")
    drifted = [row["feature"] for row in rows if row["verdict"] in ("drift", "schema_change")]
    return {
        "features": rows,
        "verdict": worst,
        "driftedFeatures": drifted,
        "thresholds": {"watch": PSI_WATCH, "drift": PSI_DRIFT},
        "note": ("a drift verdict means the inputs moved, not that the model is wrong — "
                 "retrain or re-evaluate before trusting new predictions"),
    }


__all__ = ["PSI_DRIFT", "PSI_WATCH", "compare_features", "ks_statistic", "psi"]
