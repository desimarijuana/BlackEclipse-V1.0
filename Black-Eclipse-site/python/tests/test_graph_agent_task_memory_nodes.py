"""agent.task + the extended memory nodes."""

from __future__ import annotations

import pytest

from harness.graph_runtime.agent_nodes import exec_agent_task, set_agent_task_runner
from harness.graph_runtime.memory_nodes import (
    exec_memory_context,
    exec_memory_forget,
    exec_memory_list,
    exec_memory_update,
    resolve_scope,
    set_memory_forget_runner,
    set_memory_list_runner,
    set_memory_recall_runner,
    set_memory_update_runner,
)
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.registry import NodeExecContext


def _ctx(config=None, inputs=None, *, test_run=False, workflow_id=""):
    return NodeExecContext(
        node_id="n", run_id="run-1", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config or {}, test_run=test_run,
        workflow_id=workflow_id, user_id="local",
    )


# ── agent.task ──────────────────────────────────────────────────────────────

@pytest.fixture()
def task_runner():
    seen: list[dict] = []

    def runner(context, config, objective):
        seen.append({"config": config, "objective": objective})
        return {
            "finding": {
                "text": '{"verdict": "pass", "confidence": 0.8}',
                "runId": "agent-run", "status": "completed",
                "tokens": 12, "toolCalls": 1,
            },
            "evidence": {},
        }

    set_agent_task_runner(runner)
    try:
        yield seen
    finally:
        set_agent_task_runner(None)


def test_agent_task_text_output_and_run_projection(task_runner):
    result = exec_agent_task(_ctx({"task": "Review it", "outputMode": "text"}))
    assert result["output"].startswith("{")
    assert result["run"]["runId"] == "agent-run"
    assert result["valid"] is True
    assert task_runner[0]["objective"] == "Review it"


def test_agent_task_composes_input_and_context(task_runner):
    exec_agent_task(_ctx(
        {"task": "Review it"},
        {"input": {"symbol": "AAPL"}, "context": {"note": "careful"}},
    ))
    objective = task_runner[0]["objective"]
    assert "Input (JSON)" in objective and "AAPL" in objective
    assert "Context (JSON)" in objective and "careful" in objective


def test_agent_task_json_mode_validates_the_schema(task_runner):
    result = exec_agent_task(_ctx({
        "task": "Review it", "outputMode": "json",
        "outputSchemaJson": '{"type":"object","required":["verdict"],"properties":{"verdict":{"type":"string"}}}',
    }))
    assert result["data"] == {"verdict": "pass", "confidence": 0.8}
    assert result["valid"] is True
    assert result["issues"] == []


def test_agent_task_json_mismatch_is_invalid_not_coerced(task_runner):
    result = exec_agent_task(_ctx({
        "task": "Review it", "outputMode": "json",
        "outputSchemaJson": '{"type":"object","required":["missing"],"properties":{"missing":{"type":"string"}}}',
    }))
    assert result["valid"] is False
    assert result["data"] is None
    assert result["issues"]


def test_agent_task_requires_a_task(task_runner):
    with pytest.raises(ValueError, match="needs a task"):
        exec_agent_task(_ctx({}))


def test_agent_task_refuses_a_memory_write_in_a_test_run(task_runner):
    with pytest.raises(ValueError, match="test run"):
        exec_agent_task(_ctx({"task": "x", "memoryMode": "write"}, test_run=True))


# ── memory ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def memory_runners():
    state = {"updated": None, "forgotten": None}

    def recall(context, args):
        return {"memories": [
            {"id": "m1", "memoryType": "semantic", "content": "A" * 400, "importance": 0.9},
            {"id": "m2", "memoryType": "preference", "content": "B" * 400, "importance": 0.1},
        ], "context": "raw"}

    def list_runner(context, args):
        return {"memories": [
            {"id": "m1", "memoryType": "semantic", "scope": "workflow:wf"},
            {"id": "m2", "memoryType": "preference", "scope": "workflow:wf"},
        ]}

    def update(context, args):
        state["updated"] = args
        return {"memory": {"id": args["memoryId"], "content": args["content"]}}

    def forget(context, args):
        state["forgotten"] = args
        return {"memory": {"id": args["memoryId"], "status": "archived"}}

    set_memory_recall_runner(recall)
    set_memory_list_runner(list_runner)
    set_memory_update_runner(update)
    set_memory_forget_runner(forget)
    try:
        yield state
    finally:
        set_memory_recall_runner(None)
        set_memory_list_runner(None)
        set_memory_update_runner(None)
        set_memory_forget_runner(None)


def test_scope_resolution_is_explicit():
    assert resolve_scope("general", _ctx()) == "general"
    assert resolve_scope("run", _ctx()) == "run:run-1"
    assert resolve_scope("workflow", _ctx(workflow_id="wf")) == "workflow:wf"
    with pytest.raises(ValueError, match="needs a saved workflow id"):
        resolve_scope("workflow", _ctx())
    assert resolve_scope("custom.scope", _ctx()) == "custom.scope"
    with pytest.raises(ValueError, match="invalid memory scope"):
        resolve_scope("bad scope", _ctx())


def test_memory_context_drops_low_importance_to_fit_the_budget(memory_runners):
    result = exec_memory_context(_ctx({
        "query": "rules", "budgetTokens": 128, "limit": 8,
    }))
    assert result["count"] == 1
    assert result["dropped"] == 1
    assert "semantic" in result["context"]


def test_memory_context_requires_a_query(memory_runners):
    with pytest.raises(ValueError, match="needs a query"):
        exec_memory_context(_ctx({}))


def test_memory_list_projects_scopes_and_types(memory_runners):
    result = exec_memory_list(_ctx({"scope": "workflow"}, workflow_id="wf"))
    assert result["count"] == 2
    assert result["scopes"] == ["workflow:wf"]
    assert set(result["types"]) == {"semantic", "preference"}


def test_memory_update_and_forget_are_operator_only(memory_runners):
    with pytest.raises(ValueError, match="test run"):
        exec_memory_update(_ctx({"memoryId": "m1", "content": "new"}, test_run=True))
    with pytest.raises(ValueError, match="test run"):
        exec_memory_forget(_ctx({"memoryId": "m1"}, test_run=True))


def test_memory_update_and_forget_call_the_service(memory_runners):
    result = exec_memory_update(_ctx({"memoryId": "m1", "content": "new"}))
    assert result["updated"] is True
    assert memory_runners["updated"]["content"] == "new"

    forgotten = exec_memory_forget(_ctx({"memoryId": "m1", "reason": "wrong"}))
    assert forgotten["forgotten"] is True
    assert memory_runners["forgotten"]["reason"] == "wrong"


def test_service_list_update_archive_roundtrip(tmp_path):
    from harness.eclipse_memory.service import EclipseMemoryService
    from harness.eclipse_memory.store import EclipseMemoryStore

    service = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "agent-memory.db")))
    record = service.write_memory(
        memory_type="semantic", content="original", source="manual",
        scope="workflow:wf", scope_id="wf",
    )
    memory_id = record["id"]
    listed = service.list_memories(scope="workflow:wf", scope_id="wf")
    assert [row["id"] for row in listed] == [memory_id]

    updated = service.update_memory(memory_id, content="corrected")
    assert updated["content"] == "corrected"

    archived = service.archive_memory(memory_id, reason="test")
    assert archived["status"] == "archived"
