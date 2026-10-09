"""The centralized Event Registry.

Event names are NEVER scattered as magic strings. Every event type is declared
once here with:

    version           the contract version (consumers pin a version)
    payload schema    required fields + lightweight type checks
    producer          which subsystem is allowed to publish it
    consumers         which subsystems may subscribe
    permission        the permission noun required to publish/subscribe
    priority          default delivery priority
    retention_days    how long the event log keeps it
    retry             delivery retry policy for consumers of this type
    delivery          sync / async / at_least_once / best_effort
    sensitive         whether the type is restricted to authorized actors

Exact types are registered individually. A NAMESPACE default can be registered
for a whole family (`browser.*`, `code.*`) so a subsystem's many sub-events share
a policy without enumerating each one. Resolution prefers the exact type, then the
longest matching namespace prefix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from .envelope import EclipseEvent, PRIORITIES

DELIVERY_SYNC = "sync"
DELIVERY_ASYNC = "async"
DELIVERY_AT_LEAST_ONCE = "at_least_once"
DELIVERY_BEST_EFFORT = "best_effort"
DELIVERY_MODES = (DELIVERY_SYNC, DELIVERY_ASYNC, DELIVERY_AT_LEAST_ONCE, DELIVERY_BEST_EFFORT)


@dataclass(frozen=True)
class RetryPolicy:
    """Consumer delivery retry policy (max attempts + exponential backoff + jitter)."""

    max_attempts: int = 5
    initial_backoff_s: float = 1.0
    multiplier: float = 2.0
    max_backoff_s: float = 600.0
    jitter: bool = True
    retryable: tuple[str, ...] = ()  # error classes; empty = default retryable set

    def backoff(self, attempt: int, *, rng: Optional[Callable[[], float]] = None) -> float:
        import random

        delay = self.initial_backoff_s * (self.multiplier ** max(0, attempt - 1))
        delay = min(delay, self.max_backoff_s)
        if self.jitter:
            rnd = rng or random.random
            delay = delay * (0.5 + rnd() * 0.5)
        return max(0.0, delay)


@dataclass(frozen=True)
class EventTypeSpec:
    type: str
    version: int = 1
    description: str = ""
    producer: tuple[str, ...] = ()
    consumers: tuple[str, ...] = ()
    permission: Optional[str] = None
    priority: str = "normal"
    retention_days: int = 30
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    delivery: str = DELIVERY_ASYNC
    sensitive: bool = False
    required_fields: tuple[str, ...] = ()
    field_types: Mapping[str, type] = field(default_factory=dict)
    # A namespace spec (`browser`) applies to any `browser.<...>` event.
    namespace: bool = False

    def matches_namespace(self, event_type: str) -> bool:
        if not self.namespace:
            return False
        return event_type == self.type or event_type.startswith(f"{self.type}.")


_FAST_RETRY = RetryPolicy(max_attempts=5, initial_backoff_s=1.0, multiplier=4.0, max_backoff_s=600.0)
_ONE_SHOT = RetryPolicy(max_attempts=1, initial_backoff_s=0.0)
_LONG_RETRY = RetryPolicy(max_attempts=6, initial_backoff_s=2.0, multiplier=3.0, max_backoff_s=900.0)


def _spec(
    type: str,
    *,
    description: str = "",
    producer: tuple[str, ...] = (),
    consumers: tuple[str, ...] = (),
    permission: Optional[str] = None,
    priority: str = "normal",
    retention_days: int = 30,
    retry: Optional[RetryPolicy] = None,
    delivery: str = DELIVERY_ASYNC,
    sensitive: bool = False,
    required_fields: tuple[str, ...] = (),
    field_types: Optional[Mapping[str, type]] = None,
    version: int = 1,
) -> EventTypeSpec:
    return EventTypeSpec(
        type=type,
        version=version,
        description=description,
        producer=producer,
        consumers=consumers,
        permission=permission,
        priority=priority,
        retention_days=retention_days,
        retry=retry or RetryPolicy(),
        delivery=delivery,
        sensitive=sensitive,
        required_fields=required_fields,
        field_types=field_types or {},
    )


def _build_default_specs() -> list[EventTypeSpec]:
    s: list[EventTypeSpec] = []

    # ── system / user ────────────────────────────────────────────────────────
    s += [
        _spec("system.started", description="Runtime boot completed", producer=("harness",), retention_days=7, priority="low"),
        _spec("system.shutdown", description="Runtime shutting down", producer=("harness",), retention_days=7, priority="low"),
        _spec("user.message", description="A user turn entered the runtime", producer=("frontdoor",), consumers=("harness",), sensitive=True, retention_days=90),
        _spec("user.approval.required", description="A user decision is required", producer=("harness",), sensitive=True, retention_days=90, priority="high"),
    ]

    # ── run lifecycle (existing harness emissions) ───────────────────────────
    for name, desc, prio in [
        ("run.created", "A run was created", "normal"),
        ("run.started", "A run started executing", "normal"),
        ("run.completed", "A run completed successfully", "normal"),
        ("run.failed", "A run failed", "high"),
        ("run.cancelled", "A run was cancelled", "normal"),
        ("run.resumed", "A run resumed from a checkpoint", "normal"),
        ("run.replanned", "A run replanned", "normal"),
    ]:
        s.append(_spec(name, description=desc, producer=("harness",), priority=prio, retention_days=90))

    # ── model ────────────────────────────────────────────────────────────────
    s += [
        _spec("model.requested", description="A model call was issued", producer=("model_runtime", "harness"), retention_days=14),
        _spec("model.completed", description="A model call returned", producer=("model_runtime", "harness"), retention_days=14),
        _spec("model.failed", description="A model call failed", producer=("model_runtime", "harness"), priority="high", retention_days=30),
        _spec("model.usage.recorded", description="Token/cost usage was recorded", producer=("model_runtime",), retention_days=30, priority="low"),
    ]

    # ── agent ────────────────────────────────────────────────────────────────
    for name, desc, prio in [
        ("agent.created", "An agent was created", "normal"),
        ("agent.started", "An agent started", "normal"),
        ("agent.completed", "An agent completed", "normal"),
        ("agent.failed", "An agent failed", "high"),
        ("agent.paused", "An agent paused", "normal"),
        ("agent.resumed", "An agent resumed", "normal"),
    ]:
        s.append(_spec(name, description=desc, producer=("harness",), consumers=("self_improvement",), priority=prio))

    # ── task ─────────────────────────────────────────────────────────────────
    for name, desc, prio in [
        ("task.created", "A durable task was created", "normal"),
        ("task.started", "A task started", "normal"),
        ("task.verifying", "A task entered verification", "normal"),
        ("task.asking_user", "A task is waiting on a human", "normal"),
        ("task.completed", "A task completed", "normal"),
        ("task.failed", "A task failed", "high"),
        ("task.escalated", "A task was escalated instead of failing", "high"),
        ("task.cancelled", "A task was cancelled", "normal"),
        ("task.blocked", "A task became blocked", "normal"),
        ("task.unblocked", "A task became runnable", "normal"),
        ("task.retried", "A task was retried", "normal"),
        ("task.progress.updated", "A task made progress", "low"),
    ]:
        s.append(_spec(
            name,
            description=desc,
            producer=("tasks",),
            consumers=("automation", "memory", "self_improvement"),
            priority=prio,
            retention_days=90,
            required_fields=("taskId",) if name != "task.created" else (),
        ))

    # ── workflow ─────────────────────────────────────────────────────────────
    for name, desc, prio in [
        ("workflow.created", "A workflow was created", "normal"),
        ("workflow.started", "A workflow started", "normal"),
        ("workflow.revised", "A workflow's plan structure changed", "normal"),
        ("workflow.completed", "A workflow completed", "normal"),
        ("workflow.failed", "A workflow failed", "high"),
        ("workflow.cancelled", "A workflow was cancelled", "normal"),
    ]:
        s.append(_spec(name, description=desc, producer=("workflows",), consumers=("automation",), priority=prio, retention_days=90))

    # ── tool / process ───────────────────────────────────────────────────────
    s += [
        _spec("tool.called", description="A tool was called", producer=("harness",), retention_days=30),
        _spec("tool.requested", description="A tool call was requested", producer=("harness",), retention_days=14),
        _spec("tool.completed", description="A tool call completed", producer=("harness",), retention_days=30),
        _spec("tool.failed", description="A tool call failed", producer=("harness",), consumers=("self_improvement",), priority="high", retention_days=60),
        _spec("process.started", description="A background process started", producer=("terminal",), retention_days=14),
        _spec("process.completed", description="A background process exited", producer=("terminal",), retention_days=14),
        _spec("process.failed", description="A background process failed", producer=("terminal",), priority="high", retention_days=30),
    ]

    # ── file (debounced/coalesced by the bus) ────────────────────────────────
    s += [
        _spec("file.created", description="A workspace file was created", producer=("code.fs",), priority="low", delivery=DELIVERY_BEST_EFFORT, retention_days=7),
        _spec("file.changed", description="A workspace file changed", producer=("code.fs",), priority="low", delivery=DELIVERY_BEST_EFFORT, retention_days=7),
        _spec("file.deleted", description="A workspace file was deleted", producer=("code.fs",), priority="low", delivery=DELIVERY_BEST_EFFORT, retention_days=7),
    ]

    # ── research / evidence ──────────────────────────────────────────────────
    for name, desc in [
        ("research.started", "Research began"),
        ("research.source.found", "A research source was found"),
        ("research.source.discovered", "A research source was discovered"),
        ("research.source.fetched", "A research source was fetched"),
        ("research.claim.created", "A research claim was created"),
        ("research.evidence.created", "Evidence was recorded"),
        ("research.completed", "Research completed"),
        ("research.failed", "Research failed"),
    ]:
        s.append(_spec(name, description=desc, producer=("research",), consumers=("memory",), retention_days=180))

    # ── market / financial ───────────────────────────────────────────────────
    s += [
        _spec("market.price.updated", description="A market price updated (high frequency)", producer=("market",), priority="bulk", delivery=DELIVERY_BEST_EFFORT, retention_days=3),
        _spec("market.snapshot.updated", description="A coalesced market snapshot", producer=("market",), priority="normal", retention_days=30),
        _spec("market.candle.closed", description="A candle closed", producer=("market",), priority="normal", retention_days=90),
        _spec("filing.discovered", description="A regulatory filing was discovered", producer=("research",), priority="high", retention_days=365),
        _spec("filing.updated", description="A filing was updated", producer=("research",), retention_days=365),
        _spec("fundamental.updated", description="Fundamentals changed", producer=("fundamentals",), retention_days=365),
        _spec("portfolio.position.added", description="A position was added", producer=("portfolio",), retention_days=365),
        _spec("portfolio.position.updated", description="A position was updated", producer=("portfolio",), retention_days=365),
        _spec("portfolio.position.removed", description="A position was removed", producer=("portfolio",), retention_days=365),
        _spec("risk.threshold.breached", description="A risk threshold was breached", producer=("portfolio", "risk"), priority="critical", sensitive=True, retention_days=365),
        _spec("strategy.signal.generated", description="A strategy produced a signal", producer=("quant",), priority="high", retention_days=180),
        _spec("backtest.started", description="A backtest started", producer=("quant",), retention_days=180),
        _spec("backtest.completed", description="A backtest completed", producer=("quant",), retention_days=180),
        _spec("backtest.failed", description="A backtest failed", producer=("quant",), priority="high", retention_days=180),
    ]

    # ── schedule / automation ────────────────────────────────────────────────
    s += [
        _spec("schedule.triggered", description="A scheduler fired", producer=("jobs", "automation"), consumers=("automation", "workflows", "agents"), retention_days=90),
        _spec("automation.triggered", description="An automation execution was triggered", producer=("automation",), retention_days=90),
        _spec("automation.completed", description="An automation execution completed", producer=("automation",), retention_days=90),
        _spec("automation.failed", description="An automation execution failed", producer=("automation",), priority="high", retention_days=120),
        _spec("automation.delivered", description="An automation delivered a result", producer=("automation",), priority="low", retention_days=30),
    ]

    # ── memory / evaluation / self-improvement ───────────────────────────────
    s += [
        _spec("memory.created", description="A memory was created", producer=("memory",), retention_days=365),
        _spec("memory.updated", description="A memory was updated", producer=("memory",), retention_days=365),
        _spec("memory.candidate.created", description="An event was proposed as a memory candidate", producer=("events",), consumers=("memory",), priority="low", retention_days=30),
        _spec("evaluation.started", description="An evaluation started", producer=("eval", "self_improvement"), retention_days=180),
        _spec("evaluation.completed", description="An evaluation completed", producer=("eval", "self_improvement"), consumers=("self_improvement",), retention_days=365),
        _spec("recovery.completed", description="A recovery attempt completed", producer=("self_improvement",), retention_days=180),
    ]

    # ── approval / session / misc existing ───────────────────────────────────
    s += [
        _spec("approval.requested", description="An approval was requested", producer=("harness",), sensitive=True, priority="high", retention_days=180),
        _spec("approval.granted", description="An approval was granted", producer=("harness",), sensitive=True, retention_days=180),
        _spec("session.indexed", description="A session was indexed for search", producer=("search",), priority="low", retention_days=30),
        _spec("finance.analysis", description="A financial analysis completed", producer=("research",), retention_days=180),
        _spec("prompt.plan", description="A prompt plan was produced", producer=("harness",), priority="low", retention_days=7),
        _spec("context.retry", description="Context was rebuilt and retried", producer=("harness",), priority="low", retention_days=7),
        _spec("notification.sent", description="A notification was delivered", producer=("harness",), priority="low", retention_days=30),
    ]

    # ── namespaces (many sub-events, one policy) ─────────────────────────────
    namespaces = [
        ("browser", ("browser",), 30, "normal"),
        ("code", ("code",), 60, "normal"),
        ("delegation", ("harness",), 60, "normal"),
        ("artifact", ("artifacts",), 180, "normal"),
        ("document", ("document",), 90, "normal"),
        ("vision", ("vision",), 30, "normal"),
        ("mcp", ("mcp",), 30, "normal"),
        ("terminal", ("terminal",), 14, "normal"),
        ("computer", ("computer",), 14, "normal"),
        ("git", ("git",), 30, "normal"),
        ("search", ("search",), 14, "low"),
        ("memory.history", ("harness",), 7, "low"),
        ("market", ("market",), 7, "bulk"),
        ("portfolio", ("portfolio",), 180, "normal"),
        ("evaluation", ("eval",), 180, "normal"),
        ("recovery", ("self_improvement",), 180, "normal"),
        ("skill", ("skills",), 90, "normal"),
        ("learning", ("skills",), 90, "normal"),
        ("security", ("security",), 365, "normal"),
    ]
    for prefix, producer, retention, priority in namespaces:
        spec = _spec(prefix, description=f"{prefix} namespace events", producer=producer, retention_days=retention, priority=priority)
        s.append(EventTypeSpec(
            type=spec.type, version=1, description=spec.description, producer=spec.producer,
            consumers=spec.consumers, permission=spec.permission, priority=spec.priority,
            retention_days=spec.retention_days, retry=spec.retry, delivery=spec.delivery,
            sensitive=spec.sensitive, required_fields=spec.required_fields, field_types={}, namespace=True,
        ))

    return s


class EventRegistry:
    """A registry of event contracts with validation + discovery."""

    def __init__(self) -> None:
        self._by_type: dict[str, dict[int, EventTypeSpec]] = {}
        self._namespaces: dict[str, EventTypeSpec] = {}

    # ── registration ─────────────────────────────────────────────────────────
    def register(self, spec: EventTypeSpec) -> None:
        if spec.namespace:
            self._namespaces[spec.type] = spec
            return
        versions = self._by_type.setdefault(spec.type, {})
        versions[spec.version] = spec

    def register_all(self, specs: list[EventTypeSpec]) -> None:
        for spec in specs:
            self.register(spec)

    # ── resolution ───────────────────────────────────────────────────────────
    def get(self, event_type: str, version: Optional[int] = None) -> Optional[EventTypeSpec]:
        versions = self._by_type.get(event_type)
        if versions:
            if version is not None and version in versions:
                return versions[version]
            return versions[max(versions)]
        # Longest namespace prefix wins.
        best: Optional[EventTypeSpec] = None
        for prefix, spec in self._namespaces.items():
            if spec.matches_namespace(event_type):
                if best is None or len(prefix) > len(best.type):
                    best = spec
        return best

    def latest_version(self, event_type: str) -> Optional[int]:
        versions = self._by_type.get(event_type)
        return max(versions) if versions else None

    def known(self, event_type: str) -> bool:
        return event_type in self._by_type or self.get(event_type) is not None

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for event_type, versions in sorted(self._by_type.items()):
            for version, spec in sorted(versions.items()):
                out.append(self._describe(spec, namespace=False))
        for prefix, spec in sorted(self._namespaces.items()):
            out.append(self._describe(spec, namespace=True))
        return out

    def namespaces(self) -> list[str]:
        return sorted(self._namespaces)

    @staticmethod
    def _describe(spec: EventTypeSpec, *, namespace: bool) -> dict[str, Any]:
        return {
            "type": spec.type,
            "version": spec.version,
            "namespace": namespace,
            "description": spec.description,
            "producer": list(spec.producer),
            "consumers": list(spec.consumers),
            "permission": spec.permission,
            "priority": spec.priority,
            "retentionDays": spec.retention_days,
            "delivery": spec.delivery,
            "sensitive": spec.sensitive,
            "requiredFields": list(spec.required_fields),
            "retry": {
                "maxAttempts": spec.retry.max_attempts,
                "initialBackoffS": spec.retry.initial_backoff_s,
                "multiplier": spec.retry.multiplier,
                "maxBackoffS": spec.retry.max_backoff_s,
                "jitter": spec.retry.jitter,
            },
        }

    # ── validation ───────────────────────────────────────────────────────────
    def validate(self, event: EclipseEvent, *, require_known: bool = False) -> list[str]:
        """Return a list of validation issues (empty = valid).

        `require_known=True` refuses an event whose type is not registered at all;
        the ingest bridge uses `False` (auto-registering observed legacy events) so
        no event is ever silently lost.
        """
        issues: list[str] = []
        if not event.type or "." not in event.type:
            issues.append(f"event type {event.type!r} is not hierarchical")
        if event.priority not in PRIORITIES:
            issues.append(f"invalid priority {event.priority!r}")
        spec = self.get(event.type, event.version)
        if spec is None:
            if require_known:
                issues.append(f"unknown event type {event.type!r}")
            return issues
        missing = [f for f in spec.required_fields if f not in event.payload]
        if missing:
            issues.append(f"{event.type} missing required payload fields: {', '.join(missing)}")
        for name, expected in spec.field_types.items():
            if name in event.payload and event.payload[name] is not None:
                if not isinstance(event.payload[name], expected):
                    issues.append(f"{event.type}.{name} must be {getattr(expected, '__name__', expected)}")
        return issues


_DEFAULT: Optional[EventRegistry] = None


def default_registry() -> EventRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        registry = EventRegistry()
        registry.register_all(_build_default_specs())
        _DEFAULT = registry
    return _DEFAULT


__all__ = [
    "DELIVERY_ASYNC",
    "DELIVERY_AT_LEAST_ONCE",
    "DELIVERY_BEST_EFFORT",
    "DELIVERY_MODES",
    "DELIVERY_SYNC",
    "EventRegistry",
    "EventTypeSpec",
    "RetryPolicy",
    "default_registry",
]
