"""LLM-facing task tools — the curated surface over `TaskManager`.

These tools are how a planner/agent creates and steers durable work. They are
`permission="read"` because a task is AGENT-LOCAL orchestration state, exactly
like a memory save — not an external effect. The registry's validation seam and
the run's allowlist still apply unchanged.

The tools never run a task: they create, decompose, link, block, retry, complete
or cancel it. Dispatch to the execution runtime is the scheduler's job. Every
mutation still goes through the state machine in `TaskManager`.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .goal import intake_goal
from .manager import TaskError, TaskManager
from .model import (
    CreatePlanInput,
    CreateTaskInput,
    DependencyKind,
    FailurePolicy,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from .store import TaskStore

_NO_STORE = "Task storage is unavailable in this run."


def _manager(ctx: ToolContext) -> TaskManager:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        raise TaskError("STORE_UNAVAILABLE", _NO_STORE)
    return TaskManager(TaskStore(store), publisher=_publisher(ctx))


def _publisher(ctx: ToolContext):
    bus = getattr(ctx, "bus", None)
    if bus is None:
        return None

    def publish(event_type: str, data: dict[str, Any]) -> None:
        try:
            bus.publish({"type": f"task.{event_type.lower()}", "data": data, "at": ""})
        except Exception:  # noqa: BLE001
            pass

    return publish


def _clean(value: Any) -> Any:
    """Drop `None` values the registry fills in for absent optional arguments.

    `ToolRegistry` validates arguments into a pydantic model and passes EVERY
    declared field back, so an omitted optional arrives as `None`. The task input
    contracts are strict (`extra="forbid"`, non-Optional defaults), so an explicit
    `None` for e.g. `description` would be rejected — the registry's own default
    for an absent argument must not become a value. Recurses into lists/dicts.
    """
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, dict[str, Any]]:
    return text, {"ok": True, **(data or {})}


def _err(exc: Exception) -> tuple[str, dict[str, Any]]:
    if isinstance(exc, TaskError):
        return exc.message, {"ok": False, "code": exc.code, "message": exc.message}
    return str(exc), {"ok": False, "code": "TASK_ERROR", "message": str(exc)}


def _brief(task: Any) -> str:
    mark = {
        "TODO": "○", "IN_PROGRESS": "●", "BLOCKED": "⛔", "WAITING": "…",
        "FAILED": "✗", "COMPLETED": "✓", "CANCELLED": "⊘",
    }.get(task.status.value, "·")
    extra = ""
    if task.status.value == "BLOCKED" and task.blocked_by:
        extra = f" (blocked by {', '.join(task.blocked_by[:3])})"
    if task.status.value == "WAITING" and task.waiting_reason:
        extra = f" (waiting for {task.waiting_reason.value})"
    return f"{mark} {task.id} · {task.title} · {task.status.value}{extra} · {task.progress}%"


# ── Plan tools ────────────────────────────────────────────────────────────────


async def _create_plan(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        plan = _manager(ctx).create_plan(_clean(args))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Created plan {plan.id}: {plan.name}",
               {"plan": plan.model_dump(by_alias=True)})


async def _read_plan(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        view = _manager(ctx).plan_view(str(args.get("planId") or args.get("plan_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    stats = view["stats"]
    text = (
        f"Plan {view['plan']['name']}: {stats['progress']}% · {stats['total']} tasks · "
        f"{stats['runnable']} ready · {json.dumps(stats['byStatus'])}"
    )
    return _ok(text, {"plan": view})


async def _run_plan(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        plan = _manager(ctx).start_plan(str(args.get("planId") or args.get("plan_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Plan {plan.id} is now {plan.status.value}.",
               {"plan": plan.model_dump(by_alias=True)})


# ── Task tools ────────────────────────────────────────────────────────────────


async def _create_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).create_task(_clean(args))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _read_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        view = _manager(ctx).task_view(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    text = (
        f"{view['title']} · {view['status']} · {view['progress']}% · "
        f"{len(view.get('children', []))} subtasks · {view['executionCount']} executions"
    )
    if view.get("completionFailures"):
        text += "\nNot complete: " + "; ".join(view["completionFailures"])
    return _ok(text, {"task": view})


async def _list_tasks(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        tasks = _manager(ctx).list_tasks(
            plan_id=args.get("planId") or args.get("plan_id"),
            parent_task_id=args.get("parentTaskId") or args.get("parent_task_id"),
            status=args.get("status"), limit=int(args.get("limit") or 100),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    lines = [_brief(t) for t in tasks] or ["(no tasks)"]
    return _ok("\n".join(lines), {"tasks": [t.model_dump(by_alias=True) for t in tasks]})


async def _read_task_tree(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        view = _manager(ctx).task_tree(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Task tree for {view['title']}.", {"tree": view})


async def _update_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        fields = args.get("fields") or {}
        if not isinstance(fields, dict):
            raise TaskError("INVALID_INPUT", "fields must be an object")
        task = _manager(ctx).update_task(
            str(args.get("taskId") or args.get("task_id")), dict(fields)
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _complete_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).complete_task(
            str(args.get("taskId") or args.get("task_id")),
            output_reference=args.get("outputReference"), force=bool(args.get("force")),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Completed {task.id}: {task.title}", {"task": task.model_dump(by_alias=True)})


async def _cancel_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        cancelled = _manager(ctx).cancel_task(
            str(args.get("taskId") or args.get("task_id")),
            reason=str(args.get("reason") or ""), cascade=bool(args.get("cascade", True)),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Cancelled {len(cancelled)} task(s).", {"cancelled": [t.id for t in cancelled]})


async def _delete_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        manager = _manager(ctx)
        task_id = str(args.get("taskId") or args.get("task_id"))
        manager.read_task(task_id)  # existence check (structured NOT_FOUND)
        manager._store.delete_task(task_id)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Deleted task {task_id}.", {"deleted": task_id})


async def _add_subtask(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        parent_id = str(args.get("parentTaskId") or args.get("parent_task_id"))
        payload = args.get("task") or {}
        if not isinstance(payload, dict):
            raise TaskError("INVALID_INPUT", "task must be an object")
        task = _manager(ctx).add_subtask(parent_id, _clean(payload))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _decompose_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        parent_id = str(args.get("taskId") or args.get("task_id"))
        subtasks = args.get("subtasks") or []
        if not isinstance(subtasks, list):
            raise TaskError("INVALID_INPUT", "subtasks must be an array")
        created = _manager(ctx).decompose_task(parent_id, _clean(subtasks))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Added {len(created)} subtasks to {parent_id}.",
               {"tasks": [t.model_dump(by_alias=True) for t in created]})


async def _add_dependency(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        dep = _manager(ctx).add_dependency(
            str(args.get("taskId") or args.get("task_id")),
            str(args.get("dependsOnTaskId") or args.get("depends_on_task_id")),
            kind=str(args.get("kind") or DependencyKind.REQUIRES.value),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{dep.task_id} now depends on {dep.depends_on_task_id}.",
               {"dependency": dep.model_dump(by_alias=True)})


async def _remove_dependency(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        removed = _manager(ctx).remove_dependency(
            str(args.get("taskId") or args.get("task_id")),
            str(args.get("dependsOnTaskId") or args.get("depends_on_task_id")),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Dependency removed." if removed else "No such dependency.", {"removed": removed})


async def _start_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).start_task(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _block_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).block_task(
            str(args.get("taskId") or args.get("task_id")),
            reason=str(args.get("reason") or "DEPENDENCY"),
            blocked_by=list(args.get("blockedBy") or []),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _unblock_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).unblock_task(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _retry_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).retry_task(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _resume_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).resume_task(str(args.get("taskId") or args.get("task_id")))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _escalate_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        task = _manager(ctx).escalate_task(
            str(args.get("taskId") or args.get("task_id")),
            target=str(args.get("target") or "BLOCKED"),
            error=str(args.get("error") or ""),
            error_class=args.get("errorClass") or args.get("error_class"),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(_brief(task), {"task": task.model_dump(by_alias=True)})


async def _cancel_plan(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        plan = _manager(ctx).cancel_plan(
            str(args.get("planId") or args.get("plan_id")),
            reason=str(args.get("reason") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Plan {plan.id} is {plan.status.value}.",
               {"plan": plan.model_dump(by_alias=True)})


async def _attach_artifact(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        artifact = _manager(ctx).attach_artifact(
            str(args.get("taskId") or args.get("task_id")),
            uri=str(args.get("uri") or ""), kind=str(args.get("kind") or "file"),
            digest=args.get("digest"), size_bytes=args.get("sizeBytes"),
            label=args.get("label"),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Attached {artifact.kind} artifact to {artifact.task_id}.",
               {"artifact": artifact.model_dump(by_alias=True)})


async def _set_criterion(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        manager = _manager(ctx)
        task_id = str(args.get("taskId") or args.get("task_id"))
        text = args.get("text")
        if text:
            criterion = manager.add_criterion(task_id, str(text),
                                              required=bool(args.get("required", True)))
        else:
            criterion = manager.set_criterion(
                str(args.get("criterionId") or args.get("criterion_id")),
                str(args.get("state") or "PASSED"), evidence=args.get("evidence"),
            )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Criterion {criterion.id}: {criterion.state.value}",
               {"criterion": criterion.model_dump(by_alias=True)})


async def _checkpoint_task(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        checkpoint = _manager(ctx).save_checkpoint(
            str(args.get("taskId") or args.get("task_id")),
            label=str(args.get("label") or "checkpoint"), payload=args.get("payload") or {},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Checkpoint {checkpoint.seq} saved for {checkpoint.task_id}.",
               {"checkpoint": checkpoint.model_dump(by_alias=True)})


async def _create_goal(args: dict[str, Any], ctx: ToolContext) -> Any:
    """Turn a request into a durable goal contract and start it (round 4, W8).

    The deterministic intake (`goal.intake_goal`) derives the task type,
    deliverables, acceptance and budgets from the request — or from explicit
    fields. An ambiguous request earns ONE clarifying question instead of a
    guessed contract; nothing durable is created until it is answered (or
    fields are supplied).
    """
    try:
        request = str(args.get("request") or "").strip()
        explicit = any(
            args.get(key) is not None
            for key in ("deliverables", "acceptance", "taskType", "task_type")
        )
        intake = intake_goal(
            request,
            task_type=args.get("taskType") or args.get("task_type"),
            deliverables=args.get("deliverables"),
            constraints=args.get("constraints"),
            acceptance=args.get("acceptance"),
            budgets=_clean(args.get("budgets")),
            title=args.get("title"),
        )
        if intake.ambiguous and not explicit:
            return _ok(
                "One question before this becomes a durable task: " + intake.questions[0],
                {"created": False, "questions": intake.questions,
                 "intake": intake.to_dict()},
            )
        manager = _manager(ctx)
        plan = manager.create_plan(CreatePlanInput(
            name=intake.title, objective=intake.contract.objective,
            description=intake.contract.objective, metadata={"source": "goal"},
        ))
        task_fields: dict[str, Any] = {
            "plan_id": plan.id, "title": intake.title,
            "objective": intake.contract.objective,
            "description": intake.contract.objective,
            "task_type": intake.task_type, "goal_contract": intake.contract,
        }
        budgets = intake.contract.budgets
        if budgets is not None and budgets.max_parallel_workers is not None:
            # Enforced through the scheduler's EXISTING per-agent cap.
            task_fields["metadata"] = {"maxConcurrency": int(budgets.max_parallel_workers)}
        agent = args.get("agentId") or args.get("agent_id")
        if agent:
            task_fields["assigned_agent_id"] = str(agent)
        if args.get("priority"):
            task_fields["priority"] = str(args["priority"])
        retries = args.get("maxRetries") if args.get("maxRetries") is not None else args.get("max_retries")
        if retries is not None:
            task_fields["max_retries"] = int(retries)
        task = manager.create_task(CreateTaskInput(**task_fields))
        plan = manager.start_plan(plan.id)
        text = (
            f"Goal started as a durable task: {task.id} · {intake.task_type.value} · "
            f"plan {plan.id} is {plan.status.value}. The task completes only when "
            f"its evidence passes the {intake.task_type.value} verifier."
        )
        if intake.questions:
            text += " Open question: " + intake.questions[0]
        return _ok(text, {
            "created": True, "task": task.model_dump(by_alias=True),
            "plan": plan.model_dump(by_alias=True), "intake": intake.to_dict(),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── Tool metadata ─────────────────────────────────────────────────────────────

_PRIORITIES = [p.value for p in TaskPriority]
_STATUSES = [s.value for s in TaskStatus]
_DEP_KINDS = [k.value for k in DependencyKind]
_FAILURE_POLICIES = [f.value for f in FailurePolicy]
_TASK_TYPES = [t.value for t in TaskType]

_TASK_REF = {"type": "string", "description": "A task id."}
_PLAN_REF = {"type": "string", "description": "A plan id."}
_CRITERIA = {
    "type": "array",
    "description": "Acceptance criteria the task must satisfy before it can complete.",
    "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "required": {"type": "boolean"}},
        "required": ["text"],
    },
}

_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "create_goal",
        "Start a durable goal. A deterministic intake turns the request into a "
        "contract (objective, deliverables, acceptance, task type, budgets) and "
        "runs it as a tracked task that completes ONLY when its evidence passes "
        "the task-type verifier. Use for multi-step, long-horizon or resumable "
        "work; a one-line answer does not need it.",
        {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "The user's goal in their words."},
                "title": {"type": "string"},
                "taskType": {"type": "string", "enum": _TASK_TYPES},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "acceptance": {
                    "type": "array", "items": {"type": "string"},
                    "description": "What must be proven before the goal is done.",
                },
                "budgets": {
                    "type": "object",
                    "description": "Contract caps: maxDurationMs, maxToolCalls, maxTokens.",
                },
                "agentId": {"type": "string"},
                "priority": {"type": "string", "enum": _PRIORITIES},
                "maxRetries": {"type": "integer"},
            },
            "required": ["request"],
        },
    ),
    (
        "create_plan",
        "Create a durable plan (a named objective that will contain tasks). Use this "
        "to start multi-step work you intend to track and run.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "description": {"type": "string"},
                "objective": {"type": "string"},
                "priority": {"type": "string", "enum": _PRIORITIES},
                "agentId": {"type": "string"},
            },
            "required": ["name"],
        },
    ),
    (
        "read_plan",
        "Read a plan with its full task tree, per-status counts and progress.",
        {"type": "object", "properties": {"planId": _PLAN_REF}, "required": ["planId"]},
    ),
    (
        "run_plan",
        "Start executing a plan: mark it RUNNING so runnable tasks are dispatched.",
        {"type": "object", "properties": {"planId": _PLAN_REF}, "required": ["planId"]},
    ),
    (
        "create_task",
        "Create a durable task inside a plan or under a parent task. Supports nested "
        "subtasks, dependencies (by id), acceptance criteria and priority.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "description": {"type": "string"},
                "objective": {"type": "string"}, "planId": _PLAN_REF,
                "parentTaskId": _TASK_REF,
                "priority": {"type": "string", "enum": _PRIORITIES},
                "assignedAgentId": {"type": "string"},
                "dependencies": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Task ids that must COMPLETE before this one runs.",
                },
                "acceptanceCriteria": _CRITERIA,
                "required": {"type": "boolean"},
                "failurePolicy": {"type": "string", "enum": _FAILURE_POLICIES},
                "weight": {"type": "number"},
                "maxRetries": {"type": "integer"},
            },
            "required": ["title"],
        },
    ),
    (
        "read_task",
        "Read one task: status, progress, criteria, dependencies, executions, "
        "artifacts, children and any reasons it cannot complete.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "list_tasks",
        "List tasks, optionally filtered by plan, parent or status.",
        {
            "type": "object",
            "properties": {
                "planId": _PLAN_REF, "parentTaskId": _TASK_REF,
                "status": {"type": "string", "enum": _STATUSES},
                "limit": {"type": "integer"},
            },
        },
    ),
    (
        "read_task_tree",
        "Read the nested subtree rooted at a task.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "update_task",
        "Update a task's editable fields (title, description, objective, priority, "
        "progress, deadline, metadata, assignedAgentId). Status changes go through "
        "the state machine; use the dedicated transition tools for those.",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF,
                "fields": {"type": "object", "description": "Field to value map."},
            },
            "required": ["taskId", "fields"],
        },
    ),
    (
        "complete_task",
        "Complete a task. The completion contract (required dependencies, required "
        "subtasks, required acceptance criteria, required outputs) is verified first; "
        "a task is not completed just because work stopped.",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF, "outputReference": {"type": "string"},
                "force": {"type": "boolean",
                          "description": "Override a failed check (recorded as an override)."},
            },
            "required": ["taskId"],
        },
    ),
    (
        "cancel_task",
        "Cancel a task and, by default, its non-terminal subtasks.",
        {
            "type": "object",
            "properties": {"taskId": _TASK_REF, "reason": {"type": "string"},
                           "cascade": {"type": "boolean"}},
            "required": ["taskId"],
        },
    ),
    (
        "delete_task",
        "Delete a task and its subtasks. Prefer cancel unless you truly want it gone.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "add_subtask",
        "Add one subtask under a parent task.",
        {
            "type": "object",
            "properties": {"parentTaskId": _TASK_REF,
                           "task": {"type": "object", "description": "The subtask definition."}},
            "required": ["parentTaskId", "task"],
        },
    ),
    (
        "decompose_task",
        "Replace a task's work with several subtasks in one call.",
        {
            "type": "object",
            "properties": {"taskId": _TASK_REF,
                           "subtasks": {"type": "array", "items": {"type": "object"}}},
            "required": ["taskId", "subtasks"],
        },
    ),
    (
        "add_dependency",
        "Make one task depend on another. A cycle is rejected.",
        {
            "type": "object",
            "properties": {"taskId": _TASK_REF, "dependsOnTaskId": _TASK_REF,
                           "kind": {"type": "string", "enum": _DEP_KINDS}},
            "required": ["taskId", "dependsOnTaskId"],
        },
    ),
    (
        "remove_dependency",
        "Remove a dependency edge between two tasks.",
        {
            "type": "object",
            "properties": {"taskId": _TASK_REF, "dependsOnTaskId": _TASK_REF},
            "required": ["taskId", "dependsOnTaskId"],
        },
    ),
    (
        "start_task",
        "Mark a task IN_PROGRESS (manual start). The scheduler runs claimed tasks.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "block_task",
        "Mark a task BLOCKED by a prerequisite (DEPENDENCY, RESOURCE, PERMISSION, PARENT).",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF,
                "reason": {"type": "string",
                           "enum": ["DEPENDENCY", "RESOURCE", "PERMISSION", "PARENT"]},
                "blockedBy": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["taskId"],
        },
    ),
    (
        "unblock_task",
        "Clear a BLOCKED task back to TODO.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "retry_task",
        "Move a failed/blocked/waiting task back to TODO for another attempt.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "resume_task",
        "Resume a task parked for a human (ASKING_USER) or an external event "
        "(WAITING/BLOCKED) back to TODO once the answer/event has arrived.",
        {"type": "object", "properties": {"taskId": _TASK_REF}, "required": ["taskId"]},
    ),
    (
        "escalate_task",
        "Escalate a task to BLOCKED or ASKING_USER (non-terminal, resumable) instead "
        "of failing it — for a dead-end resource or a decision only a human can make.",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF,
                "target": {"type": "string", "enum": ["BLOCKED", "ASKING_USER"]},
                "error": {"type": "string"}, "errorClass": {"type": "string"},
            },
            "required": ["taskId"],
        },
    ),
    (
        "cancel_plan",
        "Cancel a whole plan and every non-terminal task inside it.",
        {
            "type": "object",
            "properties": {"planId": _PLAN_REF, "reason": {"type": "string"}},
            "required": ["planId"],
        },
    ),
    (
        "attach_task_artifact",
        "Attach a reference to a real artifact (path, digest, asset id or URL). "
        "Never the bytes themselves.",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF, "uri": {"type": "string"}, "kind": {"type": "string"},
                "label": {"type": "string"}, "digest": {"type": "string"},
                "sizeBytes": {"type": "integer"},
            },
            "required": ["taskId", "uri"],
        },
    ),
    (
        "set_task_criterion",
        "Add an acceptance criterion (pass `text`) or mark one PASSED/FAILED "
        "(pass `criterionId` and `state`).",
        {
            "type": "object",
            "properties": {
                "taskId": _TASK_REF, "text": {"type": "string"},
                "required": {"type": "boolean"}, "criterionId": {"type": "string"},
                "state": {"type": "string", "enum": ["PENDING", "PASSED", "FAILED"]},
                "evidence": {"type": "string"},
            },
        },
    ),
    (
        "checkpoint_task",
        "Record a durable resume boundary for a long-running task.",
        {
            "type": "object",
            "properties": {"taskId": _TASK_REF, "label": {"type": "string"},
                           "payload": {"type": "object"}},
            "required": ["taskId"],
        },
    ),
]

_HANDLERS = {
    "create_goal": _create_goal,
    "create_plan": _create_plan,
    "read_plan": _read_plan,
    "run_plan": _run_plan,
    "create_task": _create_task,
    "read_task": _read_task,
    "list_tasks": _list_tasks,
    "read_task_tree": _read_task_tree,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "cancel_task": _cancel_task,
    "delete_task": _delete_task,
    "add_subtask": _add_subtask,
    "decompose_task": _decompose_task,
    "add_dependency": _add_dependency,
    "remove_dependency": _remove_dependency,
    "start_task": _start_task,
    "block_task": _block_task,
    "unblock_task": _unblock_task,
    "retry_task": _retry_task,
    "resume_task": _resume_task,
    "escalate_task": _escalate_task,
    "cancel_plan": _cancel_plan,
    "attach_task_artifact": _attach_artifact,
    "set_task_criterion": _set_criterion,
    "checkpoint_task": _checkpoint_task,
}

#: The names of the registered task tools, in registration order.
TASK_TOOLS: tuple[str, ...] = tuple(name for name, _, _ in _DEFS)


def register_task_tools(registry: ToolRegistry) -> list[str]:
    """Register the task tools on the shared registry. Returns the names."""
    registered: list[str] = []
    for name, description, schema in _DEFS:
        if registry.get(name) is not None:
            continue
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_HANDLERS[name], permission="read",  # agent-local state, like memory
            risk="low", timeout_ms=15_000,
        ))
        registered.append(name)
    return registered


__all__ = ["TASK_TOOLS", "register_task_tools"]
