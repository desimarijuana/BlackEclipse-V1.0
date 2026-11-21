"""Strict alpha benchmarking: random control + a held-out out-of-sample split.

A factor that looks good in-sample can be search luck. This module makes the two
cheap defences explicit and reportable, reusing the ONE statistical engine
(`factors.engine`) rather than duplicating IC math:

  * **Random control** — each date's factor row is permuted, destroying any
    cross-sectional relation while keeping the exact marginal distribution. A
    real factor must beat its control.
  * **Train / test split** — a contiguous chronological split. IC is reported on
    both, and `oosDecay` names how much of the in-sample IC did NOT survive.

Nothing here fetches data or computes prices; the caller supplies aligned
`(factor, forward)` panels, so the same report can be produced from a backtest
artifact or a research dataset.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import engine


def split_index(n: int, *, train_frac: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """Chronological index split. Never overlaps; never shuffles."""
    if n < 0:
        raise ValueError("n must be >= 0")
    frac = min(max(float(train_frac), 0.0), 1.0)
    cut = int(round(n * frac))
    # Both sides must be non-empty for a split to mean anything.
    cut = min(max(cut, 1), max(n - 1, 0))
    train = np.arange(0, cut, dtype=int)
    test = np.arange(cut, n, dtype=int)
    return train, test


def random_control(panel: Any, *, seed: int = 7) -> np.ndarray:
    """Row-wise permutation of a factor panel (deterministic for a seed).

    Per-date permutation preserves every date's marginal distribution *and*
    missingness, so the control differs from the factor only in the
    cross-sectional ordering that the IC measures.
    """
    values = np.array(panel, dtype=float, copy=True)
    if values.ndim != 2:
        raise ValueError("random_control expects a 2-D (time x asset) panel")
    rng = np.random.default_rng(int(seed))
    for t in range(values.shape[0]):
        row = values[t]
        finite = np.flatnonzero(np.isfinite(row))
        if finite.size < 2:
            continue
        row[finite] = row[rng.permutation(finite)]
    return values


def _slice(panel: np.ndarray, index: np.ndarray) -> np.ndarray:
    return panel[index] if index.size else np.empty((0, panel.shape[1]))


def _ic(panel: np.ndarray, forward: np.ndarray, method: str, min_obs: int) -> dict[str, Any]:
    if panel.shape[0] < 2:
        return {"available": False, "reason": "fewer than 2 periods"}
    ic, counts = engine.cross_sectional_ic(panel, forward, method=method, min_obs=min_obs)
    summary = engine.ic_summary(ic, counts)
    summary["icSeries"] = [None if not np.isfinite(v) else round(float(v), 6) for v in ic]
    return summary


def strict_bench(
    factor: Any,
    forward: Any,
    *,
    train_frac: float = 0.7,
    seed: int = 7,
    method: str = "spearman",
    min_obs: int = 5,
) -> dict[str, Any]:
    """Train/test IC plus a random control on the held-out segment.

    Returns a report, never raises for unusable data — an unavailable result
    carries a reason. The split is chronological and the control is computed on
    the TEST window only, so the OOS comparison is like-for-like.
    """
    f = np.asarray(factor, dtype=float)
    r = np.asarray(forward, dtype=float)
    if f.ndim != 2 or r.ndim != 2 or f.shape != r.shape:
        raise ValueError("factor and forward must be equal-shaped 2-D panels")
    train_index, test_index = split_index(f.shape[0], train_frac=train_frac)
    train = _ic(_slice(f, train_index), _slice(r, train_index), method, min_obs)
    test = _ic(_slice(f, test_index), _slice(r, test_index), method, min_obs)
    control_panel = random_control(_slice(f, test_index), seed=seed)
    control = _ic(control_panel, _slice(r, test_index), method, min_obs)

    train_ic = train.get("meanIC")
    test_ic = test.get("meanIC")
    control_ic = control.get("meanIC")
    decay: Optional[float] = None
    if train_ic is not None and test_ic is not None:
        decay = round(float(train_ic) - float(test_ic), 6)
    beats_control: Optional[bool] = None
    if test_ic is not None and control_ic is not None:
        beats_control = bool(abs(float(test_ic)) > abs(float(control_ic)))

    return {
        "method": method,
        "seed": int(seed),
        "trainFraction": float(train_frac),
        "periods": int(f.shape[0]),
        "trainPeriods": int(train_index.size),
        "testPeriods": int(test_index.size),
        "splitIndex": int(test_index[0]) if test_index.size else None,
        "train": train,
        "test": test,
        "control": control,
        "oosDecay": decay,
        "beatsControl": beats_control,
        "available": bool(train.get("available") and test.get("available")),
    }


__all__ = ["random_control", "split_index", "strict_bench"]
