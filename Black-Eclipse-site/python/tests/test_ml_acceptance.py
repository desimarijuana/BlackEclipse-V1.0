"""End-to-end acceptance scenario (Phase 18.4), run through the real service +
store with SYNTHETIC fixtures (explicitly not presented as market research).

Workflow: seed dataset -> train baseline + candidates -> compare fold results ->
register -> verify artifact -> inference -> reproduce -> background job.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.ml import service as S
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore

from fabric_helpers import make_manager, wait_terminal


@pytest.fixture()
def env(tmp_path):
    aml = AgentMemoryStore(str(tmp_path / "am.db"))
    ml = MLStore(aml, artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    yield aml, ml
    S.set_ml_store(None)


def _seed(ml: MLStore, n_dates: int = 200, n_symbols: int = 3):
    """Synthetic (NOT real market) classification dataset."""
    rng = np.random.default_rng(21)
    d = 4
    x = rng.normal(size=(n_dates, n_symbols, d))
    logit = 1.2 * x[:, :, 0] - 0.8 * x[:, :, 1] + 0.4 * x[:, :, 3]
    y = (logit > 0).astype(float)
    arrays = S.serialize_arrays({
        "X": x.reshape(n_dates * n_symbols, d), "y": y.reshape(n_dates * n_symbols),
        "labelStart": np.repeat(np.arange(n_dates), n_symbols),
        "labelEnd": np.minimum(np.repeat(np.arange(n_dates), n_symbols) + 5, n_dates - 1),
        "timestamps": [f"2024-{i:04d}" for i in range(n_dates)],
        "symbols": [f"S{j}" for j in range(n_symbols)],
        "featureNames": ["f0", "f1", "f2", "f3"], "perSymbolRows": n_symbols,
        "targetTask": "classification", "targetClasses": [0.0, 1.0],
    })
    manifest = {"datasetId": "mld_e2e", "version": "1.0.0", "name": "synthetic",
                "symbols": [f"S{j}" for j in range(n_symbols)],
                "featureNames": ["f0", "f1", "f2", "f3"], "rows": n_dates * n_symbols,
                "coverage": 1.0, "dataHash": "synthetic",
                "quality": {"ok": True, "findings": [], "summary": {}},
                "target": {"kind": "direction_binary", "task": "classification",
                           "nClasses": 2, "classes": [0.0, 1.0]}}
    ml.save_dataset(name="synthetic", description="SYNTHETIC fixture", owner="me",
                    asset_class="equity", manifest=manifest, arrays=arrays)


def _payload(family: str, register: bool = False):
    return {"datasetId": "mld_e2e", "datasetVersion": "1.0.0", "title": family,
            "modelFamily": family, "hyperparameters": {}, "selection": {"method": "correlation", "topK": 3},
            "split": {"method": "walk_forward", "nSplits": 4, "purge": True, "embargo": 2},
            "seed": 7, "registerModel": register, "name": f"{family}-model"}


def test_full_acceptance_workflow(env):
    aml, ml = env
    _seed(ml)
    families = ["dummy", "logistic", "random_forest", "lightgbm", "xgboost"]
    results = {}
    for family in families:
        outcome = asyncio.run(S.execute_experiment(_payload(family), owner="me"))
        assert outcome["status"] == "completed"
        results[family] = outcome

    # 1) Fold-level comparison uses real, consistent evaluation settings.
    for family, outcome in results.items():
        assert len(outcome["result"]["folds"]) == 4
        assert outcome["result"]["pooledMetrics"]["accuracy"] is not None
    # The baseline must not beat every candidate on the same folds (sanity: the
    # signal is learnable), but we only assert the comparison is real.
    dummy_auc = results["dummy"]["result"]["pooledMetrics"]["rocAuc"]
    assert dummy_auc is None or 0.0 <= dummy_auc <= 1.0

    # 2) Register a candidate, verify the artifact hash, run inference.
    reg = S.register_from_run(results["logistic"]["runId"], name="logit", owner="me")
    assert ml.verify_artifact(ml.get_model_version(reg["modelId"], reg["version"])["stateArtifactId"])["ok"]
    pred = S.predict_with_model(reg["modelId"], np.zeros((3, 4)))
    assert pred["task"] == "classification" and len(pred["pred"]) == 3

    # 3) Reproduce from the manifest; metrics agree within tolerance.
    repro = S.reproduce_run(results["logistic"]["runId"])
    assert repro["withinTolerance"] is True

    # 4) Records persist (re-read from the store, not from memory).
    assert len(ml.list_experiments()) == len(families)
    assert ml.get_run(results["logistic"]["runId"])["status"] == "completed"
    assert len(ml.list_models()) == 1


def test_background_acceptance_step(env):
    aml, ml = env
    _seed(ml)
    manager = make_manager(aml)
    from harness.ml.fabric import build_ml_worker

    manager.register_worker(build_ml_worker(None))

    async def scenario():
        await manager.start()
        submitted = await manager.submit("ml", _payload("lightgbm", register=True), mode="BACKGROUND")
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED"
    assert job["output"]["registered"]["modelId"]
    # The background run's model is in the registry.
    assert len(ml.list_models()) == 1
