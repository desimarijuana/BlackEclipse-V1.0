"""The canonical Eclipse event envelope + correlation/causation context.

An event describes something that HAS happened (past tense). It is immutable in
identity: `id` is globally unique, `timestamp` is UTC, and `type` + `version`
identify the contract. Commands request actions; tasks hold work state; workflows
orchestrate. They are distinct concepts and stay distinct.

Correlation and causation are propagated automatically through `contextvars`, so
a developer publishing a follow-up event inside a handler never has to thread ids
through every function call:

    with event_context(correlation_id="ABC"):
        await bus.publish(task_created)          # correlationId inherited

The context is read by `EclipseEvent.create` and by the bus when a handler fires.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional

from ..persistence import now_iso

PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "critical", "bulk")
ACTOR_TYPES: tuple[str, ...] = ("user", "agent", "system", "workflow", "tool")

# ── Correlation / causation context (auto-propagation) ───────────────────────
_correlation: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("eclipse_correlation_id", default=None)
_causation: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("eclipse_causation_id", default=None)
_trace: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("eclipse_trace_id", default=None)
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("eclipse_event_depth", default=0)
_actor: contextvars.ContextVar[Optional["Actor"]] = contextvars.ContextVar("eclipse_event_actor", default=None)
_session: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("eclipse_event_session", default=None)


def new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


def new_trace_id() -> str:
    return f"trc_{uuid.uuid4().hex}"


def correlation_id() -> Optional[str]:
    return _correlation.get()


def causation_id() -> Optional[str]:
    return _causation.get()


def current_depth() -> int:
    return _depth.get()


def current_actor() -> Optional["Actor"]:
    return _actor.get()


def current_trace_id() -> Optional[str]:
    return _trace.get()


@contextlib.contextmanager
def event_context(
    *,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    depth: Optional[int] = None,
    actor: Optional["Actor"] = None,
    session_id: Optional[str] = None,
) -> Iterator[None]:
    """Set event-propagation context for the enclosed block (restores on exit)."""
    tokens: list[tuple[contextvars.ContextVar[Any], contextvars.Token[Any]]] = []

    def _set(var: contextvars.ContextVar[Any], value: Any) -> None:
        if value is not None:
            tokens.append((var, var.set(value)))

    _set(_correlation, correlation_id)
    _set(_causation, causation_id)
    _set(_trace, trace_id)
    _set(_depth, depth)
    _set(_actor, actor)
    _set(_session, session_id)
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


@dataclass(frozen=True)
class Actor:
    """Who caused an event."""

    type: str
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}

    @classmethod
    def from_dict(cls, value: Optional[Mapping[str, Any]]) -> Optional["Actor"]:
        if not value:
            return None
        return cls(type=str(value.get("type") or "system"), id=str(value.get("id") or "unknown"))


@dataclass
class EclipseEvent:
    """The canonical event envelope (dict-shaped for JSON/SQLite storage)."""

    id: str
    type: str
    version: int = 1
    timestamp: str = field(default_factory=now_iso)
    source: str = "unknown"
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    trace_id: Optional[str] = None
    actor: Optional[Actor] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    priority: str = "normal"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    depth: int = 0
    # Internal: true when the event was persisted; false for transient/live-only.
    persisted: bool = True
    replay: bool = False

    # ── Construction ─────────────────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        type: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        version: int = 1,
        source: str = "eclipse",
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        actor: Optional[Actor] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        priority: str = "normal",
        metadata: Optional[Mapping[str, Any]] = None,
        depth: Optional[int] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> "EclipseEvent":
        """Build an event, inheriting correlation/causation/trace/actor from context."""
        inherited_actor = actor or _actor.get()
        return cls(
            id=event_id or new_event_id(),
            type=type,
            version=int(version),
            timestamp=timestamp or now_iso(),
            source=source,
            correlation_id=correlation_id if correlation_id is not None else _correlation.get(),
            causation_id=causation_id if causation_id is not None else _causation.get(),
            trace_id=trace_id if trace_id is not None else _trace.get(),
            actor=inherited_actor,
            session_id=session_id if session_id is not None else _session.get(),
            task_id=task_id,
            workflow_id=workflow_id,
            agent_id=agent_id,
            priority=priority if priority in PRIORITIES else "normal",
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
            depth=_depth.get() if depth is None else int(depth),
        )

    # ── Serialization ────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "timestamp": self.timestamp,
            "source": self.source,
            "correlationId": self.correlation_id,
            "causationId": self.causation_id,
            "traceId": self.trace_id,
            "actor": self.actor.to_dict() if self.actor else None,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "workflowId": self.workflow_id,
            "agentId": self.agent_id,
            "priority": self.priority,
            "payload": self.payload,
            "metadata": self.metadata,
            "depth": self.depth,
            "replay": self.replay,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EclipseEvent":
        return cls(
            id=str(data.get("id") or new_event_id()),
            type=str(data.get("type") or "unknown"),
            version=int(data.get("version") or 1),
            timestamp=str(data.get("timestamp") or data.get("at") or now_iso()),
            source=str(data.get("source") or "unknown"),
            correlation_id=data.get("correlationId") or data.get("correlation_id"),
            causation_id=data.get("causationId") or data.get("causation_id"),
            trace_id=data.get("traceId") or data.get("trace_id"),
            actor=Actor.from_dict(data.get("actor")),
            session_id=data.get("sessionId") or data.get("session_id"),
            task_id=data.get("taskId") or data.get("task_id"),
            workflow_id=data.get("workflowId") or data.get("workflow_id"),
            agent_id=data.get("agentId") or data.get("agent_id"),
            priority=str(data.get("priority") or "normal"),
            payload=dict(data.get("payload") or {}),
            metadata=dict(data.get("metadata") or {}),
            depth=int(data.get("depth") or 0),
            persisted=bool(data.get("persisted", True)),
            replay=bool(data.get("replay", False)),
        )

    def child(
        self,
        type: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        source: Optional[str] = None,
        **kwargs: Any,
    ) -> "EclipseEvent":
        """Create a directly-caused follow-up event (inherits correlation + depth+1)."""
        return EclipseEvent.create(
            type,
            payload,
            source=source or self.source,
            correlation_id=self.correlation_id,
            causation_id=self.id,
            trace_id=self.trace_id,
            actor=kwargs.pop("actor", self.actor),
            session_id=kwargs.pop("session_id", self.session_id),
            task_id=kwargs.pop("task_id", self.task_id),
            workflow_id=kwargs.pop("workflow_id", self.workflow_id),
            agent_id=kwargs.pop("agent_id", self.agent_id),
            depth=self.depth + 1,
            **kwargs,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "timestamp": self.timestamp,
            "source": self.source,
            "correlationId": self.correlation_id,
            "causationId": self.causation_id,
            "traceId": self.trace_id,
            "actorType": self.actor.type if self.actor else None,
            "actorId": self.actor.id if self.actor else None,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "workflowId": self.workflow_id,
            "agentId": self.agent_id,
            "priority": self.priority,
            "payload": _dumps(self.payload),
            "metadata": _dumps(self.metadata),
            "depth": self.depth,
            "replay": 1 if self.replay else 0,
            "createdAt": now_iso(),
        }

    @classmethod
    def from_row(cls, row: Any) -> "EclipseEvent":
        get = row.__getitem__
        keys = set(row.keys())
        actor_type = get("actorType") if "actorType" in keys else None
        actor_id = get("actorId") if "actorId" in keys else None
        return cls(
            id=get("id"),
            type=get("type"),
            version=int(get("version") or 1),
            timestamp=get("timestamp"),
            source=get("source") or "unknown",
            correlation_id=get("correlationId") if "correlationId" in keys else None,
            causation_id=get("causationId") if "causationId" in keys else None,
            trace_id=get("traceId") if "traceId" in keys else None,
            actor=Actor(type=actor_type, id=actor_id) if actor_type else None,
            session_id=get("sessionId") if "sessionId" in keys else None,
            task_id=get("taskId") if "taskId" in keys else None,
            workflow_id=get("workflowId") if "workflowId" in keys else None,
            agent_id=get("agentId") if "agentId" in keys else None,
            priority=get("priority") or "normal",
            payload=_loads(get("payload")),
            metadata=_loads(get("metadata")),
            depth=int(get("depth") or 0) if "depth" in keys else 0,
            replay=bool(get("replay")) if "replay" in keys else False,
        )


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)


def _loads(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, ValueError):
        return {}


# ── Legacy event adaptation ──────────────────────────────────────────────────
# The existing runtime publishes loose dicts on `harness.events.EventBus`. We map
# them into the canonical envelope without inventing data: `runId` becomes the
# session association, `seq` is preserved in metadata, and the event `id` is
# reused when present (so idempotency and dedup hold across both transports).
# Legacy subsystem event names → canonical Event System names. A single point so
# the terminal's `terminal.process.*` lifecycle becomes real `process.*` events
# without editing every emitter.
_LEGACY_TYPE_MAP: dict[str, str] = {
    "terminal.process.started": "process.started",
    "terminal.process.restarted": "process.started",
    "terminal.process.exited": "process.completed",
    "terminal.process.stopped": "process.completed",
    "terminal.process.crashed": "process.failed",
    "terminal.process.failed": "process.failed",
    "terminal.process.killed": "process.failed",
}


def canonical_legacy_type(event_type: str, data: Mapping[str, Any]) -> str:
    """Map a legacy event name to its canonical name (identity if none applies)."""
    mapped = _LEGACY_TYPE_MAP.get(event_type)
    if mapped is None:
        return event_type
    if mapped == "process.completed":
        rc = data.get("exitCode")
        if isinstance(rc, int) and rc != 0:
            return "process.failed"
    return mapped


def from_legacy(event: Mapping[str, Any], *, source: str = "harness") -> EclipseEvent:
    payload = event.get("data") if isinstance(event.get("data"), dict) else {}
    metadata: dict[str, Any] = {}
    if event.get("runId"):
        metadata["runId"] = event["runId"]
    if event.get("seq") is not None:
        metadata["seq"] = event["seq"]
    if event.get("transient"):
        metadata["transient"] = True
    run_id = event.get("runId")
    task_id = event.get("taskId") or event.get("task_id")
    workflow_id = event.get("workflowId") or event.get("workflow_id")
    agent_id = event.get("agentId") or event.get("agent_id")
    raw_type = str(event.get("type") or "unknown")
    return EclipseEvent.create(
        canonical_legacy_type(raw_type, payload),
        payload,
        source=source,
        session_id=run_id if isinstance(run_id, str) else None,
        task_id=str(task_id) if task_id else None,
        workflow_id=str(workflow_id) if workflow_id else None,
        agent_id=str(agent_id) if agent_id else None,
        correlation_id=event.get("correlationId") or event.get("correlation_id"),
        causation_id=event.get("causationId") or event.get("causation_id"),
        timestamp=str(event.get("at") or now_iso()) if not isinstance(event.get("at"), (int, float)) else now_iso(),
        event_id=str(event["id"]) if event.get("id") else None,
        metadata=metadata,
    )


# ── Secret redaction (defense in depth; also enforced by security.py) ────────
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|apikey|secret|password|passwd|token|authorization|bearer|"
    r"credential|private[_-]?key|client[_-]?secret|refresh[_-]?token|access[_-]?token|"
    r"cookie|session[_-]?key|signature|ssn|social[_-]?security)",
    re.IGNORECASE,
)
_SECRET_VALUE_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),          # OpenAI-style keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),      # GitHub tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                # AWS access key id
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{12,}"),  # bearer token
)
_REDACTED = "[REDACTED]"


def redact_text(text: str, *, max_len: int = 20000) -> str:
    if not isinstance(text, str):
        return text
    out = text
    for pattern in _SECRET_VALUE_RES:
        out = pattern.sub(_REDACTED, out)
    return out[:max_len]


def redact_payload(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact secrets by key name and by value pattern.

    Bounded depth/size so a pathological payload can never blow memory or the
    event store. This is the ONE redaction used by the publish middleware.
    """
    if _depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                out[key] = _REDACTED
            else:
                out[key] = redact_payload(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_payload(item, _depth=_depth + 1) for item in value[:500]]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value))


__all__ = [
    "ACTOR_TYPES",
    "PRIORITIES",
    "Actor",
    "EclipseEvent",
    "canonical_legacy_type",
    "causation_id",
    "correlation_id",
    "current_actor",
    "current_depth",
    "current_trace_id",
    "event_context",
    "from_legacy",
    "new_event_id",
    "new_trace_id",
    "redact_payload",
    "redact_text",
]
