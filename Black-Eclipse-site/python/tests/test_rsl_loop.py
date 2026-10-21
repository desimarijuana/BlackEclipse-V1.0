"""RSL R4 — the bounded conductor: claim/lease, budget, modes, decisions."""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.recorder import record_code_experiment
from harness.self_improvement.state import HarnessStateStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _evolution(store) -> EvolutionStore:
    return EvolutionStore(store)


def _candidate(
    evolution: EvolutionStore, *, status: str = "proposed",
    target: str = "python/harness/rsl_fixture.py",
) -> dict:
    return evolution.save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "Eclipse hit the same problem 3 times: the bound that timed out.",
        "targetPath": target,
        "proposedOps": [{
            "op": "create",
            "path": target,
            "content": "VALUE = 1\n",
            "reason": "RSL fixture",
        }],
        "status": status,
    })


@pytest.mark.asyncio
async def test_scheduled_climb_runs_once_due_and_pauses(store):
    calls: list[str] = []

    async def climb_runner(loop, scope):
        calls.append(scope)
        return {"accepted": [], "scope": scope}

    loop = RSLLoop(
        service=None,
        config=RSLConfig(
            mode="auto", strategy="hillclimb", climb_seconds=30,
            climb_scope="eclipse-agent",
        ),
        run_store=store, evolution=_evolution(store),
        climb_runner=climb_runner,
    )
    loop._next_climb_at = 0
    await loop._maybe_climb()
    assert calls == ["eclipse-agent"]

    loop.pause_climb()
    loop._next_climb_at = 0
    await loop._maybe_climb()
    assert calls == ["eclipse-agent"]
    assert loop.status()["climbPaused"] is True


def _loop(store, evolution, *, mode: str = "verify", verify_fn=None,
          propose_fn=None, code_benchmark_fn=None, recorder_fn=None,
          **overrides) -> RSLLoop:
    config = RSLConfig(mode=mode, **overrides)
    return RSLLoop(
        service=None, config=config, run_store=store, evolution=evolution,
        eval_store=EvaluationStore(store), verify_fn=verify_fn,
        propose_fn=propose_fn, code_benchmark_fn=code_benchmark_fn,
        recorder_fn=recorder_fn,
    )


@pytest.mark.asyncio
async def test_off_and_observe_are_strict_no_ops(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)

    off = _loop(store, evolution, mode="off")
    assert await off.tick() == {"mode": "off", "processed": []}
    assert evolution.get_candidate(candidate["id"])["status"] == "proposed"

    observe = _loop(store, evolution, mode="observe")
    assert await observe.tick() == {"mode": "observe", "processed": []}
    assert evolution.get_candidate(candidate["id"])["status"] == "proposed"


@pytest.mark.asyncio
async def test_verified_candidate_is_ok_and_recorded(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)
    calls, records = [], []

    def verify(item):
        calls.append(item["id"])
        return {"passed": True, "benchmark": "UNMEASURED", "decision": "tests_only"}

    def record(*args, **kwargs):
        records.append(kwargs)

    loop = _loop(store, evolution, verify_fn=verify, recorder_fn=record)
    result = await loop.tick()

    assert result["candidateId"] == candidate["id"]
    assert result["decision"] == "tests_passed"
    assert result["benchmark"] == "UNMEASURED"
    assert calls == [candidate["id"]]
    assert records and records[0]["run_id"] == result["runId"]
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"


@pytest.mark.asyncio
async def test_rejected_and_unmeasured_candidates_are_bad(store):
    evolution = _evolution(store)
    rejected = _candidate(evolution)
    unmeasured = _candidate(evolution)

    decisions = {
        rejected["id"]: {"passed": False, "benchmark": "UNMEASURED"},
        unmeasured["id"]: {"passed": None, "benchmark": "UNMEASURED", "unmeasured": True},
    }

    def verify(item):
        return decisions[item["id"]]

    loop = _loop(store, evolution, verify_fn=verify)
    for _ in range(2):
        await loop.tick()

    assert evolution.get_candidate(rejected["id"])["status"] == "evaluated_bad"
    assert evolution.get_candidate(unmeasured["id"])["status"] == "evaluated_bad"


@pytest.mark.asyncio
async def test_daily_budget_stops_a_fourth_experiment(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)
    for _ in range(3):
        evolution.save_attempt({
            "candidateId": candidate["id"], "targetPath": "python/harness/rsl_fixture.py",
            "baseDigest": "", "diffDigest": "prior", "proposedOps": [],
            "outcome": "failure", "outcomeReason": "prior experiment",
        })

    called = []
    loop = _loop(
        store, evolution, verify_fn=lambda item: called.append(item["id"]) or {"passed": True},
        max_experiments_per_day=3,
    )
    result = await loop.tick()
    assert result["skipped"] == "budget"
    assert called == []
    assert evolution.get_candidate(candidate["id"])["status"] == "proposed"


def test_lease_reclaim_returns_the_candidate_and_records_the_attempt(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution, status="evaluating")
    store._db.execute(
        "UPDATE EvolutionCandidate SET updatedAt=? WHERE id=?",
        ("2000-01-01T00:00:00.000Z", candidate["id"]),
    )
    store._db.commit()

    loop = _loop(store, evolution)
    reclaimed = loop.resume()

    assert reclaimed == [candidate["id"]]
    assert evolution.get_candidate(candidate["id"])["status"] == "proposed"
    attempts = evolution.list_attempts(candidate["id"])
    assert attempts[-1]["outcome"] == "failure"
    assert attempts[-1]["outcomeReason"] == "lease expired"


@pytest.mark.asyncio
async def test_start_reclaims_a_stale_lease_and_claims_it_once(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution, status="evaluating")
    store._db.execute(
        "UPDATE EvolutionCandidate SET updatedAt=? WHERE id=?",
        ("2000-01-01T00:00:00.000Z", candidate["id"]),
    )
    store._db.commit()

    loop = _loop(store, evolution, mode="propose", tick_seconds=10)
    await loop.start()
    await asyncio.sleep(0.05)
    await loop.stop()

    assert evolution.get_candidate(candidate["id"])["status"] == "proposed"
    assert loop.resume() == []
    attempts = evolution.list_attempts(candidate["id"])
    assert sum(1 for attempt in attempts if attempt["outcomeReason"] == "lease expired") == 1


@pytest.mark.asyncio
async def test_only_one_experiment_runs_at_a_time(store):
    evolution = _evolution(store)
    _candidate(evolution)
    calls = []

    def verify(item):
        calls.append(item["id"])
        time.sleep(0.2)
        return {"passed": True, "benchmark": "UNMEASURED"}

    loop = _loop(store, evolution, verify_fn=verify)
    first, second = await asyncio.gather(loop.tick(), loop.tick())
    assert len(calls) == 1
    assert any(result.get("skipped") == "busy" for result in (first, second))


@pytest.mark.asyncio
async def test_surface_candidate_uses_the_measured_path_and_counts_an_attempt(store, monkeypatch):
    evolution = _evolution(store)
    candidate = evolution.save_candidate({
        "signature": f"sig-surface-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface fixture",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": {"systemPrompt": "You are Eclipse.", "toolNames": []},
            "snapshot": {"systemPrompt": "You are Eclipse, candidate.", "toolNames": []},
            "dataset": "benchmark_v1",
        },
        "status": "proposed",
    })
    calls = []

    async def fake_surface(store_arg, row, *, config, eval_store=None):
        calls.append((row["id"], config.mode))
        return {
            "ok": True, "passed": True, "benchmark": "MEASURED",
            "decision": "benchmark", "runId": "rsl-surface-run", "measured": 1,
            "decisionRecord": {"accepted": True, "measured": 1},
            "targetDimension": "task_success",
        }

    monkeypatch.setattr(
        "harness.self_improvement.verifier.verify_surface_candidate", fake_surface,
    )
    loop = _loop(store, evolution, mode="verify")
    result = await loop.tick()

    assert calls == [(candidate["id"], "verify")]
    assert result["candidateId"] == candidate["id"]
    assert result["decision"] == "benchmark_accepted"
    assert result["benchmark"] == "MEASURED"
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"
    attempts = evolution.list_attempts(candidate["id"])
    assert len(attempts) == 1
    assert attempts[0]["targetPath"] == "surface:benchmark_v1"
    assert attempts[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_a_new_loop_picks_up_a_proposed_candidate(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)
    loop = _loop(store, evolution, verify_fn=lambda item: {"passed": True})
    await loop.tick()
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"


def test_recorder_persists_experiment_identity_and_event(store):
    evolution = EvolutionStore(store)
    eval_store = EvaluationStore(store)
    candidate = _candidate(evolution)
    run_id = f"rsl-{candidate['id']}-record"
    store.create_run(run_id, "rsl", {"query": "record experiment"})

    recorded = record_code_experiment(
        eval_store, store, run_id=run_id, candidate=candidate,
        verification={"passed": True, "report": {"checks": []}},
    )
    run = eval_store.get_run(run_id)
    assert run is not None
    assert recorded["config"]["benchmark"] == "UNMEASURED"
    assert run["config"]["mode"] == "tests_only"
    assert run["metadata"]["testsPassed"] is True
    assert run["metadata"]["benchmark"] == "UNMEASURED"
    events = [
        event for event in store.list_events(run_id)
        if event["type"] == "self_improvement.experiment_completed"
    ]
    assert len(events) == 1
    assert events[0]["data"]["benchmark"] == "UNMEASURED"


def test_recorder_records_a_measured_benchmark(store):
    evolution = EvolutionStore(store)
    eval_store = EvaluationStore(store)
    candidate = _candidate(evolution)
    run_id = f"rsl-{candidate['id']}-measured"
    store.create_run(run_id, "rsl", {"query": "measured experiment"})

    record_code_experiment(
        eval_store, store, run_id=run_id, candidate=candidate,
        verification={
            "passed": True, "benchmark": "MEASURED",
            "decisionRecord": {"accepted": True, "targetAfter": 0.9},
            "benchmarkMetrics": {
                "baseline": {"aggregates": {"task_success": 0.7}, "measuredTrials": 3},
                "candidate": {"aggregates": {"task_success": 0.9}, "measuredTrials": 3},
            },
            "report": {"checks": []},
        },
        decision="benchmark_accepted",
    )
    run = eval_store.get_run(run_id)
    assert run["config"]["benchmark"] == "MEASURED"
    assert run["config"]["mode"] == "tests_benchmark"
    assert run["metadata"]["decisionRecord"]["accepted"] is True
    assert run["metadata"]["measuredTrials"] == 3
    events = [
        event for event in store.list_events(run_id)
        if event["type"] == "self_improvement.experiment_completed"
    ]
    assert events[0]["data"]["benchmark"] == "MEASURED"
    assert events[0]["data"]["measuredTrials"] == 3


@pytest.mark.asyncio
async def test_propose_mode_validates_ops_without_running_them(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution, status="inert")
    called = []
    loop = _loop(
        store, evolution, mode="propose",
        verify_fn=lambda item: called.append(item["id"]),
    )
    result = await loop.tick()

    assert result["proposed"] == [candidate["id"]]
    assert called == []
    proposed = evolution.get_candidate(candidate["id"])
    assert proposed["status"] == "proposed"
    assert proposed["targetPath"] == "python/harness/rsl_fixture.py"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_auto_mode_proposes_then_verifies_one_candidate(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution, status="inert")
    calls = []

    def verify(item):
        calls.append(item["id"])
        return {"passed": True, "benchmark": "UNMEASURED"}

    loop = _loop(store, evolution, mode="auto", verify_fn=verify)
    result = await loop.tick()

    assert result["mode"] == "auto"
    assert candidate["id"] in result["proposed"]
    assert result["verified"]["candidateId"] == candidate["id"]
    assert calls == [candidate["id"]]
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"


@pytest.mark.asyncio
async def test_auto_mode_does_not_verify_when_nothing_is_proposed(store):
    evolution = _evolution(store)
    called = []
    loop = _loop(
        store, evolution, mode="auto",
        verify_fn=lambda item: called.append(item["id"]) or {"passed": True},
    )
    result = await loop.tick()

    assert result["proposed"] == []
    assert result["verified"]["skipped"] == "none"
    assert called == []


@pytest.mark.asyncio
async def test_measured_code_benchmark_can_reject_a_candidate(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)
    records = []

    def bench(*args, **kwargs):
        return {
            "ok": True, "passed": False, "benchmark": "MEASURED",
            "decisionRecord": {"accepted": False, "reasons": ["no improvement"]},
            "baseline": {"aggregates": {"task_success": 0.8}, "measuredTrials": 5},
            "candidate": {"aggregates": {"task_success": 0.8}, "measuredTrials": 5},
        }

    loop = _loop(
        store, evolution,
        verify_fn=lambda item: {"passed": True, "benchmark": "UNMEASURED"},
        code_benchmark_fn=bench,
        recorder_fn=lambda *a, **kw: records.append(kw),
        code_benchmark=True,
    )
    result = await loop.tick()

    assert result["decision"] == "benchmark_rejected"
    assert result["benchmark"] == "MEASURED"
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_bad"
    assert records[0]["verification"]["benchmark"] == "MEASURED"
    assert records[0]["verification"]["decisionRecord"]["accepted"] is False


@pytest.mark.asyncio
async def test_measured_code_benchmark_can_accept_a_candidate(store):
    evolution = _evolution(store)
    candidate = _candidate(evolution)

    def bench(*args, **kwargs):
        return {
            "ok": True, "passed": True, "benchmark": "MEASURED",
            "decisionRecord": {"accepted": True},
            "baseline": {"aggregates": {"task_success": 0.7}, "measuredTrials": 5},
            "candidate": {"aggregates": {"task_success": 0.85}, "measuredTrials": 5},
        }

    loop = _loop(
        store, evolution,
        verify_fn=lambda item: {"passed": True, "benchmark": "UNMEASURED"},
        code_benchmark_fn=bench,
        code_benchmark=True,
    )
    result = await loop.tick()

    assert result["decision"] == "benchmark_accepted"
    assert result["benchmark"] == "MEASURED"
    assert evolution.get_candidate(candidate["id"])["status"] == "evaluated_ok"


@pytest.mark.asyncio
async def test_measured_surface_creates_an_inert_candidate_state(store):
    evolution = _evolution(store)
    candidate = evolution.save_candidate({
        "signature": f"surface-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface state test",
        "subjectType": "surface",
        "surfaceConfig": {
            "scope": "eclipse-agent",
            "snapshot": {"sourceDigest": "snap-1", "systemPrompt": "candidate"},
            "base": {"sourceDigest": "base-1", "systemPrompt": "base"},
        },
        "status": "proposed",
    })

    def verify(item):
        return {
            "passed": True, "benchmark": "MEASURED", "runId": "evalrun-surface-state",
            "decisionRecord": {"accepted": True, "targetAfter": 0.9, "measured": 2},
        }

    loop = _loop(store, evolution, verify_fn=verify)
    result = await loop.tick()

    assert result["decision"] == "benchmark_accepted"
    assert result["stateId"]
    state = loop.state_store.get_state(result["stateId"])
    assert state["scope"] == "eclipse-agent"
    assert state["status"] == "candidate"
    assert state["candidateId"] == candidate["id"]
    assert state["acceptedRunId"] == "evalrun-surface-state"
    assert state["metrics"]["aggregates"]["task_success"] == 0.9
    assert state["utility"] == 0.9


@pytest.mark.asyncio
async def test_run_hillclimb_refuses_outside_verify_and_strategy(store):
    evolution = _evolution(store)
    off = _loop(store, evolution, mode="off", strategy="hillclimb")
    refused = await off.run_hillclimb(propose=lambda *args: [], evaluate=lambda *args: {})
    assert refused["refused"] is True and refused["reason"] == "mode"

    manual = _loop(store, evolution, mode="verify", strategy="rsl")
    refused = await manual.run_hillclimb(propose=lambda *args: [], evaluate=lambda *args: {})
    assert refused["refused"] is True and refused["reason"] == "strategy"


@pytest.mark.asyncio
async def test_run_hillclimb_needs_a_current_state(store):
    evolution = _evolution(store)
    loop = _loop(store, evolution, mode="verify", strategy="hillclimb")
    refused = await loop.run_hillclimb(
        propose=lambda *args: [], evaluate=lambda *args: {},
    )
    assert refused["refused"] is True
    assert refused["reason"] == "no_current_state"


@pytest.mark.asyncio
async def test_run_hillclimb_saves_a_candidate_and_never_promotes(store):
    evolution = _evolution(store)
    loop = _loop(store, evolution, mode="verify", strategy="hillclimb")
    root = loop.state_store.save_state({
        "scope": "global",
        "snapshotDigest": "base",
        "metrics": {"aggregates": {"task_success": 0.7}, "measuredTrials": 10},
        "utility": 0.7,
        "status": "current",
    })

    candidate = {
        "id": "climb-1",
        "snapshotDigest": "candidate-1",
        "candidateId": "evo-climb",
        "acceptedRunId": "run-climb",
        "validation": {
            "aggregates": {"task_success": 0.85}, "measuredTrials": 10,
        },
        "replay": {"taskRates": {"a": 1.0}},
    }

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await loop.run_hillclimb(
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
    )

    assert result["refused"] is False
    assert result["accepted"]
    accepted = result["accepted"][0]
    assert accepted["parentStateId"] == root["id"]
    assert accepted["status"] == "candidate"
    assert loop.state_store.current("global")["id"] == root["id"]
    assert evolution.experiments_started_since("1970-01-01T00:00:00.000Z") >= 1

@pytest.mark.asyncio
async def test_hot_config_persists_and_reloads(store):
    evolution = _evolution(store)
    loop = _loop(store, evolution, mode="off")

    status = await loop.set_config({"mode": "observe", "k": 4, "tickSeconds": 30})
    assert status["mode"] == "observe"
    assert status["k"] == 4
    assert status["configSource"] == "env+persisted"

    # A fresh conductor (the next process boot) overlays the persisted row.
    booted = RSLLoop(
        service=None, config=None, run_store=store, evolution=evolution,
    )
    assert booted.config.mode == "observe"
    assert booted.config.k == 4
    assert booted.config.tick_seconds == 30

    with pytest.raises(ValueError):
        await loop.set_config({"notAField": True})

    await loop.stop()
    await booted.stop()
