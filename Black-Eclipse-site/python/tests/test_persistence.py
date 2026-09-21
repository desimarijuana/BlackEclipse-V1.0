"""Agent-memory persistence: runs, events, tool executions, memory, skills."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore, DB_FILENAME


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-harness-py-")
    path = os.path.join(directory, DB_FILENAME)
    s = AgentMemoryStore(path)
    yield s
    s.close()


def test_creates_separate_database_file(store):
    assert store.path.endswith("agent-memory.db")


def test_run_round_trip_and_update(store):
    store.create_run("run_1", "financial-analyst", {"query": "hi"})
    run = store.get_run("run_1")
    assert run["status"] == "created"
    assert run["input"]["query"] == "hi"

    store.update_run("run_1", status="completed", output="done", modelSteps=2)
    run = store.get_run("run_1")
    assert run["status"] == "completed"
    assert run["output"] == "done"
    assert run["modelSteps"] == 2


def test_events_are_ordered_by_sequence(store):
    store.create_run("run_ev", "a", {"query": "x"})
    store.append_event("run_ev", "run.started", 2)
    store.append_event("run_ev", "run.created", 1, {"k": "v"})
    events = store.list_events("run_ev")
    assert [e["seq"] for e in events] == [1, 2]
    assert events[0]["data"] == {"k": "v"}


def test_tool_execution_recorded(store):
    class R:
        tool_call_id = "c1"
        name = "get_market_snapshot"
        ok = True
        duration_ms = 12
        text = "Price: 1"
        error = None
        args = {"symbol": "AAPL"}

    store.create_run("run_t", "a", {"query": "x"})
    store.record_tool_execution("run_t", R())
    execs = store.list_tool_executions("run_t")
    assert execs[0]["ok"] is True
    assert execs[0]["name"] == "get_market_snapshot"


def test_memory_remember_and_recall_scoped(store):
    store.remember("user", "preference", "Prefers PSX", user_id="u1")
    store.remember("user", "preference", "Loves crypto", user_id="u2")
    assert len(store.recall(scope="user", user_id="u1")) == 1


def test_memory_confidence_clamped(store):
    rec = store.remember("market", "fact", "x", confidence=5)
    assert rec["confidence"] == 1.0


def test_skills_propose_and_outcome(store):
    store.propose_skill("check-price", "Check a price", {"steps": []})
    assert store.get_skill("check-price")["status"] == "proposed"
    store.record_skill_outcome("check-price", True)
    store.record_skill_outcome("check-price", False)
    skill = store.get_skill("check-price")
    assert skill["successCount"] == 1
    assert skill["failCount"] == 1


def test_skills_upsert_not_duplicate(store):
    store.propose_skill("dup", "v1", {})
    store.propose_skill("dup", "v2", {})
    assert len([s for s in store.list_skills() if s["name"] == "dup"]) == 1
