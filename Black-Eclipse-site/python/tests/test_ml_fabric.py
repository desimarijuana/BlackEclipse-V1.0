"""Durable, cancellable, resource-bounded background training through the
Execution Fabric — the production isolation path (Phase 12)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.ml import service as S
from harness.ml import config as mlconfig
from harness.ml.fabric import build_ml_worker
from harness.ml.models import MLError
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


def _seed(ml: MLStore, task: str = "classification", n_dates: int = 120, n_symbols: int = 2):
    rng = np.random.default_rng(4)
    d = 3
    x = rng.normal(size=(n_dates, n_symbols, d))
    if task == "classification":
        y = (x[:, :, 0] - 0.5 * x[:, :, 1] > 0).astype(float)
        n_classes, classes = 2, [0.0, 1.0]
    else:
        y = 2.0 * x[:, :, 0] - x[:, :, 1] + rng.normal(scale=0.1, size=(n_dates, n_symbols))
        n_classes, classes = 0, None
    arrays = S.serialize_arrays({
        "X": x.reshape(n_dates * n_symbols, d), "y": y.reshape(n_dates * n_symbols),
        "labelStart": np.repeat(np.arange(n_dates), n_symbols),
        "labelEnd": np.minimum(np.repeat(np.arange(n_dates), n_symbols) + 3, n_dates - 1),
        "timestamps": [f"t{i}" for i in range(n_dates)], "symbols": [f"S{j}" for j in range(n_symbols)],
        "featureNames": ["f0", "f1", "f2"], "perSymbolRows": n_symbols,
        "targetTask": task, "targetClasses": classes,
    })
    manifest = {"datasetId": "mld_bg", "version": "1.0.0", "name": "bg", "symbols": ["S0", "S1"],
                "featureNames": ["f0", "f1", "f2"], "rows": n_dates * n_symbols, "coverage": 1.0,
                "dataHash": "x", "quality": {"ok": True, "findings": [], "summary": {}},
                "target": {"kind": "direction_binary" if task == "classification" else "forward_return",
                           "task": task, "nClasses": n_classes, "classes": classes}}
    ml.save_dataset(name="bg", description=None, owner="me", asset_class="equity",
                    manifest=manifest, arrays=arrays)
    return {"datasetId": "mld_bg", "datasetVersion": "1.0.0", "title": "bg",
            "modelFamily": "logistic", "hyperparameters": {"iterations": 500},
            "split": {"method": "walk_forward", "nSplits": 3, "purge": True, "embargo": 1}, "seed": 1}


def test_background_training_completes_through_the_fabric(env):
    aml, ml = env
    payload = _seed(ml)
    manager = make_manager(aml)
    worker = build_ml_worker(None)
    assert worker.kind == "ml" and worker.queues == ("ml",)
    manager.register_worker(worker)

    async def scenario():
        await manager.start()
        submitted = await manager.submit("ml", payload, mode="BACKGROUND")
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return submitted, job

    submitted, job = asyncio.run(scenario())
    assert submitted["mode"] == "BACKGROUND"
    assert job["status"] == "SUCCEEDED", job
    run_id = job["output"]["runId"]
    assert ml.get_run(run_id)["status"] == "completed"


def test_background_time_budget_is_enforced(env, monkeypatch):
    aml, ml = env
    payload = _seed(ml)
    monkeypatch.setattr(mlconfig, "_default", mlconfig.MLConfig(max_seconds=0))
    manager = make_manager(aml)
    manager.register_worker(build_ml_worker(None))

    async def scenario():
        await manager.start()
        submitted = await manager.submit("ml", payload, mode="BACKGROUND")
        job = await wait_terminal(manager, submitted["jobId"], timeout=30)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] in ("TIMED_OUT", "FAILED")
    monkeypatch.setattr(mlconfig, "_default", None)


def test_run_experiment_job_reports_cancellation_without_raising(env):
    aml, ml = env
    payload = _seed(ml)
    event = asyncio.Event()
    event.set()  # pre-cancelled
    outcome = asyncio.run(S.run_experiment_job(payload, cancel_event=event))
    assert outcome["status"] == "cancelled"
    assert ml.get_run(outcome["runId"])["status"] == "cancelled"


def test_row_guardrail_refuses_an_oversized_dataset(env, monkeypatch):
    aml, ml = env
    payload = _seed(ml)
    monkeypatch.setattr(mlconfig, "_default", mlconfig.MLConfig(max_rows=10))
    with pytest.raises(MLError) as exc:
        asyncio.run(S.run_experiment_job(payload))
    assert exc.value.code == "INVALID_INPUT"
    monkeypatch.setattr(mlconfig, "_default", None)

def test_background_compare_completes_through_the_fabric(env):
    """The arena runs on the SAME worker: same isolation, cancellation and timeout."""
    aml, ml = env
    payload = _seed(ml)
    manager = make_manager(aml)
    manager.register_worker(build_ml_worker(None))

    async def scenario():
        await manager.start()
        submitted = await manager.submit(
            "ml", {"mode": "compare", "families": ["dummy", "logistic"], **payload},
            mode="BACKGROUND")
        job = await wait_terminal(manager, submitted["jobId"], timeout=90)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    assert job["output"]["mode"] == "compare"
    assert len(job["output"]["runs"]) == 2


def test_background_search_completes_through_the_fabric(env):
    aml, ml = env
    payload = _seed(ml)
    manager = make_manager(aml)
    manager.register_worker(build_ml_worker(None))

    async def scenario():
        await manager.start()
        submitted = await manager.submit(
            "ml", {"mode": "search", "modelFamily": "logistic",
                   "grid": {"l2": [1e-3, 1e-2]}, "maxTrials": 2, **payload},
            mode="BACKGROUND")
        job = await wait_terminal(manager, submitted["jobId"], timeout=90)
        await manager.stop()
        return job

    job = asyncio.run(scenario())
    assert job["status"] == "SUCCEEDED", job
    assert job["output"]["mode"] == "search"
    assert job["output"]["trials"] == 2
