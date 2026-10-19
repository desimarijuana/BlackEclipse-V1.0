"""Turn an inert recurrence candidate into a validated, reviewable proposal.

R4 deliberately uses operator/agent-supplied operations. It does not invent a
patch with a model; a later phase may add a bounded proposer behind its own flag.
Every op target is checked against the frozen RSL denylist before the existing
`code.evolution.propose_ops` validation runs.
"""

from __future__ import annotations

from typing import Any, Optional

from ..code import evolution
from ..code.evolution_store import EvolutionStore
from .security import RSLTargetError, assert_landable_target


class ProposalRefused(ValueError):
    """A candidate cannot become a proposal; `code` is stable and testable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


def _op_targets(ops: list[dict[str, Any]]) -> list[str]:
    targets: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        for key in ("path", "fromPath"):
            value = op.get(key)
            if value:
                targets.append(str(value))
    return targets


def propose_from_ops(
    store: Any,
    candidate_id: str,
    *,
    actor: Any,
    ops: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Validate the candidate's target + ops and mark it `proposed`.

    The candidate must already name a target and carry operations (or the caller
    supplies them). The frozen target guard runs on the target AND every op path,
    then `propose_ops` applies the existing policy/FORBIDDEN_FIELDS checks.
    """
    evolution_store = EvolutionStore(store)
    candidate = evolution_store.get_candidate(candidate_id)
    if candidate is None:
        raise ProposalRefused("PROPOSAL_CANDIDATE_NOT_FOUND", "the candidate does not exist")

    target = str(candidate.get("targetPath") or "").strip()
    if not target:
        raise ProposalRefused("PROPOSAL_NO_TARGET", "the candidate names no target")
    proposed = ops if ops is not None else (candidate.get("proposedOps") or [])
    if not proposed:
        raise ProposalRefused("PROPOSAL_NO_OPS", "the candidate has no operations")

    try:
        assert_landable_target(target)
        for op_target in _op_targets(proposed):
            assert_landable_target(op_target)
    except RSLTargetError as exc:
        raise ProposalRefused(exc.code, exc.detail or "the target is frozen") from exc

    try:
        validated = evolution.propose_ops(
            {**candidate, "targetPath": target}, actor=actor, ops=proposed,
        )
    except evolution.EvolutionRefusal as exc:
        raise ProposalRefused(exc.code, exc.detail or exc.code) from exc

    return evolution_store.update_candidate(
        candidate_id,
        targetPath=target,
        proposedOps=validated,
        status="proposed",
    ) or candidate


__all__ = ["ProposalRefused", "propose_from_ops"]
