"""The Eclipse Event Bus — publish/subscribe core.

Responsibilities:

  * `publish()` / `publish_many()` — validate, authorize, redact, enrich, persist,
    route to matching subscribers, and (optionally) echo to the legacy run bus so
    live SSE consumers keep working.
  * `subscribe()` / `unsubscribe()` / `once()` — durable or ephemeral consumers with
    exact / namespace / predicate filters.
  * `request()` — request/reply over a one-shot reply subscription.
  * per-subscription async workers with bounded queues (BACKPRESSURE),
    consumer-level IDEMPOTENCY, RETRY with exponential backoff + jitter, and a
    real DEAD LETTER QUEUE.
  * metrics, tracing and graceful shutdown.

The bus holds NO business logic: handlers are provided by the service/integration layer.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence, Union

from ..automation.model import DEFAULT_RETRYABLE_ERROR_CLASSES, NON_RETRYABLE_ERROR_CLASSES
from .envelope import EclipseEvent, event_context, from_legacy
from .filters import EventFilter
from .metrics import EventMetrics
from .middleware import Middleware, MiddlewareContext, default_pipeline
from .registry import (
    DELIVERY_BEST_EFFORT,
    DELIVERY_SYNC,
    EventRegistry,
    RetryPolicy,
)
from .security import EventAuthorizer
from .store import EventStore

log = logging.getLogger("harness.events.bus")

Handler = Callable[[EclipseEvent], Union[None, Awaitable[None]]]
FilterLike = Union[str, Sequence[str], EventFilter, Callable[[EclipseEvent], bool]]

DEFAULT_MAX_QUEUE = 1000
DEFAULT_MAX_CONCURRENCY = 16
_CLOSE = object()


@dataclass
class Subscription:
    """A registered consumer. Owns its own queue + worker when async."""

    id: str
    consumer_id: str
    event_filter: EventFilter
    handler: Handler
    delivery: str = "async"
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    idempotent: bool = True
    once: bool = False
    enabled: bool = True
    queue: Optional[asyncio.Queue] = None
    worker: Optional[asyncio.Task] = None
    delivered: int = 0
    errors: int = 0
    _bus: Optional["EventBus"] = None

    def unsubscribe(self) -> None:
        if self._bus is not None:
            self._bus.unsubscribe(self)


class _Dropped(Exception):
    """Raised internally when the middleware chain drops an event."""


class EventBus:
    def __init__(
        self,
        store: EventStore,
        registry: EventRegistry,
        metrics: Optional[EventMetrics] = None,
        *,
        authorizer: Optional[EventAuthorizer] = None,
        legacy_bus: Any = None,
        middleware: Optional[list[Middleware]] = None,
        max_queue: int = DEFAULT_MAX_QUEUE,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        default_retry: Optional[RetryPolicy] = None,
        require_known_types: bool = False,
        echo_legacy: bool = True,
        deduplication_enabled: bool = True,
        persist_enabled: bool = True,
    ) -> None:
        self._store = store
        self._registry = registry
        self.metrics = metrics or EventMetrics()
        self._authorizer = authorizer or EventAuthorizer(registry)
        self._legacy = legacy_bus
        self._legacy_unsubscribe: Optional[Callable[[], None]] = None
        self._max_queue = max(1, int(max_queue))
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._default_retry = default_retry or RetryPolicy()
        self._require_known_types = require_known_types
        self._echo_legacy = echo_legacy
        self._dedup = deduplication_enabled
        self._persist_enabled = persist_enabled
        self._subscriptions: dict[str, Subscription] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        ctx = MiddlewareContext(registry=registry, authorizer=self._authorizer, require_known_types=require_known_types)
        self._middleware_ctx = ctx
        self._middleware: list[Middleware] = middleware if middleware is not None else default_pipeline(ctx)

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Capture the running loop and bridge the legacy run bus (idempotent)."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._closed = False
        self._attach_legacy()

    async def shutdown(self, *, timeout: float = 10.0) -> None:
        """Graceful shutdown: stop accepting, drain in-flight work, close queues."""
        self._closed = True
        if self._legacy_unsubscribe is not None:
            try:
                self._legacy_unsubscribe()
            except Exception:  # noqa: BLE001
                pass
            self._legacy_unsubscribe = None
        for sub in list(self._subscriptions.values()):
            if sub.queue is not None:
                try:
                    sub.queue.put_nowait(_CLOSE)
                except asyncio.QueueFull:
                    pass
        workers = [s.worker for s in self._subscriptions.values() if s.worker is not None]
        if workers:
            try:
                await asyncio.wait_for(asyncio.gather(*workers, return_exceptions=True), timeout=timeout)
            except asyncio.TimeoutError:
                for worker in workers:
                    worker.cancel()

    # ── legacy bridge ────────────────────────────────────────────────────────
    def _attach_legacy(self) -> None:
        if self._legacy is None or self._legacy_unsubscribe is not None:
            return
        bus = self

        def _listener(legacy_event: dict[str, Any]) -> None:
            loop = bus._loop
            if loop is None or not loop.is_running():
                return
            loop.create_task(bus.ingest_legacy(legacy_event))

        try:
            self._legacy_unsubscribe = self._legacy.subscribe(_listener)
        except Exception:  # noqa: BLE001
            log.warning("failed to bridge legacy event bus", exc_info=True)

    async def ingest_legacy(self, legacy_event: dict[str, Any]) -> Optional[EclipseEvent]:
        """Ingest a loose event from the legacy run bus into the canonical model."""
        event = from_legacy(legacy_event, source="harness")
        event.metadata.setdefault("_legacyIngest", True)
        # Auto-register observed legacy namespaces so nothing is silently dropped.
        if not self._registry.known(event.type):
            self._observe(event.type)
        return await self.publish(event, _from_legacy=True)

    def _observe(self, event_type: str) -> None:
        from .registry import _spec  # noqa: PLC0415

        prefix = event_type.split(".")[0]
        if not self._registry.known(f"{prefix}._observed"):
            self._registry.register(_spec(
                f"{prefix}._observed",
                description=f"auto-observed {prefix} namespace",
                namespace=True,
                retention_days=7,
            ))
        # Register the exact observed type (permissive) so validation passes.
        self._registry.register(_spec(event_type, description=f"observed {event_type}", retention_days=7))

    def _echo_to_legacy(self, event: EclipseEvent) -> None:
        if self._legacy is None or not self._echo_legacy:
            return
        if event.metadata.get("_legacyIngest"):
            return  # already originated on the legacy bus; never echo it back
        try:
            self._legacy.publish({
                "id": event.id,
                "runId": event.session_id,
                "type": event.type,
                "seq": event.metadata.get("seq"),
                "at": event.timestamp,
                "data": event.payload,
                "_eclipseEvent": True,
            })
        except Exception:  # noqa: BLE001 - live echo is best-effort
            log.debug("legacy echo failed", exc_info=True)

    # ── subscriptions ────────────────────────────────────────────────────────
    def subscribe(
        self,
        filter_like: FilterLike,
        handler: Handler,
        *,
        consumer_id: Optional[str] = None,
        delivery: Optional[str] = None,
        retry: Optional[RetryPolicy] = None,
        idempotent: bool = True,
        once: bool = False,
        sync: bool = False,
        max_queue: Optional[int] = None,
    ) -> Subscription:
        event_filter = _normalize_filter(filter_like)
        cid = consumer_id or f"consumer_{uuid.uuid4().hex[:10]}"
        delivery_mode = delivery or (DELIVERY_SYNC if sync else "async")
        sub = Subscription(
            id=f"sub_{uuid.uuid4().hex[:16]}",
            consumer_id=cid,
            event_filter=event_filter,
            handler=handler,
            delivery=delivery_mode,
            retry=retry or self._default_retry,
            idempotent=idempotent and delivery_mode != DELIVERY_BEST_EFFORT,
            once=once,
            _bus=self,
        )
        if delivery_mode != DELIVERY_SYNC:
            sub.queue = asyncio.Queue(maxsize=max_queue or self._max_queue)
            try:
                sub.worker = asyncio.get_running_loop().create_task(self._worker(sub))
            except RuntimeError:
                sub.worker = None  # not on a loop yet; started lazily on publish
        self._subscriptions[sub.id] = sub
        self.metrics.set_subscribers(len(self._subscriptions))
        return sub

    def once(self, filter_like: FilterLike, handler: Handler, **kwargs: Any) -> Subscription:
        return self.subscribe(filter_like, handler, once=True, **kwargs)

    def unsubscribe(self, sub: Subscription) -> None:
        if self._subscriptions.pop(sub.id, None) is None:
            return
        if sub.queue is not None:
            try:
                sub.queue.put_nowait(_CLOSE)
            except asyncio.QueueFull:
                pass
        if sub.worker is not None and not sub.worker.done():
            sub.worker.cancel()
        self.metrics.set_subscribers(len(self._subscriptions))

    def subscriptions(self) -> list[Subscription]:
        return list(self._subscriptions.values())

    # ── publish ──────────────────────────────────────────────────────────────
    async def publish(
        self,
        event: Union[EclipseEvent, str],
        payload: Optional[dict[str, Any]] = None,
        *,
        actor: Any = None,
        **kwargs: Any,
    ) -> Optional[EclipseEvent]:
        if isinstance(event, str):
            event = EclipseEvent.create(event, payload or {}, **kwargs)
        if self._closed:
            return None
        # Middleware chain (validation → authorization → redaction → enrichment).
        processed: Optional[EclipseEvent] = event
        for stage in self._middleware:
            if processed is None:
                break
            processed = _apply_stage(stage, processed)
        if processed is None:
            self.metrics.inc("validationFailed")
            return None

        self.metrics.inc("published")
        self.metrics.observe_type(processed.type)

        persisted = processed.persisted and self._persist_enabled and not processed.metadata.get("transient")
        if persisted:
            appended = self._store.append(processed)
            if not appended:
                # Duplicate id ⇒ already delivered. Global dedup.
                self.metrics.inc("deduplicated")
                return processed
            self.metrics.inc("persisted")

        self._echo_to_legacy(processed)
        await self._route(processed)
        return processed

    async def publish_many(self, events: Sequence[Union[EclipseEvent, str]], **kwargs: Any) -> list[EclipseEvent]:
        out: list[EclipseEvent] = []
        for event in events:
            result = await self.publish(event, **kwargs)
            if result is not None:
                out.append(result)
        return out

    async def _route(self, event: EclipseEvent) -> None:
        for sub in list(self._subscriptions.values()):
            if not sub.enabled or not sub.event_filter.matches(event):
                continue
            if sub.delivery == DELIVERY_SYNC:
                await self._invoke_sync(sub, event)
                continue
            await self._enqueue(sub, event)

    async def _enqueue(self, sub: Subscription, event: EclipseEvent) -> None:
        if sub.queue is None:
            sub.queue = asyncio.Queue(maxsize=self._max_queue)
        if sub.worker is None or sub.worker.done():
            try:
                sub.worker = asyncio.get_running_loop().create_task(self._worker(sub))
            except RuntimeError:
                pass
        try:
            sub.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Backpressure: high/critical events apply bounded backpressure; bulk
            # and low-priority events are dropped (never allowed to stall a run).
            if event.priority in ("critical", "high"):
                try:
                    await asyncio.wait_for(sub.queue.put(event), timeout=2.0)
                except (asyncio.TimeoutError, asyncio.QueueFull):
                    self.metrics.inc("droppedBackpressure")
            else:
                self.metrics.inc("droppedBackpressure")

    async def _worker(self, sub: Subscription) -> None:
        assert sub.queue is not None
        while True:
            item = await sub.queue.get()
            if item is _CLOSE:
                return
            assert isinstance(item, EclipseEvent)
            await self._deliver_with_retry(sub, item)

    # ── delivery ─────────────────────────────────────────────────────────────
    async def _deliver_with_retry(self, sub: Subscription, event: EclipseEvent) -> None:
        if self._dedup and sub.idempotent and self._store.has_processed(event.id, sub.consumer_id):
            self.metrics.inc("deduplicated")
            return
        spec = self._registry.get(event.type, event.version)
        policy = sub.retry
        non_retryable = set(NON_RETRYABLE_ERROR_CLASSES)
        retryable = set(policy.retryable) if policy.retryable else set(DEFAULT_RETRYABLE_ERROR_CLASSES)
        attempt = 0
        first_failed_at: Optional[str] = None
        error_class = "INTERNAL_ERROR"
        try:
            while True:
                attempt += 1
                started = asyncio.get_event_loop().time()
                try:
                    async with self._semaphore:
                        with event_context(
                            correlation_id=event.correlation_id,
                            causation_id=event.id,
                            trace_id=event.trace_id,
                            depth=event.depth + 1,
                            actor=event.actor,
                            session_id=event.session_id,
                        ):
                            await _invoke(sub.handler, event)
                    self.metrics.observe_processing((asyncio.get_event_loop().time() - started) * 1000.0)
                    sub.delivered += 1
                    self.metrics.inc("delivered")
                    if sub.idempotent:
                        self._store.mark_processed(event.id, sub.consumer_id)
                    if sub.once:
                        self.unsubscribe(sub)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - a consumer failure is handled
                    error_class, message, trace = _classify(exc)
                    if first_failed_at is None:
                        from ..persistence import now_iso  # noqa: PLC0415

                        first_failed_at = now_iso()
                    sub.errors += 1
                    retryable_here = error_class not in non_retryable and error_class in retryable
                    if not retryable_here or attempt >= max(1, policy.max_attempts):
                        self._store.record_failure(event.id, sub.consumer_id, error=message, error_class=error_class)
                        dlq_id = self._store.record_dead_letter(
                            event_id=event.id, consumer_id=sub.consumer_id, event_type=event.type,
                            error=message, error_class=error_class, attempts=attempt,
                            first_failed_at=first_failed_at, stack_trace=trace,
                        )
                        self.metrics.inc("failed")
                        self.metrics.inc("deadLettered")
                        log.warning("event %s -> consumer %s dead-lettered (%s): %s",
                                    event.type, sub.consumer_id, dlq_id, message)
                        return
                    self.metrics.inc("retried")
                    delay = policy.backoff(attempt)
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

    async def _invoke_sync(self, sub: Subscription, event: EclipseEvent) -> None:
        if self._dedup and sub.idempotent and self._store.has_processed(event.id, sub.consumer_id):
            self.metrics.inc("deduplicated")
            return
        try:
            with event_context(
                correlation_id=event.correlation_id, causation_id=event.id,
                trace_id=event.trace_id, depth=event.depth + 1, actor=event.actor,
                session_id=event.session_id,
            ):
                await _invoke(sub.handler, event)
            sub.delivered += 1
            self.metrics.inc("delivered")
            if sub.idempotent:
                self._store.mark_processed(event.id, sub.consumer_id)
            if sub.once:
                self.unsubscribe(sub)
        except Exception as exc:  # noqa: BLE001 - a sync handler failure is recorded
            error_class, message, trace = _classify(exc)
            self._store.record_failure(event.id, sub.consumer_id, error=message, error_class=error_class)
            self._store.record_dead_letter(
                event_id=event.id, consumer_id=sub.consumer_id, event_type=event.type,
                error=message, error_class=error_class, attempts=1,
                first_failed_at=None, stack_trace=trace,
            )
            self.metrics.inc("failed")
            self.metrics.inc("deadLettered")

    # ── request / reply ──────────────────────────────────────────────────────
    async def request(
        self,
        event: EclipseEvent,
        *,
        reply_pattern: str = "reply.**",
        timeout: float = 30.0,
    ) -> Optional[EclipseEvent]:
        """Publish an event and await a correlated reply (bounded)."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[EclipseEvent] = loop.create_future()

        def _reply(reply: EclipseEvent) -> None:
            if not future.done():
                future.set_result(reply)

        sub = self.subscribe(
            EventFilter(patterns=(reply_pattern,), predicate_fn=lambda e: e.causation_id == event.id),
            _reply,
            sync=True,
            once=True,
            consumer_id=f"reply_{event.id}",
        )
        try:
            await self.publish(event)
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(sub)

    # ── introspection ────────────────────────────────────────────────────────
    def metrics_snapshot(self) -> dict[str, Any]:
        return self.metrics.snapshot()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if not self._closed else "closing",
            "subscriptions": len(self._subscriptions),
            "subscribers": [
                {
                    "consumerId": s.consumer_id,
                    "patterns": list(s.event_filter.patterns),
                    "delivery": s.delivery,
                    "delivered": s.delivered,
                    "errors": s.errors,
                    "queueDepth": (s.queue.qsize() if s.queue else 0),
                }
                for s in self._subscriptions.values()
            ],
            "metrics": self.metrics.snapshot(),
        }


def _apply_stage(stage: Middleware, event: EclipseEvent) -> Optional[EclipseEvent]:
    try:
        return stage(event)
    except Exception:  # noqa: BLE001 - a middleware bug must not break the run; fail-closed
        log.warning("event middleware stage failed", exc_info=True)
        return None


def _normalize_filter(filter_like: FilterLike) -> EventFilter:
    if isinstance(filter_like, EventFilter):
        return filter_like
    if isinstance(filter_like, str):
        return EventFilter(patterns=(filter_like,))
    if isinstance(filter_like, (list, tuple)):
        return EventFilter(patterns=tuple(filter_like))
    if callable(filter_like):
        return EventFilter(predicate_fn=filter_like)
    raise TypeError(f"unsupported filter: {filter_like!r}")


async def _invoke(handler: Handler, event: EclipseEvent) -> None:
    result = handler(event)
    if inspect.isawaitable(result):
        await result


def _classify(exc: BaseException) -> tuple[str, str, str]:
    import traceback

    error_class = (
        getattr(exc, "error_class", None)
        or getattr(exc, "code", None)
        or ("TIMEOUT" if isinstance(exc, asyncio.TimeoutError) else "INTERNAL_ERROR")
    )
    message = f"{type(exc).__name__}: {exc}"[:2000]
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-8000:]
    return str(error_class), message, trace


__all__ = ["DEFAULT_MAX_CONCURRENCY", "DEFAULT_MAX_QUEUE", "EventBus", "Subscription"]
