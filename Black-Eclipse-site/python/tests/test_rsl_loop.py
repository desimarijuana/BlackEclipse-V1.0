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


def _loop(store, evolution, *, mode: str = "verify", verify_fn=None,
          propose_fn=None, recorder_fn=None, **overrides) -> RSLLoop:
    config = RSLConfig(mode=mode, **overrides)
    return RSLLoop(
        service=None, config=config, run_store=store, evolution=evolution,
        eval_store=EvaluationStore(store), verify_fn=verify_fn,
        propose_fn=propose_fn, recorder_fn=recorder_fn,
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

    loop = _loop(store, evolution, tick_seconds=10)
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
