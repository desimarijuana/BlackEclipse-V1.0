"""Round 5 / C2: one cross-plane append-only execution log."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.events import EventBus, RunEmitter
from harness.execution_log import ExecutionEventLog, SOURCES
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-xlog-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_1", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


def test_all_planes_append_to_the_same_ordered_log(store):
    log = ExecutionEventLog(store._db)
    log.append("run", "run_1", "run.started", {"step": 0})
    log.append("fabric", "job_1", "fabric.job.started", {"queue": "agent"})
    log.append("graph", "grun_1", "node.succeeded", {"nodeId": "n1"})
    log.append("task", "task_1", "task.claimed", {"agent": "eclipse-agent"})
    log.append("orchestration", "exec_1", "node.completed", {"nodeId": "n2"})

    for source in SOURCES:
        rows = log.list_source(source)
        assert len(rows) == 1
        assert rows[0]["source"] == source

    run_events = log.list("run_1")
    assert [row["seq"] for row in run_events] == [0]
    assert run_events[0]["type"] == "run.started"


def test_sequence_is_per_entity_not_global(store):
    log = ExecutionEventLog(store._db)
    assert log.append("run", "run_1", "a")["seq"] == 0
    assert log.append("run", "run_1", "b")["seq"] == 1
    assert log.append("run", "run_2", "a")["seq"] == 0


def test_a_run_emitter_writes_both_the_projection_and_the_log(store):
    emitter = RunEmitter("run_1", store, EventBus())
    emitter.emit_sync("run.started", {"step": 0})

    projection = [e["type"] for e in store.list_events("run_1")]
    assert "run.started" in projection
    log = ExecutionEventLog(store._db)
    assert [row["type"] for row in log.list("run_1")] == ["run.started"]


def test_an_unknown_source_is_rejected_instead_of_polluting_the_log(store):
    log = ExecutionEventLog(store._db)
    with pytest.raises(ValueError):
        log.append("made-up-plane", "x", "y")


def test_the_log_is_bounded(store):
    log = ExecutionEventLog(store._db)
    huge = {"blob": "x" * 300_000}
    row = log.append("run", "run_1", "run.huge", huge)
    assert row is not None
    persisted = log.list("run_1")[0]
    assert persisted["data"].get("truncated") is True
