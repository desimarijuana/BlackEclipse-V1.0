"""Task / Plan route group (§36).

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — this module never imports `main`.

EVERY route carries `require_operator` — reads AND mutations — exactly as the
jobs and MCP route groups were hardened to do. A directly reachable runtime must
not expose task control to an unauthenticated caller.

The routes are a thin shell over `TaskManager`; they never mutate state
themselves, so the state machine and completion contract apply to HTTP callers
exactly as they do to the agent tools.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..tasks.manager import TaskError, TaskManager
from ..tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    DependencyKind,
    TaskPriority,
)

router = APIRouter(tags=["tasks"])


def _manager() -> TaskManager:
    manager = getattr(service, "tasks", None)
    if manager is None:
        # Lazy construction (a route may be hit before the boot wiring ran).
        from ..tasks import install_task_layer  # noqa: PLC0415

        install_task_layer(service)
        manager = getattr(service, "tasks", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Task runtime unavailable")
    return manager


def _raise(exc: Exception) -> None:
    if isinstance(exc, TaskError):
        code = 404 if exc.code in ("TASK_NOT_FOUND", "PLAN_NOT_FOUND") else 400
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


# ── Request bodies ────────────────────────────────────────────────────────────


class CreatePlanBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    objective: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    agentId: str = "eclipse-agent"  # noqa: N815
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateTaskBody(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    objective: str = ""
    planId: Optional[str] = None  # noqa: N815
    parentTaskId: Optional[str] = None  # noqa: N815
    priority: TaskPriority = TaskPriority.NORMAL
    assignedAgentId: Optional[str] = None  # noqa: N815
    dependencies: list[str] = Field(default_factory=list)
    acceptanceCriteria: list[dict[str, Any]] = Field(default_factory=list)  # noqa: N815
    required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateTaskBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class DependencyBody(BaseModel):
    dependsOnTaskId: str  # noqa: N815
    kind: DependencyKind = DependencyKind.REQUIRES


class CompleteBody(BaseModel):
    outputReference: Optional[str] = None  # noqa: N815
    force: bool = False


class CancelBody(BaseModel):
    reason: str = ""
    cascade: bool = True


class BlockBody(BaseModel):
    reason: str = "DEPENDENCY"
    blockedBy: list[str] = Field(default_factory=list)  # noqa: N815


class PlanCancelBody(BaseModel):
    reason: str = ""


class EscalateBody(BaseModel):
    target: str = "BLOCKED"
    error: str = ""
    errorClass: Optional[str] = None  # noqa: N815


class CriterionBody(BaseModel):
    text: str = Field(..., min_length=1)
    required: bool = True


class CriterionStateBody(BaseModel):
    state: str
    evidence: Optional[str] = None


class ArtifactBody(BaseModel):
    uri: str
    kind: str = "file"
    label: Optional[str] = None
    digest: Optional[str] = None
    sizeBytes: Optional[int] = None  # noqa: N815


class CheckpointBody(BaseModel):
    label: str = "checkpoint"
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Plans ─────────────────────────────────────────────────────────────────────


@router.get("/plans")
def list_plans(
    limit: int = 100, status: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    plans = _manager().list_plans(limit=limit, status=status)
    return {"success": True, "plans": [p.model_dump(by_alias=True) for p in plans]}


@router.post("/plans")
def create_plan(
    body: CreatePlanBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        plan = _manager().create_plan(CreatePlanInput(
            name=body.name, description=body.description, objective=body.objective,
            priority=body.priority, agent_id=body.agentId, metadata=body.metadata,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "plan": plan.model_dump(by_alias=True)}


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        view = _manager().plan_view(plan_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "plan": view}


@router.get("/plans/{plan_id}/tasks")
def plan_tasks(plan_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        manager = _manager()
        manager.get_plan(plan_id)
        tasks = manager.list_tasks(plan_id=plan_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "tasks": [t.model_dump(by_alias=True) for t in tasks]}


@router.post("/plans/{plan_id}/start")
def start_plan(plan_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        plan = _manager().start_plan(plan_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "plan": plan.model_dump(by_alias=True)}


@router.post("/plans/{plan_id}/cancel")
def cancel_plan(
    plan_id: str, body: PlanCancelBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        plan = _manager().cancel_plan(plan_id, reason=body.reason)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "plan": plan.model_dump(by_alias=True)}


# ── Tasks ─────────────────────────────────────────────────────────────────────


@router.get("/tasks")
def list_tasks(
    planId: Optional[str] = None,  # noqa: N803
    parentTaskId: Optional[str] = None,  # noqa: N803
    status: Optional[str] = None,
    limit: int = 200,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    tasks = _manager().list_tasks(
        plan_id=planId, parent_task_id=parentTaskId, status=status, limit=limit
    )
    return {"success": True, "tasks": [t.model_dump(by_alias=True) for t in tasks]}


@router.post("/tasks")
def create_task(body: CreateTaskBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().create_task(CreateTaskInput(
            title=body.title, description=body.description, objective=body.objective,
            plan_id=body.planId, parent_task_id=body.parentTaskId, priority=body.priority,
            assigned_agent_id=body.assignedAgentId, dependencies=body.dependencies,
            acceptance_criteria=body.acceptanceCriteria, required=body.required,
            metadata=body.metadata,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        view = _manager().task_view(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": view}


@router.get("/tasks/{task_id}/tree")
def task_tree(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        view = _manager().task_tree(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "tree": view}


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        manager = _manager()
        manager.get_task(task_id)
        events = manager._store.list_task_events(task_id)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "events": [e.model_dump(by_alias=True) for e in events]}


@router.get("/tasks/{task_id}/dependencies")
def task_dependencies(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        manager = _manager()
        manager.get_task(task_id)
        dependencies = manager.get_dependencies(task_id)
        dependents = manager.get_dependents(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {
        "success": True,
        "dependencies": [d.model_dump(by_alias=True) for d in dependencies],
        "dependents": [d.model_dump(by_alias=True) for d in dependents],
    }


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str, body: UpdateTaskBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        task = _manager().update_task(task_id, dict(body.fields))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        manager = _manager()
        manager.get_task(task_id)
        manager._store.delete_task(task_id)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "deleted": task_id}


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().start_task(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str, body: CompleteBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        task = _manager().complete_task(
            task_id, output_reference=body.outputReference, force=body.force
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str, body: CancelBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        cancelled = _manager().cancel_task(task_id, reason=body.reason, cascade=body.cascade)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "cancelled": [t.id for t in cancelled]}


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().retry_task(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().resume_task(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/escalate")
def escalate_task(
    task_id: str, body: EscalateBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        task = _manager().escalate_task(
            task_id, target=body.target, error=body.error, error_class=body.errorClass,
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().reopen_task(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/block")
def block_task(
    task_id: str, body: BlockBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        task = _manager().block_task(task_id, reason=body.reason, blocked_by=body.blockedBy)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/unblock")
def unblock_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        task = _manager().unblock_task(task_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "task": task.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/dependencies")
def add_dependency(
    task_id: str, body: DependencyBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        dep = _manager().add_dependency(task_id, body.dependsOnTaskId, kind=body.kind)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "dependency": dep.model_dump(by_alias=True)}


@router.delete("/tasks/{task_id}/dependencies/{depends_on_id}")
def remove_dependency(
    task_id: str, depends_on_id: str, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        removed = _manager().remove_dependency(task_id, depends_on_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "removed": removed}


@router.post("/tasks/{task_id}/criteria")
def add_criterion(
    task_id: str, body: CriterionBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        criterion = _manager().add_criterion(task_id, body.text, required=body.required)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "criterion": criterion.model_dump(by_alias=True)}


@router.patch("/criteria/{criterion_id}")
def set_criterion(
    criterion_id: str, body: CriterionStateBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        criterion = _manager().set_criterion(
            criterion_id, body.state, evidence=body.evidence
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "criterion": criterion.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/artifacts")
def add_artifact(
    task_id: str, body: ArtifactBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        artifact = _manager().attach_artifact(
            task_id, uri=body.uri, kind=body.kind, label=body.label,
            digest=body.digest, size_bytes=body.sizeBytes,
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "artifact": artifact.model_dump(by_alias=True)}


@router.post("/tasks/{task_id}/checkpoints")
def add_checkpoint(
    task_id: str, body: CheckpointBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        checkpoint = _manager().save_checkpoint(task_id, label=body.label, payload=body.payload)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "checkpoint": checkpoint.model_dump(by_alias=True)}


@router.get("/tasks/{task_id}/checkpoints")
def list_checkpoints(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    checkpoints = _manager().list_checkpoints(task_id)
    return {"success": True, "checkpoints": [c.model_dump(by_alias=True) for c in checkpoints]}


@router.post("/tasks/{task_id}/checkpoints/restore")
def restore_checkpoint(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _manager().restore_checkpoint(task_id, resume=True)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


__all__ = ["router"]
