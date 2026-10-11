"""Target (label) construction for the ML Research Lab.

A target is computed from a ``(T, N)`` close-price panel and returns:

  * ``values``       — ``(T, N)`` label matrix (NaN where the label is invalid),
  * ``label_start``  — ``(T,)`` period index the label starts at (== t),
  * ``label_end``    — ``(T,)`` period index the label ends at (== t + h),

The start/end indices are what the split engine uses to purge training labels
that overlap an evaluation interval — the core defence against lookahead.

Point-in-time rule: a label at row ``t`` uses prices at ``t`` and ``t + h`` only.
It must never be shifted so that a future price enters an earlier feature row.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .models import MLError, TARGET_KINDS, TargetSpec
from ..stats.base import INVALID_INPUT, INSUFFICIENT_DATA


def task_for(kind: str) -> str:
    if kind in ("direction_binary", "direction_multiclass", "neutral_zone"):
        return "classification"
    if kind in ("forward_return", "volatility", "cross_sectional_rank"):
        return "regression"
    raise MLError(INVALID_INPUT, f"unknown target kind {kind!r}")


def _forward_returns(prices: np.ndarray, horizon: int) -> np.ndarray:
    """``(T, N)`` h-period forward simple return; NaN where either end is missing."""
    t, n = prices.shape
    out = np.full((t, n), np.nan)
    if horizon <= 0 or horizon >= t:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        out[: t - horizon] = prices[horizon:] / prices[: t - horizon] - 1.0
    return out


def _forward_volatility(returns: np.ndarray, horizon: int) -> np.ndarray:
    """Forward realized volatility of the 1-period returns over the next h periods."""
    t, n = returns.shape
    out = np.full((t, n), np.nan)
    if horizon <= 0:
        return out
    for i in range(t):
        end = min(t, i + horizon + 1)
        window = returns[i + 1:end]
        if window.shape[0] >= 2:
            with np.errstate(invalid="ignore"):
                out[i] = np.nanstd(window, axis=0, ddof=1)
    return out


def build_target(prices: np.ndarray, spec: TargetSpec) -> dict[str, Any]:
    """Construct a label matrix and its [start, end] period indices.

    ``prices`` must be the adjusted close panel (missing values as NaN). The
    returned ``values`` are NaN wherever the label is undefined, so downstream
    code drops those rows explicitly rather than imputing them.
    """
    prices = np.asarray(prices, dtype=float)
    if prices.ndim != 2:
        raise MLError(INVALID_INPUT, "prices must be a 2-D (T, N) panel")
    t, n = prices.shape
    if spec.kind not in TARGET_KINDS:
        raise MLError(INVALID_INPUT, f"unknown target kind {spec.kind!r}")
    if spec.horizon < 1:
        raise MLError(INVALID_INPUT, "target horizon must be >= 1")
    if n < 1 or t <= spec.horizon:
        raise MLError(INSUFFICIENT_DATA, "not enough rows for the requested horizon", 422)

    returns = np.full((t, n), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns[1:] = prices[1:] / prices[:-1] - 1.0

    label_start = np.arange(t, dtype=int)
    label_end = np.minimum(np.arange(t, dtype=int) + spec.horizon, t - 1)

    values = np.full((t, n), np.nan)
    classes: Optional[list[float]] = None
    bins: Optional[list[float]] = None
    task = task_for(spec.kind)

    if spec.kind == "forward_return":
        values = _forward_returns(prices, spec.horizon)
    elif spec.kind == "volatility":
        values = _forward_volatility(returns, spec.horizon)
    elif spec.kind == "direction_binary":
        fwd = _forward_returns(prices, spec.horizon)
        values = np.where(np.isnan(fwd), np.nan, (fwd > spec.threshold).astype(float))
        classes = [0.0, 1.0]
    elif spec.kind == "neutral_zone":
        fwd = _forward_returns(prices, spec.horizon)
        band = abs(spec.neutral_band)
        lab = np.where(fwd > band, 1.0, np.where(fwd < -band, 0.0, np.nan))
        values = np.where(np.isnan(fwd), np.nan, lab)
        classes = [0.0, 1.0]
    elif spec.kind == "direction_multiclass":
        fwd = _forward_returns(prices, spec.horizon)
        finite = fwd[np.isfinite(fwd)]
        k = max(2, int(spec.n_classes))
        if finite.size < k:
            raise MLError(INSUFFICIENT_DATA,
                          f"{finite.size} valid forward returns; need >= {k} for {k} classes", 422)
        edges = np.quantile(finite, np.linspace(0, 1, k + 1)[1:-1])
        idx = np.digitize(fwd, edges)
        values = np.where(np.isnan(fwd), np.nan, idx.astype(float))
        bins = [float(e) for e in edges]
        classes = [float(i) for i in range(k)]
    elif spec.kind == "cross_sectional_rank":
        from .metrics import _rankdata  # noqa: PLC0415

        fwd = _forward_returns(prices, spec.horizon)
        values = np.full((t, n), np.nan)
        for i in range(t):
            row = fwd[i]
            mask = np.isfinite(row)
            cnt = int(mask.sum())
            if cnt >= 2:
                # average-rank percentile in [0, 1] (ties share a rank)
                values[i, mask] = (_rankdata(row[mask]) - 1.0) / (cnt - 1.0)
        task = "regression"

    return {
        "kind": spec.kind,
        "task": task,
        "values": values,
        "labelStart": label_start,
        "labelEnd": label_end,
        "horizon": spec.horizon,
        "classes": classes,
        "bins": bins,
        "column": spec.column,
    }


__all__ = ["build_target", "task_for"]
