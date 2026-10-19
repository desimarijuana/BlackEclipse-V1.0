"""Round 4 (W8.2): durable-by-default in the chat path.

A durable chat request creates a goal task and the run becomes its first
attempt; the run itself is unchanged. Settlement verifies through the task-type
verifier — verified completion, or a bounded repair attempt re-queued for the
scheduler. A task-dispatched run is never wrapped again (no recursion).
"""

from __future__ import annotations

import types

import pytest

from harness.goal_runtime import (
    is_chat_run,
    maybe_start_goal,
    settle_goal,
    wrap_service_for_goals,
)
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tasks.manager import TaskManager
from harness.tasks.model import CriterionState, TaskStatus, TaskType
from harness.tasks.store import TaskStore


@pytest.fixture()
def service(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    manager = TaskManager(TaskStore(store))
    return types.SimpleNamespace(tasks=manager, artifacts=None)


def _request(query: str, *, run_id="run_chat_1", context=None) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query=query, context=dict(context or {})),
        modelSettings=ModelSettings(provider="ollama", model="test"),
        callbackBaseUrl="http://localhost:3000",
    )


def _result(dumped: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        status=dumped.get("status", "completed"),
        model_dump=lambda: dict(dumped),
    )


def _passing_code_dump() -> dict:
    return {
        "status": "completed", "runId": "run_chat_1", "output": "built it",
        "toolCalls": 3, "totalTokens": 100, "modelSteps": 4,
        "codeVerification": {
            "records": [{"commandClass": "python_test", "exitCode": 0,
                         "outputDigest": "d" * 16}],
            "artifacts": [{"artifactName": "greeting.py", "passed": True}],
        },
    }


def test_chat_run_detection():
    assert is_chat_run(_request("hi")) is True
    assert is_chat_run(_request("hi", context={"source": "task-scheduler"})) is False
    assert is_chat_run(_request("hi", context={"taskId": "task_x"})) is False


def test_durable_request_creates_a_goal_task_bound_to_the_run(service):
    request = _request("build a small greeting app with tests")
    started = maybe_start_goal(service, request)
    assert started is not None
    assert started["taskType"] == TaskType.CODE.value

    task = service.tasks.get_task(started["taskId"])
    assert task.status == TaskStatus.IN_PROGRESS  # the chat run IS the attempt
    assert task.assigned_run_id == "run_chat_1"
    assert task.goal_contract is not None
    assert task.goal_contract.deliverables == ["greeting app"]
    # The request context now names the task, so settlement knows what to close.
    assert request.input.context["goalTaskId"] == task.id
    # Idempotent: a second intake on the same request is a no-op.
    assert maybe_start_goal(service, request) is None


def test_non_durable_request_stays_a_single_turn(service):
    assert maybe_start_goal(service, _request("what is the weather?")) is None
    assert service.tasks.list_tasks(limit=10) == []


def test_task_dispatched_runs_are_never_wrapped_again(service):
    assert maybe_start_goal(
        service, _request("build an app", context={"source": "task-scheduler"})
    ) is None
    assert service.tasks.list_tasks(limit=10) == []


def test_settlement_completes_only_with_passing_evidence(service):
    request = _request("build a small greeting app with tests")
    started = maybe_start_goal(service, request)
    settled = settle_goal(service, request, _result(_passing_code_dump()))
    assert settled["ok"] is True
    assert settled["settled"] == "COMPLETED"
    task = service.tasks.get_task(started["taskId"])
    assert task.status == TaskStatus.COMPLETED
    assert task.output_reference == "run_chat_1"
    assert all(c.state == CriterionState.PASSED for c in service.tasks.list_criteria(task.id))


def test_settlement_requeues_when_the_verifier_refuses(service):
    request = _request("build a small greeting app with tests")
    started = maybe_start_goal(service, request)
    failing = _passing_code_dump()
    failing["codeVerification"] = {
        "records": [{"commandClass": "python_test", "exitCode": 1,
                     "outputDigest": "d" * 16}],
        "artifacts": [],
    }
    settled = settle_goal(service, request, _result(failing))
    assert settled["ok"] is False
    assert settled["requeued"] is True
    assert settled["errorClass"] == "VERIFICATION_FAILED"
    task = service.tasks.get_task(started["taskId"])
    assert task.status == TaskStatus.TODO  # the scheduler continues the loop
    assert "no successful tests run was recorded" in (task.error or "")
    assert task.retry_count == 1


def test_settlement_requeues_a_failed_run(service):
    request = _request("build a small greeting app with tests")
    started = maybe_start_goal(service, request)
    settled = settle_goal(
        service, request,
        _result({"status": "failed", "error": {"code": "PROVIDER_ERROR", "message": "model down"}}),
    )
    assert settled["requeued"] is True
    assert settled["errorClass"] == "RUN_FAILED"
    task = service.tasks.get_task(started["taskId"])
    assert task.status == TaskStatus.TODO
    assert "model down" in (task.error or "")


def test_settlement_without_a_goal_is_a_noop(service):
    assert settle_goal(service, _request("hi"), _result({"status": "completed"})) is None


@pytest.mark.asyncio
async def test_the_wrapper_decides_before_and_settles_after(service):
    calls: list[str] = []

    async def run(request):
        calls.append(request.runId)
        return _result(_passing_code_dump())

    service.run = run
    assert wrap_service_for_goals(service) is True
    assert wrap_service_for_goals(service) is False  # idempotent

    request = _request("build a small greeting app with tests")
    result = await service.run(request)
    assert result.status == "completed"
    assert calls == ["run_chat_1"]
    goal_task_id = request.input.context.get("goalTaskId")
    assert goal_task_id
    assert service.tasks.get_task(goal_task_id).status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_the_wrapper_never_breaks_the_run_on_bookkeeping_failure(service):
    class Boom:
        def get_task(self, task_id):
            raise RuntimeError("store exploded")

    async def run(request):
        return _result(_passing_code_dump())

    service.run = run
    service.tasks = Boom()
    wrap_service_for_goals(service)
    result = await service.run(_request("build a small greeting app with tests"))
    assert result.status == "completed"  # the chat turn survived
