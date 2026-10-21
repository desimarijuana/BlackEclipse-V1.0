"""The bounded hill climb: measured ascent, vetoes, replay, plateau and tabu."""

from __future__ import annotations

from harness.persistence import AgentMemoryStore
from harness.self_improvement.hillclimb import HillClimbConfig, run_hillclimb
from harness.self_improvement.state import HarnessStateStore


def _metrics(success=0.8, *, safety=1.0, measured=10):
    return {
        "aggregates": {"task_success": success, "safety_score": safety},
        "measuredTrials": measured,
    }


def _current(success=0.7, *, safety=1.0):
    return {
        "id": "state_current",
        "scope": "global",
        "snapshotDigest": "base",
        "metrics": _metrics(success, safety=safety),
    }


def _candidate(candidate_id, *, success=0.8, safety=1.0, replay=None, measured=10):
    return {
        "id": candidate_id,
        "snapshotDigest": f"digest-{candidate_id}",
        "candidateId": f"evo-{candidate_id}",
        "acceptedRunId": f"run-{candidate_id}",
        "validation": _metrics(success, safety=safety, measured=measured),
        "replay": {"taskRates": replay or {"a": 1.0, "b": 1.0}},
    }


async def test_improving_neighbor_is_accepted_and_persisted():
    candidate = _candidate("one")
    saved = []

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    async def on_accept(state):
        saved.append(state)
        return {**state, "id": "state_one"}

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
        on_accept=on_accept,
    )

    assert result["accepted"]
    assert result["current"]["id"] == "state_one"
    assert result["current"]["snapshotDigest"] == "digest-one"
    assert saved[0]["parentStateId"] == "state_current"
    assert result["generations"][0]["records"][0]["decision"] == "accepted"


async def test_pareto_objective_accepts_a_tradeoff_that_single_rejects():
    current = _current(0.7)
    current["metrics"] = {
        "aggregates": {"task_success": 0.7, "cost": 0.5, "latency": 1.0}, "measuredTrials": 10,
    }
    candidate = _candidate("trade", success=0.69)
    candidate["validation"] = {
        "aggregates": {"task_success": 0.7, "cost": 0.4, "latency": 2.0}, "measuredTrials": 10,
    }

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    single = await run_hillclimb(
        current, propose=propose, evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )
    pareto = await run_hillclimb(
        current, propose=propose, evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(
            generations=1, k=1, max_plateau=1, objective="pareto",
        ),
    )

    assert single["accepted"] == []
    print("REASONS", pareto["generations"][0]["records"][0]["reasons"])
    assert pareto["accepted"]
    assert pareto["objective"] == "pareto"
    assert pareto["pareto"]["frontier"]


async def test_critical_regression_is_rejected_even_with_a_higher_score():
    candidate = _candidate("regress", success=0.95, safety=0.5)

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )

    assert result["accepted"] == []
    record = result["generations"][0]["records"][0]
    assert record["decision"] == "rejected"
    assert any("critical regression" in reason for reason in record["reasons"])


async def test_replay_forgetting_is_rejected():
    candidate = _candidate("forget", replay={"a": 1.0, "b": 0.0})

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )

    assert result["accepted"] == []
    record = result["generations"][0]["records"][0]
    assert record["decision"] == "rejected"
    assert any("forgetting" in reason for reason in record["reasons"])


async def test_unmeasured_neighbor_is_rejected():
    candidate = _candidate("unmeasured", measured=0)
    candidate["validation"] = {"aggregates": {"task_success": None}, "measuredTrials": 0}

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )

    assert result["accepted"] == []
    assert any(
        "no measured trials" in reason
        for reason in result["generations"][0]["records"][0]["reasons"]
    )


async def test_plateau_stops_the_climb():
    async def propose(state, k, generation, rejected):
        return [_candidate(f"flat-{generation}", success=0.7)]

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=5, k=1, max_plateau=2),
    )

    assert result["accepted"] == []
    assert result["stopReason"] == "plateau"
    assert len(result["generations"]) == 2


async def test_tabu_rejects_the_same_neighbor_again():
    async def propose(state, k, generation, rejected):
        return [_candidate("same", success=0.7)] if generation < 2 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(generations=2, k=1, max_plateau=5),
    )

    second = result["generations"][1]["records"][0]
    assert second["decision"] == "rejected"
    assert any("tabu" in reason for reason in second["reasons"])


async def test_evaluation_budget_stops_the_climb():
    candidates = [
        _candidate("one", success=0.8),
        _candidate("two", success=0.9),
    ]

    async def propose(state, k, generation, rejected):
        return candidates if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(
            generations=1, k=2, max_plateau=2, max_evaluations=1,
        ),
    )

    assert result["evaluations"] == 1
    assert result["stopReason"] == "budget"
    assert len(result["generations"][0]["records"]) == 1


async def test_no_replay_baseline_blocks_acceptance_by_default():
    candidate = _candidate("no-baseline")

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )

    assert result["accepted"] == []
    assert any(
        "replay baseline" in reason
        for reason in result["generations"][0]["records"][0]["reasons"]
    )


async def test_accepted_state_persists_and_promotes_through_the_store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        root = states.save_state({
            "scope": "global",
            "snapshotDigest": "base",
            "metrics": _metrics(0.7),
            "utility": 0.7,
            "status": "current",
        })
        candidate = _candidate("persisted", success=0.85)

        async def propose(state, k, generation, rejected):
            return [candidate] if generation == 0 else []

        async def evaluate(item, split):
            return item["validation"] if split == "validation" else item["replay"]

        result = await run_hillclimb(
            root,
            propose=propose,
            evaluate=evaluate,
            replay_baseline={"a": 1.0, "b": 1.0},
            config=HillClimbConfig(generations=1, k=1, max_plateau=1),
            on_accept=states.save_state,
        )

        saved = result["accepted"][0]
        assert saved["parentStateId"] == root["id"]
        assert states.current("global")["id"] == root["id"]

        promoted = states.promote(result["current"]["id"])
        assert promoted["status"] == "current"
        assert states.get_state(root["id"])["status"] == "superseded"
    finally:
        memory.close()

async def test_validation_neighbors_run_in_parallel_with_a_cap():
    import asyncio

    active = 0
    max_active = 0

    async def propose(state, k, generation, rejected):
        if generation:
            return []
        return [_candidate(f"n{i}", success=0.8) for i in range(3)]

    async def evaluate(item, split):
        nonlocal active, max_active
        if split == "validation":
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return item["validation"]
        return item["replay"]

    result = await run_hillclimb(
        _current(),
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0, "b": 1.0},
        config=HillClimbConfig(
            generations=1, k=3, max_parallel=2, max_plateau=1,
        ),
    )
    assert max_active == 2
    assert len(result["generations"][0]["records"]) == 3
