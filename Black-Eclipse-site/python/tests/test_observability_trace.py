"""Trace-integrity tests — propagation across worker/queue/agent boundaries."""

from __future__ import annotations

from harness.observability.context import ObservationContext, bind_context, current_context, extract, inject
from harness.observability.tracing import SpanStore, Tracer


def test_cross_worker_propagation_via_carrier():
    # A run process creates the context and injects it into a job payload.
    run_ctx = ObservationContext(run_id="run_x", session_id="sess_x")
    job_payload = {"jobId": "job_x", "queue": "research"}
    carrier = inject(run_ctx, job_payload)
    assert carrier["eclipseTraceId"] == run_ctx.trace_id

    # A separate worker rebuilds the SAME trace from the payload.
    worker_ctx = extract(carrier)
    assert worker_ctx is not None
    assert worker_ctx.trace_id == run_ctx.trace_id
    assert worker_ctx.run_id == "run_x"
    assert worker_ctx.session_id == "sess_x"


def test_spans_across_boundaries_share_one_trace():
    store = SpanStore(max_spans=100, max_traces=10)
    tracer = Tracer(store=store)
    run_ctx = ObservationContext(run_id="run_shared")
    # Parent process: the run span; capture its context for propagation.
    with bind_context(run_ctx):
        with tracer.start("eclipse.run", kind="server"):
            run_span_ctx = current_context()
    assert run_span_ctx is not None and run_span_ctx.parent_span_id == run_ctx.span_id

    # Worker process: rebuilds THE RUN SPAN context from the carrier and opens a child.
    worker_ctx = extract(inject(run_span_ctx))
    assert worker_ctx is not None
    with bind_context(worker_ctx):
        with tracer.start("eclipse.tool.fetch", kind="tool"):
            pass

    spans = store.get_trace(run_ctx.trace_id)
    assert len(spans) == 2
    assert all(s["traceId"] == run_ctx.trace_id for s in spans)
    run_span = next(s for s in spans if s["name"] == "eclipse.run")
    tool_span = next(s for s in spans if s["name"] == "eclipse.tool.fetch")
    assert tool_span["parentSpanId"] == run_span_ctx.span_id
    assert run_span["spanId"] == run_span_ctx.span_id


def test_a2a_context_round_trip_between_agents():
    agent_a = ObservationContext(run_id="run_a", agent_id="agent_a", message_id="msg_1")
    # The A2A envelope carries the context to agent B.
    envelope = inject(agent_a, {"from": "agent_a", "to": "agent_b"})
    agent_b = extract(envelope)
    assert agent_b is not None
    assert agent_b.trace_id == agent_a.trace_id
    assert agent_b.message_id == "msg_1"


def test_traceparent_version_shape():
    ctx = ObservationContext()
    parts = ctx.traceparent().split("-")
    assert len(parts) == 4
    assert parts[0] == "00"
    assert len(parts[1]) == 32
    assert len(parts[2]) == 16
