"""RSL surface experiments — stored snapshots become measured, recorded runs."""

from __future__ import annotations

import uuid

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.verifier import verify_surface_candidate


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _surface_candidate(evolution: EvolutionStore) -> dict:
    base = HarnessSnapshot(
        systemPrompt="You are Eclipse.", toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    candidate = HarnessSnapshot(
        systemPrompt="You are Eclipse, candidate.",
        toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    return evolution.save_candidate({
        "signature": f"rsl-surface-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface fixture",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": base.to_dict(),
            "snapshot": candidate.to_dict(),
            "dataset": "benchmark_v1",
            "scope": "eclipse-agent",
            "taskIds": ["core.echo.001"],
            "split": "validation",
            "targetDimension": "task_success",
            "trials": 1,
            "seed": 7,
            "baselineRunId": None,
        },
        "status": "proposed",
    })


@pytest.mark.asyncio
async def test_surface_candidate_records_a_measured_run_and_its_baseline(store):
    evolution = EvolutionStore(store)
    eval_store = EvaluationStore(store)
    candidate = _surface_candidate(evolution)

    result = await verify_surface_candidate(
        store, candidate, config=RSLConfig(mode="verify", trials=1),
        eval_store=eval_store,
    )

    assert result["benchmark"] == "MEASURED"
    assert result["runId"]
    assert result["baselineRunId"]
    assert result["decisionRecord"]["measured"] == 1
    # The scripted tier cannot improve on a fixed script by narrowing the
    # snapshot, so the honest outcome is a measured rejection — never a fake
    # improvement.
    assert result["passed"] is False
    assert result["decisionRecord"]["accepted"] is False

    run = eval_store.get_run(result["runId"])
    assert run is not None
    assert run["metadata"]["kind"] == "rsl"
    assert run["metadata"]["surface"] is True
    assert run["metadata"]["scope"] == "eclipse-agent"
    assert run["metadata"]["baselineRunId"] == result["baselineRunId"]
    assert run["metadata"]["targetDimension"] == "task_success"

    baseline = eval_store.get_run(result["baselineRunId"])
    assert baseline is not None
    assert baseline["metadata"]["kind"] == "rsl-baseline"
    assert baseline["metadata"]["baseDigest"]
    assert baseline["metadata"]["taskFingerprintDigest"]


@pytest.mark.asyncio
async def test_surface_candidate_reuses_a_matching_recorded_baseline(store):
    evolution = EvolutionStore(store)
    eval_store = EvaluationStore(store)
    candidate = _surface_candidate(evolution)

    first = await verify_surface_candidate(
        store, candidate, config=RSLConfig(mode="verify", trials=1),
        eval_store=eval_store,
    )
    config = dict(candidate["surfaceConfig"])
    config["baselineRunId"] = first["baselineRunId"]
    evolution.update_candidate(candidate["id"], surfaceConfig=config)

    second = await verify_surface_candidate(
        store, evolution.get_candidate(candidate["id"]),
        config=RSLConfig(mode="verify", trials=1), eval_store=eval_store,
    )
    assert second["baselineRunId"] == first["baselineRunId"]
    assert second["benchmark"] == "MEASURED"
