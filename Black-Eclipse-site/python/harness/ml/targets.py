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


def build_unsupervised_target(n: int, spec: TargetSpec) -> dict[str, Any]:
    """A label-free target for clustering / anomaly detection.

    There is no label, so ``values`` is all-NaN and the label interval is the row
    itself. That is deliberate: NaN can never be mistaken for a ground truth, and
    the unsupervised pipeline reads only the feature matrix.
    """
    task = (spec.task or "clustering").lower()
    if task not in ("clustering", "anomaly"):
        raise MLError(INVALID_INPUT,
                      "an 'unsupervised' target needs task='clustering' or 'anomaly'")
    return {"kind": "unsupervised", "task": task,
            "values": np.full(n, np.nan),
            "labelStart": np.arange(n, dtype=int), "labelEnd": np.arange(n, dtype=int),
            "horizon": 0, "classes": None, "classLabels": None, "bins": None,
            "column": spec.column}


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
    if spec.kind == "unsupervised":
        # Label-free: the feature matrix is the whole input.
        base = build_unsupervised_target(t, spec)
        return {**base, "values": np.full((t, n), np.nan)}
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


def build_column_target(values: list[Any], spec: TargetSpec) -> dict[str, Any]:
    """Label a supplied per-row column (``kind="column"``).

    Unlike the market targets there is no forward horizon: the label interval is
    the row itself. ``spec.task`` must say how the column is modelled —
    ``regression`` (numeric values; a non-numeric entry is a data error, never a
    silent NaN) or ``classification`` (the distinct values become classes, in
    sorted order, and are returned as ``classLabels`` so a prediction can be
    decoded back to the operator's own vocabulary).

    Never invents a label: a blank/None entry is ``NaN`` and is dropped
    downstream by the existing finite-row filter.
    """
    n = len(values)
    if n == 0:
        raise MLError(INSUFFICIENT_DATA, "the target column has no values", 422)
    task = (spec.task or "regression").lower()
    if task not in ("classification", "regression"):
        raise MLError(INVALID_INPUT,
                      "a 'column' target needs task='regression' or 'classification'")

    label_start = np.arange(n, dtype=int)
    label_end = label_start.copy()

    if task == "regression":
        y = np.full(n, np.nan)
        for i, raw in enumerate(values):
            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                continue
            try:
                y[i] = float(raw)
            except (TypeError, ValueError):
                raise MLError(
                    INVALID_INPUT,
                    f"target column {spec.column!r} holds a non-numeric value at row {i}: "
                    f"{raw!r} (use task='classification' for categorical labels)",
                ) from None
        if not np.isfinite(y).any():
            raise MLError(INSUFFICIENT_DATA,
                          f"target column {spec.column!r} has no numeric values", 422)
        return {"kind": "column", "task": "regression", "values": y,
                "labelStart": label_start, "labelEnd": label_end, "horizon": 0,
                "classes": None, "classLabels": None, "bins": None,
                "column": spec.column}

    # Two passes so the code→label mapping is sorted (deterministic), not
    # dependent on the order rows happen to arrive in.
    labels = sorted({str(raw) for raw in values
                     if raw is not None and not (isinstance(raw, str) and raw.strip() == "")})
    if len(labels) < 2:
        raise MLError(INSUFFICIENT_DATA,
                      f"target column {spec.column!r} needs at least two classes "
                      f"(found {len(labels)})", 422)
    codes = {label: i for i, label in enumerate(labels)}
    y = np.full(n, np.nan)
    for i, raw in enumerate(values):
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            continue
        y[i] = float(codes[str(raw)])
    return {"kind": "column", "task": "classification", "values": y,
            "labelStart": label_start, "labelEnd": label_end, "horizon": 0,
            "classes": [float(i) for i in range(len(labels))], "classLabels": labels,
            "bins": None, "column": spec.column}


__all__ = ["build_target", "build_column_target", "build_unsupervised_target", "task_for"]