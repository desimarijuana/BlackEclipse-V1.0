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
    assert run["totalTokens"] == 0

    store.update_run(
        "run_1",
        status="completed",
        output="done",
        modelSteps=2,
        promptTokens=100,
        completionTokens=25,
        totalTokens=125,
    )
    run = store.get_run("run_1")
    assert run["status"] == "completed"
    assert run["output"] == "done"
    assert run["modelSteps"] == 2
    assert run["promptTokens"] == 100
    assert run["completionTokens"] == 25
    assert run["totalTokens"] == 125


def test_usage_summary_aggregates_by_model_and_day(store):
    for run_id, model, prompt, completion in (
        ("r1", "gpt-4o-mini", 100, 20),
        ("r2", "gpt-4o-mini", 50, 10),
        ("r3", "claude-3-5", 80, 40),
    ):
        store.create_run(run_id, "eclipse-agent", {"query": "x"}, provider="openai", model=model)
        store.update_run(
            run_id,
            status="completed",
            promptTokens=prompt,
            completionTokens=completion,
            totalTokens=prompt + completion,
        )
    summary = store.usage_summary(days=30)
    assert summary["totals"]["runs"] == 3
    assert summary["totals"]["promptTokens"] == 230
    assert summary["totals"]["completionTokens"] == 70
    assert summary["totals"]["totalTokens"] == 300
    assert summary["totals"]["runsWithUsage"] == 3
    assert summary["totals"]["completed"] == 3
    by_model = {row["model"]: row for row in summary["byModel"]}
    assert by_model["gpt-4o-mini"]["totalTokens"] == 180
    assert by_model["claude-3-5"]["totalTokens"] == 120
    assert sum(day["totalTokens"] for day in summary["byDay"]) == 300
    assert len(summary["recent"]) == 3


def test_usage_summary_counts_runs_without_reported_tokens(store):
    store.create_run("no_usage", "eclipse-agent", {"query": "x"}, provider="ollama", model="llama3.1")
    store.update_run("no_usage", status="completed")
    summary = store.usage_summary(days=30)
    assert summary["totals"]["runs"] == 1
    assert summary["totals"]["totalTokens"] == 0
    assert summary["totals"]["runsWithUsage"] == 0


def test_migration_adds_token_columns_to_legacy_db(tmp_path):
    # An old agent-memory.db has no token columns; opening it must not fail and
    # must add the columns rather than silently losing usage on upgrade.
    import sqlite3

    legacy = tmp_path / "legacy.db"
    db = sqlite3.connect(legacy)
    db.executescript(
        """CREATE TABLE HarnessRun (
             id TEXT PRIMARY KEY, agentId TEXT NOT NULL, userId TEXT, status TEXT NOT NULL,
             input TEXT NOT NULL, output TEXT, error TEXT,
             modelSteps INTEGER NOT NULL DEFAULT 0, toolCalls INTEGER NOT NULL DEFAULT 0,
             toolErrors INTEGER NOT NULL DEFAULT 0, provider TEXT, model TEXT,
             createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, startedAt TEXT, finishedAt TEXT);"""
    )
    db.execute(
        "INSERT INTO HarnessRun (id, agentId, status, input, createdAt, updatedAt) VALUES ('old','a','created','{}','2026-01-01T00:00:00.000Z','2026-01-01T00:00:00.000Z')"
    )
    db.commit()
    db.close()

    s = AgentMemoryStore(str(legacy))
    try:
        run = s.get_run("old")
        assert run is not None
        assert run["totalTokens"] == 0
        s.update_run("old", totalTokens=42)
        assert s.get_run("old")["totalTokens"] == 42
    finally:
        s.close()


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


def test_tool_execution_text_is_redacted_before_persistence(store):
    class R:
        tool_call_id = "c2"
        name = "read_file"
        ok = True
        duration_ms = 3
        text = "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
        error = None
        args = {"path": ".env"}

    store.create_run("run_redact", "a", {"query": "x"})
    store.record_tool_execution("run_redact", R())
    stored = store.list_tool_executions("run_redact")[0]["text"]
    assert "sk-proj-" not in stored
    assert "REDACTED" in stored


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
