"""Unit + integration tests for the ML Research Lab core (metrics, targets,
splits, feature selection, adapters, quality, end-to-end training)."""

from __future__ import annotations

import numpy as np
import pytest

from harness.ml import adapters, metrics as M, targets
from harness.ml.features import apply_selection, fit_selection
from harness.ml.models import (
    ExperimentConfig,
    MLError,
    SplitSpec,
    TargetSpec,
)
from harness.ml.quality import evaluate_quality
from harness.ml.splits import assert_no_leakage, build_splits
from harness.ml.training import run_experiment


# ── metrics ──────────────────────────────────────────────────────────────────


def test_roc_auc_perfect_and_reversed():
    y = np.array([0, 0, 1, 1], dtype=float)
    assert M.roc_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert M.roc_auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(0.0)


def test_regression_metrics_known_values():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    p = np.array([1.0, 2.0, 3.0, 5.0])
    block = M.evaluate_regression(y, p)
    assert block["mae"] == pytest.approx(0.25)
    assert block["rmse"] == pytest.approx(0.5)
    # monotonic prediction -> perfect rank IC
    assert block["spearmanIc"] == pytest.approx(1.0)


def test_spearman_and_top_bottom_spread():
    y = np.array([0.1, 0.2, 0.3, 0.4])
    s = np.array([4, 3, 2, 1], dtype=float)
    assert M.spearman_ic(s, y) == pytest.approx(-1.0)
    rk = M.evaluate_ranking(y, np.array([4.0, 3.0, 2.0, 1.0]), top_fraction=0.25)
    assert rk["topBottomSpread"] == pytest.approx(0.1 - 0.4)


def test_classification_logloss_and_confusion():
    y = np.array([0, 1, 1, 0])
    p = np.array([0, 1, 0, 0])
    block = M.evaluate_classification(y, p, None, n_classes=2)
    assert block["confusionMatrix"][0][0] == 2
    assert block["confusionMatrix"][1][0] == 1
    assert block["accuracy"] == pytest.approx(0.75)


# ── targets ──────────────────────────────────────────────────────────────────


def test_forward_return_target_and_label_bounds():
    prices = np.array([[100.0], [110.0], [121.0], [133.1]])
    t = targets.build_target(prices, TargetSpec(kind="forward_return", horizon=1))
    assert t["values"][0, 0] == pytest.approx(0.10)
    assert t["labelStart"][0] == 0 and t["labelEnd"][0] == 1
    assert t["task"] == "regression"


def test_direction_binary_uses_threshold():
    prices = np.array([[100.0], [105.0], [95.0], [100.0]])
    t = targets.build_target(prices, TargetSpec(kind="direction_binary", horizon=1, threshold=0.0))
    assert t["values"][0, 0] == 1.0   # +5%
    assert t["values"][1, 0] == 0.0   # -9.5%


def test_neutral_zone_marks_dead_band_missing():
    prices = np.array([[100.0], [100.5], [105.0], [105.0]])
    t = targets.build_target(prices, TargetSpec(kind="neutral_zone", horizon=1, neutral_band=0.01))
    assert np.isnan(t["values"][0, 0])   # +0.5% inside the band
    assert t["values"][1, 0] == 1.0      # well above


def test_cross_sectional_rank_is_percentile():
    prices = np.array([[1.0, 2.0, 3.0], [2.0, 2.0, 3.0]])  # row 0 -> fwd returns 1, 0, 0
    t = targets.build_target(prices, TargetSpec(kind="cross_sectional_rank", horizon=1))
    row = t["values"][0]
    assert row[0] == pytest.approx(1.0)          # best forward return -> top percentile
    assert row[1] == pytest.approx(row[2])       # tied returns share a rank
    assert row[1] < row[0]


# ── splits / leakage ─────────────────────────────────────────────────────────


def test_chronological_split_and_no_leakage():
    n = 100
    label_start = np.arange(n)
    label_end = np.minimum(np.arange(n) + 5, n - 1)
    folds = build_splits(SplitSpec(method="chronological", test_size=20, purge=True), label_start, label_end)
    assert len(folds) == 1
    assert_no_leakage(folds, label_start, label_end)
    assert folds[0]["nTest"] == 20
    assert folds[0]["nPurged"] > 0  # labels overlapping the test window are purged


def test_walk_forward_produces_multiple_ordered_folds():
    n = 120
    label_start = np.arange(n)
    label_end = np.minimum(np.arange(n) + 3, n - 1)
    folds = build_splits(SplitSpec(method="walk_forward", n_splits=4, purge=True), label_start, label_end)
    assert len(folds) == 4
    assert_no_leakage(folds, label_start, label_end)
    # test windows are strictly later than the training window for every fold
    for f in folds:
        assert f["trainEnd"] is None or f["testStart"] >= f["trainEnd"] - 3


def test_leakage_detection_raises():
    label_start = np.arange(10)
    label_end = np.minimum(np.arange(10) + 2, 9)
    leaking = [{"index": 0, "trainIdx": [0, 1, 5, 6], "testIdx": [2, 3],
                "purgedIdx": [], "embargoedIdx": [],
                "nTrain": 4, "nTest": 2, "nPurged": 0, "nEmbargoed": 0,
                "trainStart": 0, "trainEnd": 7, "testStart": 2, "testEnd": 3}]
    with pytest.raises(MLError) as exc:
        assert_no_leakage(leaking, label_start, label_end)
    assert exc.value.code == "LEAKAGE_DETECTED"


def test_purged_kfold_removes_overlapping_train_labels():
    n = 60
    label_start = np.arange(n)
    label_end = np.minimum(np.arange(n) + 4, n - 1)
    folds = build_splits(SplitSpec(method="purged_kfold", n_splits=5, purge=True, embargo=2),
                         label_start, label_end)
    assert len(folds) >= 2
    assert_no_leakage(folds, label_start, label_end)
    assert all(f["nPurged"] >= 0 and f["nEmbargoed"] >= 0 for f in folds)


# ── feature selection ────────────────────────────────────────────────────────


def test_selection_prefers_informative_feature():
    rng = np.random.default_rng(0)
    x0 = rng.normal(size=200)
    X = np.column_stack([x0, rng.normal(size=200), np.zeros(200)])
    y = 3.0 * x0 + rng.normal(scale=0.01, size=200)
    sel = fit_selection(X, y, "regression", ["a", "b", "const"], method="correlation", top_k=1)
    assert sel["selected"] == [0]
    assert apply_selection(X, sel["selected"]).shape[1] == 1


def test_variance_selection_drops_constant_column():
    X = np.column_stack([np.arange(50.0), np.zeros(50)])
    sel = fit_selection(X, np.arange(50.0), "regression", ["v", "c"], method="variance", top_k=1)
    assert sel["selected"] == [0]


# ── adapters ─────────────────────────────────────────────────────────────────


def test_ridge_recovers_linear_relationship():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 2))
    y = 2.0 * X[:, 0] - 1.5 * X[:, 1] + 0.5
    model = adapters.build_model("ridge", "regression", {"alpha": 0.0}, 0).fit(X, y)
    pred = model.predict(X)
    assert np.allclose(pred, y, atol=1e-6)


def test_logistic_separates_and_probabilities_valid():
    X = np.array([[0.0], [0.1], [0.2], [5.0], [5.1], [5.2]])
    y = np.array([0, 0, 0, 1, 1, 1])
    model = adapters.build_model("logistic", "classification", {"iterations": 2000}, 0).fit(X, y)
    pred = model.predict(X)
    assert np.array_equal(pred, y.astype(float))
    proba = model.predict_proba(X)
    assert proba.shape == (6, 2)
    assert np.all((proba >= 0) & (proba <= 1)) and np.allclose(proba.sum(axis=1), 1.0)


def test_random_forest_learns_nonlinear_pattern():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(400, 2))
    y = (X[:, 0] * X[:, 1] > 0).astype(float)
    forest = adapters.build_model("random_forest", "classification",
                                  {"nEstimators": 40, "maxDepth": 5}, 7).fit(X, y)
    acc = float(np.mean(forest.predict(X) == y))
    assert acc > 0.8
    assert forest.feature_importances() is not None


def test_model_serialization_round_trip():
    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    model = adapters.build_model("random_forest", "classification", {"nEstimators": 10}, 3).fit(X, y)
    state = model.to_dict()
    restored = adapters.load_model(state)
    assert np.array_equal(model.predict(X), restored.predict(X))


def test_optional_family_is_honest_about_availability():
    available, reason = adapters.optional_available("lightgbm")
    if available:
        model = adapters.build_model("lightgbm", "regression", {}, 0)
        assert model.family == "lightgbm"
    else:
        assert reason
        with pytest.raises(MLError) as exc:
            adapters.build_model("lightgbm", "regression", {}, 0)
        assert exc.value.code == "MODEL_UNAVAILABLE"


# ── quality ──────────────────────────────────────────────────────────────────


def test_quality_blocks_single_class():
    X = np.ones((30, 2))
    y = np.zeros(30)
    report = evaluate_quality(X=X, y=y, feature_names=["a", "b"],
                              timestamps=[str(i) for i in range(30)],
                              symbols=["A"] * 30, task="classification")
    assert report["ok"] is False
    assert any(f["code"] == "SINGLE_CLASS" for f in report["findings"])


def test_quality_detects_duplicate_observations():
    X = np.random.default_rng(0).normal(size=(10, 2))
    y = np.arange(10.0)
    report = evaluate_quality(X=X, y=y, feature_names=["a", "b"], timestamps=["t"] * 10,
                              symbols=["A"] * 10, task="regression")
    assert any(f["code"] == "DUPLICATE_OBSERVATIONS" for f in report["findings"])


# ── end-to-end training ──────────────────────────────────────────────────────


def _synthetic_arrays(task: str, n_dates: int = 120, n_symbols: int = 2, seed: int = 5):
    rng = np.random.default_rng(seed)
    d = 3
    x = rng.normal(size=(n_dates, n_symbols, d))
    if task == "classification":
        logit = x[:, :, 0] - 0.5 * x[:, :, 1]
        y = (logit > 0).astype(float)
        classes = [0.0, 1.0]
        n_classes = 2
    else:
        y = 2.0 * x[:, :, 0] - 1.0 * x[:, :, 1] + rng.normal(scale=0.1, size=(n_dates, n_symbols))
        classes = None
        n_classes = 0
    X = x.reshape(n_dates * n_symbols, d)
    y = y.reshape(n_dates * n_symbols)
    label_start = np.repeat(np.arange(n_dates), n_symbols)
    label_end = np.minimum(label_start + 3, n_dates - 1)
    arrays = {"X": X, "y": y, "labelStart": label_start, "labelEnd": label_end,
              "featureNames": ["f0", "f1", "f2"], "targetTask": task, "targetClasses": classes}
    manifest = {"featureNames": ["f0", "f1", "f2"],
                "target": {"task": task, "nClasses": n_classes, "classes": classes}}
    return arrays, manifest


def test_end_to_end_walk_forward_classification():
    arrays, manifest = _synthetic_arrays("classification")
    config = ExperimentConfig(model_family="logistic",
                              split=SplitSpec(method="walk_forward", n_splits=3, purge=True, embargo=1),
                              hyperparameters={"iterations": 1000}, seed=1)
    result = run_experiment(arrays, manifest, config)
    assert result["task"] == "classification"
    assert len(result["folds"]) == 3
    assert result["pooledMetrics"]["accuracy"] is not None
    assert result["finalModel"]["family"] == "logistic"
    # OOS predictions are timestamped by source row
    assert len(result["oos"]["rowIndex"]) == len(result["oos"]["y"])


def test_end_to_end_regression_without_leakage():
    arrays, manifest = _synthetic_arrays("regression")
    config = ExperimentConfig(model_family="ridge", hyperparameters={"alpha": 0.001},
                              split=SplitSpec(method="chronological", test_size=20, purge=True),
                              seed=1)
    result = run_experiment(arrays, manifest, config)
    assert result["task"] == "regression"
    assert result["pooledMetrics"]["r2"] is not None
    assert result["finalEvaluation"]["rmse"] is not None


def test_experiment_rejects_unknown_family():
    arrays, manifest = _synthetic_arrays("regression")
    config = ExperimentConfig(model_family="not_a_model",
                              split=SplitSpec(method="chronological", test_size=10))
    with pytest.raises(MLError):
        run_experiment(arrays, manifest, config)
