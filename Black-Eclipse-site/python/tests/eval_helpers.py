"""Shared helpers for the evaluation test suite."""

from __future__ import annotations

from typing import Any, Optional

from harness.evaluation.graders import GradeContext
from harness.evaluation.tasks import EvaluationTask
from harness.evaluation.trajectory import Trajectory


def make_task(**overrides: Any) -> EvaluationTask:
    data: dict[str, Any] = {
        "id": "test.task.001",
        "version": 1,
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "do the thing"},
    }
    data.update(overrides)
    return EvaluationTask.from_dict(data)


def make_trajectory(
    *,
    tool_events: Optional[list[dict[str, Any]]] = None,
    output: str = "",
    status: str = "completed",
    metrics: Optional[dict[str, Any]] = None,
    run_id: str = "run_test",
) -> Trajectory:
    events: list[dict[str, Any]] = [
        {"type": "run.created", "at": "2026-01-01T00:00:00Z", "data": {}},
        {"type": "run.started", "at": "2026-01-01T00:00:00Z", "data": {}},
    ]
    for event in tool_events or []:
        events.append(event)
    events.append({"type": "run.completed", "at": "2026-01-01T00:00:01Z",
                   "data": {"status": status}})
    trajectory = Trajectory.from_events(
        events, run_id=run_id, task_id="test.task.001", trial_id="trial_0",
        final_answer={"output": output, "status": status},
        outcome={"status": status},
    )
    if metrics:
        trajectory.metrics.update(metrics)
    return trajectory


def tool_call(name: str, args: dict[str, Any], *, call_id: str = "c1",
              status: str = "completed", code: Optional[str] = None) -> list[dict[str, Any]]:
    events = [{"type": "tool.requested", "at": "2026-01-01T00:00:00Z",
               "data": {"name": name, "toolCallId": call_id, "args": args}}]
    if status == "completed":
        events.append({"type": "tool.completed", "at": "2026-01-01T00:00:01Z",
                       "data": {"name": name, "toolCallId": call_id, "durationMs": 1}})
    elif status == "failed":
        events.append({"type": "tool.failed", "at": "2026-01-01T00:00:01Z",
                       "data": {"name": name, "toolCallId": call_id, "code": code or "TOOL_ERROR"}})
    return events


def make_ctx(
    task: EvaluationTask,
    trajectory: Trajectory,
    *,
    output: str = "",
    env_state: Optional[dict[str, Any]] = None,
    environment: Any = None,
) -> GradeContext:
    return GradeContext(
        task=task,
        trajectory=trajectory,
        final_output=output,
        environment=environment,
        env_state=env_state or {},
        tool_calls=trajectory.tool_calls(),
        outcome=trajectory.outcome,
    )
