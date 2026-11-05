"""Code-task lifecycle + external-action approvals routes (Phase 5).

A code task IS a run whose agent id is `code-agent`; the lifecycle is the ONE
run lineage, never a second table. Every MUTATING route (and any read that
touches a workspace) carries `require_operator` — transport/token proof only,
never a request-body flag — mirroring the MCP router. Shared state comes from
`harness.deps`; this module never imports `main`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..code.request_intent import classify_code_request
from ..code.land import LandPlan, plan_land_checks, run_land_plan
from ..code.session import SessionError, SessionStore, apply_budget, resolve_budget
from ..code.tasks import DEFAULT_AUTONOMY, TaskStore
from ..deps import require_operator, service
from ..schemas import RunInput, RunRequest
from ..schemas import ModelSettings as _ModelSettings

router = APIRouter(tags=["code"])

_AUTONOMY_PROFILES = ("plan_only", "edit_verify", "approve_external")


class CreateTaskRequest(BaseModel):
    """Create a code task. `autonomy` defaults to edit_verify."""

    query: str = Field(min_length=1, max_length=4000)
    autonomy: Optional[str] = None
    workspaceId: Optional[str] = None  # noqa: N815
    runId: Optional[str] = None  # noqa: N815
    callbackBaseUrl: str  # noqa: N815
    callbackToken: Optional[str] = None  # noqa: N815
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815
    # Folder-selection (additive): edit the selected real folder directly
    # instead of a disposable copy. None = resolve from the selected root
    # (a chosen folder edits directly; the built-in repo stays isolated).
    direct: Optional[bool] = None
    # Phase 11 (additive): a caller-supplied scope FILTER label. It narrows what is
    # listed; it NEVER authorizes anything — `require_operator` does.
    scopeId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    # Phase 22 (additive): the build session's budget profile (small / standard /
    # deep). Absent means `standard`. It is a profile NAME, never a raw number.
    budgetProfile: Optional[str] = Field(None, max_length=20)  # noqa: N815
    # What "done" means, in the caller's words. Recorded with the budget so a
    # resumed session can restate its contract.
    acceptance: list[str] = Field(default_factory=list, max_length=20)


class CodeIntentRequest(BaseModel):
    """One chat turn to classify. Pure, read-only — no state is created."""

    query: str = Field(min_length=1, max_length=4000)
    history: Optional[list[dict[str, Any]]] = None


class DecideApprovalRequest(BaseModel):
    approve: bool
    reason: str = Field("", max_length=400)
    # "Always allow": create a standing grant for the exact program/tool the
    # pending approval describes (only when the row carries a grantable pattern).
    remember: bool = False


class RequestActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    message: str = Field("", max_length=500)
    baseRef: str = Field("", max_length=200)  # noqa: N815
    headRef: str = Field("", max_length=200)  # noqa: N815


class PromoteRequest(BaseModel):
    """Confirm a previewed change: the single-use approval + the preview digest."""

    approvalId: str = Field(min_length=1, max_length=64)  # noqa: N815
    previewDigest: str = Field(min_length=8, max_length=128)  # noqa: N815
    # Phase 22 / S5 slice 2: the files the reviewer kept. Empty = all of them.
    include: list[str] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    """Narrow the preview to the files the reviewer kept. Empty = all."""

    include: list[str] = Field(default_factory=list)


class PostLandingRequest(BaseModel):
    """Identify the promoted RSL run whose restart/health probe to run."""

    runId: str = Field(min_length=1, max_length=200)  # noqa: N815
    activationId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    # The front door/supervisor has already restarted the runtime; probe only.
    alreadyRestarted: bool = False  # noqa: N815


def _resolve_autonomy(raw: Optional[str]) -> str:
    value = (raw or DEFAULT_AUTONOMY).strip()
    if value not in _AUTONOMY_PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown autonomy profile {raw!r}")
    return value


def _tasks() -> TaskStore:
    return service.code_tasks()


def _sessions() -> SessionStore:
    return SessionStore(service.store)


# ── Chat request classification (Phase 14) ──────────────────────────────────


@router.post("/code/intent")
def classify_intent(body: CodeIntentRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Classify one chat turn. A read-only, stateless deterministic verdict.

    Operator-gated (transport/token only) like every other code route, so the
    front-door proxy is the only caller. No model call, no state.
    """
    intent = classify_code_request(body.query, body.history)
    return {"success": True, "intent": {
        "verdict": intent.verdict,
        "confidence": intent.confidence,
        "reason": intent.reason,
        "signals": list(intent.signals),
    }}


class ShellRunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    cwd: Optional[str] = None  # relative to the resolved root; must stay inside it
    timeoutS: Optional[int] = Field(default=None, ge=1, le=900)  # noqa: N815


@router.post("/code/shell")
def code_shell(body: ShellRunRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Run one command through the host shell for the in-app terminal panel.

    Operator-gated like every other code route; cwd is confined to the
    server-resolved workspace root, so the panel cannot escape it.
    """
    from ..code import shell as shell_mod  # noqa: PLC0415
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        raise HTTPException(status_code=503, detail="no workspace root")
    cwd = root
    if body.cwd:
        candidate = (root / body.cwd).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="cwd must stay inside the workspace")
        if candidate.is_dir():
            cwd = candidate
    result = shell_mod.run(body.command, cwd=cwd, timeout_s=body.timeoutS)
    return {"success": True, "result": {
        "command": result.command, "cwd": result.cwd, "exitCode": result.exit_code,
        "stdout": result.stdout, "stderr": result.stderr,
        "durationMs": result.duration_ms, "timedOut": result.timed_out,
        "truncated": result.truncated, "status": result.status,
    }}


# ── Task lifecycle ──────────────────────────────────────────────────────────


@router.get("/code/root")
def code_root(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The runtime's SERVER-RESOLVED code root. Read-only and operator-gated.

    Used by the chat front door (a confirmation ref) and the task list's
    schedule action (a code job needs a folder to work in). The runtime binds
    only its own server-resolved root (`workspace.resolve_workspace` refuses a
    mismatch), so the value can never point a run at another directory.
    """
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        return {"success": True, "root": None, "available": False}
    return {"success": True, "root": str(root), "available": True}


@router.post("/code/tasks")
async def create_task(body: CreateTaskRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Create and run a code task. The autonomy defaults to edit_verify."""
    autonomy = _resolve_autonomy(body.autonomy)
    try:
        budget = resolve_budget(body.budgetProfile)
    except SessionError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
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
        userId=body.scopeId,
        direct=body.direct,
    )
    # Phase 22 / S2: the session's budget floor (clamped again in the graph).
    apply_budget(request, budget)
    # Create the run ROW first: `RunCheckpoint` has a FOREIGN KEY on
    # `HarnessRun(id)`, so `record_created` before the row exists fails with a
    # FOREIGN KEY constraint error. `execute_run` re-uses this row (it does not
    # re-create an existing run), so the `task.created` boundary and the run row
    # are guaranteed to name the SAME run.
    try:
        service.store.create_run(
            run_id, "code-agent", request.input.model_dump(), body.scopeId,
            body.modelSettings.get("provider"), body.modelSettings.get("model"),
        )
    except Exception:  # noqa: BLE001 - a duplicate run id is not fatal here
        pass
    # Record the durable `task.created` boundary BEFORE the run so a resume can
    # prove it re-enters the SAME workspace + profile.
    _tasks().record_created(
        run_id, workspace_id=body.workspaceId, autonomy=autonomy, scope_id=body.scopeId,
    )
    # Phase 22 / S2: the goal + acceptance + budget, on the SAME lineage.
    _sessions().record(
        run_id, goal=body.query, budget=budget,
        acceptance=body.acceptance, workspace_id=body.workspaceId,
    )
    result = await service.run(request)
    return {
        "success": True,
        "task": _tasks().view(run_id),
        "session": _sessions().view(run_id),
        "run": result.model_dump(),
    }


@router.get("/code/tasks")
def list_tasks(
    status: Optional[str] = None, limit: int = 50,
    scopeId: Optional[str] = None,  # noqa: N803 - the wire name
) -> dict[str, Any]:
    """List code tasks. `scopeId` is a caller-supplied FILTER, never authorization."""
    return {"success": True, "tasks": _tasks().list(limit=limit, status=status, scope_id=scopeId)}


@router.get("/code/scorecard")
def code_scorecard(days: int = 30, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """The honest self-build scorecard. Read-only; `UNKNOWN` where unmeasured."""
    from ..code.scorecard import build_scorecard  # noqa: PLC0415

    return {"success": True, **build_scorecard(service.store, window_days=days)}


@router.get("/code/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    view = _tasks().view(task_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": view, "session": _sessions().view(task_id)}


def _land_preview(task_id: str) -> tuple[dict[str, Any], Path]:
    """The task's current preview and the folder the checks must run in.

    Checks run against the project ON DISK (the checkout the change lands in),
    not the disposable copy: the copy has no installed dependencies, so npm and
    the vendored Python would fail there for the wrong reason. The Code screen
    places the checks after the change is applied.
    """
    from ..code import promotion  # noqa: PLC0415
    from ..code.workspace import default_root  # noqa: PLC0415

    try:
        preview = promotion.build_preview(task_id, code_store=service.code_store)
    except promotion.PromotionError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
    root = default_root() or Path(".")
    return preview, Path(root).resolve()


@router.get("/code/tasks/{task_id}/land")
def get_land_plan(task_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """The ordered checks this change must pass. Read-only, runs nothing."""
    preview, root = _land_preview(task_id)
    files = [str(item.get("path") or "") for item in (preview.get("files") or [])]
    plan = plan_land_checks(files, root=root)
    return {
        "success": True,
        "previewDigest": preview.get("previewDigest"),
        "plan": plan.to_dict(),
    }


@router.post("/code/tasks/{task_id}/land/verify")
def verify_landing(
    task_id: str, full: bool = False, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Run the landing checks. `full=false` skips the long suite for a quick pass.

    The exit code is the judge; the result is recorded as a `land.verified`
    checkpoint so the landing is auditable. A check that cannot run is an error,
    never a pass.
    """
    preview, root = _land_preview(task_id)
    files = [str(item.get("path") or "") for item in (preview.get("files") or [])]
    plan = plan_land_checks(files, root=root)
    if not full:
        plan = LandPlan(
            changed=plan.changed,
            checks=tuple(check for check in plan.checks if check.id != "tests"),
            source=plan.source, warnings=plan.warnings,
        )
    result = run_land_plan(plan, root=root)
    checkpoint = service.run_lineage().save_checkpoint(task_id, "land.verified", {
        "previewDigest": preview.get("previewDigest"),
        "ok": result.ok,
        "failed": result.failed,
        "full": bool(full),
        "checks": [item.to_dict() for item in result.results],
    })
    return {
        "success": True,
        "previewDigest": preview.get("previewDigest"),
        "full": bool(full),
        "checkpointId": checkpoint["id"],
        "result": result.to_dict(),
    }


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
def list_workspaces(
    scopeId: Optional[str] = None,  # noqa: N803 - the wire name
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """List disposable workspaces. `scopeId` is a FILTER; it never widens access."""
    rows = service.code_store.list_workspaces(limit=100, scope_id=scopeId)
    return {
        "success": True,
        "workspaces": [
            {"id": r["id"], "baseRevision": r["baseRevision"], "strategy": r["strategy"],
             "releasedAt": r["releasedAt"], "fileCount": r["fileCount"]}
            for r in rows
        ],
    }


# ── External-action approvals ───────────────────────────────────────────────


# Kinds a person can review on this surface. `code_action` is a commit/push/PR;
# `terminal_command`/`shell_command` are an `ask`-classified command the terminal
# authorizers created (e.g. `New-Item`). They MUST be listed here, or a pending
# command approval is created but never shown — the agent reports "blocked" and
# the user has no way to approve it.
_REVIEWABLE_APPROVAL_KINDS = (
    "code_action", "terminal_command", "shell_command", "code_promote", "scraper_domain",
    "trade_order",
)


@router.get("/code/approvals")
def list_code_approvals(status: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if service.approvals is None:
        return {"success": True, "approvals": [], "unavailable": True}
    approvals: list[dict[str, Any]] = []
    for kind in _REVIEWABLE_APPROVAL_KINDS:
        approvals.extend(service.approvals.list_kind(kind, status, limit=100))
    return {"success": True, "approvals": approvals}


@router.post("/code/approvals/{approval_id}/decide")
def decide_code_approval(
    approval_id: str, body: DecideApprovalRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    if service.approvals is None:
        raise HTTPException(status_code=503, detail="approvals unavailable")
    current = service.approvals.get(approval_id)
    if current is None or current.get("kind") not in _REVIEWABLE_APPROVAL_KINDS:
        raise HTTPException(status_code=404, detail="Approval not found")
    decided = service.approvals.decide(
        approval_id, approve=body.approve, decided_by="operator", reason=body.reason,
    )
    grant = None
    if body.approve and body.remember:
        grant = service.approvals.remember_grant(approval_id)
    return {"success": True, "approval": decided, "grant": grant}


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


# ── Promotion: put a reviewed change into the user's real project (Phase 15) ──
# A chat/code run edits a DISPOSABLE copy. Nothing reaches the user's real folder
# until they preview the exact file set and confirm it through a single-use,
# digest-bound approval (ADR-H119). The write itself reuses `code/patch.py`'s
# atomic, base-hash-checked, protected-path-aware engine.


@router.post("/code/tasks/{task_id}/promote/preview")
def promote_preview(
    task_id: str, body: Optional[PreviewRequest] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Preview exactly what a task's change would put into the user's project."""
    from ..code import promotion, selfhost  # noqa: PLC0415

    if service.get_run(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        preview = promotion.build_preview(task_id, code_store=service.code_store)
        include = (body.include if body else []) or []
        if include:
            preview = promotion.filter_preview(preview, include)
    except promotion.PromotionError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
    verdict = selfhost.classify_landing([str(f.get("path") or "") for f in preview.get("files", [])])
    if verdict.refused:
        # Never request an approval for a change the self-host floor refuses.
        raise HTTPException(status_code=403, detail="SELFHOST_AUTHORITY_REFUSED")
    approval = None
    if service.approvals is not None:
        approval = service.approvals.request_kind(
            kind=promotion.PROMOTION_KIND,
            request_key=preview["workspaceId"],
            digest=preview["previewDigest"],
            effect="external_action",
            run_id=task_id,
            workspace_id=preview["workspaceId"],
            action_summary=(
                f"Put {preview['filesChanged']} change(s) into your project "
                f"(+{preview['added']} new, {preview['modified']} edited, {preview['deleted']} removed)"
            ),
            risk="high",
        )
    view = {k: v for k, v in preview.items() if k != "worktreeRoot"}
    return {"success": True, "preview": view, "approval": approval, "landing": verdict.to_dict()}


@router.post("/code/tasks/{task_id}/promote")
def promote_apply(
    task_id: str, body: PromoteRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Confirm a previewed change and put it into the user's real project."""
    from ..code import promotion, selfhost  # noqa: PLC0415

    if service.approvals is None:
        raise HTTPException(status_code=503, detail="approvals unavailable")
    current = service.approvals.get(body.approvalId)
    if current is None or current.get("kind") != promotion.PROMOTION_KIND:
        raise HTTPException(status_code=404, detail="Approval not found")
    # Re-derive the live preview: a change to either copy since the preview makes
    # the confirmed set stale and the promotion is refused (nothing is written).
    try:
        preview = promotion.build_preview(task_id, code_store=service.code_store)
        if body.include:
            preview = promotion.filter_preview(preview, body.include)
    except promotion.PromotionError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
    if preview["previewDigest"] != body.previewDigest:
        raise HTTPException(status_code=409, detail="PROMOTION_PREVIEW_STALE")
    verdict = selfhost.classify_landing([str(f.get("path") or "") for f in preview.get("files", [])])
    if verdict.refused:
        # Refuse BEFORE consuming the approval: the change can never be landed
        # through this path, so the operator must not spend the decision.
        raise HTTPException(status_code=403, detail="SELFHOST_AUTHORITY_REFUSED")
    claimed = service.approvals.consume_kind(
        kind=promotion.PROMOTION_KIND,
        request_key=preview["workspaceId"],
        digest=body.previewDigest,
        workspace_id=preview["workspaceId"],
    )
    if claimed is None:
        raise HTTPException(status_code=403, detail="PROMOTION_NOT_APPROVED")
    try:
        result = promotion.apply_promotion(preview)
    except promotion.PromotionError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    # Phase 22 / S6: the durable landing marker the self-build scorecard reads.
    # A best-effort checkpoint: a landing that succeeded must not be reported as
    # failed because its metric row could not be written.
    try:
        service.run_lineage().save_checkpoint(task_id, "land.promoted", {
            "previewDigest": preview.get("previewDigest"),
            "rollbackId": result.get("rollbackId"),
            "filesChanged": result.get("filesChanged"),
            "landing": verdict.to_dict(),
        })
    except Exception:  # noqa: BLE001 - metrics never block a landing
        pass
    # Tell the front door whether this change needs a runtime restart / build gate
    # (self-hosting). The route cannot restart the process, so it reports the
    # requirement; `code/selfhost.py` owns the health-gated apply when a restart
    # seam is available. An RSL landing also carries the post-landing probe URL,
    # so the front door/supervisor can prove the restarted runtime is healthy and
    # roll the change back when it is not.
    post_landing = None
    if task_id.startswith("rsl-") and verdict.restartRequired:
        rollback_id = str(result.get("rollbackId") or "")
        post_landing = {
            "required": True,
            "runId": task_id,
            "rollbackId": rollback_id or None,
            "endpoint": (
                f"/api/code/promotions/{rollback_id}/post-landing"
                if rollback_id else None
            ),
            "status": "pending" if rollback_id else "unavailable",
        }
    return {
        "success": True,
        "promotion": result,
        "landing": verdict.to_dict(),
        "postLanding": post_landing,
    }


@router.post("/code/promotions/{rollback_id}/rollback")
def rollback_promotion_route(
    rollback_id: str, runId: Optional[str] = None,  # noqa: N803 - the wire name
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Put a previously-promoted change back - the exact original contents.

    The inverse of promotion: a created file is removed, an edited file is
    restored, a deleted file is recreated. Both versions are kept.
    """
    from ..code import promotion  # noqa: PLC0415

    try:
        result = promotion.rollback_promotion(rollback_id)
    except promotion.PromotionError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    # The scorecard's rollback marker, only when the caller named the run.
    if runId:
        try:
            service.run_lineage().save_checkpoint(runId, "land.rolled_back", {
                "rollbackId": rollback_id,
            })
        except Exception:  # noqa: BLE001 - metrics never block a rollback
            pass
    return {"success": True, "rollback": result}


@router.post("/code/promotions/{rollback_id}/post-landing")
async def post_landing_probe(
    rollback_id: str,
    body: PostLandingRequest,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Restart, probe, and roll back an unhealthy RSL landing.

    The restart itself is a front-door/supervisor seam (`service._restart_runtime`).
    Without it the probe is recorded as `unverified`, never as a success.
    """
    from ..self_improvement.post_landing import (  # noqa: PLC0415
        PostLandingPolicy,
        run_post_landing,
    )

    restart = getattr(service, "_restart_runtime", None)
    record = await run_post_landing(
        store=service.store,
        run_id=body.runId,
        rollback_id=rollback_id,
        activation_id=body.activationId or "",
        restart=restart,
        policy=PostLandingPolicy(),
        restart_already_done=body.alreadyRestarted,
    )
    return {"success": True, "postLanding": record}


@router.get("/code/promotions/post-landing")
def list_post_landing(
    runId: Optional[str] = None,  # noqa: N803
    limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Read the bounded post-landing records (newest first)."""
    from ..self_improvement.post_landing import PostLandingStore  # noqa: PLC0415

    return {
        "success": True,
        "records": PostLandingStore(service.store).list(
            run_id=runId, limit=limit,
        ),
    }


__all__ = ["router"]
