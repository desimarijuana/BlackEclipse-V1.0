"""Performance tests — telemetry overhead must stay small and non-blocking."""

from __future__ import annotations

import time

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub


def _hub() -> ObservabilityHub:
    return ObservabilityHub(ObservabilityConfig(jsonl_dir=""), capture_inmemory=True, start_exporters=False)


def test_hook_ingestion_overhead_bounded():
    hub = _hub()
    iterations = 2000
    started = time.monotonic()
    for i in range(iterations):
        hub.emit("onToolEnd", tool_name="web_search", status="OK", duration_ms=float(i % 200))
    elapsed = time.monotonic() - started
    per_event_ms = (elapsed / iterations) * 1000.0
    # A generous ceiling: ingestion is in-process bookkeeping, no I/O.
    assert per_event_ms < 1.0, f"per-event overhead {per_event_ms:.3f}ms"


def test_span_creation_overhead_bounded():
    hub = _hub()
    started = time.monotonic()
    for i in range(1000):
        with hub.span("eclipse.tool.x", kind="tool", attributes={"i": i}):
            pass
    elapsed = time.monotonic() - started
    per_span_ms = (elapsed / 1000) * 1000.0
    assert per_span_ms < 1.0, f"per-span overhead {per_span_ms:.3f}ms"


def test_bounded_span_store_does_not_grow_unbounded():
    from harness.observability.tracing import SpanStore, Tracer
    from harness.observability.context import ObservationContext, bind_context

    store = SpanStore(max_spans=50, max_traces=5)
    tracer = Tracer(store=store)
    for i in range(500):
        ctx = ObservationContext()
        with bind_context(ctx):
            with tracer.start(f"op{i}"):
                pass
    stats = store.stats()
    assert stats["spans"] <= 50
    assert stats["traces"] <= 5
    assert stats["dropped"] > 0
