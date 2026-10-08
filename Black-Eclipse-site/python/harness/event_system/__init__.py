"""Eclipse Event System — the durable, reactive nervous system of the harness.

This package is the ONE canonical event model. It does NOT replace the existing
per-run live bus in `harness.events` (which stays the low-latency SSE transport);
it *unifies* around it: every legacy event published on the run bus is ingested
here, validated against the registry, persisted to the event store, and delivered
to durable subscribers with retry, dead-letter handling, idempotency, correlation
and metrics.

Layering:

    envelope     canonical `EclipseEvent` + correlation/causation context vars
    registry     centralized event-type registry (schema + policy)
    filters      exact / namespace-wildcard / predicate subscriptions
    store        durable event log + consumer idempotency + DLQ (agent-memory.db)
    metrics      counters + latency percentiles
    middleware   composable validation / redaction / enrichment / tracing
    bus          publish/subscribe core + async workers + retry + DLQ
    rules        event → action rule bridge (delegates to the Automation Engine)
    replay       safe observe/simulation/full replay
    security     publish/subscribe authorization + secret redaction
    service      the EventSystem facade (owns store+bus+registry+replay)
    bootstrap    install into the process-wide AgenticService

Nothing here runs an agent loop or a workflow: it is transport + policy. Actions
are dispatched through the existing runtime (`service.run`, automations, tools).
"""

from __future__ import annotations

from .envelope import (
    ACTOR_TYPES,
    PRIORITIES,
    Actor,
    EclipseEvent,
    causation_id,
    correlation_id,
    event_context,
    new_event_id,
    new_trace_id,
)
from .registry import (
    DELIVERY_AT_LEAST_ONCE,
    DELIVERY_BEST_EFFORT,
    DELIVERY_SYNC,
    EventRegistry,
    EventTypeSpec,
    RetryPolicy,
    default_registry,
)
from .bus import EventBus, Subscription
from .store import EventStore
from .service import EventSystem
from .bootstrap import install_event_system

__all__ = [
    "ACTOR_TYPES",
    "PRIORITIES",
    "Actor",
    "EclipseEvent",
    "EventBus",
    "EventRegistry",
    "EventStore",
    "EventSystem",
    "EventTypeSpec",
    "RetryPolicy",
    "Subscription",
    "causation_id",
    "correlation_id",
    "default_registry",
    "event_context",
    "install_event_system",
    "new_event_id",
    "new_trace_id",
    "DELIVERY_AT_LEAST_ONCE",
    "DELIVERY_BEST_EFFORT",
    "DELIVERY_SYNC",
]
