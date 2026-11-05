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
from ..graph_runtime.model import ExecutionMode, WorkflowIR
from ..graph_runtime.service import GraphCompileError, GraphService, NodeTestError

router = APIRouter(tags=["graphs"])


def _owner(request: Request) -> str:
    """The verified owner, never a caller-supplied label when auth is on."""
    try:
        from ..deps import identity_for  # noqa: PLC0415

        identity = identity_for(request)
        if identity.is_authenticated:
            if identity.user_id:
                return str(identity.user_id)[:120]
            if identity.tenant_id:
                return str(identity.tenant_id)[:120]
    except Exception:  # noqa: BLE001 - never break a route on identity resolution
        pass
    return (request.headers.get("x-harness-user") or "local").strip()[:120] or "local"


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


class PlanRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=4_000)
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815
    workflowId: Optional[str] = None  # noqa: N815

    model_config = {"populate_by_name": True}


class AssistRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=8_000)
    mode: str = Field(default="edit", pattern="^(edit|ask)$")
    ir: dict[str, Any]
    selection: Optional[dict[str, Any]] = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    lastRun: Optional[dict[str, Any]] = None  # noqa: N815
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815

    model_config = {"populate_by_name": True}


def _preview_output(value: Any) -> Any:
    if value is None:
        return None
    try:
        text = json.dumps(value, default=str)
    except Exception:  # noqa: BLE001 - a preview must never break the run result
        text = str(value)
    return text[:2_000]


def _summarize_assistant_run(run: Any) -> dict[str, Any]:
    """The model sees failures and a bounded node table, not the whole record."""
    failed = [
        {
            "nodeId": node.node_id,
            "label": node.label,
            "error": node.error,
            "errorCode": node.error_code,
        }
        for node in run.node_runs
        if node.status.value == "failed"
    ]
    return {
        "ok": run.status.value == "succeeded",
        "status": run.status.value,
        "error": run.error,
        "durationMs": run.duration_ms,
        "failed": failed,
        "nodes": [
            {
                "nodeId": node.node_id,
                "type": node.node_type,
                "status": node.status.value,
                "error": node.error,
                "durationMs": node.duration_ms,
            }
            for node in run.node_runs[:50]
        ],
        "output": _preview_output(run.output),
    }


def _assistant_runner(
    request: Request,
    model_settings: Optional[dict[str, Any]],
) -> Any:
    """Assistant-initiated execution is ALWAYS a test run.

    Network, trading and external writes are refused by the compiler; the model
    receives that refusal and tells the user to use the operator run. Credentials
    never leave memory and are never persisted with the run.
    """

    async def run(ir: WorkflowIR) -> dict[str, Any]:
        try:
            record = await asyncio.to_thread(
                _graph_service().run_sync,
                ir,
                owner_id=_owner(request),
                grants=GraphRunGrants(test_run=True),
                model_settings=model_settings,
            )
        except GraphCompileError as exc:
            return {
                "ok": False,
                "status": "refused",
                "error": str(exc),
                "diagnostics": [item.model_dump(by_alias=True) for item in exc.plan.diagnostics],
            }
        except Exception as exc:  # noqa: BLE001 - a failed run is data for the model
            return {"ok": False, "status": "error", "error": str(exc)[:500]}
        return _summarize_assistant_run(record)

    return run


class RunRequest(BaseModel):
    ir: dict[str, Any]
    workflowVersion: Optional[int] = Field(default=None, alias="workflowVersion")  # noqa: N815
    testRun: bool = Field(default=True, alias="testRun")  # noqa: N815
    grantedCapabilities: list[str] = Field(default_factory=list, alias="grantedCapabilities")  # noqa: N815
    allowNetwork: bool = Field(default=False, alias="allowNetwork")  # noqa: N815
    allowTrading: bool = Field(default=False, alias="allowTrading")  # noqa: N815
    allowWrite: bool = Field(default=False, alias="allowWrite")  # noqa: N815
    allowedWriteScopes: list[str] = Field(default_factory=list, alias="allowedWriteScopes")  # noqa: N815
    allowLiveTrading: bool = Field(default=False, alias="allowLiveTrading")  # noqa: N815
    subworkflows: list[SubworkflowPayload] = Field(default_factory=list)
    # One-off trigger input for THIS run. The front door sends `runInput` (the
    # same key the durable job payload uses), so accept that alias; `input`
    # still works for direct callers and older payloads.
    input: Any = Field(default=None, alias="runInput")
    # Verified inbound-trigger context (webhook headers/query/method/delivery).
    # Authenticated by the front door; never contains a secret or signature.
    triggerContext: Optional[dict[str, Any]] = Field(default=None, alias="triggerContext")  # noqa: N815
    # Front-door base URL for run-scoped credential re-resolution after a
    # restart. The response carries the key in memory only, never this payload.
    callbackBaseUrl: Optional[str] = Field(default=None, alias="callbackBaseUrl")  # noqa: N815
    # Resolved by the front door from the settings vault. Held in memory by the
    # service, never written into the durable Fabric job payload.
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815

    model_config = {"populate_by_name": True}


def _grants(body: RunRequest) -> GraphRunGrants:
    return GraphRunGrants(
        test_run=body.testRun,
        granted_capabilities=frozenset(body.grantedCapabilities),
        allow_network=body.allowNetwork,
        allow_trading=body.allowTrading,
        allow_write=body.allowWrite,
        allowed_write_scopes=frozenset(body.allowedWriteScopes),
        allow_live_trading=body.allowLiveTrading,
    )


class NodeTestRequest(BaseModel):
    nodeType: str = Field(min_length=1, max_length=200)  # noqa: N815
    version: Optional[str] = Field(default=None, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="research", max_length=20)
    # Explicit operator confirmation for a single network node test. Write,
    # trading and model nodes are still refused.
    allowNetwork: bool = Field(default=False, alias="allowNetwork")  # noqa: N815

    model_config = {"populate_by_name": True}


@router.post("/graphs/nodes/test")
def test_node(
    body: NodeTestRequest,
    request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Execute ONE node with explicit inputs (the editor's Test node action)."""
    try:
        mode = ExecutionMode(body.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="mode must be research, backtest, paper or live",
        ) from exc
    owner = _owner(request)
    try:
        return _graph_service().test_node(
            node_type=body.nodeType,
            version=body.version,
            config=body.config,
            inputs=body.inputs,
            mode=mode,
            owner_id=owner,
            allow_network=body.allowNetwork,
        )
    except NodeTestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/graphs/compile")
def compile_graph(body: CompileRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ir = _parse_ir(body.ir)
    plan = _graph_service().compile(ir, subworkflows=_bundle(body.subworkflows))
    return {"plan": plan.model_dump(by_alias=True)}


@router.post("/graphs/runs", status_code=201)
def start_run(body: RunRequest, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ir = _parse_ir(body.ir)
    owner = _owner(request)
    try:
        run = _graph_service().start_run(
            ir,
            workflow_version=body.workflowVersion,
            owner_id=owner,
            grants=_grants(body),
            subworkflows=_bundle(body.subworkflows),
            run_input=body.input,
            trigger_context=body.triggerContext,
            model_settings=body.modelSettings,
            callback_base_url=body.callbackBaseUrl or "",
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


@router.post("/graphs/plan")
async def plan_graph(body: PlanRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Chat-to-graph: propose a validated IR. Nothing is saved or executed."""
    from ..graph_runtime.planner import plan_graph as _plan  # noqa: PLC0415

    try:
        result = await _plan(
            body.objective,
            model_settings=body.modelSettings,
            registry=_graph_service()._registry,
            workflow_id=body.workflowId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/graphs/assist")
async def assist_graph(
    body: AssistRequest,
    request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """In-editor assistant: propose validated edit operations. Nothing is saved."""
    from ..graph_runtime.assistant import assist_graph as _assist  # noqa: PLC0415

    try:
        return await _assist(
            body.instruction,
            ir_payload=body.ir,
            model_settings=body.modelSettings,
            registry=_graph_service()._registry,
            selection=body.selection,
            history=body.history,
            mode=body.mode,
            last_run=body.lastRun,
            runner=_assistant_runner(request, body.modelSettings),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graphs/assist/stream")
async def assist_graph_stream(
    body: AssistRequest,
    request: Request,
    _: bool = Depends(require_operator),
) -> StreamingResponse:
    """The same assistant turn, streamed as Server-Sent Events."""
    from ..graph_runtime.assistant import stream_assist  # noqa: PLC0415

    async def events() -> Any:
        async for chunk in stream_assist(
            body.instruction,
            ir_payload=body.ir,
            model_settings=body.modelSettings,
            registry=_graph_service()._registry,
            selection=body.selection,
            history=body.history,
            mode=body.mode,
            last_run=body.lastRun,
            runner=_assistant_runner(request, body.modelSettings),
        ):
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/graphs/datasets")
def list_datasets(
    request: Request,
    limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Saved local datasets for the dataset picker (read-only metadata)."""
    from ..graph_runtime.datasets import DatasetError, require_dataset_store

    owner = (request.headers.get("x-harness-user") or "local").strip() or "local"
    try:
        return {"datasets": require_dataset_store().list(limit, owner=owner)}
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/graphs/health")
def graph_health(
    windowHours: int = 24,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Bounded run/node telemetry for the operator surface."""
    return {"health": _graph_service().health(window_hours=windowHours)}


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
