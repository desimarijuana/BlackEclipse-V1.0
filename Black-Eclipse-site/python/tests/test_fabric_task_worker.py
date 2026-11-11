"""Round 5 / C2: the Fabric `task` worker executes through the task layer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.fabric.builtin_workers import build_default_workers
from harness.fabric.config import FabricConfig
from harness.fabric.models import Job
from harness.fabric.workers import WorkerContext


class _Tasks:
    _store = None

    def get_dependencies(self, _task_id):
        return []

    def list_artifacts(self, _task_id):
        return []

    def list_executions(self, _task_id):
        return []

    def list_criteria(self, _task_id):
        return []

    def get_task(self, task_id):
        return SimpleNamespace(
            id=task_id,
            plan_id="plan_1",
            parent_task_id=None,
            title="Check AAPL",
            objective="Check AAPL",
            description="",
            priority=SimpleNamespace(value="medium"),
            metadata={},
            assigned_agent_id="eclipse-agent",
        )


async def _executor(task, context, run_id):
    return SimpleNamespace(
        to_dict=lambda: {
            "status": "completed", "output": f"done:{task.id}", "runId": run_id,
            "error": "", "errorClass": "",
        }
    )


@pytest.mark.asyncio
async def test_the_task_worker_reconstructs_the_live_task_and_reports_its_outcome():
    service = SimpleNamespace(tasks=_Tasks(), task_executor=_executor)
    workers = {worker.kind: worker for worker in build_default_workers(service, FabricConfig())}
    assert "task" in workers

    job = Job(type="task", queue="task", worker_kind="task",
              task_id="task_1", input={"taskId": "task_1", "runId": "run_1"})
    ctx = WorkerContext(job=job, worker_id="test", attempt=1, store=None, service=service)

    outcome = await workers["task"].handle(ctx)
    assert outcome.status == "succeeded"
    assert outcome.output["output"] == "done:task_1"
    assert outcome.metrics["taskId"] == "task_1"


@pytest.mark.asyncio
async def test_a_missing_task_runtime_fails_honestly():
    service = SimpleNamespace(tasks=None, task_executor=None)
    workers = {worker.kind: worker for worker in build_default_workers(service, FabricConfig())}
    job = Job(type="task", queue="task", task_id="task_1", input={"taskId": "task_1"})
    ctx = WorkerContext(job=job, worker_id="test", attempt=1, store=None, service=service)

    outcome = await workers["task"].handle(ctx)
    assert outcome.status == "failed"
    assert outcome.error_class == "RUNTIME_UNAVAILABLE"
