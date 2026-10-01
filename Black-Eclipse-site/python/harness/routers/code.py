"""Code-task lifecycle + external-action approvals routes (Phase 5).

A code task IS a run whose agent id is `code-agent`; the lifecycle is the ONE
run lineage, never a second table. Every MUTATING route (and any read that
touches a workspace) carries `require_operator` — transport/token proof only,
never a request-body flag — mirroring the MCP router. Shared state comes from
`harness.deps`; this module never imports `main`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..code.tasks import DEFAULT_AUTONOMY, TaskStore
from ..deps import require_operator, service
from ..schemas import RunInput, RunRequest
from ..schemas import ModelSettings as _ModelSettings

router = APIRouter(tags=["code"])

_AUTONOMY_PROFILES = ("plan_only", "edit_verify", "approve_external")


class CreateTaskRequest(BaseModel):
    """Create a code task. `autonomy` defaults to plan_only (safest)."""

    query: str = Field(min_length=1, max_length=4000)
    autonomy: Optional[str] = None
    workspaceId: Optional[str] = None  # noqa: N815
    runId: Optional[str] = None  # noqa: N815
    callbackBaseUrl: str  # noqa: N815
    callbackToken: Optional[str] = None  # noqa: N815
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815


class DecideApprovalRequest(BaseModel):
    approve: bool
    reason: str = Field("", max_length=400)


class RequestActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    message: str = Field("", max_length=500)
    baseRef: str = Field("", max_length=200)  # noqa: N815
    headRef: str = Field("", max_length=200)  # noqa: N815


def _resolve_autonomy(raw: Optional[str]) -> str:
    value = (raw or DEFAULT_AUTONOMY).strip()
    if value not in _AUTONOMY_PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown autonomy profile {raw!r}")
    return value


def _tasks() -> TaskStore:
    return service.code_tasks()


# ── Task lifecycle ──────────────────────────────────────────────────────────


@router.post("/code/tasks")
async def create_task(body: CreateTaskRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Create and run a code task. The autonomy defaults to plan_only."""
    autonomy = _resolve_autonomy(body.autonomy)
    run_id = body.runId or f"code_{abs(hash(body.query)) & 0xFFFFFFFF:08x}_{int(__import__('time').time())}"
    if body.modelSettings is None:
        raise HTTPException(status_code=400, detail="modelSettings is required")
    request = RunRequest(
        runId=run_id,
        input=RunInput(query=body.query),
        agentId="code-agent",
        modelSettings=_ModelSettings(**body.modelSettings),
        autonomy=autonomy,
        workspaceId=body.workspaceId,
        callbackBaseUrl=body.callbackBaseUrl,
        callbackToken=body.callbackToken,
    )
    # Record the durable `task.created` boundary BEFORE the run so a resume can
    # prove it re-enters the SAME workspace + profile.
    _tasks().record_created(run_id, workspace_id=body.workspaceId, autonomy=autonomy)
    result = await service.run(request)
    return {"success": True, "task": _tasks().view(run_id), "run": result.model_dump()}


@router.get("/code/tasks")
def list_tasks(status: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    return {"success": True, "tasks": _tasks().list(limit=limit, status=status)}


@router.get("/code/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    view = _tasks().view(task_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": view}


@router.post("/code/tasks/{task_id}/resume")
def resume_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Whether a task can resume from its latest checkpoint (dry, read-only).

    The actual resume re-enters through `POST /runs/{id}/resume`, which owns the
    CHECKPOINT_NOT_FOUND / RESUME_CONFLICT semantics.
    """
    run = service.get_run(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    checkpoint = service.run_lineage().latest_checkpoint(task_id)
    if checkpoint is None:
        return {"success": False, "error": "CHECKPOINT_NOT_FOUND"}
    if run.get("status") in ("completed", "failed", "cancelled"):
        return {"success": False, "error": "RESUME_CONFLICT", "status": run.get("status")}
    return {"success": True, "checkpointId": checkpoint["id"]}


@router.post("/code/tasks/{task_id}/cancel")
def cancel_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if service.get_run(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    cancelled = service.cancel(task_id)
    # Release the disposable workspace so a cancel never leaves an orphan.
    released = False
    created = _tasks().latest_created(task_id)
    workspace_id = ((created or {}).get("payload") or {}).get("workspaceId")
    if workspace_id:
        try:
            from ..code import worktree  # noqa: PLC0415

            worktree.release(workspace_id)
            released = True
        except Exception:  # noqa: BLE001 - release is best-effort on cancel
            released = False
    _tasks().record_cancelled(task_id, reason="operator cancelled", worktree_released=released)
    return {"success": True, "taskId": task_id, "cancelled": cancelled, "worktreeReleased": released}


@router.post("/code/tasks/{task_id}/discard")
def discard_task(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Remove the task's disposable workspace; keep the run record as audit."""
    if service.get_run(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    released = False
    created = _tasks().latest_created(task_id)
    workspace_id = ((created or {}).get("payload") or {}).get("workspaceId")
    if workspace_id:
        try:
            from ..code import worktree  # noqa: PLC0415

            worktree.release(workspace_id)
            released = True
        except Exception:  # noqa: BLE001
            released = False
    _tasks().record_discarded(task_id, reason="operator discarded", worktree_released=released)
    return {"success": True, "taskId": task_id, "discarded": True, "worktreeReleased": released}


class AcceptPlanRequest(BaseModel):
    steps: list[dict[str, Any]] = Field(default_factory=list)
    checkClasses: list[str] = Field(default_factory=list)  # noqa: N815


@router.post("/code/tasks/{task_id}/plan/accept")
def accept_plan(
    task_id: str, body: AcceptPlanRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Operator accepts a plan_only plan, permitting a later edit_verify re-run."""
    if service.get_run(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    checkpoint = _tasks().record_plan_accepted(
        task_id, steps=list(body.steps), check_classes=list(body.checkClasses),
    )
    return {"success": True, "planDigest": checkpoint["payload"]["planDigest"]}


@router.get("/code/tasks/{task_id}/checks")
def task_checks(task_id: str) -> dict[str, Any]:
    run = service.get_run(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "verification": run.get("codeVerification")}


@router.get("/code/tasks/{task_id}/diff")
def task_diff(task_id: str) -> dict[str, Any]:
    """The worktree diff for a task's disposable copy, when one is bound."""
    created = _tasks().latest_created(task_id)
    workspace_id = ((created or {}).get("payload") or {}).get("workspaceId")
    if not workspace_id:
        raise HTTPException(status_code=404, detail="No workspace bound to this task")
    try:
        from ..code import worktree  # noqa: PLC0415

        return {"success": True, "diff": worktree.diff(workspace_id)}
    except Exception as exc:  # noqa: BLE001 - a diff failure is an honest 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Workspaces ──────────────────────────────────────────────────────────────


@router.get("/code/workspaces")
def list_workspaces(_: bool = Depends(require_operator)) -> dict[str, Any]:
    rows = service.code_store.list_workspaces(limit=100)
    return {
        "success": True,
        "workspaces": [
            {"id": r["id"], "baseRevision": r["baseRevision"], "strategy": r["strategy"],
             "releasedAt": r["releasedAt"], "fileCount": r["fileCount"]}
            for r in rows
        ],
    }


# ── External-action approvals ───────────────────────────────────────────────


@router.get("/code/approvals")
def list_code_approvals(status: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if service.approvals is None:
        return {"success": True, "approvals": [], "unavailable": True}
    return {"success": True, "approvals": service.approvals.list_kind("code_action", status, limit=100)}


@router.post("/code/approvals/{approval_id}/decide")
def decide_code_approval(
    approval_id: str, body: DecideApprovalRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    if service.approvals is None:
        raise HTTPException(status_code=503, detail="approvals unavailable")
    current = service.approvals.get(approval_id)
    if current is None or current.get("kind") != "code_action":
        raise HTTPException(status_code=404, detail="Approval not found")
    decided = service.approvals.decide(
        approval_id, approve=body.approve, decided_by="operator", reason=body.reason,
    )
    return {"success": True, "approval": decided}


@router.post("/code/tasks/{task_id}/actions")
def request_task_action(
    task_id: str, body: RequestActionRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Request an external action (commit/push/open_pr/deploy) for operator review."""
    from ..code.actions import CODE_ACTION_KINDS, CodeActionRequest, request_code_action  # noqa: PLC0415

    if body.action not in CODE_ACTION_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown action {body.action!r}")
    if service.approvals is None:
        raise HTTPException(status_code=503, detail="approvals unavailable")
    created = _tasks().latest_created(task_id)
    workspace_id = ((created or {}).get("payload") or {}).get("workspaceId")
    if not workspace_id:
        raise HTTPException(status_code=400, detail="no workspace bound to this task")
    request = CodeActionRequest(
        kind=body.action,  # type: ignore[arg-type]
        workspaceId=workspace_id, message=body.message or None,
        baseRef=body.baseRef or None, headRef=body.headRef or None, runId=task_id,
    )
    approval = request_code_action(service.approvals, request)
    return {"success": True, "approval": approval}


__all__ = ["router"]
