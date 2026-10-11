"""Statistical validation primitives: bootstrap confidence intervals and
chronological out-of-sample partitioning.

This module is deliberately *separate* from walk-forward and Monte-Carlo — the
three answer different questions and must not be conflated:

  * **walk-forward** (`walkforward.py`) rolls train→test windows and re-optimizes;
  * **Monte-Carlo** (`montecarlo.py`) perturbs a completed backtest's trades,
    returns, parameters or execution to characterise uncertainty;
  * **bootstrap** (here) estimates the sampling distribution of *one* statistic
    from one return series, with a method whose assumptions are explicit.

The bootstrap never treats a dependent series as independent without saying so:
the IID method emits a `BOOTSTRAP_IID_ASSUMES_INDEPENDENCE` warning, and the block
methods exist precisely for serially dependent returns.
"""

from __future__ import annotations

import math
import random
from typing import Any, Optional

import numpy as np

from .data import bars_per_year
from .errors import QuantError


class ValidationError_(QuantError):
    code = "VALIDATION_ERROR"


_METHODS = {"iid", "block", "stationary"}
_STATISTICS = {"mean", "total", "std", "sharpe"}


def _statistic(name: str, values: np.ndarray, annualization: float) -> Optional[float]:
    if values.size == 0:
        return None
    if name == "mean":
        return float(np.mean(values))
    if name == "total":
        return float(np.sum(values))
    if name == "std":
        return float(np.std(values, ddof=1)) if values.size > 1 else None
    if name == "sharpe":
        if values.size < 2:
            return None
        sd = float(np.std(values, ddof=1))
        if sd <= 0.0:
            return None
        return float(np.mean(values) / sd * math.sqrt(annualization))
    raise ValidationError_(f"unknown statistic {name!r}")


def _resample_indices(rng: random.Random, n: int, method: str,
                      block_size: int) -> np.ndarray:
    if method == "iid":
        return np.array([rng.randrange(n) for _ in range(n)], dtype=int)
    indices: list[int] = []
    if method == "block":
        while len(indices) < n:
            start = rng.randrange(n)
            for j in range(block_size):
                indices.append((start + j) % n)
    else:  # stationary bootstrap — geometric block lengths with mean `block_size`
        p = 1.0 / max(1, block_size)
        while len(indices) < n:
            start = rng.randrange(n)
            length = 1
            while rng.random() > p and length < n:
                length += 1
            for j in range(length):
                indices.append((start + j) % n)
    return np.array(indices[:n], dtype=int)


def bootstrap_ci(
    series: list[float],
    *,
    method: str = "iid",
    statistic: str = "mean",
    iterations: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
    block_size: Optional[int] = None,
    interval: str = "1d",
) -> dict[str, Any]:
    """Percentile bootstrap CI for `statistic` over one return series.

    Returns the point estimate, the CI, the per-iteration distribution summary
    and full provenance (method, seed, block size, failed iterations). Assumptions
    that the chosen method makes are surfaced as warnings, never hidden.
    """
    if method not in _METHODS:
        raise ValidationError_(f"unknown bootstrap method {method!r}")
    if statistic not in _STATISTICS:
        raise ValidationError_(f"unknown statistic {statistic!r}")
    if iterations < 1:
        raise ValidationError_("iterations must be >= 1")
    if not (0.0 < confidence < 1.0):
        raise ValidationError_("confidence must be in (0, 1)")

    values = np.asarray([float(x) for x in series], dtype=float)
    warnings: list[dict[str, Any]] = []
    if values.size < 2:
        raise ValidationError_(
            f"need at least 2 observations to bootstrap, got {values.size}",
            detail={"length": int(values.size)})

    n = int(values.size)
    if method == "iid":
        warnings.append({
            "code": "BOOTSTRAP_IID_ASSUMES_INDEPENDENCE",
            "message": "IID resampling assumes independent observations; use `block` or "
                       "`stationary` for serially correlated returns",
        })
    default_block = max(1, int(round(n ** (1.0 / 3.0))))
    b = int(block_size) if block_size else default_block
    if method in ("block", "stationary") and b > n:
        raise ValidationError_(
            f"block size {b} exceeds series length {n}", detail={"blockSize": b, "length": n})

    annualization = float(bars_per_year(interval))
    estimate = _statistic(statistic, values, annualization)

    rng = random.Random(seed)
    draws: list[float] = []
    failed = 0
    for _ in range(int(iterations)):
        idx = _resample_indices(rng, n, method, b)
        sample = values[idx]
        value = _statistic(statistic, sample, annualization)
        if value is None or not math.isfinite(value):
            failed += 1
            continue
        draws.append(value)

    if not draws:
        return {
            "available": False,
            "reason": "every bootstrapped replicate produced an undefined statistic "
                      "(zero variance / too few observations)",
            "method": method, "statistic": statistic, "iterations": int(iterations),
            "failed": failed, "seed": seed, "length": n, "warnings": warnings,
        }

    arr = np.array(draws, dtype=float)
    alpha = (1.0 - confidence) / 2.0
    lower = float(np.percentile(arr, alpha * 100.0))
    upper = float(np.percentile(arr, (1.0 - alpha) * 100.0))
    return {
        "available": True,
        "method": method,
        "statistic": statistic,
        "estimate": estimate,
        "confidence": confidence,
        "ciMethod": "percentile",
        "ciLower": lower,
        "ciUpper": upper,
        "stdError": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "iterations": int(iterations),
        "successful": len(draws),
        "failed": failed,
        "seed": seed,
        "blockSize": b if method in ("block", "stationary") else None,
        "length": n,
        "annualization": annualization,
        "distribution": {
            "mean": float(np.mean(arr)),
            "p5": float(np.percentile(arr, 5)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
        },
        "warnings": warnings,
    }


def returns_from_equity(equity: list[float]) -> list[float]:
    """Simple per-period returns from an equity curve (0 for a flat/zero base)."""
    out: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        out.append((equity[i] / prev - 1.0) if prev else 0.0)
    return out


def split_index(length: int, *, oos_fraction: Optional[float] = None,
                oos_start_index: Optional[int] = None) -> tuple[int, int]:
    """Split `length` observations into (is_end_exclusive, oos_start).

    A chronological split only: the OOS block is always the tail. `oos_fraction`
    and `oos_start_index` are mutually exclusive; exactly one is required.
    """
    if length < 2:
        raise ValidationError_(f"need at least 2 bars to split, got {length}")
    if (oos_fraction is None) == (oos_start_index is None):
        raise ValidationError_("provide exactly one of `oosFraction` or `oosStartIndex`")
    if oos_start_index is not None:
        start = int(oos_start_index)
        if start < 1 or start >= length:
            raise ValidationError_(
                f"oosStartIndex must be in [1, {length - 1}], got {start}")
        return start, start
    frac = float(oos_fraction)
    if not (0.0 < frac < 1.0):
        raise ValidationError_("oosFraction must be in (0, 1)")
    start = max(1, min(length - 1, int(round(length * (1.0 - frac)))))
    return start, start


__all__ = [
    "ValidationError_",
    "bootstrap_ci",
    "returns_from_equity",
    "split_index",
]
