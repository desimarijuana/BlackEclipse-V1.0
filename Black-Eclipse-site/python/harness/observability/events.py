"""Typed observer events — the strongly-typed vocabulary the runtime emits.

Every observable operation produces ONE `HookEvent`: a dataclass with the
correlation context, a closed hook name, and typed fields for the values that
matter (duration, status, error, model, tool, tokens, cost). Free-form
`attributes` carry operation-specific detail that has no dedicated field.

The `HOOKS` frozenset is the complete, closed vocabulary. `make_event` is the
single constructor; helper builders (`run_event`, `llm_event`, `tool_event`, …)
cover the common shapes so call sites never hand-build a dict.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .context import ObservationContext, current_context, get_or_create_context
from .redaction import get_default_redactor

HOOKS: frozenset[str] = frozenset({
    "onRunStart", "onRunEnd",
    "onAgentStart", "onAgentEnd",
    "onPlanStart", "onPlanEnd",
    "onTaskStart", "onTaskEnd",
    "onLLMStart", "onLLMEnd", "onLLMError",
    "onToolStart", "onToolEnd", "onToolError",
    "onQueueEnqueue", "onQueueStart", "onQueueEnd", "onQueueError",
    "onJobStart", "onJobEnd", "onJobRetry", "onJobFailure",
    "onEventPublished", "onEventConsumed", "onEventProcessed", "onEventFailed",
    "onPluginStart", "onPluginEnd", "onPluginError",
    "onA2AMessageSent", "onA2AMessageReceived",
    "onMemoryRead", "onMemoryWrite", "onMemorySearch",
    "onSkillLoaded", "onSkillExecuted",
    "onResearchStart", "onResearchEnd",
    "onEvidenceRetrieved", "onEvidenceValidated",
    "onRecoveryStart", "onRecoveryEnd",
    "onApproval", "onSecurityEvent",
    "onAnomaly", "onSLOViolation", "onLoopDetected",
    "onError", "onSpan",
})

_STATUSES = frozenset({"OK", "ERROR", "CANCELLED", "TIMEOUT", "DEGRADED", "UNSET"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HookEvent:
    hook: str
    context: ObservationContext
    name: str = ""
    status: str = "UNSET"
    duration_ms: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tool_name: Optional[str] = None
    tool_version: Optional[str] = None
    tool_category: Optional[str] = None
    tokens: dict[str, int] = field(default_factory=dict)
    cost: Optional[dict[str, Any]] = None
    retries: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if self.hook not in HOOKS:
            raise ValueError(f"unknown observability hook: {self.hook!r}")
        if self.status not in _STATUSES:
            self.status = "UNSET"

    @property
    def trace_id(self) -> str:
        return self.context.trace_id

    @property
    def span_id(self) -> str:
        return self.context.span_id

    @property
    def is_error(self) -> bool:
        return self.status in ("ERROR", "TIMEOUT") or bool(self.error_type)

    def redacted(self) -> dict[str, Any]:
        """A fully redacted, JSON-safe dict for logging/export."""
        redactor = get_default_redactor()
        payload = asdict(self)
        payload["context"] = self.context.to_dict()
        payload["attributes"] = redactor.redact(self.attributes)
        if self.error_message is not None:
            payload["error_message"] = redactor.redact_text(self.error_message)
        payload["cost"] = redactor.redact(self.cost)
        return payload


def make_event(
    hook: str,
    *,
    context: Optional[ObservationContext] = None,
    **fields: Any,
) -> HookEvent:
    ctx = context or current_context() or get_or_create_context()
    attributes = dict(fields.pop("attributes", None) or {})
    known = {k: fields.pop(k) for k in list(fields) if k in HookEvent.__dataclass_fields__}
    known.pop("hook", None)
    known.pop("context", None)
    attributes.update(fields)  # anything not a dedicated field becomes an attribute
    return HookEvent(hook=hook, context=ctx, attributes=attributes, **known)


# ── convenience builders ────────────────────────────────────────────────────
def run_event(hook: str, run_id: str, **fields: Any) -> HookEvent:
    ctx = (current_context() or get_or_create_context()).with_fields(run_id=run_id)
    return make_event(hook, context=ctx, **fields)


def llm_event(hook: str, *, provider: Optional[str] = None, model: Optional[str] = None, **fields: Any) -> HookEvent:
    return make_event(hook, provider=provider, model=model, name=fields.pop("name", f"{provider}/{model}"), **fields)


def tool_event(hook: str, tool_name: str, **fields: Any) -> HookEvent:
    return make_event(hook, tool_name=tool_name, name=tool_name, **fields)


__all__ = ["HookEvent", "HOOKS", "make_event", "run_event", "llm_event", "tool_event"]
