"""Probability calibration and feature drift — the "can I trust it?" phase.

Calibration must be fitted on out-of-fold predictions only, and drift must be a
measurement (PSI/KS), never a guess. Both are deterministic and need no new
dependency.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.ml import service as S
from harness.ml.calibration import apply_calibration, fit_calibration
from harness.ml.drift import compare_features, ks_statistic, psi
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


# ── calibration ──────────────────────────────────────────────────────────────


def test_platt_pulls_over_confident_scores_back_to_the_observed_rate() -> None:
    rng = np.random.default_rng(0)
    # The outcome happens 30% of the time, but the model always says 0.75.
    y = (rng.random(400) < 0.3).astype(float)
    scores = np.full(400, 0.75)

    state = fit_calibration(scores, y, method="platt")
    assert state is not None and state["method"] == "platt"
    calibrated = apply_calibration(state, scores)
    assert float(np.mean(calibrated)) == pytest.approx(0.3, abs=0.05)
    assert state["brierAfter"] < state["brierBefore"]
    assert state["fittedOn"] == "out-of-fold"


def test_isotonic_is_monotone_and_bounded() -> None:
    rng = np.random.default_rng(1)
    y = (rng.random(300) < 0.4).astype(float)
    scores = rng.random(300)

    state = fit_calibration(scores, y, method="isotonic")
    assert state is not None
    grid = np.linspace(0.0, 1.0, 50)
    out = apply_calibration(state, grid)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)
    assert np.all(np.diff(out) >= -1e-12)


def test_calibration_declines_instead_of_faking_an_identity() -> None:
    assert fit_calibration(np.full(10, 0.5), np.zeros(10), method="none") is None
    assert fit_calibration(np.full(10, 0.5), np.zeros(10), method="platt") is None  # too few
    # three-class probabilities are not a binary curve
    assert fit_calibration(np.full(200, 0.5), np.resize([0.0, 1.0, 2.0], 200),
                           method="platt") is None
    with pytest.raises(Exception):
        fit_calibration(np.full(100, 0.5), np.zeros(100), method="magic")


def test_apply_without_a_curve_is_the_identity() -> None:
    p = np.array([0.1, 0.9])
    np.testing.assert_allclose(apply_calibration({}, p), p)


# ── drift ───────────────────────────────────────────────────────────────────


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift() -> None:
    rng = np.random.default_rng(2)
    a = rng.normal(0, 1, 2000)
    assert psi(a, a) == pytest.approx(0.0, abs=1e-6)
    shifted = rng.normal(3, 1, 2000)
    assert psi(a, shifted) > 0.25


def test_ks_sees_identical_and_disjoint_samples() -> None:
    rng = np.random.default_rng(3)
    a = rng.normal(0, 1, 500)
    same = ks_statistic(a, a)
    assert same is not None and same["statistic"] == pytest.approx(0.0, abs=1e-9)

    disjoint = ks_statistic(np.zeros(200), np.ones(200))
    assert disjoint is not None
    assert disjoint["statistic"] == pytest.approx(1.0)
    assert disjoint["pValue"] < 0.01


def test_a_missing_feature_is_a_schema_change_not_a_zero() -> None:
    rng = np.random.default_rng(4)
    report = compare_features(
        {"a": rng.normal(size=200), "b": rng.normal(size=200)},
        {"a": rng.normal(size=200)},
        feature_names=["a", "b"],
    )
    by_name = {row["feature"]: row for row in report["features"]}
    assert by_name["b"]["verdict"] == "schema_change"
    assert by_name["b"]["psi"] is None
    assert report["verdict"] == "schema_change"
    assert "b" in report["driftedFeatures"]


# ── the whole path through the service ──────────────────────────────────────


def _rows(shift: float, n: int = 200) -> list[dict[str, object]]:
    rng = np.random.default_rng(11)
    rows = []
    for i in range(n):
        a = float(rng.normal(0 + shift, 1))
        b = float(rng.normal(0, 1))
        rows.append({"a": a, "b": b, "label": "up" if a + b > 0 else "down"})
    return rows


@pytest.fixture()
def env(tmp_path):
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        yield ml
    finally:
        S.set_ml_store(None)


def _build(name: str, shift: float) -> tuple[str, str]:
    built = asyncio.run(S.build_dataset_version(None, {
        "name": name, "source": "records", "records": _rows(shift),
        "featureNames": ["a", "b"],
        "target": {"kind": "column", "column": "label", "task": "classification"},
    }, name=name))
    return built["datasetId"], built["version"]


def test_a_calibrated_run_records_its_curve_and_predicts_with_it(env) -> None:
    dataset_id, version = _build("calibrated", 0.0)
    run = asyncio.run(S.execute_experiment({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
        "seed": 5, "calibration": "platt", "registerModel": True, "name": "cal",
    }))
    result = run["result"]
    assert result["calibration"]["fittedOn"] == "out-of-fold"
    assert result["calibration"]["rows"] > 0
    assert result["finalModel"]["calibration"]["method"] == "platt"
    assert "finalCalibratedEvaluation" in result

    model_id = run["registered"]["modelId"]
    prediction = S.predict_with_model(model_id, [[0.5, 0.5], [-1.0, 0.2]])
    assert prediction["calibration"] == "platt"
    assert np.allclose(np.sum(prediction["proba"], axis=1), 1.0, atol=1e-6)


def test_reproducing_a_calibrated_run_uses_the_same_curve(env) -> None:
    dataset_id, version = _build("reproduce", 0.0)
    run = asyncio.run(S.execute_experiment({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
        "seed": 4, "calibration": "isotonic",
    }))
    reproduced = S.reproduce_run(run["runId"])
    assert reproduced["withinTolerance"] is True
    diffs = reproduced.get("diffs") or []
    assert all(d["within"] for d in diffs if d.get("delta") is not None)


def test_drift_between_the_training_data_and_a_shifted_version(env) -> None:
    trained_on = _build("before", 0.0)
    later = _build("after", 3.0)

    run = asyncio.run(S.execute_experiment({
        "datasetId": trained_on[0], "datasetVersion": trained_on[1],
        "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
        "seed": 2, "registerModel": True, "name": "drift-model",
    }))
    model_id = run["registered"]["modelId"]

    drift = S.model_drift(model_id, dataset_id=later[0], dataset_version=later[1])
    assert drift["report"]["verdict"] == "drift"
    assert "a" in drift["report"]["driftedFeatures"]
    row = next(r for r in drift["report"]["features"] if r["feature"] == "a")
    assert row["psi"] > 0.25
    assert drift["reference"]["datasetId"] == trained_on[0]

    # the same version is stable — the detector is not just always alarmed
    same = S.model_drift(model_id, dataset_id=trained_on[0], dataset_version=trained_on[1])
    assert same["report"]["verdict"] == "stable"
