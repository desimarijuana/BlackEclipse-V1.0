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

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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


class RenderChartBody(BaseModel):
    """The chart spec as the front door sends it."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., min_length=1, max_length=32)
    title: Optional[str] = Field(default=None, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    footnote: Optional[str] = Field(default=None, max_length=300)
    source: Optional[str] = Field(default=None, max_length=200)
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    categories: list[str] = Field(default_factory=list)
    series: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    points: list[dict[str, Any]] = Field(default_factory=list)
    matrix: list[list[float]] = Field(default_factory=list)
    row_labels: list[str] = Field(default_factory=list)
    col_labels: list[str] = Field(default_factory=list)
    candles: list[dict[str, Any]] = Field(default_factory=list)
    stacked: bool = False
    normalized: bool = False
    smooth: bool = False
    show_points: bool = False
    theme: str = Field(default="eclipse-dark", max_length=32)
    width: int = Field(default=960, ge=320, le=2_400)
    height: int = Field(default=440, ge=240, le=2_400)


@router.post("/charts/render")
async def render_chart_route(
    body: RenderChartBody,
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Draw a chart and record it in the Artifact Center.

    A spec that does not satisfy its kind is a 400 with the missing part
    named; a missing matplotlib is a 503 (the picture cannot be drawn here);
    anything else that goes wrong is a 500 that says what failed.
    """
    payload = body.model_dump(exclude_none=True)
    try:
        spec = ChartSpec(**payload)
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


__all__ = ["RenderChartBody", "router"]
