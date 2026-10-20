"""RSL R5 — operator evidence routes and their authorization boundary."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
import harness.routers.evolution as evolution_router


class _Service:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store

    def evolution_store(self) -> EvolutionStore:
        return EvolutionStore(self.store)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    monkeypatch.setattr(evolution_router, "service", _Service(memory))
    yield memory
    memory.close()


def _candidate(store: AgentMemoryStore) -> dict:
    return EvolutionStore(store).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "the bound that timed out",
        "targetPath": "python/harness/foo.py",
        "proposedOps": [],
        "status": "evaluated_ok",
    })


def _experiment(store: AgentMemoryStore, proposal_id: str, run_id: str = "rsl-e1") -> str:
    eval_store = EvaluationStore(store)
    eval_store.create_run(
        id=run_id, suite="rsl-code", datasetName="owning-tests",
        datasetVersion="1", datasetChecksum="abc",
        config={
            "kind": "rsl", "proposalId": proposal_id, "split": "validation",
            "trials": 0, "tier": 0, "graderVersion": 1, "benchmark": "UNMEASURED",
        },
        metadata={
            "kind": "rsl", "proposalId": proposal_id,
            "benchmark": "UNMEASURED", "testsPassed": True,
            "taskFingerprintDigest": "digest",
        },
        status="completed",
    )
    eval_store.add_metric(runId=run_id, dimension="task_success", value=1.0, sampleSize=1)
    eval_store.add_trial(
        runId=run_id, taskId="t.1", trialIndex=0, passed=True,
        score={"cost": None, "graderVersion": 1},
        trajectory={"events": [{"type": "secret-raw-trace"}]},
    )
    return run_id


def test_list_and_get_experiments(store):
    candidate = _candidate(store)
    run_id = _experiment(store, candidate["id"])

    listed = evolution_router.list_experiments()
    assert listed["success"] is True
    assert [item["id"] for item in listed["experiments"]] == [run_id]
    assert listed["experiments"][0]["metadata"]["benchmark"] == "UNMEASURED"

    detail = evolution_router.get_experiment(run_id)
    assert detail["experiment"]["id"] == run_id
    assert detail["metrics"][0]["dimension"] == "task_success"
    assert detail["trials"][0]["score"]["cost"] is None
    assert "trajectory" not in detail["trials"][0]


def test_candidate_evidence_links_attempts_and_experiments(store):
    candidate = _candidate(store)
    evolution = EvolutionStore(store)
    evolution.save_attempt({
        "candidateId": candidate["id"], "targetPath": "python/harness/foo.py",
        "baseDigest": "", "diffDigest": "d", "proposedOps": [],
        "outcome": "success", "outcomeReason": "owning checks passed",
    })
    _experiment(store, candidate["id"])

    evidence = evolution_router.candidate_evidence(candidate["id"])
    assert evidence["candidate"]["id"] == candidate["id"]
    assert evidence["attempts"][0]["outcome"] == "success"
    assert evidence["experiments"][0]["metadata"]["proposalId"] == candidate["id"]


def test_get_missing_or_non_rsl_experiment_is_404(store):
    EvaluationStore(store).create_run(
        id="ordinary", suite="evaluation", status="completed",
        metadata={"kind": "evaluation"},
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as missing:
        evolution_router.get_experiment("does-not-exist")
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as ordinary:
        evolution_router.get_experiment("ordinary")
    assert ordinary.value.status_code == 404


def test_every_rsl_route_refuses_a_remote_caller():
    from harness import main as main_module

    client = TestClient(main_module.app, client=("203.0.113.9", 1234))
    for method, path in (
        ("get", "/evolution/experiments"),
        ("get", "/evolution/experiments/rsl-e1"),
        ("get", "/evolution/candidates/evo_x/evidence"),
        ("get", "/evolution/lessons"),
        ("post", "/evolution/candidates/evo_x/lessons"),
        ("post", "/evolution/candidates/evo_x/recursive"),
        ("post", "/evolution/candidates/evo_x/propose"),
        ("post", "/evolution/surface-experiments"),
        ("get", "/evolution/rsl"),
        ("post", "/evolution/rsl/tick"),
        ("post", "/evolution/candidates/evo_x/prepare-landing"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 403, (method, path, response.text)
