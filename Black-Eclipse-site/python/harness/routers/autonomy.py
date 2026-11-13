"""W4 autonomy routes: goals, verdicts, loops/heartbeats, health.

Operator-gated (transport/token only) like `/code/*` and `/recovery/*`. The
router owns no execution: it delegates to `AutonomyService`, which rides the one
task scheduler and the one automation tick.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..goals.bootstrap import install_autonomy_layer
from ..goals.goal_runtime import GoalError

router = APIRouter(tags=["autonomy"])


def _autonomy() -> Any:
    layer = getattr(service, "autonomy", None)
    if layer is None:
        install_autonomy_layer(service)
        layer = getattr(service, "autonomy", None)
    if layer is None:
        raise HTTPException(status_code=503, detail="autonomy runtime is unavailable")
    return layer


def _goal_error(exc: GoalError) -> HTTPException:
    if exc.code.endswith("_NOT_FOUND"):
        return HTTPException(status_code=404, detail=exc.message)
    if exc.code in ("GOAL_NOT_ACTIVE", "TURN_BUDGET", "LOOP_TERMINAL"):
        return HTTPException(status_code=409, detail=exc.message)
    if exc.code in ("MISSING_OBJECTIVE", "MISSING_SESSION", "MISSING_PROMPT",
                    "INVALID_LOOP_KIND", "INVALID_LOOP_MODE", "INVALID_CONTRACT",
                    "DUPLICATE_GATE", "WORKSPACE_REQUIRED_FOR_GATES",
                    "GATES_REQUIRE_EXECUTION", "GATE_WORKSPACE_MISMATCH"):
        return HTTPException(status_code=422, detail=exc.message)
    return HTTPException(status_code=400, detail=exc.message)


class GoalModel(BaseModel):
    provider: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=200)
    baseUrl: Optional[str] = Field(None, max_length=500)  # noqa: N815


class CreateGoalRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=8_000)
    acceptance: list[str] = Field(default_factory=list, max_length=24)
    constraints: list[str] = Field(default_factory=list, max_length=24)
    deliverables: list[str] = Field(default_factory=list, max_length=24)
    boundaries: list[str] = Field(default_factory=list, max_length=24)
    stopWhen: list[str] = Field(default_factory=list, max_length=24)  # noqa: N815
    gates: list[dict[str, Any]] = Field(default_factory=list, max_length=24)
    maxTurns: Optional[int] = Field(None, ge=1, le=100)  # noqa: N815
    sessionId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    workspaceId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    autonomy: Optional[str] = Field(None, max_length=40)
    model: Optional[GoalModel] = None
    start: bool = True


class CreateLoopRequest(BaseModel):
    sessionId: str = Field(min_length=1, max_length=200)  # noqa: N815
    kind: str = Field("loop", max_length=20)
    prompt: str = Field(min_length=1, max_length=8_000)
    intervalSeconds: Optional[int] = Field(None, ge=30, le=86_400)  # noqa: N815
    mode: str = Field("fixed", max_length=20)
    maxTicks: Optional[int] = Field(None, ge=1, le=1_000)  # noqa: N815
    workspaceId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    model: Optional[GoalModel] = None


class DecisionRequest(BaseModel):
    reason: str = Field("", max_length=400)


# ── Goals ─────────────────────────────────────────────────────────────────────
@router.get("/autonomy/health")
def autonomy_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "health": _autonomy().health()}


@router.post("/goals")
def create_goal(
    body: CreateGoalRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    contract = {
        "objective": body.objective,
        "acceptance": body.acceptance,
        "constraints": body.constraints,
        "deliverables": body.deliverables,
        "boundaries": body.boundaries,
        "stopWhen": body.stopWhen,
    }
    model = body.model.model_dump() if body.model is not None else None
    try:
        goal = _autonomy().create_goal(
            body.objective, contract=contract, gates=body.gates,
            max_turns=body.maxTurns, session_id=body.sessionId,
            workspace_id=body.workspaceId, model=model,
            autonomy=body.autonomy or "edit_verify", start=body.start,
        )
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "goal": goal.to_dict()}


@router.get("/goals")
def list_goals(
    sessionId: Optional[str] = None,  # noqa: N803
    status: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    goals = _autonomy().list_goals(session_id=sessionId, status=status)
    return {"success": True, "goals": [goal.to_dict() for goal in goals]}


@router.get("/goals/{goal_id}")
def get_goal(goal_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        goal = _autonomy().get_goal(goal_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "goal": goal.to_dict()}


@router.get("/goals/{goal_id}/verdicts")
def goal_verdicts(goal_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        _autonomy().get_goal(goal_id)
        verdicts = _autonomy().verdicts(goal_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "verdicts": verdicts, "goalId": goal_id}


@router.post("/goals/{goal_id}/pause")
def pause_goal(
    goal_id: str, body: Optional[DecisionRequest] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    reason = body.reason if body is not None else "operator"
    try:
        goal = _autonomy().pause_goal(goal_id, reason)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "goal": goal.to_dict()}


@router.post("/goals/{goal_id}/resume")
def resume_goal(goal_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        goal = _autonomy().resume_goal(goal_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "goal": goal.to_dict()}


@router.post("/goals/{goal_id}/cancel")
def cancel_goal(
    goal_id: str, body: Optional[DecisionRequest] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        goal = _autonomy().cancel_goal(goal_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "goal": goal.to_dict()}


# ── Loops / heartbeats ────────────────────────────────────────────────────────
@router.post("/loops")
def create_loop(
    body: CreateLoopRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    model = body.model.model_dump() if body.model is not None else None
    try:
        loop = _autonomy().create_loop(
            body.sessionId, kind=body.kind, prompt=body.prompt,
            interval_seconds=body.intervalSeconds, mode=body.mode,
            max_ticks=body.maxTicks, model=model,
            workspace_id=body.workspaceId,
        )
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "loop": loop.to_dict()}


@router.get("/loops")
def list_loops(
    sessionId: Optional[str] = None,  # noqa: N803
    status: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    loops = _autonomy().list_loops(session_id=sessionId, status=status)
    return {"success": True, "loops": [loop.to_dict() for loop in loops]}


@router.post("/loops/{loop_id}/pause")
def pause_loop(
    loop_id: str, body: Optional[DecisionRequest] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    reason = body.reason if body is not None else "operator"
    try:
        loop = _autonomy().pause_loop(loop_id, reason)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "loop": loop.to_dict()}


@router.post("/loops/{loop_id}/resume")
def resume_loop(loop_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        loop = _autonomy().resume_loop(loop_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "loop": loop.to_dict()}


@router.post("/loops/{loop_id}/cancel")
def cancel_loop(loop_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        loop = _autonomy().cancel_loop(loop_id)
    except GoalError as exc:
        raise _goal_error(exc) from exc
    return {"success": True, "loop": loop.to_dict()}
