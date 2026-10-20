"""RSL R5 — operator evidence routes and their authorization boundary."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig
from harness.self_improvement.lesson_feedback import LessonOutcomeStore
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.state import HarnessStateStore
import harness.agents as agents_module
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


def test_list_and_promote_harness_states(store):
    states = HarnessStateStore(store)
    root = states.save_state({
        "scope": "global", "snapshotDigest": "base",
        "metrics": {"aggregates": {"task_success": 0.7}},
        "utility": 0.7, "status": "current",
    })
    child = states.save_state({
        "scope": "global", "snapshotDigest": "candidate",
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "candidate", "parentStateId": root["id"],
    })

    listed = evolution_router.list_harness_states()
    assert listed["success"] is True
    assert listed["current"]["id"] == root["id"]
    assert [row["id"] for row in listed["currents"]] == [root["id"]]
    assert any(row["id"] == child["id"] for row in listed["states"])

    promoted = evolution_router.promote_harness_state(child["id"])
    assert promoted["state"]["status"] == "current"
    assert states.get_state(root["id"])["status"] == "superseded"


def test_lesson_outcomes_route_reports_stats_and_rows(store):
    outcomes = LessonOutcomeStore(store)
    outcomes.record_injections(
        "run-1", [{"id": "cand-lesson"}], ["cand-lesson"],
        cue="market data timeout",
    )
    outcomes.record_run_outcome("run-1", "completed")

    result = evolution_router.lesson_outcomes("cand-lesson")
    assert result["success"] is True
    assert result["stats"]["injected"] == 1
    assert result["stats"]["status"] == "insufficient"
    assert result["outcomes"][0]["outcome"] == "success"


def _small_agent(agent_id: str = "eclipse-agent") -> AgentConfig:
    return AgentConfig(
        id=agent_id, name=agent_id, systemPrompt="base prompt",
        tools=["tool_a", "tool_b"], maxSteps=8, maxToolCalls=10,
    )


def _use_surface_base(monkeypatch, *agent_ids: str):
    for agent_id in agent_ids or ("eclipse-agent",):
        monkeypatch.setitem(
            agents_module.AGENT_PRESETS, agent_id, _small_agent(agent_id),
        )


def _surface_candidate(store: AgentMemoryStore, *, model_name=None) -> dict:
    base = HarnessSnapshot(
        systemPrompt="base prompt", toolNames=("tool_a", "tool_b"),
        maxSteps=8, maxToolCalls=10,
    )
    snapshot = HarnessSnapshot(
        systemPrompt="measured prompt", toolNames=("tool_a",),
        maxSteps=6, maxToolCalls=8, modelName=model_name,
    )
    return EvolutionStore(store).save_candidate({
        "signature": f"surface-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface test",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": base.to_dict(), "snapshot": snapshot.to_dict(),
            "dataset": "benchmark_v1", "split": "validation",
            "taskIds": ["core.echo.001"], "targetDimension": "task_success",
            "trials": 1,
        },
        "status": "evaluated_ok",
    })


def _accepted_rsl_run(store: AgentMemoryStore, candidate_id: str, run_id: str) -> str:
    EvaluationStore(store).create_run(
        id=run_id, suite="rsl", datasetName="benchmark_v1",
        datasetVersion="1", datasetChecksum="abc", status="completed",
        config={"kind": "rsl", "benchmark": "MEASURED"},
        metadata={
            "kind": "rsl", "proposalId": candidate_id,
            "benchmark": "MEASURED", "accepted": True, "decision": "accepted",
        },
    )
    return run_id


def test_surface_state_activation_and_rollback(store, monkeypatch):
    _use_surface_base(monkeypatch)
    candidate = _surface_candidate(store)
    run_id = _accepted_rsl_run(store, candidate["id"], "rsl-surface-ok")
    states = HarnessStateStore(store)
    root = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "base",
        "metrics": {"aggregates": {"task_success": 0.7}},
        "utility": 0.7, "status": "current",
    })
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "candidateId": candidate["id"], "acceptedRunId": run_id,
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "candidate", "parentStateId": root["id"],
    })

    activated = evolution_router.activate_surface_state(state["id"])
    assert activated["activation"]["scope"] == "eclipse-agent"
    assert states.current("eclipse-agent")["id"] == state["id"]

    rolled = evolution_router.rollback_surface_activation(
        activated["activation"]["id"],
    )
    assert rolled["activation"]["rolledBackAt"]
    assert states.current("eclipse-agent")["id"] == root["id"]


def test_surface_preview_and_scope_override(store, monkeypatch):
    _use_surface_base(monkeypatch, "eclipse-agent", "code-agent")
    candidate = _surface_candidate(store)
    run_id = _accepted_rsl_run(store, candidate["id"], "rsl-surface-preview")
    states = HarnessStateStore(store)
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "candidateId": candidate["id"], "acceptedRunId": run_id,
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "candidate",
    })

    preview = evolution_router.preview_surface_state(state["id"], scope="eclipse-agent")
    assert preview["canActivate"] is True
    assert preview["baseDigestMatches"] is True
    assert preview["diff"]["toolsRemoved"] == ["tool_b"]
    assert preview["diff"]["maxStepsAfter"] == 6
    assert "eclipse-agent" in preview["availableScopes"]

    activated = evolution_router.activate_surface_state(
        state["id"],
        evolution_router.SurfaceActivationRequest(scope="code-agent"),
    )
    assert activated["activation"]["scope"] == "code-agent"
    assert activated["state"]["scope"] == "code-agent"
    assert states.current("code-agent")["id"] == activated["state"]["id"]
    # The original state remains in its own scope.
    assert states.get_state(state["id"])["scope"] == "eclipse-agent"


def test_surface_activation_refuses_model_identity(store, monkeypatch):
    _use_surface_base(monkeypatch)
    candidate = _surface_candidate(store, model_name="other-model")
    run_id = _accepted_rsl_run(store, candidate["id"], "rsl-surface-model")
    states = HarnessStateStore(store)
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "candidateId": candidate["id"], "acceptedRunId": run_id,
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "candidate",
    })

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        evolution_router.activate_surface_state(state["id"])
    assert refused.value.status_code == 400
    assert "model identity" in str(refused.value.detail)


def test_surface_activation_refuses_an_unmeasured_state(store, monkeypatch):
    _use_surface_base(monkeypatch)
    candidate = _surface_candidate(store)
    run_id = _accepted_rsl_run(store, candidate["id"], "rsl-surface-unmeasured")
    states = HarnessStateStore(store)
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "candidateId": candidate["id"], "acceptedRunId": run_id,
        "metrics": {}, "utility": None, "status": "candidate",
    })

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        evolution_router.activate_surface_state(state["id"])
    assert refused.value.status_code == 409


def test_every_rsl_route_refuses_a_remote_caller():
    from harness import main as main_module

    client = TestClient(main_module.app, client=("203.0.113.9", 1234))
    for method, path in (
        ("get", "/evolution/experiments"),
        ("get", "/evolution/experiments/rsl-e1"),
        ("get", "/evolution/candidates/evo_x/evidence"),
        ("get", "/evolution/lessons"),
        ("get", "/evolution/lessons/cand_x/outcomes"),
        ("get", "/evolution/states"),
        ("post", "/evolution/states/hstate_x/promote"),
        ("post", "/evolution/states/hstate_x/activate-surface"),
        ("get", "/evolution/states/hstate_x/surface-preview"),
        ("get", "/evolution/surface-activations"),
        ("post", "/evolution/surface-activations/hact_x/rollback"),
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
