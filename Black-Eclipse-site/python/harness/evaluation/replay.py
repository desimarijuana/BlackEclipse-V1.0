"""Trajectory replay, inspection and comparison.

Given a recorded trajectory, replay re-runs the SAME task through a chosen
invoker (same or a different model/agent version) and compares the resulting
behavior; inspect summarizes a trajectory deterministically. Nothing here needs a
second agent implementation — replay uses whichever invoker the caller supplies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .trajectory import Trajectory


def inspect(trajectory: Trajectory) -> dict[str, Any]:
    calls = trajectory.tool_calls()
    return {
        "runId": trajectory.run_id,
        "taskId": trajectory.task_id,
        "trialId": trajectory.trial_id,
        "trajectoryVersion": trajectory.trajectory_version,
        "agent": trajectory.agent,
        "model": trajectory.model,
        "gitCommit": trajectory.git_commit,
        "eventCount": len(trajectory.events),
        "toolSequence": trajectory.tool_sequence(),
        "toolCalls": [
            {"name": c["name"], "status": c["status"], "args": c["args"], "error": c.get("error")}
            for c in calls
        ],
        "modelCalls": len(trajectory.model_calls()),
        "errors": [{"type": e.type, "data": e.data} for e in trajectory.error_events()],
        "metrics": trajectory.metrics,
        "finalAnswer": trajectory.final_answer,
        "outcome": trajectory.outcome,
    }


@dataclass
class ReplayResult:
    original: dict[str, Any]
    replayed: dict[str, Any]
    differences: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"original": self.original, "replayed": self.replayed,
                "differences": self.differences}


def compare_trajectories(a: Trajectory, b: Trajectory) -> dict[str, Any]:
    """Deterministic, structured comparison of two trajectories' behavior."""
    seq_a, seq_b = a.tool_sequence(), b.tool_sequence()
    metrics_a, metrics_b = a.metrics, b.metrics
    differences: list[dict[str, Any]] = []
    if seq_a != seq_b:
        differences.append({"field": "toolSequence", "a": seq_a, "b": seq_b})
    for key in ("totalTokens", "toolCalls", "toolErrors", "cost", "latencyMs"):
        if metrics_a.get(key) != metrics_b.get(key):
            differences.append({"field": key, "a": metrics_a.get(key), "b": metrics_b.get(key)})
    if a.outcome.get("status") != b.outcome.get("status"):
        differences.append({"field": "status", "a": a.outcome.get("status"), "b": b.outcome.get("status")})
    return {"differences": differences, "identical": not differences}


async def replay(
    trajectory: Trajectory,
    invoker: Any,
    task: Any,
    *,
    environment: Optional[Any] = None,
) -> ReplayResult:
    """Re-run the same task through `invoker` and compare the outcome."""
    from .environments import build_environment  # noqa: PLC0415

    env = environment or build_environment(getattr(task, "environment", {}) or {})
    env.reset(getattr(task, "initial_state", {}) or {})
    invocation = await invoker.invoke(task, f"replay-{trajectory.trial_id}", env)
    replayed = Trajectory.from_events(
        invocation.events, run_id=invocation.run_id, task_id=task.id,
        trial_id=f"replay-{trajectory.trial_id}", task_version=task.version,
        agent=invocation.agent, model=invocation.model,
        final_answer={"output": invocation.output, "status": invocation.status},
        outcome={"status": invocation.status, "error": invocation.error},
    )
    env.teardown()
    comparison = compare_trajectories(trajectory, replayed)
    return ReplayResult(
        original=inspect(trajectory),
        replayed=inspect(replayed),
        differences=comparison["differences"],
    )


__all__ = ["ReplayResult", "compare_trajectories", "inspect", "replay"]
