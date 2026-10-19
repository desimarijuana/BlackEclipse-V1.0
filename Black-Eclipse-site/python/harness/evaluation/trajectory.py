"""Trajectory capture and the normalized, versioned trajectory format.

A trajectory is the complete, replayable record of one trial: every event the REAL
runtime emitted, plus the derived metrics a grader needs (tokens, latency, cost,
tool calls, retries, state changes, final answer). It is captured by subscribing
to the runtime's own event bus — this module NEVER re-implements the agent loop.

The format is versioned (:data:`TRAJECTORY_FORMAT_VERSION`); an old trajectory
keeps its original meaning when the shape changes.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import TRAJECTORY_FORMAT_VERSION
from .provenance import AGENT_VERSION

# The events that carry a tool invocation, in order.
_TOOL_REQUEST_EVENTS = ("tool.requested",)
_TOOL_DONE_EVENTS = ("tool.completed", "tool.failed", "tool.truncated")
_MODEL_EVENTS = ("model.requested", "model.completed")
_MODEL_REQUEST_EVENTS = ("model.request.completed", "model.request.failed")


def _git_commit() -> Optional[str]:
    try:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:  # noqa: BLE001 - git is best-effort provenance
        return None
    return None


@dataclass
class TrajectoryEvent:
    index: int
    type: str
    at: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "type": self.type, "at": self.at, "data": self.data}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TrajectoryEvent":
        return cls(
            index=int(raw.get("index", 0)),
            type=str(raw.get("type", "")),
            at=str(raw.get("at", "")),
            data=dict(raw.get("data") or {}),
        )


def normalize_events(raw_events: list[dict[str, Any]]) -> list[TrajectoryEvent]:
    """Normalize runtime events into the stable trajectory event list.

    Accepts the runtime's per-run event dicts (``type``/``at``/``data``) and the
    canonical envelope dicts (``type``/``timestamp``/``payload``) so a capture
    works whether it read the legacy bus or the canonical store.
    """
    events: list[TrajectoryEvent] = []
    for index, raw in enumerate(raw_events):
        etype = raw.get("type") or raw.get("event") or ""
        at = raw.get("at") or raw.get("timestamp") or raw.get("time") or ""
        data = raw.get("data")
        if data is None:
            data = raw.get("payload")
        events.append(
            TrajectoryEvent(index=index, type=str(etype), at=str(at), data=dict(data or {}))
        )
    return events


@dataclass
class Trajectory:
    run_id: str
    task_id: str
    trial_id: str
    events: list[TrajectoryEvent] = field(default_factory=list)
    task_version: int = 1
    agent: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    final_answer: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    agent_version: Optional[str] = None
    git_commit: Optional[str] = None
    trajectory_version: str = TRAJECTORY_FORMAT_VERSION

    # -- construction ------------------------------------------------------
    @classmethod
    def from_events(
        cls,
        events: list[dict[str, Any]] | list[TrajectoryEvent],
        *,
        run_id: str,
        task_id: str,
        trial_id: str,
        task_version: int = 1,
        agent: Optional[dict[str, Any]] = None,
        model: Optional[dict[str, Any]] = None,
        final_answer: Optional[dict[str, Any]] = None,
        outcome: Optional[dict[str, Any]] = None,
        state_before: Optional[dict[str, Any]] = None,
        state_after: Optional[dict[str, Any]] = None,
    ) -> "Trajectory":
        normalized = (
            [e if isinstance(e, TrajectoryEvent) else TrajectoryEvent.from_dict(e) for e in events]
        )
        trajectory = cls(
            run_id=run_id,
            task_id=task_id,
            trial_id=trial_id,
            task_version=task_version,
            events=normalized,
            agent=dict(agent or {}),
            model=dict(model or {}),
            final_answer=dict(final_answer or {}),
            outcome=dict(outcome or {}),
            agent_version=AGENT_VERSION,
            git_commit=_git_commit(),
        )
        trajectory.metrics = trajectory.derive_metrics(state_before, state_after)
        return trajectory

    # -- derived views -----------------------------------------------------
    @property
    def types(self) -> list[str]:
        return [e.type for e in self.events]

    def by_type(self, *types: str) -> list[TrajectoryEvent]:
        wanted = set(types)
        return [e for e in self.events if e.type in wanted]

    def tool_calls(self) -> list[dict[str, Any]]:
        """The ordered tool invocations: name, args, result summary, outcome."""
        calls: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for event in self.events:
            if event.type == "tool.requested":
                data = event.data
                call = {
                    "name": data.get("name"),
                    "args": data.get("args") or {},
                    "toolCallId": data.get("toolCallId"),
                    "step": data.get("step"),
                    "at": event.at,
                    "status": "requested",
                    "error": None,
                }
                calls.append(call)
                if call["toolCallId"]:
                    by_id[call["toolCallId"]] = call
            elif event.type in _TOOL_DONE_EVENTS:
                data = event.data
                target = by_id.get(data.get("toolCallId"))
                if target is None and calls:
                    target = calls[-1]
                if target is not None:
                    target["status"] = event.type.split(".")[-1]
                    target["durationMs"] = data.get("durationMs")
                    target["truncated"] = data.get("truncated")
                    if event.type == "tool.failed":
                        target["error"] = {
                            "code": data.get("code"),
                            "message": data.get("message") or data.get("reason"),
                        }
        return calls

    def tool_sequence(self) -> list[str]:
        return [c["name"] for c in self.tool_calls() if c.get("name")]

    def model_calls(self) -> list[dict[str, Any]]:
        return [
            {"type": e.type, "at": e.at, **e.data}
            for e in self.events
            if e.type in _MODEL_EVENTS
        ]

    def retry_count(self) -> int:
        return sum(1 for e in self.events if "retry" in e.type)

    def error_events(self) -> list[TrajectoryEvent]:
        return [e for e in self.events if "error" in e.type or e.type.endswith(".failed")]

    def state_changes(self) -> list[dict[str, Any]]:
        return [{"type": e.type, "data": e.data} for e in self.events
                if e.type in ("state.changed", "checkpoint", "resume", "recovery")]

    def derive_metrics(
        self,
        state_before: Optional[dict[str, Any]] = None,
        state_after: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        prompt = completion = total = 0
        cost = 0.0
        cost_seen = False
        latencies: list[float] = []
        for event in self.events:
            if event.type == "model.completed":
                prompt += int(event.data.get("promptTokens") or 0)
                completion += int(event.data.get("completionTokens") or 0)
                total += int(event.data.get("totalTokens") or 0)
            if event.type in _MODEL_REQUEST_EVENTS and event.data.get("latencyMs") is not None:
                latencies.append(float(event.data["latencyMs"]))
            if event.data.get("cost") is not None:
                cost += float(event.data["cost"])
                cost_seen = True
        tool_calls = self.tool_calls()
        metrics: dict[str, Any] = {
            "events": len(self.events),
            "modelSteps": len(self.model_calls()) // 2 or len(self.model_calls()),
            "toolCalls": len(tool_calls),
            "toolErrors": sum(1 for c in tool_calls if c["status"] == "failed"),
            "retries": self.retry_count(),
            "promptTokens": prompt,
            "completionTokens": completion,
            "totalTokens": total,
            "cost": round(cost, 6) if cost_seen else None,
            "latencyMs": round(sum(latencies), 3) if latencies else None,
        }
        if state_before is not None and state_after is not None:
            metrics["stateChanged"] = state_before != state_after
        return metrics

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectoryVersion": self.trajectory_version,
            "runId": self.run_id,
            "taskId": self.task_id,
            "taskVersion": self.task_version,
            "trialId": self.trial_id,
            "agentVersion": self.agent_version,
            "gitCommit": self.git_commit,
            "agent": self.agent,
            "model": self.model,
            "events": [e.to_dict() for e in self.events],
            "finalAnswer": self.final_answer,
            "outcome": self.outcome,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Trajectory":
        version = str(raw.get("trajectoryVersion") or raw.get("trajectory_version") or "1")
        if version != TRAJECTORY_FORMAT_VERSION:
            # Historical trajectories keep their original version string; the
            # normalizer still reads the shared fields, and the version is kept
            # so a reader can tell which shape produced the record.
            pass
        return cls(
            run_id=str(raw.get("runId") or raw.get("run_id") or ""),
            task_id=str(raw.get("taskId") or raw.get("task_id") or ""),
            trial_id=str(raw.get("trialId") or raw.get("trial_id") or ""),
            task_version=int(raw.get("taskVersion") or raw.get("task_version") or 1),
            trajectory_version=version,
            agent_version=raw.get("agentVersion") or raw.get("agent_version"),
            git_commit=raw.get("gitCommit") or raw.get("git_commit"),
            agent=dict(raw.get("agent") or {}),
            model=dict(raw.get("model") or {}),
            events=[TrajectoryEvent.from_dict(e) for e in (raw.get("events") or [])],
            final_answer=dict(raw.get("finalAnswer") or raw.get("final_answer") or {}),
            outcome=dict(raw.get("outcome") or {}),
            metrics=dict(raw.get("metrics") or {}),
        )

    def write(self, directory: str) -> str:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{self.trial_id or self.run_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
        return path


def capture_from_store(
    store: Any,
    run_id: str,
    *,
    task_id: str,
    trial_id: str,
    task_version: int = 1,
    agent: Optional[dict[str, Any]] = None,
    model: Optional[dict[str, Any]] = None,
) -> Trajectory:
    """Build a trajectory from the runtime's persisted events for a run."""
    raw = store.list_events(run_id) if hasattr(store, "list_events") else []
    run = store.get_run(run_id) if hasattr(store, "get_run") else None
    run = run or {}
    final_answer = {
        "output": run.get("output"),
        "status": run.get("status"),
    }
    outcome = {
        "status": run.get("status"),
        "error": run.get("error"),
    }
    model_info = dict(model or {})
    if run.get("model"):
        model_info.setdefault("model", run.get("model"))
    if run.get("provider"):
        model_info.setdefault("provider", run.get("provider"))
    return Trajectory.from_events(
        raw,
        run_id=run_id,
        task_id=task_id,
        trial_id=trial_id,
        task_version=task_version,
        agent=agent or {"id": run.get("agentId")},
        model=model_info,
        final_answer=final_answer,
        outcome=outcome,
    )


__all__ = [
    "Trajectory",
    "TrajectoryEvent",
    "capture_from_store",
    "normalize_events",
]
