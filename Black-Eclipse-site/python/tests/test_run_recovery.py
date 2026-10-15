"""Run recovery: orphaned runs left by a process restart become failed."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore, DB_FILENAME
from harness.run_recovery import fail_orphaned_runs


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-harness-py-")
    path = os.path.join(directory, DB_FILENAME)
    s = AgentMemoryStore(path)
    yield s
    s.close()


def test_fail_orphaned_runs_marks_non_terminal_rows_and_appends_event(store):
    # A previous process died mid-run: the row must become failed with a durable
    # run.failed event, so a watching client sees a terminal state.
    store.create_run("run_stuck", "eclipse-agent", {"query": "x"})
    store.update_run("run_stuck", status="running")
    store.append_event("run_stuck", "model.requested", 1, {"step": 1})
    store.create_run("run_done", "eclipse-agent", {"query": "y"})
    store.update_run("run_done", status="completed", output="ok")

    failed = fail_orphaned_runs(store, "the agent runtime restarted while this run was in flight")

    assert failed == 1
    stuck = store.get_run("run_stuck")
    assert stuck["status"] == "failed"
    assert stuck["error"]["code"] == "RUN_ORPHANED"
    assert stuck["finishedAt"]
    events = store.list_events("run_stuck")
    assert events[-1]["type"] == "run.failed"
    assert events[-1]["seq"] == 2
    assert events[-1]["data"]["code"] == "RUN_ORPHANED"
    # A terminal run is untouched; a second pass is a no-op.
    assert store.get_run("run_done")["status"] == "completed"
    assert fail_orphaned_runs(store, "again") == 0


def test_fail_orphaned_runs_labels_approval_wait_as_interrupted(store):
    # A run paused on an operator approval was blocked on the OPERATOR, not on
    # model progress: it must be reported as RUN_INTERRUPTED (the wait was lost,
    # nothing was applied) rather than a generic RUN_ORPHANED. A run blocked on a
    # tool call is still a plain orphan.
    store.create_run("run_waiting", "eclipse-agent", {"query": "e"})
    store.update_run("run_waiting", status="running")
    store.append_event("run_waiting", "model.requested", 1, {"step": 1})
    store.append_event(
        "run_waiting", "approval.requested", 2, {"approvalId": "appr_x", "kind": "code_write"}
    )
    store.create_run("run_busy", "eclipse-agent", {"query": "b"})
    store.update_run("run_busy", status="running")
    store.append_event("run_busy", "tool.requested", 1, {"name": "workspace_status"})

    failed = fail_orphaned_runs(store, "the agent runtime restarted while this run was in flight")

    assert failed == 2
    waiting = store.get_run("run_waiting")
    assert waiting["status"] == "failed"
    assert waiting["error"]["code"] == "RUN_INTERRUPTED"
    assert "approval" in waiting["error"]["message"]
    events = store.list_events("run_waiting")
    assert events[-1]["type"] == "run.failed"
    assert events[-1]["data"]["code"] == "RUN_INTERRUPTED"
    assert store.get_run("run_busy")["error"]["code"] == "RUN_ORPHANED"
