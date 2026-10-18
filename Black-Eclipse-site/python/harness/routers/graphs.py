"""Graph runtime routes — compile, run, inspect, cancel.

Operator-gated like every other runtime surface. The IR is re-validated here
(pydantic) before it reaches the compiler; a graph that fails to compile is
returned as ``400`` WITH its plan and diagnostics, so the UI can show exactly
what is wrong instead of a bare error string.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from ..deps import require_operator, service
from ..graph_runtime.compiler import RunGrants as GraphRunGrants
from ..graph_runtime.model import WorkflowIR
from ..graph_runtime.service import GraphCompileError, GraphService

router = APIRouter(tags=["graphs"])


def _graph_service() -> GraphService:
    graph_service = getattr(service, "graphs", None)
    if graph_service is None:
        from ..graph_runtime.bootstrap import install_graph_layer  # noqa: PLC0415

        install_graph_layer(service)
        graph_service = getattr(service, "graphs", None)
    if graph_service is None:
        raise HTTPException(status_code=503, detail="Graph runtime unavailable")
    return graph_service


def _parse_ir(payload: Any) -> WorkflowIR:
    try:
        return WorkflowIR.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", ()))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workflow IR{f' at {location}' if location else ''}: {first.get('msg', 'invalid')}",
        ) from exc


class CompileRequest(BaseModel):
    ir: dict[str, Any]


class RunRequest(BaseModel):
    ir: dict[str, Any]
    workflowVersion: Optional[int] = Field(default=None, alias="workflowVersion")  # noqa: N815
    testRun: bool = Field(default=True, alias="testRun")  # noqa: N815
    grantedCapabilities: list[str] = Field(default_factory=list, alias="grantedCapabilities")  # noqa: N815
    allowNetwork: bool = Field(default=False, alias="allowNetwork")  # noqa: N815
    allowTrading: bool = Field(default=False, alias="allowTrading")  # noqa: N815

    model_config = {"populate_by_name": True}


def _grants(body: RunRequest) -> GraphRunGrants:
    return GraphRunGrants(
        test_run=body.testRun,
        granted_capabilities=frozenset(body.grantedCapabilities),
        allow_network=body.allowNetwork,
        allow_trading=body.allowTrading,
    )


@router.post("/graphs/compile")
def compile_graph(body: CompileRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ir = _parse_ir(body.ir)
    plan = _graph_service().compile(ir)
    return {"plan": plan.model_dump(by_alias=True)}


@router.post("/graphs/runs", status_code=201)
def start_run(body: RunRequest, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ir = _parse_ir(body.ir)
    owner = (request.headers.get("x-harness-user") or "local").strip() or "local"
    try:
        run = _graph_service().start_run(
            ir,
            workflow_version=body.workflowVersion,
            owner_id=owner,
            grants=_grants(body),
        )
    except GraphCompileError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "graph_not_executable",
                "message": str(exc),
                "plan": exc.plan.model_dump(by_alias=True),
            },
        ) from exc
    return {"run": run}


@router.get("/graphs/runs")
def list_runs(
    workflowId: Optional[str] = None,  # noqa: N803
    limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"runs": _graph_service().list_runs(workflowId, limit)}


@router.get("/graphs/runs/{run_id}")
def get_run(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    run = _graph_service().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run}


@router.post("/graphs/runs/{run_id}/cancel")
def cancel_run(run_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    run = _graph_service().cancel(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run}


__all__ = ["router"]
