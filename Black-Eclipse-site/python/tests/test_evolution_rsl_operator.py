"""RSL operator surfaces: lesson adoption + recursive experiments (R7/R8 wiring)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from harness.code.evolution_store import EvolutionStore
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
import harness.routers.evolution as evolution_router
from harness.routers.evolution import (
    LessonAdoptionRequest,
    ProposeRequest,
    RecursiveExperimentRequest,
    RecursiveVariant,
    SurfaceExperimentRequest,
    SurfaceSnapshotInput,
)


class _Service:
    def __init__(self, store, skill_store, loop=None) -> None:
        self.store = store
        self.skill_store = skill_store
        self._rsl_loop = loop

    def evolution_store(self) -> EvolutionStore:
        return EvolutionStore(self.store)

    def operator_actor(self):
        from harness.skills.permissions import Actor

        return Actor(id="operator", operator=True)

    def evolution_context(self, *, run_id):
        return None


@pytest.fixture()
def env(tmp_path, monkeypatch):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    skill_store = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    service = _Service(store, skill_store)
    monkeypatch.setattr(evolution_router, "service", service)
    yield {"store": store, "skill_store": skill_store, "service": service}
    skill_store.close()
    store.close()


class _Loop:
    def __init__(self) -> None:
        self.wakes = 0
        self.ticks = 0
        self.config = RSLConfig(mode="verify", trials=1)

    def wake(self) -> None:
        self.wakes += 1

    def budget_ok(self) -> bool:
        return True

    def status(self) -> dict:
        return {
            "mode": self.config.mode, "running": False, "busy": False,
            "maxCandidates": self.config.max_candidates,
            "maxExperimentsPerDay": self.config.max_experiments_per_day,
            "k": self.config.k, "startedToday": 0, "remainingToday": 3,
            "budgetExhausted": False,
        }

    async def tick(self) -> dict:
        self.ticks += 1
        return {"mode": self.config.mode, "processed": []}


def _candidate(store: AgentMemoryStore) -> dict:
    return EvolutionStore(store).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "the bound that timed out",
        "targetPath": "python/harness/rsl_operator_fixture.py",
        "proposedOps": [{
            "op": "create", "path": "python/harness/rsl_operator_fixture.py",
            "content": "VALUE = 1\n", "reason": "fixture",
        }],
        "status": "evaluated_ok",
    })


def _experiment(store, candidate_id: str, *, accepted: bool = True, run_id: str = "rsl-ok") -> str:
    EvaluationStore(store).create_run(
        id=run_id, suite="rsl-code", datasetName="owning-tests",
        datasetVersion="1", datasetChecksum="abc",
        config={"kind": "rsl", "proposalId": candidate_id, "benchmark": "MEASURED"},
        metadata={
            "kind": "rsl", "proposalId": candidate_id, "benchmark": "MEASURED",
            "accepted": accepted,
        },
        status="completed",
    )
    return run_id


def _variants() -> list[RecursiveVariant]:
    return [
        RecursiveVariant(
            kind="invariant", targetPath="python/harness/rsl_operator_a.py",
            ops=[{
                "op": "create", "path": "python/harness/rsl_operator_a.py",
                "content": "A = 1\n", "reason": "invariant",
            }],
        ),
        RecursiveVariant(
            kind="domain", targetPath="python/harness/rsl_operator_b.py",
            ops=[{
                "op": "create", "path": "python/harness/rsl_operator_b.py",
                "content": "B = 1\n", "reason": "domain",
            }],
        ),
    ]


def _lesson_body(run_id: str, **overrides) -> LessonAdoptionRequest:
    body = LessonAdoptionRequest(
        cue="market data timeout",
        lesson="Retry the market data call once before falling back.",
        evidence=[{"kind": "experiment", "runId": run_id}],
        validationRunId=run_id,
    )
    for key, value in overrides.items():
        setattr(body, key, value)
    return body


def test_lesson_adoption_records_and_lists_the_adopted_lesson(env):
    candidate = _candidate(env["store"])
    run_id = _experiment(env["store"], candidate["id"])

    result = evolution_router.adopt_lesson(
        candidate["id"], _lesson_body(run_id),
    )
    assert result["stored"] is True
    lesson = result["lesson"]
    assert lesson["cue"] == "market data timeout"
    assert lesson["adoptedArtifactId"] == candidate["id"]
    assert lesson["validationRunId"] == run_id
    assert lesson["status"] == "adopted"

    listed = evolution_router.list_lessons()
    assert [item["id"] for item in listed["lessons"]] == [lesson["id"]]


def test_lesson_adoption_refuses_an_unaccepted_experiment(env):
    candidate = _candidate(env["store"])
    run_id = _experiment(env["store"], candidate["id"], accepted=False, run_id="rsl-rejected")
    with pytest.raises(HTTPException) as refused:
        evolution_router.adopt_lesson(candidate["id"], _lesson_body(run_id))
    assert refused.value.status_code == 409
    assert env["skill_store"].list_candidates(status="adopted") == []


def test_lesson_adoption_refuses_a_verdict_leak(env):
    candidate = _candidate(env["store"])
    run_id = _experiment(env["store"], candidate["id"])
    body = _lesson_body(
        run_id, lesson="The candidate reached pass_rate 0.9 after the edit.",
    )
    with pytest.raises(HTTPException) as refused:
        evolution_router.adopt_lesson(candidate["id"], body)
    assert refused.value.status_code == 400
    assert refused.value.detail == "VERDICT_LEAK"
    assert env["skill_store"].list_candidates(status="adopted") == []


@pytest.mark.asyncio
async def test_rsl_status_and_tick_routes_use_the_loop(env):
    loop = _Loop()
    env["service"]._rsl_loop = loop

    status = evolution_router.rsl_status()
    assert status["mode"] == "verify"
    assert status["remainingToday"] == 3

    tick = await evolution_router.rsl_tick()
    assert tick == {"success": True, "mode": "verify", "processed": []}
    assert loop.ticks == 1


def test_propose_route_stages_operator_ops_on_an_inert_candidate(env):
    candidate = EvolutionStore(env["store"]).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "the bound that timed out",
        "status": "inert",
    })
    result = evolution_router.propose_candidate_route(
        candidate["id"],
        ProposeRequest(
            targetPath="python/harness/rsl_operator_proposal.py",
            ops=[{
                "op": "create",
                "path": "python/harness/rsl_operator_proposal.py",
                "content": "VALUE = 1\n",
                "reason": "operator-staged proposal",
            }],
        ),
    )

    assert result["candidate"]["status"] == "proposed"
    assert result["candidate"]["targetPath"] == "python/harness/rsl_operator_proposal.py"
    assert result["candidate"]["proposedOps"][0]["op"] == "create"


def test_propose_route_refuses_a_frozen_op_path(env):
    candidate = EvolutionStore(env["store"]).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "the bound that timed out",
        "status": "inert",
    })
    with pytest.raises(HTTPException) as refused:
        evolution_router.propose_candidate_route(
            candidate["id"],
            ProposeRequest(
                targetPath="python/harness/rsl_operator_proposal.py",
                ops=[{
                    "op": "create",
                    "path": "python/tests/test_rsl_operator_judge.py",
                    "content": "def test_x():\n    assert True\n",
                    "reason": "candidate edits its judge",
                }],
            ),
        )
    assert refused.value.status_code == 400
    assert refused.value.detail == "RSL_FROZEN_TARGET"


def test_surface_route_creates_one_typed_candidate_and_wakes_the_loop(env):
    loop = _Loop()
    env["service"]._rsl_loop = loop
    body = SurfaceExperimentRequest(
        candidate=SurfaceSnapshotInput(
            systemPrompt="You are Eclipse, candidate.",
        ),
        base=SurfaceSnapshotInput(systemPrompt="You are Eclipse."),
        dataset="benchmark_v1",
        taskIds=["core.echo.001"],
        trials=1,
        seed=7,
    )

    result = evolution_router.create_surface_experiment(body)

    assert result["queued"] is True
    candidate = result["candidate"]
    assert candidate["subjectType"] == "surface"
    assert candidate["status"] == "proposed"
    assert candidate["surfaceConfig"]["dataset"] == "benchmark_v1"
    assert candidate["surfaceConfig"]["taskIds"] == ["core.echo.001"]
    assert candidate["surfaceConfig"]["snapshot"]["systemPrompt"].endswith("candidate.")
    assert candidate["surfaceConfig"]["base"]["sourceDigest"]
    assert loop.wakes == 1

    duplicate = evolution_router.create_surface_experiment(body)
    assert duplicate["candidate"]["id"] == candidate["id"]
    assert duplicate["created"] is False
    assert duplicate["queued"] is True


@pytest.mark.asyncio
async def test_recursive_route_persists_children_and_records_the_experiment(env, monkeypatch):
    candidate = _candidate(env["store"])
    loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="verify", k=2),
        run_store=env["store"],
        evolution=EvolutionStore(env["store"]),
        eval_store=EvaluationStore(env["store"]),
    )
    env["service"]._rsl_loop = loop

    import harness.self_improvement.verifier as verifier_module

    def fake_verify(store, candidate_id, *, ctx, actor):
        assert store is env["store"]
        return {"passed": True, "benchmark": "UNMEASURED", "decision": "tests_only"}

    monkeypatch.setattr(verifier_module, "verify_code", fake_verify)
    result = await evolution_router.run_recursive_experiment(
        candidate["id"],
        RecursiveExperimentRequest(variants=_variants(), seed=1),
    )
    assert result["success"] is True
    assert result["k"] == 2
    assert [child["status"] for child in result["children"]] == ["inert", "inert"]
    assert result["composition"]["decision"] == "no_gain"
    run = EvaluationStore(env["store"]).get_run(result["runId"])
    assert run["metadata"]["kind"] == "rsl-recursion"
    assert run["config"]["k"] == 2
    assert len(result["children"]) == 2


@pytest.mark.asyncio
async def test_recursive_route_refuses_outside_verify_mode(env):
    candidate = _candidate(env["store"])
    env["service"]._rsl_loop = RSLLoop(
        service=None,
        config=RSLConfig(mode="observe", k=2),
        run_store=env["store"],
        evolution=EvolutionStore(env["store"]),
        eval_store=EvaluationStore(env["store"]),
    )
    with pytest.raises(HTTPException) as refused:
        await evolution_router.run_recursive_experiment(
            candidate["id"],
            RecursiveExperimentRequest(variants=_variants(), seed=1),
        )
    assert refused.value.status_code == 409
