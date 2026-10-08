"""The task context envelope — what the execution engine gives a task.

A task is executed from DURABLE STATE, never from a chat transcript. This module
builds a bounded `TaskContext` from the store (the task, its inputs, its
dependencies' outputs, its artifacts, and its previous attempts) and renders it
into the run's query. The context is DATA handed to the agent; it is never a
prompt that grants anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .manager import TaskManager
from .model import Task, TaskStatus

#: Caps keep a context from becoming an unbounded memory dump.
MAX_CONTEXT_ARTIFACTS = 20
MAX_CONTEXT_DEPENDENCIES = 50
MAX_CONTEXT_ATTEMPTS = 10
MAX_CONTEXT_CHARS = 12_000


@dataclass
class TaskContext:
    """Everything a worker needs to execute one task, from durable state."""

    task_id: str
    plan_id: Optional[str]
    parent_task_id: Optional[str]
    title: str
    objective: str
    instructions: str
    priority: str
    inputs: dict[str, Any] = field(default_factory=dict)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    relevant_memory: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    previous_attempts: list[dict[str, Any]] = field(default_factory=list)
    assigned_agent: Optional[str] = None
    permissions: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "planId": self.plan_id,
            "parentTaskId": self.parent_task_id,
            "title": self.title,
            "objective": self.objective,
            "instructions": self.instructions,
            "priority": self.priority,
            "inputs": self.inputs,
            "dependencies": self.dependencies,
            "relevantMemory": self.relevant_memory,
            "artifacts": self.artifacts,
            "previousAttempts": self.previous_attempts,
            "assignedAgent": self.assigned_agent,
            "permissions": self.permissions,
            "constraints": self.constraints,
            "acceptanceCriteria": self.acceptance_criteria,
            "metadata": self.metadata,
        }


def build_task_context(
    manager: TaskManager, task: Task, *,
    permissions: Optional[dict[str, Any]] = None,
    constraints: Optional[dict[str, Any]] = None,
    relevant_memory: Optional[list[str]] = None,
) -> TaskContext:
    """Assemble the context for one task from the durable task graph."""
    dependencies: list[dict[str, Any]] = []
    for dep in manager.get_dependencies(task.id)[:MAX_CONTEXT_DEPENDENCIES]:
        prereq = manager._store.get_task(dep.depends_on_task_id)  # noqa: SLF001
        if prereq is None:
            continue
        dependencies.append({
            "taskId": prereq.id,
            "title": prereq.title,
            "kind": dep.kind.value,
            "status": prereq.status.value,
            "outputReference": prereq.output_reference,
        })
    artifacts = [
        {"kind": a.kind, "uri": a.uri, "digest": a.digest, "label": a.label}
        for a in manager.list_artifacts(task.id)[:MAX_CONTEXT_ARTIFACTS]
    ]
    attempts = [
        {
            "attempt": e.attempt,
            "status": e.status.value,
            "error": e.error,
            "errorClass": e.error_class,
            "runId": e.run_id,
        }
        for e in manager.list_executions(task.id)[-MAX_CONTEXT_ATTEMPTS:]
    ]
    criteria = [c.text for c in manager.list_criteria(task.id) if c.required]
    return TaskContext(
        task_id=task.id,
        plan_id=task.plan_id,
        parent_task_id=task.parent_task_id,
        title=task.title,
        objective=task.objective or task.title,
        instructions=task.description,
        priority=task.priority.value,
        inputs=dict(task.metadata.get("inputs") or {}),
        dependencies=dependencies,
        relevant_memory=list(relevant_memory or [])[:20],
        artifacts=artifacts,
        previous_attempts=attempts,
        assigned_agent=task.assigned_agent_id,
        permissions=dict(permissions or {}),
        constraints=dict(constraints or {}),
        acceptance_criteria=criteria,
        metadata=dict(task.metadata),
    )


def render_task_query(context: TaskContext) -> str:
    """Render a context into the run query the agent executes.

    Deterministic and bounded: the same task always produces the same query. The
    acceptance criteria are labelled as REQUIREMENTS the run must satisfy, and a
    previous failed attempt is quoted so a retry does not repeat it blindly.
    """
    lines: list[str] = []
    lines.append(context.objective or context.title)
    if context.instructions:
        lines.append("")
        lines.append(f"Instructions: {context.instructions}")
    if context.acceptance_criteria:
        lines.append("")
        lines.append("You must satisfy all of these before the task is complete:")
        lines.extend(f"- {c}" for c in context.acceptance_criteria)
    if context.dependencies:
        done = [d for d in context.dependencies if d["status"] == TaskStatus.COMPLETED.value]
        if done:
            lines.append("")
            lines.append("Completed prerequisites you may rely on:")
            lines.extend(
                f"- {d['title']} (output: {d['outputReference'] or 'n/a'})" for d in done
            )
    if context.previous_attempts:
        last = context.previous_attempts[-1]
        if last.get("error"):
            lines.append("")
            lines.append(
                f"A previous attempt failed ({last.get('errorClass') or 'error'}): "
                f"{last['error']}. Address the cause rather than repeating it."
            )
    if context.artifacts:
        lines.append("")
        lines.append("Artifacts already attached:")
        lines.extend(f"- {a.get('label') or a.get('kind')}: {a.get('uri')}" for a in context.artifacts)
    rendered = "\n".join(lines).strip()
    return rendered[:MAX_CONTEXT_CHARS]


__all__ = [
    "MAX_CONTEXT_CHARS",
    "TaskContext",
    "build_task_context",
    "render_task_query",
]
