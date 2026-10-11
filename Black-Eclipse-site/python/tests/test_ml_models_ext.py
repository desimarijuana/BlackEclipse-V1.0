"""The required model families train end-to-end: baselines, scikit-learn,
LightGBM and XGBoost. Optional families are exercised only when their wheel is
importable (it is in this runtime), so the suite never fakes availability."""

from __future__ import annotations

import numpy as np
import pytest

from harness.ml import adapters
from harness.ml.models import ExperimentConfig, SplitSpec
from harness.ml.training import run_experiment


def _synthetic(task: str, n_dates: int = 160, n_symbols: int = 2, seed: int = 3):
    rng = np.random.default_rng(seed)
    d = 3
    x = rng.normal(size=(n_dates, n_symbols, d))
    if task == "classification":
        y = (x[:, :, 0] - 0.5 * x[:, :, 1] + 0.3 * x[:, :, 2] > 0).astype(float)
        classes: list[float] | None = [0.0, 1.0]
        n_classes = 2
    else:
        y = 2.0 * x[:, :, 0] - x[:, :, 1] + rng.normal(scale=0.1, size=(n_dates, n_symbols))
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


@pytest.mark.parametrize("family", ["dummy", "ridge", "logistic", "random_forest"])
def test_native_families_train(family):
    task = "regression" if family == "ridge" else "classification"
    arrays, manifest = _synthetic(task)
    config = ExperimentConfig(model_family=family, seed=1,
                              split=SplitSpec(method="walk_forward", n_splits=3, purge=True, embargo=1))
    result = run_experiment(arrays, manifest, config)
    assert result["pooledMetrics"]
    assert result["finalModel"]["family"] == family


@pytest.mark.parametrize("family", ["sklearn_forest", "sklearn_extra_trees", "lightgbm", "xgboost"])
def test_optional_families_train_when_available(family):
    available, reason = adapters.optional_available(family)
    if not available:
        pytest.skip(f"{family} not installed: {reason}")
    arrays, manifest = _synthetic("classification")
    config = ExperimentConfig(model_family=family, seed=7,
                              hyperparameters={"n_estimators": 30} if family.startswith("sklearn") else {},
                              split=SplitSpec(method="walk_forward", n_splits=3, purge=True, embargo=1))
    result = run_experiment(arrays, manifest, config)
    assert result["pooledMetrics"]["accuracy"] is not None
    assert result["pooledMetrics"]["rocAuc"] is not None
    assert result["finalModel"]["family"] == family


def test_capabilities_report_all_families_in_this_runtime():
    caps = {m["family"]: m["available"] for m in adapters.model_capabilities()}
    for family in ("dummy", "ridge", "logistic", "random_forest"):
        assert caps[family] is True
    # The optional families must report their TRUE availability, never assumed.
    for family in ("sklearn_forest", "sklearn_extra_trees", "lightgbm", "xgboost"):
        available, _ = adapters.optional_available(family)
        assert caps[family] is available
