"""RSL R4 — the surface benchmark path is the only measured one."""

from __future__ import annotations

import pytest

from harness.evaluation.store import EvaluationStore
from harness.evaluation.tasks import EvaluationTask
from harness.persistence import AgentMemoryStore
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.verifier import verify_surface


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _task() -> EvaluationTask:
    return EvaluationTask.from_dict({
        "id": "rsl.surface",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "say READY"},
        "expected_output": {"equals": "READY"},
        "metadata": {"agent_script": [{"type": "final", "content": "READY"}]},
    })


@pytest.mark.asyncio
async def test_surface_benchmark_is_measured_and_persisted(store):
    base = HarnessSnapshot(
        systemPrompt="You are Eclipse.", toolNames=(), maxSteps=8, maxToolCalls=8,
    )
    candidate = HarnessSnapshot(
        systemPrompt="You are Eclipse, candidate.", toolNames=(),
        maxSteps=8, maxToolCalls=8,
    )
    eval_store = EvaluationStore(store)
    result = await verify_surface(
        store=store,
        snapshot=candidate,
        base=base,
        tasks=[_task()],
        baseline_metrics={"aggregates": {"task_success": 0.0, "safety_score": 1.0}},
        target_dimension="task_success",
        proposal_id="evo_surface",
        eval_store=eval_store,
        trials=1,
        seed=7,
        metadata={"source": "test"},
    )

    assert result["benchmark"] == "MEASURED"
    assert result["decision"] == "benchmark"
    assert result["measured"] == 1
    assert result["decisionRecord"]["accepted"] is True
    assert result["runId"]

    run = eval_store.get_run(result["runId"])
    assert run is not None
    assert run["metadata"]["kind"] == "rsl"
    assert run["metadata"]["proposalId"] == "evo_surface"
    assert run["metadata"]["benchmark"] == "MEASURED"
    assert run["config"]["snapshotDigest"] == candidate.sourceDigest
