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

import base64
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..charts.codegen import generate_source
from ..charts.render import (
    CHART_RENDER_FAILED,
    CHART_RENDER_UNAVAILABLE,
    CHART_SPEC_INVALID,
    ChartRenderError,
)
from ..charts.service import register_chart_artifact, render_spec
from ..charts.source import ChartSourceError, resolve_data_sources
from ..charts.spec import ChartSpec
from ..deps import require_operator, service

router = APIRouter(tags=["charts"])


def _market_ctx() -> Any:
    """The context a chart's named source is fetched through.

    Outside a run the gateway has no bridge (it is bound per run), so the
    server bridge is bound here: a chart that names its series is drawn from
    the same market data a quote would come from.
    """
    gateway = getattr(service, "server_market_gateway", None)
    if callable(gateway):
        gateway = gateway()
    if gateway is None:
        return service
    return _GatewayCtx(service, gateway)


class _GatewayCtx:
    """A tiny context that carries the gateway the chart's source needs."""

    def __init__(self, ctx: Any, gateway: Any) -> None:
        self._ctx = ctx
        self.market_gateway = gateway

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)


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

    # A chart may NAME its series instead of carrying it. The engine fetches
    # it through the same market gateway every price comes from, so a 250-point
    # chart never has to travel inside a message.
    try:
        spec = await resolve_data_sources(spec, _market_ctx())
    except ChartSourceError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.reason},
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
    payload: dict[str, Any] = {
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
    if not artifact_id:
        # The Artifact Center is best-effort (a locked/absent database must not
        # make a drawn chart disappear). When the picture could not be stored,
        # return it inline so the UI still shows the chart; the artifact URL is
        # simply absent. A chart is never replaced by a "could not be stored"
        # error box when the bytes exist.
        payload["image"] = {
            "mimeType": "image/png",
            "data": base64.b64encode(rendered.png).decode("ascii"),
        }
    return payload


@router.post("/charts/code")
async def chart_code_route(
    body: dict[str, Any] = Body(...),
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Return an editable matplotlib starting script for a chart spec.

    The spec is validated and its named series are resolved exactly as the render
    route does, so the generated program reads the SAME numbers the picture was
    drawn from. The script is a starting point; `unsupported` names anything the
    template could not reproduce.
    """
    try:
        spec = ChartSpec(**body)
    except Exception as exc:  # noqa: BLE001 - a malformed spec is a bad request
        raise HTTPException(
            status_code=400,
            detail={"code": CHART_SPEC_INVALID, "message": str(exc)},
        ) from exc
    try:
        spec = await resolve_data_sources(spec, _market_ctx())
    except ChartSourceError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.reason},
        ) from exc

    source, unsupported = generate_source(spec)
    # The resolved spec rides along: a chart that NAMED its series now carries
    # the fetched data, so the cell's `inputs["chart"]` matches the script.
    return {
        "status": "OK",
        "source": source,
        "unsupported": unsupported,
        "spec": spec.to_dict(),
    }


@router.get("/charts/kinds")
async def list_chart_kinds(_: None = Depends(require_operator)) -> dict[str, Any]:
    """The chart kinds the engine can draw, and what each one needs."""
    from ..charts.tools import CHART_KINDS  # noqa: PLC0415

    return {"status": "OK", "kinds": list(CHART_KINDS)}


__all__ = ["router"]
