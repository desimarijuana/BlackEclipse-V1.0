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
