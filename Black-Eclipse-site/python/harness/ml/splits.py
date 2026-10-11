"""Temporal validation and leakage prevention — the mandatory correctness gate.

Random train/test splitting is deliberately NOT offered: financial labels overlap
in time, so a shuffled split leaks the future into the past. This module builds
only chronological designs and purges/embargoes overlapping labels:

  * ``chronological`` — a single final-holdout (train -> test) split,
  * ``walk_forward``  — expanding or rolling windows over successive test blocks,
  * ``purged_kfold``  — contiguous test blocks with train rows whose label
    interval overlaps the test interval removed (purged) and observations just
    after the test period embargoed.

Every fold records exactly which rows were purged and embargoed, and
``assert_no_leakage`` re-derives the invariant from the fold assignments so a bug
in the split code cannot pass silently.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .models import ML_ENGINE_VERSION, MLError, LEAKAGE_DETECTED, SplitSpec
from ..stats.base import INVALID_INPUT, INSUFFICIENT_DATA


def _purge_embargo(
    train_idx: np.ndarray, test_idx: np.ndarray,
    label_start: np.ndarray, label_end: np.ndarray, spec: SplitSpec,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(kept, purged, embargoed)`` train indices for one fold."""
    if train_idx.size == 0 or test_idx.size == 0:
        return train_idx, np.array([], dtype=int), np.array([], dtype=int)
    test_ls = int(label_start[test_idx].min())
    test_le = int(label_end[test_idx].max())

    keep: list[int] = []
    purged: list[int] = []
    embargoed: list[int] = []
    for i in train_idx:
        ls, le = int(label_start[i]), int(label_end[i])
        overlaps = not (le < test_ls or ls > test_le)
        if spec.purge and overlaps:
            purged.append(i)
            continue
        # Embargo: training rows that start within `embargo` periods AFTER the
        # test label window are dropped to break short-horizon serial dependence.
        if spec.embargo > 0 and test_le < ls <= test_le + spec.embargo:
            embargoed.append(i)
            continue
        keep.append(i)
    return (np.asarray(keep, dtype=int), np.asarray(purged, dtype=int),
            np.asarray(embargoed, dtype=int))


def _fold(index: int, train: np.ndarray, test: np.ndarray, purged: np.ndarray,
          embargoed: np.ndarray, label_start: np.ndarray, label_end: np.ndarray) -> dict[str, Any]:
    return {
        "index": index,
        "trainIdx": train.tolist(),
        "testIdx": test.tolist(),
        "purgedIdx": purged.tolist(),
        "embargoedIdx": embargoed.tolist(),
        "nTrain": int(train.size),
        "nTest": int(test.size),
        "nPurged": int(purged.size),
        "nEmbargoed": int(embargoed.size),
        "trainStart": int(label_start[train].min()) if train.size else None,
        "trainEnd": int(label_end[train].max()) if train.size else None,
        "testStart": int(label_start[test].min()) if test.size else None,
        "testEnd": int(label_end[test].max()) if test.size else None,
    }


def build_splits(spec: SplitSpec, label_start: np.ndarray, label_end: np.ndarray) -> list[dict[str, Any]]:
    """Build the fold list for a split specification."""
    label_start = np.asarray(label_start, dtype=int)
    label_end = np.asarray(label_end, dtype=int)
    t = label_start.size
    if t < 8:
        raise MLError(INSUFFICIENT_DATA, f"{t} rows; at least 8 required for temporal splitting", 422)
    if spec.method not in ("chronological", "walk_forward", "purged_kfold"):
        raise MLError(INVALID_INPUT, f"unknown split method {spec.method!r}")
    n_splits = max(2, int(spec.n_splits))

    if spec.method == "chronological":
        test_size = spec.test_size or max(1, t // 5)
        if test_size >= t - 1:
            raise MLError(INVALID_INPUT, "test_size leaves no training rows")
        all_idx = np.arange(t)
        test = all_idx[t - test_size:]
        train_pool = all_idx[: t - test_size]
        train, purged, emb = _purge_embargo(train_pool, test, label_start, label_end, spec)
        if train.size == 0:
            raise MLError(INSUFFICIENT_DATA, "purge/embargo removed every training row", 422)
        return [_fold(0, train, test, purged, emb, label_start, label_end)]

    if spec.method == "walk_forward":
        test_size = spec.test_size or max(1, t // (n_splits + 1))
        first_test_start = t - n_splits * test_size
        min_train = spec.min_train_size or max(1, test_size)
        if first_test_start < min_train:
            raise MLError(INVALID_INPUT, "not enough rows for the requested walk-forward windows")
        folds = []
        all_idx = np.arange(t)
        for k in range(n_splits):
            ts = first_test_start + k * test_size
            te = min(t, ts + test_size)
            test = all_idx[ts:te]
            if spec.window_mode == "rolling" and spec.window > 0:
                train_pool = all_idx[max(0, ts - spec.window):ts]
            else:
                train_pool = all_idx[:ts]
            train, purged, emb = _purge_embargo(train_pool, test, label_start, label_end, spec)
            if train.size == 0:
                continue
            folds.append(_fold(k, train, test, purged, emb, label_start, label_end))
        if not folds:
            raise MLError(INSUFFICIENT_DATA, "no valid walk-forward folds were produced", 422)
        return folds

    # purged_kfold
    all_idx = np.arange(t)
    test_size = spec.test_size or max(1, t // n_splits)
    folds = []
    for k in range(n_splits):
        ts = k * test_size
        if ts >= t:
            break
        te = min(t, ts + test_size)
        test = all_idx[ts:te]
        pool = np.concatenate([all_idx[:ts], all_idx[te:]])
        train, purged, emb = _purge_embargo(pool, test, label_start, label_end, spec)
        if train.size == 0:
            continue
        folds.append(_fold(k, train, test, purged, emb, label_start, label_end))
    if not folds:
        raise MLError(INSUFFICIENT_DATA, "no valid purged folds were produced", 422)
    return folds


def assert_no_leakage(folds: list[dict[str, Any]], label_start: np.ndarray,
                      label_end: np.ndarray) -> None:
    """Verify no kept training label interval overlaps any test label interval.

    Raises ``MLError(LEAKAGE_DETECTED)`` if a fold leaks. This is re-derived from
    the fold assignments, independent of the split construction.
    """
    label_start = np.asarray(label_start, dtype=int)
    label_end = np.asarray(label_end, dtype=int)
    for fold in folds:
        test = np.asarray(fold["testIdx"], dtype=int)
        train = np.asarray(fold["trainIdx"], dtype=int)
        if test.size == 0 or train.size == 0:
            continue
        t_ls, t_le = int(label_start[test].min()), int(label_end[test].max())
        for i in train:
            ls, le = int(label_start[i]), int(label_end[i])
            if not (le < t_ls or ls > t_le):
                raise MLError(
                    LEAKAGE_DETECTED,
                    f"fold {fold['index']}: training label [{ls},{le}] overlaps test window "
                    f"[{t_ls},{t_le}]",
                    422,
                )


def coverage_summary(folds: list[dict[str, Any]], n_rows: int) -> dict[str, Any]:
    """A compact, UI-facing summary of the split design (real assignments)."""
    return {
        "engineVersion": ML_ENGINE_VERSION,
        "nRows": int(n_rows),
        "nFolds": len(folds),
        "folds": [
            {
                "index": f["index"], "nTrain": f["nTrain"], "nTest": f["nTest"],
                "nPurged": f["nPurged"], "nEmbargoed": f["nEmbargoed"],
                "trainStart": f["trainStart"], "trainEnd": f["trainEnd"],
                "testStart": f["testStart"], "testEnd": f["testEnd"],
            }
            for f in folds
        ],
    }


def fold_assignments(folds: list[dict[str, Any]], n_rows: int) -> list[dict[str, Any]]:
    """Per-row assignment records for persistence and the split visualizer.

    A row belongs to exactly one role within a fold: train, test, purged or
    embargoed. Rows outside every fold are omitted (the UI renders the gap).
    """
    records: list[dict[str, Any]] = []
    for fold in folds:
        for role, key in (("test", "testIdx"), ("train", "trainIdx"),
                          ("purged", "purgedIdx"), ("embargoed", "embargoedIdx")):
            for i in fold[key]:
                records.append({"fold": fold["index"], "row": int(i), "role": role})
    return records


__all__ = ["build_splits", "assert_no_leakage", "coverage_summary", "fold_assignments"]
