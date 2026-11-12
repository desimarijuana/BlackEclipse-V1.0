"""Observability HTTP routes — `/observability/*`.

Operator-gated reads over the process observability hub: status, diagnostics,
Prometheus scrape, health, traces, run trajectories, errors, costs, anomalies,
SLOs, metrics and the active configuration. Endpoints are thin adapters over the
SAME hub the runtime records into; they never mutate runtime state.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..deps import require_operator, service
from ..observability.dashboard import render_dashboard

router = APIRouter(tags=["observability"], prefix="/observability")


def _hub():
    hub = getattr(service, "observability", None)
    if hub is None:
        raise HTTPException(status_code=503, detail="observability is unavailable")
    return hub


@router.get("/status")
def observability_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_hub().status()}


@router.get("/diagnostics")
def observability_diagnostics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_hub().diagnostics()}


@router.get("/config")
def observability_config(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **(_hub().config.to_dict())}


@router.get("/health")
def observability_health(
    only: Optional[str] = Query(default=None, description="comma-separated subsystem names"),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    names = [n.strip() for n in only.split(",") if n.strip()] if only else None
    return {"success": True, **_hub().health.report(only=names).to_dict()}


@router.get("/metrics")
def observability_metrics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_hub().metrics.snapshot()}


@router.get("/metrics/prometheus")
def observability_prometheus(_: bool = Depends(require_operator)) -> Response:
    hub = _hub()
    hub.refresh_use_metrics()
    return Response(content=hub.metrics.render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/traces")
def observability_traces(
    limit: int = Query(default=50, ge=1, le=500),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, "traceIds": _hub().recent_traces(limit)}


@router.get("/traces/{trace_id}")
def observability_trace(trace_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    spans = _hub().get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail="trace not found")
    return {"success": True, "traceId": trace_id, "spans": spans}


@router.get("/traces/{trace_id}/trajectory")
def observability_trajectory(trace_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    trajectory = _hub().trajectory(trace_id)
    if not trajectory.get("found"):
        raise HTTPException(status_code=404, detail="trace not found")
    return {"success": True, **trajectory}


@router.get("/errors")
def observability_errors(
    limit: int = Query(default=100, ge=1, le=500),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"success": True, "errors": _hub().errors(limit)}


@router.get("/costs")
def observability_costs(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_hub().costs.summary()}


@router.get("/costs/runs/{run_id}")
def observability_run_cost(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "runId": run_id, **_hub().costs.run_cost(run_id)}


@router.get("/anomalies")
def observability_anomalies(_: bool = Depends(require_operator)) -> dict[str, Any]:
    hub = _hub()
    return {"success": True, "anomaly": hub.anomaly.snapshot(), "loops": hub.loops.snapshot()}


@router.get("/slos")
def observability_slos(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_hub().slos.report()}


@router.get("/release-report")
def observability_release_report(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """C7: the machine-readable report `npm run gate:slo` consumes."""
    hub = _hub()
    hub.refresh_use_metrics()
    return {"success": True, **hub.release_report()}


@router.get("/dashboard", response_class=HTMLResponse)
def observability_dashboard(_: bool = Depends(require_operator)) -> HTMLResponse:
    """C7: one card per SLO, with budget, burn and failure classes."""
    hub = _hub()
    hub.refresh_use_metrics()
    return HTMLResponse(render_dashboard(hub.release_report()))


class ExporterAction(BaseModel):
    name: str


@router.post("/exporters/reset")
def observability_reset_exporter(body: ExporterAction, _: bool = Depends(require_operator)) -> dict[str, Any]:
    hub = _hub()
    for exporter in hub._exporters:  # noqa: SLF001 - deliberate operator action
        if exporter.name == body.name:
            exporter.force_circuit_reset()
            return {"success": True, "name": body.name, "circuitReset": True}
    raise HTTPException(status_code=404, detail=f"exporter {body.name!r} not found")


__all__ = ["router"]
