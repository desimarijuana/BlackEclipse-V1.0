"""Orchestration HTTP routes — the operator/UI surface over parallel execution.

Every route is `require_operator` (transport/token), exactly like the terminal,
code and execution routers. The routes are thin adapters over the SAME
`OrchestrationService` the agent tools use, so the UI and the agent can never
disagree about what is running.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["orchestration"])


class RuntimeBody(BaseModel):
    """Optional credentials for recovery/resume/retry of agent-bearing executions."""

    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815
    callbackBaseUrl: Optional[str] = None  # noqa: N815
    callbackToken: Optional[str] = None  # noqa: N815
    userId: Optional[str] = None  # noqa: N815


class CreateExecutionRequest(BaseModel):
    tasks: list[dict[str, Any]] = Field(min_length=1)
    failurePolicy: str = "CONTINUE"  # noqa: N815
    concurrency: int = Field(default=0, ge=0, le=256)
    quorum: int = Field(default=0, ge=0)
    aggregate: bool = False
    aggregateMode: str = "list"  # noqa: N815
    timeoutMs: Optional[int] = Field(default=None, ge=1)  # noqa: N815
    modelSettings: Optional[dict[str, Any]] = None  # noqa: N815
    callbackBaseUrl: Optional[str] = None  # noqa: N815
    callbackToken: Optional[str] = None  # noqa: N815
    userId: Optional[str] = None  # noqa: N815


def _orchestration():
    layer = getattr(service, "orchestration", None)
    if layer is None:
        raise HTTPException(status_code=503, detail="the orchestration layer is unavailable")
    return layer


def _runtime(layer, body: Optional[RuntimeBody]):
    if body is None or not body.modelSettings:
        return None
    from ..schemas import ModelSettings

    try:
        model_settings = ModelSettings(**body.modelSettings)
    except Exception as exc:  # noqa: BLE001 - a bad settings body is a 400
        raise HTTPException(status_code=400, detail=f"invalid modelSettings: {exc}") from exc
    return layer.runtime_for(
        model_settings=model_settings,
        callback_base_url=body.callbackBaseUrl or "",
        callback_token=body.callbackToken,
        user_id=body.userId,
        run_id="",
    )


@router.get("/orchestration/status")
def orchestration_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_orchestration().status()}


@router.get("/orchestration/resources")
def orchestration_resources(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "resources": _orchestration().primary.resources()}


@router.get("/orchestration/list")
def list_executions(limit: int = 100, status: Optional[str] = None,
                    _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True,
            "executions": _orchestration().store.list_executions(limit=limit, status=status)}


@router.post("/orchestration/executions")
async def create_execution(body: CreateExecutionRequest,
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..schemas import ModelSettings
    from ..orchestration import FailurePolicy
    from ..orchestration.primitives import parallel_execute

    layer = _orchestration()
    model_settings = None
    if body.modelSettings:
        try:
            model_settings = ModelSettings(**body.modelSettings)
        except Exception as exc:  # noqa: BLE001 - a bad settings body is a 400
            raise HTTPException(status_code=400, detail=f"invalid modelSettings: {exc}") from exc
    runtime = layer.runtime_for(
        model_settings=model_settings,
        callback_base_url=body.callbackBaseUrl or "",
        callback_token=body.callbackToken,
        user_id=body.userId,
        run_id="",
    )
    engine = layer.new_engine(runtime)
    try:
        policy = FailurePolicy(body.failurePolicy.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown failurePolicy {body.failurePolicy!r}") from exc
    result = await parallel_execute(
        engine, body.tasks, concurrency=body.concurrency, failure_policy=policy,
        quorum=body.quorum, aggregate=body.aggregate, aggregate_mode=body.aggregateMode,
        timeout_ms=body.timeoutMs, metadata={"source": "http"},
    )
    return {"success": True, "result": result.to_dict()}


@router.get("/orchestration/executions/{execution_id}")
def get_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    status = _orchestration().find(execution_id).get_status(execution_id)
    if status is None:
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, "status": status}


@router.get("/orchestration/executions/{execution_id}/graph")
def get_graph(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    graph = _orchestration().primary.get_graph(execution_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, "graph": graph}


@router.get("/orchestration/executions/{execution_id}/result")
def get_result(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = _orchestration().primary.get_result(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, "result": result.to_dict()}


@router.get("/orchestration/executions/{execution_id}/events")
def get_events(execution_id: str, limit: int = 1000,
               _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True,
            "events": _orchestration().store.list_events(execution_id, limit=limit)}


@router.get("/orchestration/executions/{execution_id}/attempts")
def get_attempts(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True,
            "attempts": _orchestration().store.list_attempts(execution_id)}


@router.post("/orchestration/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    cancelled = await _orchestration().find(execution_id).cancel(execution_id)
    return {"success": True, "executionId": execution_id, "cancelled": cancelled}


@router.post("/orchestration/executions/{execution_id}/pause")
async def pause_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    paused = await _orchestration().find(execution_id).pause(execution_id)
    return {"success": True, "executionId": execution_id, "paused": paused}


@router.post("/orchestration/executions/{execution_id}/resume")
async def resume_execution(execution_id: str, body: Optional[RuntimeBody] = None,
                           _: bool = Depends(require_operator)) -> dict[str, Any]:
    layer = _orchestration()
    engine = layer.find(execution_id)
    result = await engine.resume_execution(execution_id, runtime=_runtime(layer, body))
    return {"success": True, "executionId": execution_id, "result": result.to_dict()}


@router.post("/orchestration/executions/{execution_id}/nodes/{node_id}/retry")
async def retry_node(execution_id: str, node_id: str, body: Optional[RuntimeBody] = None,
                     _: bool = Depends(require_operator)) -> dict[str, Any]:
    layer = _orchestration()
    engine = layer.find(execution_id)
    retried = await engine.retry_node(execution_id, node_id, runtime=_runtime(layer, body))
    if not retried:
        raise HTTPException(status_code=409, detail="node is not in a retryable state or is unknown")
    return {"success": True, "executionId": execution_id, "nodeId": node_id, "retried": True}


@router.post("/orchestration/recover")
async def recover(body: Optional[RuntimeBody] = None,
                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    layer = _orchestration()
    recovered = await layer.primary.recover(runtime=_runtime(layer, body))
    return {"success": True, "recovered": recovered}


__all__ = ["router"]
