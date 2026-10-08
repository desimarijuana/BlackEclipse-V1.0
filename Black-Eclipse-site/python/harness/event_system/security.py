"""Event System security — publish/subscribe authorization + secret redaction.

The Event System is a security boundary: publishing a sensitive event or
subscribing to one must be authorized, and no event payload may carry a secret.
Authorization reuses the ONE permission authority (`skills.permissions`), so an
event's declared `permission` is checked against the publishing actor's resolved
grants. Sensitive event types are additionally restricted to operator/system
actors. Redaction is applied as publish middleware (defense in depth), so a
payload that slips a secret past a producer is scrubbed before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..skills.permissions import Actor, check_permissions
from .envelope import EclipseEvent, redact_payload
from .registry import EventRegistry, EventTypeSpec


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: Optional[str] = None


class EventAuthorizer:
    def __init__(self, registry: EventRegistry, *, enforce: bool = True) -> None:
        self._registry = registry
        self.enforce = enforce

    def authorize_publish(self, event: EclipseEvent, actor: Optional[Actor]) -> AuthDecision:
        if not self.enforce:
            return AuthDecision(True)
        spec = self._registry.get(event.type, event.version)
        if spec is None:
            return AuthDecision(True)  # unknown (observed) events are unrestricted
        return self._authorize(spec, actor, verb="publish")

    def authorize_subscribe(self, spec: Optional[EventTypeSpec], actor: Optional[Actor]) -> AuthDecision:
        if not self.enforce or spec is None:
            return AuthDecision(True)
        return self._authorize(spec, actor, verb="subscribe")

    @staticmethod
    def _authorize(spec: EventTypeSpec, actor: Optional[Actor], *, verb: str) -> AuthDecision:
        if spec.sensitive:
            if actor is None or not actor.operator:
                return AuthDecision(False, f"{verb} of sensitive event {spec.type!r} requires an operator")
        if spec.permission:
            decision = check_permissions((spec.permission,), actor or Actor())
            if not decision.allowed:
                return AuthDecision(False, f"{verb} of {spec.type!r} requires {spec.permission}: {decision.reason}")
        return AuthDecision(True)


def sanitize(event: EclipseEvent) -> EclipseEvent:
    """Return a copy of the event with secrets redacted from payload + metadata."""
    event.payload = redact_payload(event.payload)
    event.metadata = redact_payload(event.metadata)
    return event


__all__ = ["AuthDecision", "EventAuthorizer", "sanitize"]
