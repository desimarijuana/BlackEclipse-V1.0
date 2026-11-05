"""Unsupervised tasks — clustering and anomaly detection.

The rules that make the supervised path trustworthy apply unchanged: the same
chronological folds, the same independent leakage assertion, and no invented
ground truth. An undefined metric is `None`, never zero.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from harness.ml import adapters
from harness.ml import metrics as M
from harness.ml.datasets import build_records_dataset
from harness.ml.models import DatasetSpec, ExperimentConfig, SplitSpec, TargetSpec
from harness.ml.training import run_experiment


def _rows(n: int = 90) -> list[dict[str, object]]:
    start = dt.date(2024, 1, 1)
    rows: list[dict[str, object]] = []
    for i in range(n):
        rows.append({
            "date": (start + dt.timedelta(days=i)).isoformat(),
            "a": float(i % 5),
            "b": float((i * 7) % 13) - 6.0,
        })
    # Two obvious outliers so the anomaly detector has something real to find.
    rows[40]["a"], rows[40]["b"] = 500.0, -500.0
    rows[70]["a"], rows[70]["b"] = -600.0, 600.0
    return rows


def _spec(task: str, **overrides: object) -> DatasetSpec:
    base: dict[str, object] = {
        "source": "records",
        "feature_names": ["a", "b"],
        "target": TargetSpec(kind="unsupervised", task=task),
        "time_column": "date",
    }
    base.update(overrides)
    return DatasetSpec(**base)  # type: ignore[arg-type]


# ── adapters ────────────────────────────────────────────────────────────────


def test_kmeans_is_deterministic_and_round_trips() -> None:
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(0, 0.2, size=(40, 2)), rng.normal(10, 0.2, size=(40, 2))])
    a = adapters.build_model("kmeans", "clustering", {"nClusters": 2}, seed=11).fit(X)
    b = adapters.build_model("kmeans", "clustering", {"nClusters": 2}, seed=11).fit(X)
    np.testing.assert_allclose(a.centers_, b.centers_)

    labels = a.predict(X)
    assert set(np.unique(labels)) == {0.0, 1.0}

    restored = adapters.load_model(a.to_dict())
    np.testing.assert_allclose(restored.predict(X), labels)


def test_mad_anomaly_flags_the_planted_outliers_without_seeing_them_first() -> None:
    rng = np.random.default_rng(3)
    train = rng.normal(0, 1, size=(200, 2))
    model = adapters.build_model("mad_z", "anomaly", {"contamination": 0.02}, seed=0).fit(train)
    unseen = np.array([[0.1, -0.2], [0.0, 0.1], [50.0, -50.0]])
    flags = model.predict(unseen)
    assert flags.tolist() == [0.0, 0.0, 1.0]

    restored = adapters.load_model(model.to_dict())
    assert restored.predict(unseen).tolist() == flags.tolist()


def test_adapters_refuse_the_wrong_task() -> None:
    with pytest.raises(Exception):
        adapters.build_model("kmeans", "regression", {}, seed=0)
    with pytest.raises(Exception):
        adapters.build_model("mad_z", "classification", {}, seed=0)


def test_capabilities_report_only_real_families() -> None:
    caps = {c["family"]: c for c in adapters.model_capabilities()}
    assert caps["kmeans"]["tasks"] == ["clustering"]
    assert caps["mad_z"]["tasks"] == ["anomaly"]
    assert caps["kmeans"]["available"] is True


# ── metrics ─────────────────────────────────────────────────────────────────


def test_silhouette_rewards_separation_and_refuses_one_cluster() -> None:
    rng = np.random.default_rng(7)
    separated = np.vstack([rng.normal(0, 0.1, size=(30, 2)), rng.normal(9, 0.1, size=(30, 2))])
    labels = np.array([0.0] * 30 + [1.0] * 30)
    assert M.silhouette(separated, labels) > 0.9
    assert M.silhouette(separated, np.zeros(60)) is None


def test_anomaly_metrics_report_a_rate_and_never_an_accuracy() -> None:
    block = M.evaluate_anomaly(np.array([0.1, 0.2, 9.0]), np.array([0.0, 0.0, 1.0]),
                               contamination=0.05)
    assert block["flagged"] == 1
    assert block["anomalyRate"] == pytest.approx(1 / 3)
    assert "accuracy" not in block


# ── datasets + training ─────────────────────────────────────────────────────


def test_unsupervised_records_dataset_needs_no_label_column() -> None:
    built = build_records_dataset(_spec("clustering"), _rows())
    manifest = built["manifest"]
    assert manifest["target"]["task"] == "clustering"
    assert manifest["target"]["kind"] == "unsupervised"
    assert np.isnan(built["arrays"]["y"]).all()
    assert manifest["coverage"] == pytest.approx(1.0)
    assert manifest["quality"]["ok"] is True


def test_unsupervised_target_requires_a_real_task() -> None:
    with pytest.raises(Exception):
        build_records_dataset(_spec("regression"), _rows())


def test_clustering_experiment_runs_out_of_sample() -> None:
    built = build_records_dataset(_spec("clustering"), _rows())
    config = ExperimentConfig(
        dataset_id="mld_unsup", dataset_version="1.0.0", model_family="kmeans",
        hyperparameters={"nClusters": 2},
        split=SplitSpec(method="walk_forward", n_splits=3, test_size=15), seed=5,
    )
    result = run_experiment(built["arrays"], built["manifest"], config)
    assert result["task"] == "clustering"
    assert any(f["status"] == "ok" for f in result["folds"])
    assert result["pooledMetrics"]["nClusters"] >= 1
    assert result["oos"]["y"] == []
    assert result["finalModel"]["family"] == "kmeans"


def test_anomaly_experiment_reports_an_out_of_sample_rate() -> None:
    built = build_records_dataset(_spec("anomaly"), _rows())
    config = ExperimentConfig(
        dataset_id="mld_unsup", dataset_version="1.0.0", model_family="mad_z",
        hyperparameters={"contamination": 0.02},
        split=SplitSpec(method="walk_forward", n_splits=3, test_size=15), seed=5,
    )
    result = run_experiment(built["arrays"], built["manifest"], config)
    assert result["task"] == "anomaly"
    assert result["pooledMetrics"]["flagged"] >= 0
    assert result["pooledMetrics"]["targetRate"] == pytest.approx(0.02)
    assert "accuracy" not in result["pooledMetrics"]


def test_feature_selection_needs_a_label() -> None:
    built = build_records_dataset(_spec("clustering"), _rows())
    config = ExperimentConfig(
        dataset_id="mld_unsup", dataset_version="1.0.0", model_family="kmeans",
        selection={"method": "correlation"}, split=SplitSpec(n_splits=2, test_size=15),
    )
    with pytest.raises(Exception):
        run_experiment(built["arrays"], built["manifest"], config)
