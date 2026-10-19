"""Round 4 (W4) — prepare a routing repair for the existing promotion path.

The self-repair loop may PROPOSE and VERIFY a change; landing it stays an
operator decision. This module bridges the two WITHOUT a second approval system:

1. take a stored incident's typed proposal (W2),
2. classify the target with `code/selfhost.py` (authority refusal, restart/build),
3. allocate a DISPOSABLE worktree and apply the proposal's `PatchOp` there,
4. register that workspace under a synthetic run id and build the SAME
   `promotion.PromotionPreview` the existing `/code/tasks/{runId}/promote` route
   expects.

The front door then renders the existing promotion card: single-use,
digest-bound approval, apply, restart/build verdict, rollback. This module never
applies the change to the real checkout.
"""

from __future__ import annotations

from typing import Any, Optional

from ..code import patch as patch_mod
from ..code import policy, promotion, selfhost, worktree
from ..code.workspace import ResolvedWorkspace
from ..skills.permissions import Actor


class RoutingLandingError(Exception):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def run_id_for(incident_id: str) -> str:
    return f"routing-repair-{incident_id}"


def _retry_run(service: Any, run_id: str, summary: str, incident_id: str) -> None:
    """The promotion route requires a HarnessRun row; create it only if absent."""
    if service.get_run(run_id) is not None:
        return
    service.store.create_run(
        run_id, "routing-repair",
        {"query": summary, "incidentId": incident_id, "kind": "routing-repair"},
    )


def prepare(
    service: Any,
    incident_id: str,
    *,
    catalog: Any = None,
    allocate: Any = None,
) -> dict[str, Any]:
    """Prepare the worktree + preview. READ-ONLY with respect to the checkout."""
    proposal = service.propose_routing_repair(incident_id, catalog=catalog)
    if proposal is None:
        raise RoutingLandingError("ROUTING_INCIDENT_NOT_FOUND", "the incident does not exist")
    if proposal.get("kind") != "classifier_rule" or not proposal.get("patch"):
        raise RoutingLandingError(
            "ROUTING_REPAIR_NOT_LANDABLE",
            "this proposal has no code change to land; the engineering/acquisition "
            "route is the correct next step",
        )
    target = str(proposal.get("targetFile") or "")
    verdict = selfhost.classify_landing([target])
    if verdict.refused:
        raise RoutingLandingError(
            "SELFHOST_AUTHORITY_REFUSED",
            "Eclipse won't change its own policy or approval code in a running app",
        )

    run_id = run_id_for(incident_id)
    _retry_run(service, run_id, str(proposal.get("summary") or ""), incident_id)

    # Reuse a live prepared workspace for this incident; otherwise allocate one.
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
        actor = Actor(
            id="routing-repair", operator=False, workspace_id=cw.id,
            autonomy="edit_verify",
        )
        patch = proposal["patch"]
        operation = patch_mod.PatchOp(
            op="replace", path=target,
            reason=str(proposal.get("summary") or "routing repair"),
            old=str(patch["old"]), new=str(patch["new"]),
        )
        result = patch_mod.apply(resolved, [operation], binding=binding, actor=actor)
        if not result.get("ok"):
            worktree.release(cw.id)
            refused = result.get("refused") or {}
            raise RoutingLandingError(
                "ROUTING_PATCH_REFUSED",
                str(refused.get("reason") or "the worktree refused the change"),
            )
        service.code_store.save_workspace(
            cw.id, str(cw.root), cw.base_revision, cw.strategy,
            run_id=run_id, file_count=cw.file_count,
        )

    preview = promotion.build_preview(run_id, code_store=service.code_store)
    view = {k: v for k, v in preview.items() if k != "worktreeRoot"}
    return {
        "incidentId": incident_id,
        "runId": run_id,
        "proposal": proposal,
        "preview": view,
        "landing": verdict.to_dict(),
    }


__all__ = ["RoutingLandingError", "prepare", "run_id_for"]
