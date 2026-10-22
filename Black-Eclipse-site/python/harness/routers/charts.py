"""The chart route group — draw a chart from a spec.

The front door (Next.js) is the only caller: it validates the request, calls
this route, and hands the browser the recorded artifact. The route never
serves a file from a caller-supplied path — the picture is drawn here, then
recorded in the Artifact Center, and the browser fetches it back through the
artifact route like any other produced file.

Every route carries `require_operator`, exactly as the artifact route group
does: a directly reachable runtime must not draw pictures for an
unauthenticated caller.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..charts.render import (
    CHART_RENDER_FAILED,
    CHART_RENDER_UNAVAILABLE,
    CHART_SPEC_INVALID,
    ChartRenderError,
)
from ..charts.service import register_chart_artifact, render_spec
from ..charts.spec import ChartSpec
from ..deps import require_operator, service

router = APIRouter(tags=["charts"])


@router.post("/charts/render")
async def render_chart_route(
    body: dict[str, Any] = Body(...),
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Draw a chart and record it in the Artifact Center.

    The body IS the chart spec — the same contract the `python_chart` tool
    takes, so there is exactly one shape to learn and one validator. A spec
    that does not satisfy its kind is a 400 with the missing part named; a
    missing matplotlib is a 503 (the picture cannot be drawn here); anything
    else that goes wrong is a 500 that says what failed.
    """
    try:
        spec = ChartSpec(**body)
    except Exception as exc:  # noqa: BLE001 - a malformed spec is a bad request
        raise HTTPException(
            status_code=400,
            detail={"code": CHART_SPEC_INVALID, "message": str(exc)},
        ) from exc

    try:
        rendered = render_spec(spec)
    except ChartRenderError as exc:
        status = 503 if exc.code == CHART_RENDER_UNAVAILABLE else 500
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": exc.reason},
        ) from exc

    ctx = service
    entry = register_chart_artifact(ctx, rendered, source_tool="chart_render")
    figure = rendered.to_dict()
    artifact_id = getattr(entry, "id", None) if entry is not None else None
    if artifact_id:
        figure["artifactId"] = artifact_id
    return {
        "status": "OK",
        "figure": figure,
        # The LIVE chart: a Plotly figure the browser renders (vector, zoomable).
        **({"chart": rendered.chart} if rendered.chart else {}),
        "artifact": {
            "id": artifact_id,
            "name": rendered.name,
            "bytes": rendered.bytes,
            "sha256": rendered.sha256,
            # The browser fetches the picture back through the artifact route;
            # the chart engine never serves bytes from a caller-supplied path.
            "downloadUrl": f"/artifacts/{artifact_id}/download" if artifact_id else None,
        },
    }


@router.get("/charts/kinds")
async def list_chart_kinds(_: None = Depends(require_operator)) -> dict[str, Any]:
    """The chart kinds the engine can draw, and what each one needs."""
    from ..charts.tools import CHART_KINDS  # noqa: PLC0415

    return {"status": "OK", "kinds": list(CHART_KINDS)}


__all__ = ["router"]
