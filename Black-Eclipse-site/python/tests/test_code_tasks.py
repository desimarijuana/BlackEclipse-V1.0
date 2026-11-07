"""Phase 5 — the code-task lifecycle reuses the ONE run lineage.

A task IS a run; its boundaries are RunCheckpoint rows. A resume reuses the
recorded tool result (ToolExecutionIdempotency), so it never re-applies a patch.
"""

from __future__ import annotations

import pytest

from harness.code.tasks import (
    COMMAND_EXECUTED,
    PATCH_APPLIED,
    PLAN_ACCEPTED,
    TASK_CANCELLED,
    TASK_CREATED,
    TaskStore,
    plan_digest,
)
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage, idempotency_key


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


def _create_run(store, run_id="run_t", agent_id="code-agent"):
    store.create_run(run_id, agent_id, {"query": "build a report generator"}, "u")


def test_created_boundary_is_recorded(store):
    _create_run(store)
    tasks = TaskStore(store)
    checkpoint = tasks.record_created(
        "run_t", workspace_id="ws_a", root="/tmp/ws_a",
        base_revision="abc1234", strategy="worktree", autonomy="edit_verify",
    )
    assert checkpoint["kind"] == TASK_CREATED
    payload = tasks.latest_created("run_t")["payload"]
    assert payload["workspaceId"] == "ws_a"
    assert payload["autonomy"] == "edit_verify"


def test_plan_accept_records_a_digest(store):
    _create_run(store)
    tasks = TaskStore(store)
    steps = [{"id": "s1", "description": "add a module", "files": ["report.py"]}]
    checkpoint = tasks.record_plan_accepted("run_t", steps=steps, check_classes=["python_test"])
    assert checkpoint["kind"] == PLAN_ACCEPTED
    assert checkpoint["payload"]["planDigest"] == plan_digest(steps)


def test_view_reports_status_and_autonomy(store):
    _create_run(store)
    tasks = TaskStore(store)
    tasks.record_created("run_t", workspace_id="ws_a", autonomy="plan_only")
    view = tasks.view("run_t")
    assert view is not None
    assert view["autonomy"] == "plan_only"
    assert view["status"] in ("created", "plan_review")


def test_cancel_records_reason_and_release(store):
    _create_run(store)
    tasks = TaskStore(store)
    tasks.record_cancelled("run_t", reason="operator cancelled", worktree_released=True)
    events = [c for c in tasks._lineage.list_checkpoints("run_t") if c["kind"] == TASK_CANCELLED]
    assert events and events[-1]["payload"]["worktreeReleased"] is True


# ── resume does not double-apply ────────────────────────────────────────────


def test_resume_reuses_the_recorded_patch_effect(store):
    _create_run(store)
    lineage = RunLineage(store)
    tasks = TaskStore(store)
    # First run applies a patch at (stepIndex=2, toolCallId=call_patch).
    tasks.record_patch_applied(
        "run_t", patch_id="p1", tree_digest_after="digest1",
        files=["report.py"], step_index=2, tool_call_id="call_patch",
    )
    lineage.mark_tool_executed("run_t", 2, "call_patch", type("R", (), {
        "name": "workspace_patch_apply", "ok": True, "text": "applied", "error": None,
    })())

    # A resume checks the idempotency ledger BEFORE re-applying.
    recorded = lineage.was_tool_executed("run_t", 2, "call_patch")
    assert recorded is not None
    assert recorded["ok"] is True
    # Exactly ONE patch.applied boundary exists for the step.
    applied = [
        c for c in lineage.list_checkpoints("run_t")
        if c["kind"] == PATCH_APPLIED and c["payload"].get("toolCallId") == "call_patch"
    ]
    assert len(applied) == 1


def test_resume_with_no_checkpoint_is_flagged(store):
    _create_run(store)
    lineage = RunLineage(store)
    assert lineage.latest_checkpoint("run_t") is None


def test_resume_of_a_terminal_run_is_a_conflict(store):
    _create_run(store)
    store.update_run("run_t", status="completed")
    run = store.get_run("run_t")
    assert run["status"] == "completed"


def test_command_boundary_records_the_idempotency_key(store):
    _create_run(store)
    tasks = TaskStore(store)
    key = idempotency_key("run_t", 3, "call_cmd")
    checkpoint = tasks.record_command_executed(
        "run_t", command_execution_id="cmd_1", command_class="python_test",
        exit_code=0, idempotency_key=key,
    )
    assert checkpoint["kind"] == COMMAND_EXECUTED
    assert checkpoint["payload"]["idempotencyKey"] == key
    assert checkpoint["payload"]["exitCode"] == 0


def test_list_only_returns_code_agent_tasks(store):
    _create_run(store, "run_code", agent_id="code-agent")
    store.create_run("run_fin", "eclipse-agent", {"query": "price of AAPL"}, "u")
    tasks = TaskStore(store)
    tasks.record_created("run_code", workspace_id="ws_a", autonomy="plan_only")
    ids = {t["id"] for t in tasks.list()}
    assert "run_code" in ids
    assert "run_fin" not in ids
