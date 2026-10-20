"""RSL surface end-to-end — route -> conductor -> measured baseline/candidate."""

from __future__ import annotations

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
import harness.routers.evolution as evolution_router
from harness.routers.evolution import (
    SurfaceExperimentRequest,
    SurfaceSnapshotInput,
)


class _Service:
    def __init__(self, store: AgentMemoryStore, loop: RSLLoop | None = None) -> None:
        self.store = store
        self._rsl_loop = loop

    def evolution_store(self) -> EvolutionStore:
        return EvolutionStore(self.store)

    def operator_actor(self):
        from harness.skills.permissions import Actor

        return Actor(id="operator", operator=True)

    def evolution_context(self, *, run_id):
        return None


@pytest.fixture()
def memory(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


@pytest.mark.asyncio
async def test_surface_route_runs_through_the_conductor_and_records_both_runs(memory, monkeypatch):
    service = _Service(memory)
    loop = RSLLoop(
        service=service,
        config=RSLConfig(mode="verify", trials=1),
    )
    service._rsl_loop = loop
    monkeypatch.setattr(evolution_router, "service", service)

    queued = evolution_router.create_surface_experiment(SurfaceExperimentRequest(
        candidate=SurfaceSnapshotInput(
            systemPrompt="You are Eclipse, candidate.",
        ),
        base=SurfaceSnapshotInput(systemPrompt="You are Eclipse."),
        dataset="benchmark_v1",
        taskIds=["core.echo.001"],
        split="validation",
        targetDimension="task_success",
        trials=1,
        seed=7,
    ))
    assert queued["created"] is True
    candidate_id = queued["candidate"]["id"]

    result = await loop.tick()

    assert result["candidateId"] == candidate_id
    assert result["benchmark"] == "MEASURED"
    assert result["decision"] == "benchmark_rejected"
    assert result["runId"].startswith("evalrun-")

    evolution = EvolutionStore(memory)
    candidate = evolution.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate["status"] == "evaluated_bad"
    assert candidate["subjectType"] == "surface"

    attempts = evolution.list_attempts(candidate_id)
    assert len(attempts) == 1
    assert attempts[0]["targetPath"] == "surface:benchmark_v1"
    assert attempts[0]["outcome"] == "failure"
    assert attempts[0]["outcomeReason"] == "benchmark_rejected"

    eval_store = EvaluationStore(memory)
    run = eval_store.get_run(result["runId"])
    assert run is not None
    assert run["metadata"]["kind"] == "rsl"
    assert run["metadata"]["surface"] is True
    assert run["metadata"]["benchmark"] == "MEASURED"
    baseline_id = run["metadata"]["baselineRunId"]
    baseline = eval_store.get_run(baseline_id)
    assert baseline is not None
    assert baseline["metadata"]["kind"] == "rsl-baseline"

    events = [
        event for event in memory.list_events(result["runId"])
        if event["type"] == "self_improvement.experiment_completed"
    ]
    assert len(events) == 1
    assert events[0]["data"]["decision"] == "benchmark_rejected"
    assert events[0]["data"]["benchmark"] == "MEASURED"
