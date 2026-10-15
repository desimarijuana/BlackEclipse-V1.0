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


class ReviewBody(BaseModel):
    reviewerAgentId: str = "qa-agent"  # noqa: N815


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
