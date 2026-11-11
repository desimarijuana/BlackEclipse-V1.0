"""Round 5 / C2: the task scheduler's execution attempt goes through Fabric."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.tasks.scheduler import TaskScheduler


class _Fabric:
    def __init__(self, result=None, raises: bool = False) -> None:
        self.result = result
        self.raises = raises
        self.calls: list[dict] = []

    async def submit(self, job_type, payload, **kwargs):
        self.calls.append({"jobType": job_type, "payload": payload, **kwargs})
        if self.raises:
            raise RuntimeError("fabric unavailable")
        return self.result


class _Manager:
    """Only the reads `build_task_context` performs for a dependency-free task."""

    _store = None

    def get_dependencies(self, _task_id):
        return []

    def list_artifacts(self, _task_id):
        return []

    def list_executions(self, _task_id):
        return []

    def list_criteria(self, _task_id):
        return []


def _task():
    return SimpleNamespace(
        id="task_1",
        plan_id="plan_1",
        parent_task_id=None,
        title="Check AAPL",
        objective="Check AAPL",
        description="",
        priority=SimpleNamespace(value="medium"),
        metadata={},
        assigned_agent_id="eclipse-agent",
    )


@pytest.mark.asyncio
async def test_the_execution_attempt_is_one_fabric_job():
    fabric = _Fabric(result={
        "status": "SUCCEEDED",
        "outcome": {"output": {"status": "completed", "output": "done", "runId": "run_1"}},
    })
    called = {"executor": 0}

    async def executor(*_args):
        called["executor"] += 1
        return {"status": "completed", "output": "inline"}

    scheduler = TaskScheduler(_Manager(), executor=executor, fabric=fabric)
    outcome = await scheduler._run(_task(), "run_1")

    assert outcome.status == "completed"
    assert outcome.output == "done"
    assert called["executor"] == 0
    assert len(fabric.calls) == 1
    call = fabric.calls[0]
    assert call["jobType"] == "task"
    assert call["worker_kind"] == "task"
    assert call["payload"]["taskId"] == "task_1"
    assert call["await_result"] is True


@pytest.mark.asyncio
async def test_a_deduplicated_submit_uses_the_stored_job_output():
    fabric = _Fabric(result={
        "status": "SUCCEEDED",
        "deduplicated": True,
        "output": {"status": "completed", "output": "cached", "runId": "run_1"},
    })

    async def executor(*_args):
        raise AssertionError("must not run inline for an existing job")

    scheduler = TaskScheduler(_Manager(), executor=executor, fabric=fabric)
    outcome = await scheduler._run(_task(), "run_1")

    assert outcome.status == "completed"
    assert outcome.output == "cached"


@pytest.mark.asyncio
async def test_a_failed_job_is_reported_not_rerun_inline():
    fabric = _Fabric(result={"status": "FAILED", "error": "boom", "errorClass": "TASK_FAILED"})
    called = {"executor": 0}

    async def executor(*_args):
        called["executor"] += 1
        return {"status": "completed", "output": "inline"}

    scheduler = TaskScheduler(_Manager(), executor=executor, fabric=fabric)
    outcome = await scheduler._run(_task(), "run_1")

    assert outcome.status == "failed"
    assert outcome.error_class == "TASK_FAILED"
    assert called["executor"] == 0


@pytest.mark.asyncio
async def test_a_submit_failure_falls_back_to_the_inline_executor():
    fabric = _Fabric(raises=True)
    called = {"executor": 0}

    async def executor(*_args):
        called["executor"] += 1
        return {"status": "completed", "output": "inline"}

    scheduler = TaskScheduler(_Manager(), executor=executor, fabric=fabric)
    outcome = await scheduler._run(_task(), "run_1")

    assert outcome.status == "completed"
    assert outcome.output == "inline"
    assert called["executor"] == 1


@pytest.mark.asyncio
async def test_set_fabric_can_detach_the_plane():
    fabric = _Fabric(result={"status": "SUCCEEDED", "outcome": {"output": {}}})
    scheduler = TaskScheduler(_Manager(), executor=None, fabric=fabric)
    scheduler.set_fabric(None)

    outcome = await scheduler._run(_task(), "run_1")
    assert outcome.status == "failed"
    assert outcome.error_class == "RUNTIME_UNAVAILABLE"
