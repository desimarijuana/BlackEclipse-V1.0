"""Turn an inert recurrence candidate into validated, reviewable proposals.

R4 deliberately uses operator/agent-supplied operations. It does not invent a
patch with a model. R7 adds a bounded multi-candidate path (`propose_many`) over
the SAME operator-supplied operations: typed `invariant`/`domain` variants are
validated independently, and only the existing deterministic gates run. No
model proposer is invoked.

Every op target is checked against the frozen RSL denylist before the existing
`code.evolution.propose_ops` validation runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from ..code import evolution
from ..code.evolution_store import EvolutionStore
from .security import RSLTargetError, assert_landable_target

VARIANT_KINDS = ("invariant", "domain")
MAX_PROPOSALS = 8


class ProposalRefused(ValueError):
    """A candidate cannot become a proposal; `code` is stable and testable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class CandidateProposal:
    """One typed, validated candidate from the same observation.

    `invariant` is a change that should hold generally; `domain` is scoped to the
    observation's domain. The type is carried into the recursion record and the
    experiment config; it never grants authority.
    """

    id: str
    kind: str
    targetPath: str
    ops: tuple[dict[str, Any], ...]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "targetPath": self.targetPath,
            "ops": [dict(op) for op in self.ops],
            "description": self.description,
        }


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


def _actor_or_default(actor: Any) -> Any:
    if actor is not None:
        return actor
    from ..skills.permissions import Actor  # noqa: PLC0415 - keep the module light

    return Actor(id="rsl", operator=False, autonomy="edit_verify")


def _validated_proposal(
    observation: Mapping[str, Any],
    *,
    proposal_id: str,
    kind: str,
    target: str,
    ops: Sequence[Mapping[str, Any]],
    description: str,
    actor: Any,
) -> CandidateProposal:
    target = str(target or "").strip()
    if not target:
        raise ProposalRefused("PROPOSAL_NO_TARGET", "the candidate names no target")
    raw_ops = list(ops or [])
    if any(not isinstance(op, Mapping) for op in raw_ops):
        raise ProposalRefused(
            "PROPOSAL_INVALID_VARIANT", "each operation must be an object",
        )
    proposed = [dict(op) for op in raw_ops]
    if not proposed:
        raise ProposalRefused("PROPOSAL_NO_OPS", "the candidate has no operations")
    if kind not in VARIANT_KINDS:
        raise ProposalRefused(
            "PROPOSAL_INVALID_KIND",
            "a recursive candidate must be typed invariant or domain",
        )

    try:
        assert_landable_target(target)
        for op_target in _op_targets(proposed):
            assert_landable_target(op_target)
    except RSLTargetError as exc:
        raise ProposalRefused(exc.code, exc.detail or "the target is frozen") from exc

    try:
        validated = evolution.propose_ops(
            {**dict(observation), "targetPath": target}, actor=actor, ops=proposed,
        )
    except evolution.EvolutionRefusal as exc:
        raise ProposalRefused(exc.code, exc.detail or exc.code) from exc

    return CandidateProposal(
        id=proposal_id,
        kind=kind,
        targetPath=target,
        ops=tuple(validated),
        description=str(description or ""),
    )


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


def propose_many(
    observation: Mapping[str, Any],
    k: int = 1,
    *,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    actor: Any = None,
) -> list[CandidateProposal]:
    """Build up to `k` typed proposals from ONE observation.

    This is the deterministic R7 path: the caller supplies the variant
    operations (operator/agent-authored); this function validates each one
    independently against the frozen denylist and the existing `propose_ops`
    checks. It never invents a patch, never calls a model and never persists.

    `k=1` is the trivial path and reuses the observation's own ops. `k>1`
    requires explicit `variants`, each shaped as
    `{"kind": "invariant"|"domain", "targetPath": str, "ops": [...]}`. The first
    `k` valid variants are returned; a malformed variant refuses the whole set
    (a partial, silently-dropped proposal would be a fabricated comparison).
    """
    k = max(1, min(int(k), MAX_PROPOSALS))
    resolved_actor = _actor_or_default(actor)

    if variants is None:
        if k != 1:
            raise ProposalRefused(
                "PROPOSAL_NO_VARIANTS",
                "k>1 needs explicit typed variants; RSL does not invent proposals",
            )
        target = str(observation.get("targetPath") or "")
        ops = observation.get("proposedOps") or []
        return [
            _validated_proposal(
                observation,
                proposal_id="v1",
                kind="invariant",
                target=target,
                ops=ops,
                description=str(observation.get("problemStatement") or ""),
                actor=resolved_actor,
            )
        ]

    supplied = list(variants)
    if not supplied:
        raise ProposalRefused("PROPOSAL_NO_VARIANTS", "no candidate variants were supplied")
    proposals: list[CandidateProposal] = []
    for index, variant in enumerate(supplied[:k]):
        if not isinstance(variant, Mapping):
            raise ProposalRefused(
                "PROPOSAL_INVALID_VARIANT", "each variant must be an object",
            )
        proposals.append(
            _validated_proposal(
                observation,
                proposal_id=f"v{index + 1}",
                kind=str(variant.get("kind") or "").strip().lower(),
                target=str(variant.get("targetPath") or observation.get("targetPath") or ""),
                ops=variant.get("ops") or variant.get("proposedOps") or [],
                description=str(
                    variant.get("description") or observation.get("problemStatement") or ""
                ),
                actor=resolved_actor,
            )
        )
    return proposals


__all__ = [
    "CandidateProposal",
    "MAX_PROPOSALS",
    "ProposalRefused",
    "VARIANT_KINDS",
    "propose_from_ops",
    "propose_many",
]
