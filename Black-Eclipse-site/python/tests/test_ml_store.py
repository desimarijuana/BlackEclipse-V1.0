"""Persistence + service round-trips for the ML Research Lab (dataset immutability,
experiment runs, model registry, artifact integrity, inference, reproduction)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.ml import service as S
from harness.ml.models import MLError
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def ml_store(tmp_path):
    store = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(store)
    yield store
    S.set_ml_store(None)


def _synthetic_dataset(task: str = "classification", n_dates: int = 120, n_symbols: int = 2,
                       seed: int = 11):
    rng = np.random.default_rng(seed)
    d = 3
    x = rng.normal(size=(n_dates, n_symbols, d))
    if task == "classification":
        y = (x[:, :, 0] - 0.5 * x[:, :, 1] > 0).astype(float)
        n_classes = 2
        classes = [0.0, 1.0]
    else:
        y = 2.0 * x[:, :, 0] - x[:, :, 1] + rng.normal(scale=0.1, size=(n_dates, n_symbols))
        n_classes = 0
        classes = None
    X = x.reshape(n_dates * n_symbols, d)
    y_flat = y.reshape(n_dates * n_symbols)
    label_start = np.repeat(np.arange(n_dates), n_symbols)
    label_end = np.minimum(label_start + 3, n_dates - 1)
    arrays = S.serialize_arrays({
        "X": X, "y": y_flat, "labelStart": label_start, "labelEnd": label_end,
        "timestamps": [f"2024-{i:04d}" for i in range(n_dates)],
        "symbols": [f"S{j}" for j in range(n_symbols)],
        "featureNames": ["f0", "f1", "f2"], "perSymbolRows": n_symbols,
        "targetTask": task, "targetClasses": classes,
    })
    manifest = {"datasetId": "mld_test", "version": "1.0.0", "name": "test",
                "symbols": [f"S{j}" for j in range(n_symbols)], "featureNames": ["f0", "f1", "f2"],
                "rows": n_dates * n_symbols, "coverage": 1.0, "dataHash": "abc",
                "quality": {"ok": True, "findings": [], "summary": {}},
                "target": {"kind": "direction_binary" if task == "classification" else "forward_return",
                           "task": task, "nClasses": n_classes, "classes": classes}}
    return manifest, arrays


def test_dataset_version_is_immutable(ml_store):
    manifest, arrays = _synthetic_dataset()
    ml_store.save_dataset(name="test", description=None, owner="me", asset_class="equity",
                          manifest=manifest, arrays=arrays)
    assert ml_store.get_dataset_version("mld_test", "1.0.0") is not None
    with pytest.raises(MLError) as exc:
        ml_store.save_dataset(name="test", description=None, owner="me", asset_class="equity",
                              manifest=manifest, arrays=arrays)
    assert exc.value.code == "IMMUTABLE_VERSION"


def test_experiment_run_and_model_registry(ml_store):
    manifest, arrays = _synthetic_dataset("classification")
    ml_store.save_dataset(name="test", description=None, owner="me", asset_class="equity",
                          manifest=manifest, arrays=arrays)
    payload = {"datasetId": "mld_test", "datasetVersion": "1.0.0", "title": "logit",
               "modelFamily": "logistic", "hyperparameters": {"iterations": 1000},
               "selection": {"method": "none"},
               "split": {"method": "walk_forward", "nSplits": 3, "purge": True, "embargo": 1},
               "seed": 1, "registerModel": True, "name": "logit-model"}
    result = asyncio.run(S.execute_experiment(payload, owner="me"))
    assert result["status"] == "completed"
    run = ml_store.get_run(result["runId"])
    assert run["status"] == "completed" and len(run["folds"]) == 3

    model_id = result["registered"]["modelId"]
    version = result["registered"]["version"]
    verify = ml_store.verify_artifact(ml_store.get_model_version(model_id, version)["stateArtifactId"])
    assert verify["ok"] is True

    # inference through the registered version
    pred = S.predict_with_model(model_id, np.zeros((2, 3)))
    assert pred["task"] == "classification" and len(pred["pred"]) == 2

    # lifecycle transition is recorded
    S.transition_model(model_id, version=version, action="approve_research", actor="me",
                       reason="walk-forward stable")
    mv = ml_store.get_model_version(model_id, version)
    assert mv["status"] == "approved_research"
    assert any(a["action"] == "approve_research" for a in mv["approvals"])


def test_reproduce_run_matches_within_tolerance(ml_store):
    manifest, arrays = _synthetic_dataset("regression")
    ml_store.save_dataset(name="reg", description=None, owner="me", asset_class="equity",
                          manifest=manifest, arrays=arrays)
    payload = {"datasetId": "mld_test", "datasetVersion": "1.0.0", "title": "ridge",
               "modelFamily": "ridge", "hyperparameters": {"alpha": 0.01},
               "split": {"method": "chronological", "testSize": 20, "purge": True}, "seed": 1}
    result = asyncio.run(S.execute_experiment(payload, owner="me"))
    repro = S.reproduce_run(result["runId"])
    assert repro["reproduced"] is True
    assert repro["withinTolerance"] is True


def test_artifact_integrity_detects_tampering(ml_store, tmp_path):
    ref = ml_store.save_artifact({"hello": "world"}, kind="test")
    assert ml_store.verify_artifact(ref["id"])["ok"] is True
    # corrupt the underlying file
    with open(ref["path"], "wb") as fh:
        fh.write(b"tampered")
    assert ml_store.verify_artifact(ref["id"])["ok"] is False


def test_run_failure_is_recorded_not_hidden(ml_store):
    manifest, arrays = _synthetic_dataset("regression")
    ml_store.save_dataset(name="reg", description=None, owner="me", asset_class="equity",
                          manifest=manifest, arrays=arrays)
    payload = {"datasetId": "mld_test", "datasetVersion": "1.0.0", "title": "bad",
               "modelFamily": "not_a_real_model",
               "split": {"method": "chronological", "testSize": 20}}
    with pytest.raises(MLError):
        asyncio.run(S.execute_experiment(payload, owner="me"))
    experiments = ml_store.list_experiments()
    runs = ml_store.list_runs(experiments[0]["id"])
    assert runs and runs[0]["status"] == "failed"
    assert runs[0]["error"] is not None
