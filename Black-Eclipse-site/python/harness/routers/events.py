"""Event Console route group — `/events/*`.

Operator-gated reads AND mutations (transport/token), matching the rest of the
runtime: this is the observability + control surface for the Event System
(live events, history, details, subscriptions, consumers, DLQ, replay, graph,
registry, metrics). Reads never leak secrets — payloads are redacted at publish.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..event_system.bootstrap import event_system

router = APIRouter(tags=["events"], prefix="/events")


def _events():
    return event_system(service)


class SubscriptionRequest(BaseModel):
    subscriberId: str = Field(..., max_length=200)  # noqa: N815
    subscriberType: str = "internal"  # noqa: N815
    patterns: list[str] = Field(..., min_length=1)
    predicate: Optional[str] = None
    source: Optional[str] = None
    scopeId: Optional[str] = None  # noqa: N815
    enabled: bool = True


class ReplayRequest(BaseModel):
    mode: str = "observe"
    eventId: Optional[str] = None  # noqa: N815
    correlationId: Optional[str] = None  # noqa: N815
    taskId: Optional[str] = None  # noqa: N815
    workflowId: Optional[str] = None  # noqa: N815
    traceId: Optional[str] = None  # noqa: N815
    types: Optional[list[str]] = None
    since: Optional[str] = None
    until: Optional[str] = None
    limit: int = 200
    authorized: bool = False
    confirmDestructive: bool = False  # noqa: N815


class RuleRequest(BaseModel):
    name: str = Field(..., max_length=160)
    eventType: str = Field(..., max_length=200)  # noqa: N815
    action: str = Field(..., max_length=60)
    condition: Optional[str] = None
    eventFilter: dict[str, Any] = Field(default_factory=dict)  # noqa: N815
    agentId: Optional[str] = None  # noqa: N815
    workflowId: Optional[str] = None  # noqa: N815
    toolName: Optional[str] = None  # noqa: N815
    toolArgs: dict[str, Any] = Field(default_factory=dict)  # noqa: N815
    objective: Optional[str] = None
    requiresApproval: bool = False  # noqa: N815
    activated: bool = False


# ── Static routes FIRST (so `/events/{id}` cannot shadow them) ────────────────
@router.get("/health")
def events_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return _events().health()


@router.get("/metrics")
def events_metrics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return _events().metrics_snapshot()


@router.get("/registry")
def events_registry(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"events": _events().registry_view()}


@router.get("/types")
def events_types(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"types": _events().store.types()}


@router.get("/subscriptions")
def list_subscriptions(_: bool = Depends(require_operator)) -> dict[str, Any]:
    system = _events()
    return {
        "live": system.subscriptions(),
        "declared": system.store.list_subscriptions(),
    }


@router.post("/subscriptions")
def declare_subscription(body: SubscriptionRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    saved = _events().store.save_subscription(
        subscriber_id=body.subscriberId, subscriber_type=body.subscriberType,
        patterns=body.patterns, predicate=body.predicate, source=body.source,
        scope_id=body.scopeId, enabled=body.enabled,
    )
    return {"subscription": saved}


@router.delete("/subscriptions/{subscriber_id}")
def delete_subscription(subscriber_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    removed = _events().store.delete_subscription(subscriber_id)
    return {"removed": removed}


@router.get("/dlq")
def list_dlq(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"deadLetters": _events().dlq(status=status, limit=limit)}


@router.get("/dlq/{dlq_id}")
def get_dlq(dlq_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    entry = _events().store.get_dead_letter(dlq_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="dead letter not found")
    return {"deadLetter": entry}


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq(
    dlq_id: str,
    confirmDestructive: bool = Query(False),  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..event_system.replay import ReplayError

    try:
        result = await _events().retry_dead_letter(dlq_id, confirm_destructive=confirmDestructive)
    except ReplayError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    return {"replay": result.to_dict()}


@router.post("/dlq/{dlq_id}/discard")
def discard_dlq(dlq_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    changed = _events().store.set_dead_letter_status(dlq_id, "discarded")
    if not changed:
        raise HTTPException(status_code=404, detail="dead letter not found")
    return {"status": "discarded"}


@router.post("/replay")
async def replay(body: ReplayRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..event_system.replay import ReplayError

    try:
        result = await _events().replay(
            mode=body.mode, authorized=body.authorized, confirm_destructive=body.confirmDestructive,
            event_id=body.eventId, correlation_id=body.correlationId, task_id=body.taskId,
            workflow_id=body.workflowId, trace_id=body.traceId, types=body.types,
            since=body.since, until=body.until, limit=body.limit,
        )
    except ReplayError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    return {"replay": result.to_dict()}


@router.get("/graph")
def event_graph(
    correlationId: Optional[str] = Query(None),  # noqa: N803
    traceId: Optional[str] = Query(None),  # noqa: N803
    limit: int = Query(500, ge=1, le=2000),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return _events().graph(correlation_id=correlationId, trace_id=traceId, limit=limit)


@router.get("/rules")
def list_rules(limit: int = Query(200, ge=1, le=1000), _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"rules": _events().rules.list_rules(limit=limit)}


@router.post("/rules")
def create_rule(body: RuleRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..event_system.rules import EventRuleError

    try:
        rule = _events().rules.create_rule(
            name=body.name, event_type=body.eventType, action=body.action,
            condition=body.condition, event_filter=body.eventFilter,
            agent_id=body.agentId, workflow_id=body.workflowId, tool_name=body.toolName,
            tool_args=body.toolArgs, objective=body.objective,
            requires_approval=body.requiresApproval, activated=body.activated,
        )
    except EventRuleError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    return {"rule": rule}


@router.get("")
def list_events(
    type: Optional[str] = Query(None),  # noqa: A002
    namespace: Optional[str] = Query(None),
    correlationId: Optional[str] = Query(None),  # noqa: N803
    taskId: Optional[str] = Query(None),  # noqa: N803
    workflowId: Optional[str] = Query(None),  # noqa: N803
    agentId: Optional[str] = Query(None),  # noqa: N803
    sessionId: Optional[str] = Query(None),  # noqa: N803
    priority: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    events = _events().store.query(
        type=type, namespace=namespace, correlation_id=correlationId, task_id=taskId,
        workflow_id=workflowId, agent_id=agentId, session_id=sessionId, priority=priority,
        source=source, since=since, until=until, limit=limit, offset=offset,
    )
    return {"events": [e.to_dict() for e in events], "count": len(events)}


# ── Dynamic route LAST ───────────────────────────────────────────────────────
@router.get("/{event_id}")
def get_event(event_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    view = _events().event(event_id)
    if view is None:
        raise HTTPException(status_code=404, detail="event not found")
    return {"event": view}


__all__ = ["router"]
