"""The EventSystem facade — the ONE entry point for publishing and observing.

Owns the registry, event store, bus, replay service and metrics, and installs the
handful of built-in consumers that turn the event stream into useful behaviour
WITHOUT creating feedback loops or an event storm:

  * memory candidate extractor — selected durable events become bounded
    `memory.candidate.created` events (never a direct memory write);
  * self-improvement trigger — failures request ONE bounded evaluation per
    correlation (loop- and depth-guarded);
  * market sampler — high-frequency `market.price.updated` events are coalesced
    into `market.snapshot.updated` so a price tick can never cause an LLM call.

The facade is transport + policy only. It never runs an agent loop itself.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from .bus import EventBus, Subscription
from .config import EventConfig
from .envelope import Actor, EclipseEvent
from .metrics import EventMetrics
from .registry import EventRegistry, RetryPolicy, default_registry
from .replay import ReplayResult, ReplayService
from .rules import EventRuleBridge
from .security import EventAuthorizer
from .store import EventStore

log = logging.getLogger("harness.events")

# Loop prevention: no auto-triggered recovery evaluation deeper than this, and at
# most this many per correlation id. A failure → analyzer → failure cycle stops.
MAX_CAUSATION_DEPTH = 6
MAX_RECOVERY_PER_CORRELATION = 2
_MEMORY_SOURCES = (
    "task.completed",
    "run.completed",
    "research.completed",
    "evaluation.completed",
    "memory.updated",
)
_FAILURE_TYPES = (
    "task.failed",
    "agent.failed",
    "tool.failed",
    "workflow.failed",
    "run.failed",
    "automation.failed",
    "process.failed",
    "backtest.failed",
    "research.failed",
)
_MARKET_SOURCES = ("market.price.updated",)
_MARKET_DEFAULT_INTERVAL = 2.0
_MARKET_MAX_SYMBOLS = 500


class EventSystem:
    def __init__(
        self,
        service: Any,
        *,
        store: Optional[EventStore] = None,
        registry: Optional[EventRegistry] = None,
        bus: Optional[EventBus] = None,
        config: Optional[EventConfig] = None,
        max_concurrency: Optional[int] = None,
        echo_legacy: Optional[bool] = None,
    ) -> None:
        self._service = service
        self.config = config or EventConfig.from_env()
        self.registry = registry or default_registry()
        self.store = store or EventStore(service.store)
        self.metrics = EventMetrics()
        self.authorizer = EventAuthorizer(self.registry)
        self.bus = bus or EventBus(
            self.store, self.registry, self.metrics,
            authorizer=self.authorizer,
            legacy_bus=getattr(service, "bus", None),
            max_concurrency=max_concurrency or self.config.max_concurrency,
            max_queue=self.config.max_queue,
            deduplication_enabled=self.config.deduplication_enabled,
            persist_enabled=self.config.store_enabled,
            default_retry=RetryPolicy(max_attempts=self.config.max_retries),
            echo_legacy=self.config.echo_legacy if echo_legacy is None else echo_legacy,
        )
        self.replay_service = ReplayService(self.store, self.bus)
        self.rules = EventRuleBridge(service)
        self._subscriptions: list[Subscription] = []
        self._recovery_counts: dict[str, int] = {}
        self._sampler: Optional[MarketSampler] = None
        self._started = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._started:
            return
        from .emit import set_loop  # noqa: PLC0415

        set_loop(asyncio.get_running_loop())
        self.bus.start()
        self._prune_retention()
        # Drop any subscriptions left over from a previous lifespan so consumers
        # never accumulate (and stale workers never linger) across restarts.
        self._subscriptions.clear()
        self._install_default_consumers()
        self._sampler = MarketSampler(self)
        await self._sampler.start()
        self._started = True
        await self.publish(
            "system.started",
            {"pid": __import__("os").getpid()},
            source="harness",
            priority="low",
            metadata={"boot": True},
        )

    async def stop(self) -> None:
        # `_started` MUST be reset even if the bus teardown raises, otherwise the
        # next boot's `start()` early-returns and the bus stays `_closed=True`
        # (its `publish()` then silently drops every event).
        try:
            if self._sampler is not None:
                await self._sampler.stop()
            await self.bus.shutdown()
        finally:
            self._started = False

    # ── publish API ──────────────────────────────────────────────────────────
    async def publish(
        self,
        type: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        source: str = "harness",
        version: int = 1,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        actor: Optional[Actor] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[EclipseEvent]:
        event = EclipseEvent.create(
            type,
            payload or {},
            source=source,
            version=version,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            task_id=task_id,
            workflow_id=workflow_id,
            agent_id=agent_id,
            session_id=session_id,
            priority=priority or (self.registry.get(type, version).priority if self.registry.get(type, version) else "normal"),
            metadata=metadata,
        )
        return await self.bus.publish(event)

    def emit_nowait(self, type: str, payload: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        """Publish from a synchronous seam (fire-and-forget onto the loop)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(type, payload, **kwargs))

    def _prune_retention(self) -> None:
        """Best-effort retention sweep on boot (never blocks startup)."""
        try:
            import datetime as _dt

            cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=self.config.retention_days))
            before = cutoff.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"
            self.store.prune(before_iso=before)
        except Exception:  # noqa: BLE001 - retention must never block boot
            log.warning("event retention prune failed", exc_info=True)

    # ── built-in consumers ───────────────────────────────────────────────────
    def _install_default_consumers(self) -> None:
        self._subscriptions.append(self.bus.subscribe(
            _MEMORY_SOURCES, self._on_memory_candidate,
            consumer_id="events.memory_candidate", retry=None, idempotent=True,
        ))
        self._subscriptions.append(self.bus.subscribe(
            _FAILURE_TYPES, self._on_failure,
            consumer_id="events.self_improvement", idempotent=True,
        ))
        # The RSL conductor is a periodic task; `evaluation.started` is its
        # event wake. This consumer only wakes the loop — it never runs an
        # evaluation itself (the loop owns claim/lease/budget).
        self._subscriptions.append(self.bus.subscribe(
            "evaluation.started", self._on_evaluation_started,
            consumer_id="events.rsl_wake", idempotent=True,
        ))

    async def _on_memory_candidate(self, event: EclipseEvent) -> None:
        if event.replay:
            return
        candidate = {
            "sourceEventId": event.id,
            "sourceType": event.type,
            "correlationId": event.correlation_id,
            "taskId": event.task_id,
            "workflowId": event.workflow_id,
            "agentId": event.agent_id,
            "summary": _summarize(event.payload),
        }
        # Emit the candidate on a child event; the memory subsystem decides whether
        # to turn it into a durable memory. The Event Store is never agent memory.
        await self.bus.publish(event.child(
            "memory.candidate.created", candidate, source="events",
            metadata={"kind": "memory_candidate"},
        ))

    async def _on_failure(self, event: EclipseEvent) -> None:
        if event.replay:
            return
        if event.depth >= MAX_CAUSATION_DEPTH:
            self.metrics.inc("loopGuarded")
            return
        key = event.correlation_id or event.id
        count = self._recovery_counts.get(key, 0)
        if count >= MAX_RECOVERY_PER_CORRELATION:
            self.metrics.inc("loopGuarded")
            return
        if len(self._recovery_counts) > 5000:
            self._recovery_counts.clear()
        self._recovery_counts[key] = count + 1
        await self.bus.publish(event.child(
            "evaluation.started",
            {
                "reason": "failure_analysis",
                "failedEventId": event.id,
                "failedType": event.type,
                "recoveryAttempt": count + 1,
            },
            source="self_improvement",
            priority="high",
            metadata={"kind": "recovery_evaluation", "recovery": True},
        ))

    # ── subscriptions ────────────────────────────────────────────────────────
    async def _on_evaluation_started(self, event: EclipseEvent) -> None:
        """Wake the RSL conductor; the loop decides whether there is work."""
        if event.replay:
            return
        try:
            rsl_loop = getattr(self._service, "_rsl_loop", None)
            if rsl_loop is not None:
                rsl_loop.wake()
        except Exception:  # noqa: BLE001 - waking the loop is best-effort
            pass

    def subscribe(self, filter_like: Any, handler: Any, **kwargs: Any) -> Subscription:
        return self.bus.subscribe(filter_like, handler, **kwargs)

    def subscriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "consumerId": s.consumer_id,
                "patterns": list(s.event_filter.patterns),
                "delivery": s.delivery,
                "delivered": s.delivered,
                "errors": s.errors,
                "queueDepth": s.queue.qsize() if s.queue else 0,
            }
            for s in self.bus.subscriptions()
        ]

    # ── introspection / console ──────────────────────────────────────────────
    def recent(self, **query: Any) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.store.query(**query)]

    def event(self, event_id: str) -> Optional[dict[str, Any]]:
        found = self.store.get(event_id)
        if found is None:
            return None
        view = found.to_dict()
        view["consumers"] = self.store.list_consumers(event_id=event_id)
        return view

    def graph(self, **kwargs: Any) -> dict[str, Any]:
        return self.store.graph(**kwargs)

    def dlq(self, *, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_dead_letters(status=status, limit=limit)

    def registry_view(self) -> list[dict[str, Any]]:
        return self.registry.list()

    def metrics_snapshot(self) -> dict[str, Any]:
        snapshot = self.metrics.snapshot()
        snapshot["eventStoreCount"] = self.store.count()
        snapshot["deadLetterPending"] = self.store.dlq_count()
        return snapshot

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._started else "stopped",
            "bus": self.bus.health(),
            "eventCount": self.store.count(),
            "deadLetterPending": self.store.dlq_count(),
            "registrySize": len(self.registry.list()),
        }

    # ── replay ───────────────────────────────────────────────────────────────
    async def replay(
        self,
        *,
        mode: str = "observe",
        authorized: bool = False,
        confirm_destructive: bool = False,
        **query: Any,
    ) -> ReplayResult:
        if not self.config.replay_enabled:
            from .replay import ReplayError  # noqa: PLC0415

            raise ReplayError("REPLAY_DISABLED", "replay is disabled (EVENT_REPLAY_ENABLED=0)")
        events = self.replay_service.query(**query)
        return await self.replay_service.replay(
            events, mode=mode, authorized=authorized, confirm_destructive=confirm_destructive
        )

    async def retry_dead_letter(self, dlq_id: str, *, confirm_destructive: bool = False) -> ReplayResult:
        entry = self.store.get_dead_letter(dlq_id)
        if entry is None:
            from .replay import ReplayError  # noqa: PLC0415

            raise ReplayError("NOT_FOUND", "dead letter not found")
        event = self.store.get(entry["eventId"])
        if event is None:
            self.store.set_dead_letter_status(dlq_id, "discarded")
            from .replay import ReplayError  # noqa: PLC0415

            raise ReplayError("EVENT_GONE", "the original event is no longer in the store")
        result = await self.replay_service.replay(
            [event], mode="full", authorized=True, confirm_destructive=confirm_destructive
        )
        self.store.set_dead_letter_status(dlq_id, "replayed")
        return result


def _summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Bounded summary: primitives only, capped field count and string length."""
    out: dict[str, Any] = {}
    for key, value in list(payload.items())[:20]:
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value[:300] if isinstance(value, str) else value
    return out


class MarketSampler:
    """Coalesce high-frequency market events; never one LLM call per price tick.

    Buffers the latest payload per symbol and flushes a single
    `market.snapshot.updated` per interval. Bounded by symbol count and interval,
    so an event storm degrades to a fixed-rate aggregated stream.
    """

    def __init__(self, system: EventSystem, *, interval: float = _MARKET_DEFAULT_INTERVAL, max_symbols: int = _MARKET_MAX_SYMBOLS) -> None:
        self._system = system
        self._interval = max(0.05, float(interval))
        self._max_symbols = max(1, int(max_symbols))
        self._buffer: dict[str, dict[str, Any]] = {}
        self._task: Optional[asyncio.Task] = None
        self._sub: Optional[Subscription] = None

    async def start(self) -> None:
        self._sub = self._system.bus.subscribe(
            _MARKET_SOURCES, self._on_tick,
            consumer_id="events.market_sampler", idempotent=False,
        )
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._sub is not None:
            self._system.bus.unsubscribe(self._sub)
            self._sub = None

    def _on_tick(self, event: EclipseEvent) -> None:
        symbol = str(event.payload.get("symbol") or event.payload.get("instrument") or "unknown")
        if len(self._buffer) >= self._max_symbols and symbol not in self._buffer:
            return
        entry = self._buffer.setdefault(symbol, {"symbol": symbol, "ticks": 0, "first": None, "last": None})
        entry["ticks"] += 1
        for key in ("price", "changePercent", "volume", "bid", "ask", "last"):
            if key in event.payload:
                entry[key] = event.payload[key]
        if entry["first"] is None:
            entry["first"] = event.payload.get("price")
        entry["last"] = event.payload.get("price")
        entry.setdefault("correlationId", event.correlation_id)
        entry["lastAt"] = event.timestamp

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            if not self._buffer:
                continue
            batch = list(self._buffer.values())
            self._buffer.clear()
            for snapshot in batch:
                snapshot["windowSeconds"] = self._interval
                await self._system.publish(
                    "market.snapshot.updated",
                    snapshot,
                    source="events.market_sampler",
                    priority="normal",
                    correlation_id=snapshot.get("correlationId"),
                    metadata={"sampled": True, "ticks": snapshot.get("ticks", 0)},
                )


__all__ = ["EventSystem", "MarketSampler", "MAX_CAUSATION_DEPTH", "MAX_RECOVERY_PER_CORRELATION"]
