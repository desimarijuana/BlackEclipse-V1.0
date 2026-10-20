"""Prepare an RSL code candidate for the existing promotion approval.

This module NEVER applies a change. It mirrors `recovery/routing_landing.py`:

1. validate the target against the frozen RSL denylist;
2. classify it with `code/selfhost.py` (authority refusal, restart/build);
3. apply the ops inside a DISPOSABLE worktree;
4. register that workspace under a synthetic run id;
5. return the SAME `promotion.build_preview` the `/code/tasks/{id}/promote`
   route consumes.

The operator's existing single-use promotion approval is the only write path.
"""

from __future__ import annotations

from typing import Any, Optional

from ..code import evolution, patch as patch_mod
from ..code import policy, promotion, selfhost, worktree
from ..code.evolution_store import EvolutionStore
from ..code.workspace import ResolvedWorkspace
from ..skills.permissions import Actor
from .security import RSLTargetError, assert_landable_target


class RSLLandingError(Exception):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def run_id_for(candidate_id: str) -> str:
    return f"rsl-{candidate_id}"


def _ensure_run(service: Any, run_id: str, candidate: dict[str, Any]) -> None:
    if service.get_run(run_id) is not None:
        return
    service.store.create_run(
        run_id, "rsl",
        {
            "query": f"RSL prepared change for {candidate.get('targetPath')}",
            "candidateId": candidate.get("id"),
            "kind": "rsl",
        },
    )


def _actor(workspace_id: Optional[str] = None) -> Actor:
    return Actor(
        id="rsl", operator=False, workspace_id=workspace_id,
        autonomy="edit_verify",
    )


def prepare(
    service: Any,
    candidate_id: str,
    *,
    ops: Optional[list[dict[str, Any]]] = None,
    allocate: Any = None,
) -> dict[str, Any]:
    """Prepare the worktree + promotion preview. READ-ONLY for the checkout."""
    candidate = EvolutionStore(service.store).get_candidate(candidate_id)
    if candidate is None:
        raise RSLLandingError("RSL_CANDIDATE_NOT_FOUND", "the candidate does not exist")
    if candidate.get("subjectType") == "surface":
        raise RSLLandingError(
            "RSL_SURFACE_NOT_LANDABLE",
            "a surface snapshot is benchmarked but has no code change to promote in v1",
        )
    if candidate.get("status") != "evaluated_ok":
        raise RSLLandingError(
            "RSL_NOT_EVALUATED",
            "only a candidate whose own checks passed can be prepared for landing",
        )
    target = str(candidate.get("targetPath") or "").strip()
    proposed = ops if ops is not None else (candidate.get("proposedOps") or [])
    if not target or not proposed:
        raise RSLLandingError(
            "RSL_NOT_LANDABLE",
            "this candidate has no validated target and operations to prepare",
        )

    try:
        assert_landable_target(target)
        for op in proposed:
            if not isinstance(op, dict):
                continue
            for key in ("path", "fromPath"):
                if op.get(key):
                    assert_landable_target(str(op[key]))
    except RSLTargetError as exc:
        raise RSLLandingError(exc.code, exc.detail or "the target is frozen") from exc

    try:
        evolution.propose_ops(
            {**candidate, "targetPath": target}, actor=_actor(), ops=proposed,
        )
    except evolution.EvolutionRefusal as exc:
        raise RSLLandingError(exc.code, exc.detail or exc.code) from exc

    verdict = selfhost.classify_landing([target])
    if verdict.refused:
        raise RSLLandingError(
            "SELFHOST_AUTHORITY_REFUSED",
            "Eclipse won't change its own policy or approval code in a running app",
        )

    run_id = run_id_for(candidate_id)
    _ensure_run(service, run_id, candidate)

    existing = [
        row for row in service.code_store.list_workspaces(run_id=run_id, limit=20)
        if not row.get("releasedAt")
    ]
    if not existing:
        allocate = allocate or worktree.allocate
        cw = allocate(base_revision="HEAD")
        binding = policy.WorkspaceBinding(
            id=cw.id, root=cw.root, base_revision=cw.base_revision, strategy=cw.strategy,
        )
        resolved = ResolvedWorkspace(
            id=cw.id, root=cw.root, base_revision=cw.base_revision,
            strategy=cw.strategy, binding=binding,
        )
        try:
            parsed = patch_mod.parse_patch({"operations": proposed})
            applied = patch_mod.apply(
                resolved, parsed, binding=binding, actor=_actor(cw.id),
            )
        except patch_mod.PatchError as exc:
            worktree.release(cw.id)
            raise RSLLandingError(exc.code, exc.reason) from exc
        if not applied.get("ok"):
            worktree.release(cw.id)
            refused = applied.get("refused") or {}
            raise RSLLandingError(
                "RSL_PATCH_REFUSED",
                str(refused.get("reason") or "the worktree refused the change"),
            )
        service.code_store.save_workspace(
            cw.id, str(cw.root), cw.base_revision, cw.strategy,
            run_id=run_id, file_count=cw.file_count,
        )

    preview = promotion.build_preview(run_id, code_store=service.code_store)
    view = {k: v for k, v in preview.items() if k != "worktreeRoot"}
    return {
        "candidateId": candidate_id,
        "runId": run_id,
        "preview": view,
        "landing": verdict.to_dict(),
    }


__all__ = ["RSLLandingError", "prepare", "run_id_for"]
