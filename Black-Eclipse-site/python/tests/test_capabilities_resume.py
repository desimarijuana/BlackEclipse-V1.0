"""Capability activation resumes the original durable task from its checkpoint."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.capabilities.resume import resume_original_task


class _Manager:
    def __init__(self, status: str = "WAITING") -> None:
        self.status = status
        self.resumed: list[str] = []

    def get_task(self, task_id: str):
        return SimpleNamespace(id=task_id, status=self.status)

    def restore_checkpoint(self, task_id: str, *, resume: bool = True):
        self.resumed.append(task_id)
        return {
            "checkpoint": {"id": "chk_1"},
            "task": SimpleNamespace(id=task_id, status="TODO"),
            "resumed": True,
        }


def test_a_parked_task_is_resumed_from_its_checkpoint():
    manager = _Manager("WAITING")
    result = resume_original_task(manager, "task_1")
    assert result["resumed"] is True
    assert result["checkpointId"] == "chk_1"
    assert manager.resumed == ["task_1"]


def test_a_running_task_is_never_rewound():
    manager = _Manager("IN_PROGRESS")
    result = resume_original_task(manager, "task_1")
    assert result["resumed"] is False
    assert manager.resumed == []
    assert "not parked" in result["reason"]


def test_no_task_or_runtime_is_reported_honestly():
    assert resume_original_task(None, "task_1")["resumed"] is False
    assert resume_original_task(_Manager(), "")["resumed"] is False


def test_a_missing_checkpoint_is_not_reported_as_resumed():
    class _NoCheckpoint(_Manager):
        def restore_checkpoint(self, task_id: str, *, resume: bool = True):
            raise RuntimeError("no checkpoint exists")

    result = resume_original_task(_NoCheckpoint(), "task_1")
    assert result["resumed"] is False
    assert "no checkpoint" in result["reason"]


def test_builder_stores_the_original_task_on_the_record(tmp_path):
    from harness.capabilities import builder
    from harness.capabilities.manifest import CapabilityPort
    from harness.capabilities.request import CapabilityRequest
    from harness.capabilities.store import CapabilityStore
    from harness.code import sandbox as sandbox_mod
    from harness.code.execution import interpreter_path
    from harness.persistence import AgentMemoryStore

    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        pytest.skip("sandbox/interpreter unavailable")
    if not interpreter_path():
        pytest.skip("sandbox/interpreter unavailable")

    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        store = CapabilityStore(memory)
        request = CapabilityRequest(
            need="sum a series of values",
            kind="recipe",
            capabilityId="sum_for_task",
            inputs=[CapabilityPort(name="values", kind="series")],
            outputs=[CapabilityPort(name="sum", kind="scalar")],
            implementation='values = inputs.get("values")\nresult = {"sum": sum(values)}\n',
            test='assert result["sum"] == 6\n',
            sampleInputs={"values": [1, 2, 3]},
            resume_task_id="task_42",
        )
        outcome = builder.build(request, store=store, root=tmp_path, run_id="run_1")
        assert outcome["status"] == "active"
        record = store.get("sum_for_task", "1.0.0")
        assert record["taskId"] == "task_42"
    finally:
        memory.close()


def test_the_activate_tool_resumes_the_parked_task(tmp_path):
    from harness.capabilities import builder
    from harness.capabilities.manifest import CapabilityPort
    from harness.capabilities.request import CapabilityRequest
    from harness.capabilities.store import CapabilityStore
    from harness.capabilities.tools import capability_activate
    from harness.code import sandbox as sandbox_mod
    from harness.code.execution import interpreter_path
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolContext

    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        pytest.skip("sandbox/interpreter unavailable")
    if not interpreter_path():
        pytest.skip("sandbox/interpreter unavailable")

    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        store = CapabilityStore(memory)
        request = CapabilityRequest(
            need="sum a series of values",
            kind="recipe",
            capabilityId="sum_activate",
            inputs=[CapabilityPort(name="values", kind="series")],
            outputs=[CapabilityPort(name="sum", kind="scalar")],
            implementation='values = inputs.get("values")\nresult = {"sum": sum(values)}\n',
            test='assert result["sum"] == 6\n',
            sampleInputs={"values": [1, 2, 3]},
            resume_task_id="task_activate",
        )
        built = builder.build(request, store=store, root=tmp_path)
        assert built["status"] == "active"
        builder.deactivate("sum_activate", "1.0.0", store=store, root=tmp_path)

        manager = _Manager("WAITING")
        ctx = ToolContext(
            run_id="run_activate", log=lambda *_: None, memory_store=memory,
            task_manager=manager, task_id="task_activate",
            workspace=SimpleNamespace(root=tmp_path, id="ws_cap"),
        )
        _text, activated = asyncio.run(capability_activate(
            {"capabilityId": "sum_activate"}, ctx,
        ))
        assert activated["status"] == "active"
        assert activated["resume"]["resumed"] is True
        assert manager.resumed == ["task_activate"]
    finally:
        memory.close()


def test_a_capability_failure_records_the_learning_recurrence():
    from harness.code.evolution import record_mistake_recurrence
    from harness.persistence import AgentMemoryStore
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        memory = AgentMemoryStore(str(Path(directory) / "agent-memory.db"))
        try:
            counts = record_mistake_recurrence(
                memory, ["capability_failure"], run_id="run_failure",
            )
            assert counts["capability_failure"] == 1
        finally:
            memory.close()
