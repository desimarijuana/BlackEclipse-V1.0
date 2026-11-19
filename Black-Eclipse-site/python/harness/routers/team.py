"""Bot-team orchestration route group.

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — this module never imports `main`.

EVERY route carries `require_operator` (reads AND mutations), exactly as the A2A,
tasks and jobs route groups do. The routes are a thin shell over `TeamService`;
they never mutate state themselves, so the same registry/budget/permission/review
rules apply to HTTP callers as to the agent tools.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import require_operator, service
from ..institution.preset import bot_specs, build_team, descriptor as preset_descriptor
from ..team.model import TeamDefinition
from ..team.service import TeamError, TeamService

router = APIRouter(tags=["team"])


def _team() -> TeamService:
    team = getattr(service, "team", None)
    if team is None:
        from ..team.bootstrap import install_team_layer  # noqa: PLC0415

        install_team_layer(service)
        team = getattr(service, "team", None)
    if team is None:
        raise HTTPException(status_code=503, detail="team runtime unavailable")
    return team


def _raise(exc: Exception) -> None:
    if isinstance(exc, TeamError):
        code = 404 if exc.code in ("TEAM_NOT_FOUND",) else 400
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.reason})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


class TeamRunBody(BaseModel):
    team: TeamDefinition
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815
    rootRunId: Optional[str] = None  # noqa: N815


class TeamValidateBody(BaseModel):
    team: TeamDefinition


class ReviewBody(BaseModel):
    reviewerAgentId: str = "qa-agent"  # noqa: N815


class InstitutionRunBody(BaseModel):
    objective: str = ""
    universe: str = ""
    horizon: str = ""
    constraints: list[str] = []
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815


@router.get("/team/presets")
async def list_presets(_: Any = Depends(require_operator)) -> dict[str, Any]:
    """The stable preset catalogue (no objective required)."""
    return {"success": True, "presets": [preset_descriptor()]}


@router.get("/team/presets/institution")
async def get_institution_preset(
    objective: str = "",
    universe: str = "",
    horizon: str = "",
    constraints: str = "",
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """The filled team definition + bot specs for one committee run."""
    parsed = [part.strip() for part in constraints.split(",") if part.strip()]
    team = build_team(
        objective, universe=universe, horizon=horizon, constraints=parsed,
    )
    return {
        "success": True,
        "preset": preset_descriptor(),
        "team": team.model_dump(by_alias=True),
        "bots": bot_specs(),
    }


@router.post("/team/presets/institution/run")
async def run_institution_preset(
    body: InstitutionRunBody, _: Any = Depends(require_operator),
) -> dict[str, Any]:
    """Build and start the committee in one call (thin shell over TeamService)."""
    team = build_team(
        body.objective, universe=body.universe, horizon=body.horizon,
        constraints=body.constraints,
    )
    try:
        run = await _team().run(team, model_settings=body.modelSettings)
        return {"success": True, "teamRun": run.model_dump(by_alias=True)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/team/validate")
async def validate_team(body: TeamValidateBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    """Every reason a team cannot run, so the desk builder refuses before save."""
    service_ = _team()
    return {
        "success": True,
        "errors": service_.validate(body.team),
        "stages": [subtask.id for subtask in body.team.subtasks],
    }


@router.post("/team/runs")
async def start_run(body: TeamRunBody, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        run = await _team().run(
            body.team, root_run_id=body.rootRunId, model_settings=body.modelSettings,
        )
        return {"success": True, "teamRun": run.model_dump(by_alias=True)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/team/runs")
async def list_runs(status: Optional[str] = None, _: Any = Depends(require_operator)) -> dict[str, Any]:
    runs = _team().list_runs(limit=100, status=status)
    return {"success": True, "runs": [r.model_dump(by_alias=True) for r in runs]}


@router.get("/team/runs/by-root/{root_run_id}")
async def get_run_by_root(root_run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    """Resolve a desk's stage timeline from its automation execution run id."""
    try:
        run = _team().get_run_by_root(root_run_id)
        return {"success": True, "teamRun": _team().status(run.id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/team/runs/{run_id}")
async def get_run(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "teamRun": _team().status(run_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/team/runs/{run_id}/result")
async def get_result(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "result": _team().synthesize(run_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/team/runs/{run_id}/review")
async def review_run(run_id: str, body: ReviewBody,
                     _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        report = await _team().finalize(run_id, reviewer_agent_id=body.reviewerAgentId)
        return {"success": True, "review": report}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/team/runs/{run_id}/cancel")
async def cancel_run(run_id: str, _: Any = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "cancel": await _team().cancel(run_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/team/status")
async def status(_: Any = Depends(require_operator)) -> dict[str, Any]:
    runs = _team().list_runs(limit=200)
    return {
        "success": True,
        "status": {"runs": len(runs), "active": len([r for r in runs if r.status.value in
                                                      ("PLANNING", "RUNNING", "REVIEWING", "REPAIRING")])},
    }
