"""Supervised auto-apply: the one path that may activate an L1 surface state."""

from __future__ import annotations

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.state import HarnessStateStore
from harness.self_improvement.surface_candidate import save_surface_candidate

TASKS = [f"task.{index}" for index in range(6)]


def _surface(store, *, guidance="use the filings tool first", tools=("a", "b")):
    base = HarnessSnapshot(systemPrompt="base prompt", toolNames=tools)
    snapshot = HarnessSnapshot(
        systemPrompt="base prompt", toolNames=tools, toolGuidance=guidance,
    )
    result = save_surface_candidate(
        store,
        base=base,
        snapshot=snapshot,
        task_ids=TASKS,
        baseline_run_id="baseline-run",
    )
    return result["candidate"], base, snapshot


def _seed_run(eval_store, run_id, passed: bool):
    eval_store.create_run(
        id=run_id, suite="test", datasetName="fixture",
        datasetVersion="1", datasetChecksum="checksum", status="completed",
    )
    for index, task_id in enumerate(TASKS):
        eval_store.add_trial(
            runId=run_id, taskId=task_id, trialIndex=index,
            passed=passed, unmeasured=False,
            status="passed" if passed else "failed", score={},
            cost=0.0, latencyMs=1.0, totalTokens=0,
        )


def _state(states, candidate, snapshot, *, scope="global"):
    return states.save_state({
        "scope": scope,
        "snapshotDigest": snapshot.sourceDigest,
        "candidateId": candidate["id"],
        "acceptedRunId": "candidate-run",
        "utility": 0.9,
        "metrics": {"aggregates": {"task_success": 0.9}, "measuredTrials": 6},
        "status": "candidate",
    })


def _loop(memory, states, eval_store, **overrides):
    values = {
        "mode": "verify", "strategy": "hillclimb", "autonomy": "supervised",
        "auto_min_lift": 0.02, "auto_max_per_day": 1,
    }
    values.update(overrides)
    return RSLLoop(
        service=None,
        config=RSLConfig(**values),
        run_store=memory,
        evolution=EvolutionStore(memory),
        eval_store=eval_store,
        state_store=states,
    )


def _fixture(tmp_path, *, guidance="use the filings tool first"):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    states = HarnessStateStore(memory)
    eval_store = EvaluationStore(memory)
    _seed_run(eval_store, "baseline-run", False)
    _seed_run(eval_store, "candidate-run", True)
    candidate, base, snapshot = _surface(memory, guidance=guidance)
    root = states.save_state({
        "scope": "global", "snapshotDigest": "root",
        "utility": 0.5,
        "metrics": {"aggregates": {"task_success": 0.5}, "measuredTrials": 6},
        "status": "current",
    })
    state = _state(states, candidate, snapshot)
    return memory, states, eval_store, candidate, base, snapshot, root, state


@pytest.mark.asyncio
async def test_a_clean_l1_surface_state_is_applied_and_rolls_back(tmp_path):
    memory, states, eval_store, _candidate, _base, _snapshot, root, state = _fixture(tmp_path)
    try:
        loop = _loop(memory, states, eval_store)
        result = await loop.auto_apply_surface(state["id"])

        assert result["applied"] is True
        assert result["risk"]["riskClass"] == "L1"
        assert result["paired"]["ciLow"] > 0
        assert states.current("global")["id"] == state["id"]
        assert loop.autonomy_kill.activations_today() == 1

        activation = result["activation"]
        states.rollback_activation(activation["id"])
        assert states.current("global")["id"] == root["id"]
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_the_daily_budget_and_kill_switch_stop_auto_apply(tmp_path):
    memory, states, eval_store, _candidate, _base, _snapshot, _root, state = _fixture(tmp_path)
    try:
        loop = _loop(memory, states, eval_store)
        first = await loop.auto_apply_surface(state["id"])
        assert first["applied"] is True

        # A second eligible state is refused by the daily budget.
        second_candidate, _b, second_snapshot = _surface(
            memory, guidance="cite the filing date before the number",
        )
        second = _state(states, second_candidate, second_snapshot)
        refused = await loop.auto_apply_surface(second["id"])
        assert refused["applied"] is False
        assert "daily_budget" in refused["decision"]["reasons"]

        # The kill switch stops the next one even when the budget is raised.
        await loop.set_config({"autoMaxPerDay": 5})
        loop.pause_autonomy("operator stop")
        third_candidate, _b, third_snapshot = _surface(
            memory, guidance="name the currency before the price",
        )
        third = _state(states, third_candidate, third_snapshot)
        stopped = await loop.auto_apply_surface(third["id"])
        assert stopped["applied"] is False
        assert "kill_switch" in stopped["decision"]["reasons"]
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_l2_and_non_surface_candidates_are_refused(tmp_path):
    memory, states, eval_store, _candidate, _base, _snapshot, _root, _state1 = _fixture(tmp_path)
    try:
        loop = _loop(memory, states, eval_store)

        # Widening the tool set is L2, not auto-eligible.
        base = HarnessSnapshot(systemPrompt="base prompt", toolNames=("a", "b"))
        widened = HarnessSnapshot(
            systemPrompt="base prompt", toolNames=("a", "b", "c"),
            toolGuidance="use the new tool",
        )
        created = save_surface_candidate(
            memory, base=base, snapshot=widened, task_ids=TASKS,
            baseline_run_id="baseline-run",
        )
        l2_state = _state(states, created["candidate"], widened)
        refused = await loop.auto_apply_surface(l2_state["id"])
        assert refused["applied"] is False
        assert refused["risk"]["riskClass"] == "L2"
        assert "risk_L2_requires_human" in refused["decision"]["reasons"]

        # A code candidate is not a surface at all.
        evolution = EvolutionStore(memory)
        code = evolution.save_candidate({
            "signature": "code-sig", "sourceCategory": "timeout",
            "observedCount": 1, "problemStatement": "code", "status": "inert",
        })
        code_state = states.save_state({
            "scope": "global", "snapshotDigest": "code-digest",
            "candidateId": code["id"], "acceptedRunId": "candidate-run",
            "utility": 0.9,
            "metrics": {"aggregates": {"task_success": 0.9}, "measuredTrials": 6},
            "status": "candidate",
        })
        not_surface = await loop.auto_apply_surface(code_state["id"])
        assert not_surface["applied"] is False
        assert not_surface["reason"] == "not_a_surface_candidate"
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_missing_paired_evidence_is_refused(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        eval_store = EvaluationStore(memory)
        root = states.save_state({
            "scope": "global", "snapshotDigest": "root",
            "utility": 0.5, "metrics": {"aggregates": {"task_success": 0.5}},
            "status": "current",
        })
        base = HarnessSnapshot(systemPrompt="base prompt", toolNames=("a", "b"))
        snapshot = HarnessSnapshot(
            systemPrompt="base prompt", toolNames=("a", "b"),
            toolGuidance="a new hint",
        )
        created = save_surface_candidate(
            memory, base=base, snapshot=snapshot, task_ids=TASKS,
        )
        state = _state(states, created["candidate"], snapshot)
        loop = _loop(memory, states, eval_store)

        refused = await loop.auto_apply_surface(state["id"])
        assert refused["applied"] is False
        assert "no_paired_evidence" in refused["decision"]["reasons"]
        assert states.current("global")["id"] == root["id"]
    finally:
        memory.close()
