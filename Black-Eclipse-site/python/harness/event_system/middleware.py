"""Composable publish middleware (validation → authorization → redaction →
enrichment → tracing → persistence → routing → delivery → metrics).

Each stage is a plain callable `(event) -> Optional[EclipseEvent]`; returning
`None` drops the event (with a metric). Stages are composed in order by the bus.
This keeps the bus itself free of business logic while making every stage unit
testable in isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..skills.permissions import Actor
from .envelope import EclipseEvent, new_trace_id, redact_payload
from .registry import EventRegistry
from .security import EventAuthorizer

log = logging.getLogger("harness.events.middleware")

Middleware = Callable[[EclipseEvent], Optional[EclipseEvent]]


@dataclass
class MiddlewareContext:
    registry: EventRegistry
    authorizer: EventAuthorizer
    actor: Optional[Actor] = None
    require_known_types: bool = False
    dropped: list[str] = field(default_factory=list)


def validation_middleware(ctx: MiddlewareContext) -> Middleware:
    def _stage(event: EclipseEvent) -> Optional[EclipseEvent]:
        issues = ctx.registry.validate(event, require_known=ctx.require_known_types)
        if issues:
            ctx.dropped.append("; ".join(issues))
            return None
        return event

    return _stage


def authorization_middleware(ctx: MiddlewareContext) -> Middleware:
    def _stage(event: EclipseEvent) -> Optional[EclipseEvent]:
        decision = ctx.authorizer.authorize_publish(event, ctx.actor)
        if not decision.allowed:
            ctx.dropped.append(decision.reason or "not authorized")
            return None
        return event

    return _stage


def redaction_middleware() -> Middleware:
    def _stage(event: EclipseEvent) -> Optional[EclipseEvent]:
        event.payload = redact_payload(event.payload)
        event.metadata = redact_payload(event.metadata)
        return event

    return _stage


def enrichment_middleware() -> Middleware:
    def _stage(event: EclipseEvent) -> Optional[EclipseEvent]:
        if not event.trace_id:
            event.trace_id = new_trace_id()
        if event.actor and event.actor.type not in ("user", "agent", "system", "workflow", "tool"):
            event.actor = Actor(type="system", id=event.actor.id)
        return event

    return _stage


def logging_middleware() -> Middleware:
    def _stage(event: EclipseEvent) -> Optional[EclipseEvent]:
        log.debug("event %s %s source=%s corr=%s", event.id, event.type, event.source, event.correlation_id)
        return event

    return _stage


def default_pipeline(ctx: MiddlewareContext, *, logging_enabled: bool = False) -> list[Middleware]:
    stages: list[Middleware] = [
        validation_middleware(ctx),
        authorization_middleware(ctx),
        redaction_middleware(),
        enrichment_middleware(),
    ]
    if logging_enabled:
        stages.append(logging_middleware())
    return stages


__all__ = [
    "Middleware",
    "MiddlewareContext",
    "authorization_middleware",
    "default_pipeline",
    "enrichment_middleware",
    "logging_middleware",
    "redaction_middleware",
    "validation_middleware",
]
