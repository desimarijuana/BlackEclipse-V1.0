"""Git / Version-Control HTTP routes for the front door and UI.

The UI consumes the SAME `GitService` the agent tools use — there is no second
Git implementation. Reads are operator-gated like every other surface (transport
or token proof, never a body flag). Mutations are operator-gated too; a
dangerous/remote action still needs the single-use approval the agent path
requires, so the UI cannot bypass authorization by talking to a route.

Shared state comes from `harness.deps`; this module never imports `main`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..git import readers, recovery
from ..git.repository import discover

router = APIRouter(tags=["git"])


def _repo():
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        raise HTTPException(status_code=503, detail="no workspace root")
    repo = discover(root)
    if repo is None:
        raise HTTPException(status_code=404, detail="NOT_A_REPOSITORY")
    return repo


def _svc():
    return service.git if getattr(service, "git", None) is not None else None


# ── Reads ──────────────────────────────────────────────────────────────────────


@router.get("/git/info")
def git_info(_: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    if svc is None:
        return {"success": True, "is_repository": False}
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        return {"success": True, "is_repository": False}
    return {"success": True, **svc.info(root)}


@router.get("/git/status")
def git_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, "status": readers.status(repo, full=True)}


@router.get("/git/diff")
def git_diff(
    base: Optional[str] = None,
    paths: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    repo = _repo()
    path_list = [p for p in (paths or "").split(",") if p] or None
    return {"success": True, "diff": readers.diff_worktree(repo, base=base, paths=path_list)}


@router.get("/git/log")
def git_log(maxCount: int = 50, rev: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, **readers.log(repo, max_count=min(max(1, maxCount), 500), rev=rev)}


@router.get("/git/branches")
def git_branches(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, **readers.branches(repo)}


@router.get("/git/conflicts")
def git_conflicts(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, **readers.conflicts(repo)}


@router.get("/git/state")
def git_state(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, "state": readers.repository_state(repo)}


@router.get("/git/remotes")
def git_remotes(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    return {"success": True, **readers.remotes(repo)}


@router.get("/git/recovery")
def git_recovery(_: bool = Depends(require_operator)) -> dict[str, Any]:
    repo = _repo()
    svc = _svc()
    result = recovery.recovery_options(repo).to_dict()
    if svc is not None and svc.journal is not None:
        result["reconciliation"] = recovery.reconcile(repo, svc.journal).to_dict()
    return {"success": True, **result}


@router.get("/git/journal")
def git_journal(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    if svc is None or svc.journal is None:
        return {"success": True, "entries": []}
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    repository = str(root) if root else None
    return {"success": True, "entries": svc.journal.list(repository=repository, limit=limit)}


# ── Mutations (operator-gated; the service still enforces the lock + journal) ──────


class StageRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    all: bool = False


@router.post("/git/stage")
def git_stage(body: StageRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    repo = _repo()
    if svc is None:
        raise HTTPException(status_code=503, detail="git service unavailable")
    outcome = svc.stage(repo, body.paths, all=body.all)
    return {"success": outcome.success, "outcome": outcome.to_dict()}


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    amend: bool = False
    allowSecrets: bool = False


@router.post("/git/commit")
def git_commit(body: CommitRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    repo = _repo()
    if svc is None:
        raise HTTPException(status_code=503, detail="git service unavailable")
    outcome = svc.commit(repo, body.message, amend=body.amend, allow_secrets=body.allowSecrets)
    return {"success": outcome.success, "outcome": outcome.to_dict()}


class BranchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start: Optional[str] = None
    checkout: bool = True


@router.post("/git/branches")
def git_create_branch(body: BranchRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    repo = _repo()
    if svc is None:
        raise HTTPException(status_code=503, detail="git service unavailable")
    outcome = svc.create_branch(repo, body.name, start=body.start, checkout=body.checkout)
    return {"success": outcome.success, "outcome": outcome.to_dict()}


class CheckoutRequest(BaseModel):
    target: Optional[str] = None
    create: Optional[str] = None


@router.post("/git/checkout")
def git_checkout(body: CheckoutRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    repo = _repo()
    if svc is None:
        raise HTTPException(status_code=503, detail="git service unavailable")
    outcome = svc.checkout(repo, body.target, create=body.create)
    return {"success": outcome.success, "outcome": outcome.to_dict()}


__all__ = ["router"]
