"""Supervised-autonomy routes (RSL v4 P6).

Kept in their own module so `routers/evolution.py` does not grow past its size
ratchet. Every route is operator-gated; the decide route is a PREVIEW and never
activates anything.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_operator, service

router = APIRouter(tags=["evolution"])


def _loop() -> Any:
    loop = getattr(service, "_rsl_loop", None)
    if loop is None:
        raise HTTPException(status_code=503, detail="RSL loop unavailable")
    return loop


@router.get("/evolution/rsl/autonomy")
def rsl_autonomy_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The supervised-autonomy level, risk ceiling and kill-switch state."""
    return {"success": True, **_loop().autonomy_status()}


@router.post("/evolution/rsl/autonomy/pause")
def pause_rsl_autonomy(
    body: Optional[dict[str, Any]] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """The emergency stop: no automatic decision runs while this is paused."""
    reason = str((body or {}).get("reason") or "")
    return {"success": True, "killSwitch": _loop().pause_autonomy(reason)}


@router.post("/evolution/rsl/autonomy/resume")
def resume_rsl_autonomy(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "killSwitch": _loop().resume_autonomy()}


@router.post("/evolution/rsl/autonomy/decide")
def decide_rsl_autonomy(
    body: dict[str, Any],
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Preview the admission decision for a candidate. It never activates."""
    try:
        activations = int(body.get("activationsToday") or 0)
    except (TypeError, ValueError):
        activations = 0
    decision = _loop().decide_autonomy(
        risk=str(body.get("risk") or ""),
        delta_ci_low=body.get("deltaCiLow"),
        critical_regression=bool(body.get("criticalRegression")),
        canary_ok=bool(body.get("canaryOk", True)),
        replay_ok=bool(body.get("replayOk", True)),
        predicted_delta=body.get("predictedDelta"),
        measured_delta=body.get("measuredDelta"),
        activations_today=max(0, activations),
        changed=bool(body.get("changed", True)),
    )
    return {"success": True, "decision": decision, "activates": False}


@router.get("/evolution/capabilities")
def capability_contract(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """The truthful autonomy matrix. Marketing and agents read the same contract."""
    executor = getattr(service, "_self_modification", None)
    status = executor.status() if executor is not None else {}
    return {
        "success": True,
        "selfImproving": True,
        "mode": status.get("mode"),
        "autonomous": {
            "readOnlySkillCreation": True,
            "memoryPolicyLearning": True,
            "crossSessionRecall": True,
            "codePatchSandbox": True,
            "codeMerge": False,
            "readOnlyToolWidening": False,
            "effectfulToolUse": False,
            "financialActions": False,
            "policyChanges": False,
        },
        "operatorRequired": [
            "effectful/financial actions",
            "tool widening",
            "code promotion/merge",
            "policy and guardrail changes",
            "skill_create and skill_update",
        ],
        "statement": (
            "Eclipse is a bounded self-improving agent: autonomous read-only skill "
            "creation, policy-governed memory, and cross-session recall; effectful "
            "and financial actions and code merges remain operator-approved."
        ),
    }


@router.get("/evolution/learning-loop")
def learning_loop_status(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """One read-only view of the autonomous read-only learning loop."""
    candidates = service.skill_store.list_candidates(limit=1000)
    candidate_counts: dict[str, int] = {}
    for row in candidates:
        status = str(row.get("status") or "unknown")
        candidate_counts[status] = candidate_counts.get(status, 0) + 1
    skills = service.skill_store.list_skills()
    learned = [row for row in skills if str(row.get("id") or "").startswith("learned.")]
    learned_counts: dict[str, int] = {}
    for row in learned:
        status = str(row.get("status") or "unknown")
        learned_counts[status] = learned_counts.get(status, 0) + 1
    executor = getattr(service, "_self_modification", None)
    self_mod = executor.status() if executor is not None else {"running": False}
    return {
        "success": True,
        "mode": self_mod.get("mode"),
        "selfModification": self_mod,
        "candidates": candidate_counts,
        "learnedSkills": learned_counts,
        "enabledLearnedSkills": [
            row.get("id") for row in learned if str(row.get("status") or "") == "enabled"
        ],
        "automatic": {
            "drafts": "self-modification tick: auto_draft_ready_candidates",
            "evaluation": "candidate accept path + usage evaluation after 3 uses",
            "enable": "read-only learned skills only, with TTL/audit",
            "effectful": "operator-approved only",
        },
    }


@router.get("/evolution/widening")
def widening_list(
    limit: int = 100, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_queue import WideningProposalStore  # noqa: PLC0415

    return {"success": True, "proposals": WideningProposalStore(service.store).list(limit=limit)}


@router.post("/evolution/widening/stage")
def widening_stage(
    body: Optional[dict[str, Any]] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..agents import get_agent  # noqa: PLC0415
    from ..self_improvement.widening_queue import stage_proposals  # noqa: PLC0415

    agent = get_agent("eclipse-agent")
    return {
        "success": True,
        **stage_proposals(
            service.store, service.registry, agent.tools or (),
            limit=int((body or {}).get("limit") or 5),
            staged_by="operator",
            ttl_days=int((body or {}).get("ttlDays") or 14),
        ),
    }


@router.post("/evolution/widening/{proposal_id}/evidence")
def widening_evidence(
    proposal_id: str,
    body: dict[str, Any],
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_queue import WideningProposalStore  # noqa: PLC0415

    key = str(body.get("key") or "").strip()
    proposal = WideningProposalStore(service.store).attach_evidence(
        proposal_id, key, body.get("detail") if isinstance(body.get("detail"), dict) else {},
    )
    return {
        "success": proposal is not None,
        "proposal": proposal,
        "note": "evidence only; no tool is granted or applied",
    }


@router.post("/evolution/widening/{proposal_id}/approve")
def widening_approve(
    proposal_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_queue import WideningProposalStore  # noqa: PLC0415

    proposal = WideningProposalStore(service.store).approve(proposal_id)
    return {
        "success": proposal is not None,
        "proposal": proposal,
        "note": "approved for application; no runtime surface changed by this route",
    }


@router.get("/evolution/widening/grants")
def widening_grants(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_runtime import list_grants  # noqa: PLC0415

    return {"success": True, "grants": list_grants(service.store)}


@router.post("/evolution/widening/grants/{grant_id}/revoke")
def widening_grant_revoke(
    grant_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_runtime import revoke_grant  # noqa: PLC0415

    return {"success": True, **revoke_grant(service.store, grant_id)}


@router.post("/evolution/widening/{proposal_id}/apply")
def widening_apply(
    proposal_id: str,
    body: Optional[dict[str, Any]] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_runtime import apply_proposal  # noqa: PLC0415

    return {
        "success": True,
        **apply_proposal(
            service.store, service.registry, proposal_id,
            ttl_days=int((body or {}).get("ttlDays") or 7),
            agent_id=str((body or {}).get("agentId") or "eclipse-agent"),
        ),
    }


@router.post("/evolution/widening/{proposal_id}/withdraw")
def widening_withdraw(
    proposal_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.widening_queue import WideningProposalStore  # noqa: PLC0415

    ok = WideningProposalStore(service.store).withdraw(proposal_id)
    return {"success": ok, "proposalId": proposal_id, "withdrawn": ok}


@router.get("/evolution/effectful-widening")
def effectful_widening_list(
    limit: int = 100, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.effectful_widening import EffectfulProposalStore  # noqa: PLC0415

    return {"success": True, "proposals": EffectfulProposalStore(service.store).list(limit=limit)}


@router.post("/evolution/effectful-widening/propose")
def effectful_widening_propose(
    body: dict[str, Any],
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..agents import get_agent  # noqa: PLC0415
    from ..self_improvement.effectful_widening import propose  # noqa: PLC0415

    agent = get_agent("eclipse-agent")
    result = propose(
        service.store, service.registry, str(body.get("toolName") or ""),
        justification=str(body.get("justification") or ""),
        caps=body.get("caps") if isinstance(body.get("caps"), dict) else {},
        ttl_hours=int(body.get("ttlHours") or 4),
        already_allowed=tuple(agent.tools or ()),
    )
    return {"success": bool(result.get("ok")), **result}


@router.post("/evolution/effectful-widening/{proposal_id}/approve")
def effectful_widening_approve(
    proposal_id: str,
    body: dict[str, Any],
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.effectful_widening import approve  # noqa: PLC0415

    result = approve(service.store, proposal_id, str(body.get("token") or ""))
    return {"success": bool(result.get("ok")), **result}


@router.get("/evolution/effectful-widening/grants")
def effectful_widening_grants(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.effectful_widening import list_grants  # noqa: PLC0415

    return {"success": True, "grants": list_grants(service.store)}


@router.post("/evolution/effectful-widening/grants/{grant_id}/revoke")
def effectful_widening_revoke(
    grant_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..self_improvement.effectful_widening import revoke_grant  # noqa: PLC0415

    result = revoke_grant(service.store, grant_id)
    return {"success": bool(result.get("ok")), **result}


@router.get("/evolution/tool-contracts")
def tool_contract_shadow(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Read-only inventory of widen-eligible tools. Grants nothing."""
    from ..agents import get_agent  # noqa: PLC0415
    from ..self_improvement.tool_shadow import shadow_report  # noqa: PLC0415

    agent = get_agent("eclipse-agent")
    return {
        "success": True,
        **shadow_report(service.registry, agent.tools or ()),
    }


@router.get("/evolution/self-modification")
def self_modification_status(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, **service.self_modification_status()}


@router.post("/evolution/self-modification/run")
async def self_modification_run(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, "result": await service.run_self_modification_once()}


@router.post("/evolution/self-modification/pause")
def self_modification_pause(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, **service.pause_self_modification()}


@router.post("/evolution/self-modification/resume")
def self_modification_resume(
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, **service.resume_self_modification()}


@router.post("/evolution/self-modification/revoke/{action_id}")
def self_modification_revoke(
    action_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, **service.revoke_self_modification(action_id)}


@router.post("/evolution/states/{state_id}/autonomy-apply")
async def auto_apply_surface_state(
    state_id: str, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Apply one measured L1 surface state when the policy allows.

    This is the only automatic activation path. The activation row it creates is
    the rollback handle; the kill switch and the daily budget still apply.
    """
    result = await _loop().auto_apply_surface(state_id)
    if result.get("applied") is False and result.get("reason") == "policy_refused":
        return {"success": True, **result}
    return {"success": bool(result.get("applied")), **result}


__all__ = ["router"]
