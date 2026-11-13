"""Skill promotion lifecycle — review, approve, reject, roll back.

The lifecycle is explicit and operator-gated:

    draft → testing → review → validated → enabled

A promotion may only proceed from a passing evaluation. Approval is a distinct
authorized action from evaluation. Rollback selects a prior stored version and
does not delete anything — behavior changes are always traceable.
"""

from __future__ import annotations

from typing import Any, Optional

from .evaluation import promotion_gate
from .permissions import Actor
from .registry import SkillRegistry


def _require(actor: Actor, permission: str) -> Optional[dict[str, Any]]:
    if permission not in actor.granted():
        return {"ok": False, "error": f"{permission} requires an authorized operator"}
    return None


def request_promotion(
    registry: SkillRegistry,
    *,
    skill_id: str,
    version: Optional[str],
    actor: Actor,
    reason: str,
    evaluation_id: Optional[str] = None,
) -> dict[str, Any]:
    denied = _require(actor, "skill.review")
    if denied:
        return denied
    manifest = registry.manifest(skill_id)
    if manifest is None:
        return {"ok": False, "error": "skill not installed"}
    resolved_version = registry.resolve_version(skill_id, version) or manifest.version

    evaluation = registry.store.get_evaluation(evaluation_id) if evaluation_id else None
    if evaluation is None:
        # Fall back to the most recent evaluation for this version.
        evals = [e for e in registry.store.list_evaluations(skill_id, limit=20) if e["version"] == resolved_version]
        evaluation = evals[0] if evals else None
    if evaluation is None:
        return {"ok": False, "error": "no evaluation exists for this version; evaluate before promotion"}

    from ..config.flags import get_bool  # noqa: PLC0415
    from .evaluation import execution_gate_applies  # noqa: PLC0415

    gate = promotion_gate(
        evaluation,
        require_execution=(
            get_bool("HARNESS_SKILL_EXEC_EVAL") and execution_gate_applies(manifest)
        ),
        store=registry.store,
    )
    if not gate["passed"]:
        registry.store.save_review(
            skill_id=skill_id, version=resolved_version, actor=actor.id,
            decision="blocked", notes=gate["reason"],
        )
        return {"ok": False, "error": gate["reason"], "gate": gate}

    # Move to review / validated.
    registry.store.set_version_status(skill_id, resolved_version, "validated", evaluation_status="passed")
    registry.store.save_review(
        skill_id=skill_id, version=resolved_version, actor=actor.id,
        decision="validated", notes=reason,
    )
    request_id = registry.store.save_promotion_request(
        skill_id=skill_id, version=resolved_version, requested_by=actor.id,
        reason=reason, evaluation_id=evaluation["id"], status="pending",
    )
    registry.store.append_event("skill.promotion_requested", skill_id=skill_id, version=resolved_version,
                                data={"requestId": request_id, "actor": actor.id})
    return {"ok": True, "requestId": request_id, "status": "validated"}


def approve_promotion(
    registry: SkillRegistry,
    *,
    request_id: str,
    actor: Actor,
    notes: str = "",
) -> dict[str, Any]:
    denied = _require(actor, "skill.enable")
    if denied:
        return denied
    requests = [r for r in registry.store.list_promotion_requests(limit=500) if r["id"] == request_id]
    if not requests:
        return {"ok": False, "error": "promotion request not found"}
    request = requests[0]
    if request["status"] != "pending":
        return {"ok": False, "error": f"promotion request is already {request['status']}"}

    skill_id = request["skillId"]
    version = request["version"]
    report = registry.validate(skill_id, version)
    if not report["ok"]:
        return {"ok": False, "error": "skill failed validation", "validation": report}

    registry.store.set_version_status(skill_id, version, "enabled", evaluation_status="passed")
    registry.store.set_latest_version(skill_id, version)
    registry.store.decide_promotion(request_id, "approved")
    registry.store.save_review(skill_id=skill_id, version=version, actor=actor.id,
                               decision="approved", notes=notes)
    registry.store.append_event("skill.enabled", skill_id=skill_id, version=version,
                                data={"requestId": request_id, "actor": actor.id})
    return {"ok": True, "skillId": skill_id, "version": version, "status": "enabled"}


def reject_promotion(
    registry: SkillRegistry,
    *,
    request_id: str,
    actor: Actor,
    reason: str,
) -> dict[str, Any]:
    denied = _require(actor, "skill.review")
    if denied:
        return denied
    requests = [r for r in registry.store.list_promotion_requests(limit=500) if r["id"] == request_id]
    if not requests:
        return {"ok": False, "error": "promotion request not found"}
    request = requests[0]
    registry.store.decide_promotion(request_id, "rejected")
    registry.store.save_review(skill_id=request["skillId"], version=request["version"],
                               actor=actor.id, decision="rejected", notes=reason)
    registry.store.set_version_status(request["skillId"], request["version"], "rejected")
    return {"ok": True, "requestId": request_id, "status": "rejected"}


def rollback(
    registry: SkillRegistry,
    *,
    skill_id: str,
    to_version: str,
    actor: Actor,
    reason: str,
) -> dict[str, Any]:
    """Re-point a skill at a prior version. Nothing is deleted; the change is
    recorded as a review so the rollback itself is auditable."""
    denied = _require(actor, "skill.enable")
    if denied:
        return denied
    stored = registry.store.get_version(skill_id, to_version)
    if stored is None:
        return {"ok": False, "error": f"version {to_version!r} does not exist for {skill_id!r}"}
    registry.store.set_latest_version(skill_id, to_version)
    registry.store.set_version_status(skill_id, to_version, "enabled", evaluation_status=stored["evaluationStatus"])
    registry.store.save_review(skill_id=skill_id, version=to_version, actor=actor.id,
                               decision="rollback", notes=reason)
    registry.store.append_event("skill.enabled", skill_id=skill_id, version=to_version,
                                data={"rollback": True, "reason": reason, "actor": actor.id})
    return {"ok": True, "skillId": skill_id, "version": to_version, "status": "enabled"}


__all__ = [
    "approve_promotion",
    "reject_promotion",
    "request_promotion",
    "rollback",
]
