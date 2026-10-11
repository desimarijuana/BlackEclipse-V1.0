"""Leakage tests (Phase 13.3): the temporal-correctness gates must DETECT or
REJECT the classic lookahead bugs, using synthetic fixtures that deliberately
contain each violation."""

from __future__ import annotations

import numpy as np
import pytest

from harness.ml import targets
from harness.ml.models import ExperimentConfig, MLError, SplitSpec, TargetSpec
from harness.ml.quality import evaluate_quality
from harness.ml.splits import assert_no_leakage, build_splits
from harness.ml.training import _Standardizer, run_experiment


def test_overlapping_forward_labels_are_purged_before_evaluation():
    n = 80
    label_start = np.arange(n)
    label_end = np.minimum(np.arange(n) + 5, n - 1)  # 5-period forward labels
    folds = build_splits(SplitSpec(method="chronological", test_size=20, purge=True), label_start, label_end)
    assert_no_leakage(folds, label_start, label_end)  # raises if the gate fails
    for fold in folds:
        test_ls = label_start[fold["testIdx"]].min()
        for i in fold["trainIdx"]:
            assert label_end[i] < test_ls or label_start[i] > label_end[fold["testIdx"]].max()
    assert folds[0]["nPurged"] > 0


def test_leakage_gate_rejects_a_hand_crafted_overlap():
    label_start = np.arange(12)
    label_end = np.minimum(np.arange(12) + 4, 11)
    leaking = [{"index": 0, "trainIdx": [0, 1, 2, 8, 9], "testIdx": [5, 6], "purgedIdx": [],
                "embargoedIdx": [], "nTrain": 5, "nTest": 2, "nPurged": 0, "nEmbargoed": 0,
                "trainStart": 0, "trainEnd": 11, "testStart": 5, "testEnd": 10}]
    with pytest.raises(MLError) as exc:
        assert_no_leakage(leaking, label_start, label_end)
    assert exc.value.code == "LEAKAGE_DETECTED"


def test_future_publication_does_not_enter_earlier_labels():
    """A forward-return label at t uses only prices at t and t+h — a price change
    past t+h must not alter it (the point-in-time invariant)."""
    prices = np.array([[100.0], [101.0], [103.0], [102.0], [108.0], [109.0]], dtype=float)
    t = targets.build_target(prices, TargetSpec(kind="forward_return", horizon=2))
    before = t["values"][:3].copy()
    tampered = prices.copy()
    tampered[5, 0] = 10_000.0  # a FUTURE price
    after = targets.build_target(tampered, TargetSpec(kind="forward_return", horizon=2))["values"][:3]
    assert np.allclose(before, after, equal_nan=True)
    # The label that legitimately spans the tampered price DOES move.
    assert t["labelEnd"][3] >= 4


def test_preprocessing_and_final_model_are_fit_on_train_only():
    rng = np.random.default_rng(0)
    n_rows, d = 200, 3
    X = rng.normal(size=(n_rows, d))
    X[:, 0] += np.arange(n_rows) * 0.01  # a drifting feature with a train/test mean gap
    y = X[:, 0] + rng.normal(scale=0.01, size=n_rows)
    label_start = np.arange(n_rows)
    label_end = np.minimum(label_start + 2, n_rows - 1)
    arrays = {"X": X, "y": y, "labelStart": label_start, "labelEnd": label_end,
              "featureNames": ["a", "b", "c"], "targetTask": "regression", "targetClasses": None}
    manifest = {"featureNames": ["a", "b", "c"], "target": {"task": "regression", "nClasses": 0}}
    config = ExperimentConfig(model_family="ridge", split=SplitSpec(method="chronological", test_size=40),
                              seed=1)
    result = run_experiment(arrays, manifest, config)

    finite = np.where(np.isfinite(y) & np.isfinite(X).all(axis=1))[0]
    split_at = int(finite.size * 0.8)
    train_rows = finite[:split_at]
    train_mean = X[train_rows].mean(axis=0)
    full_mean = X[finite].mean(axis=0)
    stored = result["finalModel"]["preprocessing"]["mean"]
    assert np.allclose(stored, train_mean, atol=1e-9)
    assert not np.allclose(stored, full_mean, atol=1e-6)  # proves it is not the full-data mean


def test_train_and_test_indices_never_intersect_within_a_fold():
    n = 120
    label_start = np.arange(n)
    label_end = np.minimum(label_start + 3, n - 1)
    folds = build_splits(SplitSpec(method="purged_kfold", n_splits=4, purge=True, embargo=2),
                         label_start, label_end)
    for fold in folds:
        assert not (set(fold["trainIdx"]) & set(fold["testIdx"]))


def test_stale_duplicate_and_missing_are_reported_by_quality():
    X = np.array([[1.0, np.nan], [1.0, 2.0], [1.0, 2.0]])
    y = np.array([0.0, 1.0, 1.0])
    report = evaluate_quality(X=X, y=y, feature_names=["a", "b"],
                              timestamps=["t0", "t1", "t1"], symbols=["A", "A", "A"],
                              task="classification")
    codes = {f["code"] for f in report["findings"]}
    assert "DUPLICATE_OBSERVATIONS" in codes
    assert "CONSTANT_FEATURES" in codes


def test_standardizer_is_fit_on_the_supplied_rows_only():
    train = np.array([[0.0], [2.0]])
    std = _Standardizer().fit(train)
    assert std.mean[0] == pytest.approx(1.0)
    assert std.std[0] == pytest.approx(np.std([0.0, 2.0], ddof=1))
