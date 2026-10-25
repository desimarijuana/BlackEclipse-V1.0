"""Graph runtime routes — compile, run, inspect, cancel.

Operator-gated like every other runtime surface. The IR is re-validated here
(pydantic) before it reaches the compiler; a graph that fails to compile is
returned as ``400`` WITH its plan and diagnostics, so the UI can show exactly
what is wrong instead of a bare error string.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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


class SubworkflowPayload(BaseModel):
    id: str
    version: int = Field(ge=1)
    ir: dict[str, Any]


def _bundle(entries: list[SubworkflowPayload]) -> dict[str, Any]:
    """Validate the front-door subworkflow bundle and key it by id@version."""
    bundle: dict[str, Any] = {}
    for entry in entries:
        sub_ir = _parse_ir(entry.ir)
        if sub_ir.id != entry.id:
            raise HTTPException(
                status_code=400,
                detail=f"Subworkflow bundle entry {entry.id}@{entry.version} contains IR id {sub_ir.id}.",
            )
        bundle[f"{entry.id}@{entry.version}"] = sub_ir
    return bundle


class CompileRequest(BaseModel):
    ir: dict[str, Any]
    subworkflows: list[SubworkflowPayload] = Field(default_factory=list)


class RunRequest(BaseModel):
    ir: dict[str, Any]
    workflowVersion: Optional[int] = Field(default=None, alias="workflowVersion")  # noqa: N815
    testRun: bool = Field(default=True, alias="testRun")  # noqa: N815
    grantedCapabilities: list[str] = Field(default_factory=list, alias="grantedCapabilities")  # noqa: N815
    allowNetwork: bool = Field(default=False, alias="allowNetwork")  # noqa: N815
    allowTrading: bool = Field(default=False, alias="allowTrading")  # noqa: N815
    subworkflows: list[SubworkflowPayload] = Field(default_factory=list)
    input: Any = None

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
    plan = _graph_service().compile(ir, subworkflows=_bundle(body.subworkflows))
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
            subworkflows=_bundle(body.subworkflows),
            run_input=body.input,
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


@router.get("/graphs/runs/{run_id}/stream")
async def stream_run(
    run_id: str,
    request: Request,
    after: int = 0,
    _: bool = Depends(require_operator),
) -> StreamingResponse:
    """SSE for one graph run: replay persisted events, then tail new ones.

    The DB is the stream's source of truth, so a late subscriber, a reconnecting
    `EventSource` (Last-Event-ID) and a finished run all see the same ordered
    log. The stream ends with a `stream.end` data frame once the run is terminal.
    """
    graph = _graph_service()
    if graph.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        last_id = max(int(after), int(request.headers.get("last-event-id") or 0))
    except (TypeError, ValueError):
        last_id = max(0, after)

    async def frames():
        nonlocal last_id
        last_write = time.monotonic()
        while True:
            events = graph.events_since(run_id, last_id)
            for event in events:
                last_id = max(last_id, int(event["id"]))
                yield f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"
                last_write = time.monotonic()
            record = graph.get_run(run_id)
            if record is None:
                yield 'data: {"kind":"stream.error","message":"run not found"}\n\n'
                break
            if record.get("status") in ("succeeded", "failed", "cancelled"):
                # Drain anything written between the status read and now.
                for event in graph.events_since(run_id, last_id):
                    last_id = max(last_id, int(event["id"]))
                    yield f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"
                yield 'data: {"kind":"stream.end"}\n\n'
                break
            if time.monotonic() - last_write > 10:
                yield ": keep-alive\n\n"
                last_write = time.monotonic()
            await asyncio.sleep(0.25)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
