"""Observation context — the correlation identity that follows every operation.

One immutable `ObservationContext` travels with a unit of work (a run, a job, a
message) and is carried in a `contextvars.ContextVar`, so nested sync/async code
automatically sees it without threading a parameter through every call. Spans
derive a child context (same `trace_id`, a new `span_id`, `parent_span_id` set).

Cross-process propagation uses a W3C `traceparent`-compatible carrier plus the
Eclipse-specific ids (run/task/job/worker/message). `inject`/`extract` are the
only sanctioned way to move context across a queue, a subprocess or an HTTP hop.
"""

from __future__ import annotations

import contextvars
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Iterator, Optional

# W3C trace flags: bit 0 == sampled.
FLAG_SAMPLED = 0x01


def new_trace_id() -> str:
    """A 16-byte / 32-hex trace id (W3C shape, never all-zero)."""
    while True:
        value = secrets.token_hex(16)
        if value != "0" * 32:
            return value


def new_span_id() -> str:
    """An 8-byte / 16-hex span id (W3C shape, never all-zero)."""
    while True:
        value = secrets.token_hex(8)
        if value != "0" * 16:
            return value


def new_id(prefix: str) -> str:
    """A short opaque id with a readable prefix for non-trace entities."""
    return f"{prefix}_{secrets.token_hex(8)}"


@dataclass(frozen=True)
class ObservationContext:
    """Immutable correlation identity for one unit of work."""

    trace_id: str = field(default_factory=new_trace_id)
    span_id: str = field(default_factory=new_span_id)
    parent_span_id: Optional[str] = None
    sampled: bool = True

    session_id: Optional[str] = None
    request_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    job_id: Optional[str] = None
    worker_id: Optional[str] = None
    plugin_id: Optional[str] = None
    event_id: Optional[str] = None
    message_id: Optional[str] = None
    tenant_id: Optional[str] = None

    attributes: dict[str, Any] = field(default_factory=dict)

    def child(self, *,
              span_id: Optional[str] = None,
              attributes: Optional[dict[str, Any]] = None,
              **changes: Any) -> "ObservationContext":
        """Derive a child context: same trace, new span, parent = this span."""
        merged = dict(self.attributes)
        if attributes:
            merged.update(attributes)
        base = replace(
            self,
            span_id=span_id or new_span_id(),
            parent_span_id=self.span_id,
            attributes=merged,
            **{k: v for k, v in changes.items() if v is not None},
        )
        return base

    def with_fields(self, **changes: Any) -> "ObservationContext":
        return replace(self, **{k: v for k, v in changes.items() if v is not None})

    @property
    def trace_flags(self) -> int:
        return FLAG_SAMPLED if self.sampled else 0

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"

    def w3c(self) -> dict[str, str]:
        return {
            "traceparent": self.traceparent(),
            "tracestate": f"eclipse={self.run_id or self.span_id}",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "sampled": self.sampled,
            "sessionId": self.session_id,
            "requestId": self.request_id,
            "runId": self.run_id,
            "agentId": self.agent_id,
            "agentRunId": self.agent_run_id,
            "taskId": self.task_id,
            "workflowId": self.workflow_id,
            "jobId": self.job_id,
            "workerId": self.worker_id,
            "pluginId": self.plugin_id,
            "eventId": self.event_id,
            "messageId": self.message_id,
            "tenantId": self.tenant_id,
        }


_CURRENT: contextvars.ContextVar[Optional[ObservationContext]] = contextvars.ContextVar(
    "eclipse_observation_context", default=None,
)


def current_context() -> Optional[ObservationContext]:
    return _CURRENT.get()


def get_or_create_context(**fields: Any) -> ObservationContext:
    """Return the active context, creating one (and binding it) if absent."""
    ctx = _CURRENT.get()
    if ctx is not None:
        if fields:
            ctx = ctx.with_fields(**fields)
            _CURRENT.set(ctx)
        return ctx
    ctx = ObservationContext(**fields)
    _CURRENT.set(ctx)
    return ctx


@contextmanager
def bind_context(ctx: ObservationContext) -> Iterator[ObservationContext]:
    """Bind `ctx` for the duration of the block, restoring the previous value."""
    token = _CURRENT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT.reset(token)


@contextmanager
def use_fields(**fields: Any) -> Iterator[ObservationContext]:
    """Bind an enriched view of the current context for the block."""
    ctx = get_or_create_context(**fields)
    token = _CURRENT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT.reset(token)


def inject(ctx: Optional[ObservationContext], carrier: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Write the context into a carrier for cross-process propagation.

    The carrier is a plain dict so it can ride a Redis job payload, an A2A
    message envelope, an HTTP header map or a subprocess argv/env. Existing keys
    are preserved; only observability keys are added.
    """
    carrier = dict(carrier or {})
    if ctx is None:
        return carrier
    carrier.update({
        "traceparent": ctx.traceparent(),
        "eclipseTraceId": ctx.trace_id,
        "eclipseSpanId": ctx.span_id,
        "eclipseSampled": ctx.sampled,
    })
    for key, value in (
        ("eclipseSessionId", ctx.session_id),
        ("eclipseRequestId", ctx.request_id),
        ("eclipseRunId", ctx.run_id),
        ("eclipseAgentId", ctx.agent_id),
        ("eclipseTaskId", ctx.task_id),
        ("eclipseWorkflowId", ctx.workflow_id),
        ("eclipseJobId", ctx.job_id),
        ("eclipseWorkerId", ctx.worker_id),
        ("eclipsePluginId", ctx.plugin_id),
        ("eclipseEventId", ctx.event_id),
        ("eclipseMessageId", ctx.message_id),
    ):
        if value:
            carrier[key] = value
    return carrier


def _parse_traceparent(value: str) -> Optional[tuple[str, str, bool]]:
    parts = str(value).strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, flags = parts
    if len(trace_id) != 32 or len(span_id) != 16:
        return None
    try:
        int(trace_id, 16)
        int(span_id, 16)
        int(flags, 16)
    except ValueError:
        return None
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return trace_id, span_id, bool(int(flags, 16) & FLAG_SAMPLED)


def extract(carrier: Optional[dict[str, Any]]) -> Optional[ObservationContext]:
    """Rebuild a context from a carrier; None when no trace identity is present."""
    if not carrier:
        return None
    trace_id = carrier.get("eclipseTraceId")
    span_id = carrier.get("eclipseSpanId")
    sampled = carrier.get("eclipseSampled")
    if not trace_id or not span_id:
        parsed = _parse_traceparent(str(carrier.get("traceparent", "")))
        if parsed is None:
            return None
        trace_id, span_id, parsed_sampled = parsed
        if sampled is None:
            sampled = parsed_sampled
    try:
        sampled_bool = bool(sampled) if isinstance(sampled, bool) else str(sampled).lower() in ("1", "true", "yes")
    except Exception:  # noqa: BLE001
        sampled_bool = True
    return ObservationContext(
        trace_id=str(trace_id),
        span_id=str(span_id),
        sampled=sampled_bool,
        session_id=carrier.get("eclipseSessionId") or carrier.get("sessionId"),
        request_id=carrier.get("eclipseRequestId") or carrier.get("requestId"),
        run_id=carrier.get("eclipseRunId") or carrier.get("runId"),
        agent_id=carrier.get("eclipseAgentId") or carrier.get("agentId"),
        task_id=carrier.get("eclipseTaskId") or carrier.get("taskId"),
        workflow_id=carrier.get("eclipseWorkflowId") or carrier.get("workflowId"),
        job_id=carrier.get("eclipseJobId") or carrier.get("jobId"),
        worker_id=carrier.get("eclipseWorkerId") or carrier.get("workerId"),
        plugin_id=carrier.get("eclipsePluginId") or carrier.get("pluginId"),
        event_id=carrier.get("eclipseEventId") or carrier.get("eventId"),
        message_id=carrier.get("eclipseMessageId") or carrier.get("messageId"),
    )


__all__ = [
    "ObservationContext",
    "FLAG_SAMPLED",
    "new_trace_id",
    "new_span_id",
    "new_id",
    "current_context",
    "get_or_create_context",
    "bind_context",
    "use_fields",
    "inject",
    "extract",
]
