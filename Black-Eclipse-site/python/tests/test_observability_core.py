"""Unit tests for the observability core (context, tracing, redaction, metrics, cost)."""

from __future__ import annotations

import pytest

from harness.observability.anomaly import AnomalyDetector, LoopDetector
from harness.observability.context import (
    ObservationContext,
    bind_context,
    current_context,
    extract,
    inject,
    new_span_id,
    new_trace_id,
)
from harness.observability.costs import CostEngine, Pricing, PricingRegistry
from harness.observability.events import HookEvent, make_event
from harness.observability.health import DEGRADED, HEALTHY, UNHEALTHY, HealthRegistry
from harness.observability.metrics import MetricsRegistry
from harness.observability.observers import Observer, ObserverHub
from harness.observability.redaction import REDACTED, Redactor
from harness.observability.sampling import Sampler
from harness.observability.slo import SLORegistry
from harness.observability.tracing import SpanStore, Tracer, STATUS_ERROR


def test_context_child_and_propagation():
    parent = ObservationContext(run_id="run_1")
    child = parent.child(attributes={"stage": "tool"})
    assert child.trace_id == parent.trace_id
    assert child.parent_span_id == parent.span_id
    assert child.span_id != parent.span_id
    assert child.run_id == "run_1"
    assert child.attributes["stage"] == "tool"


def test_context_carrier_round_trip():
    ctx = ObservationContext(run_id="run_9", job_id="job_3", message_id="msg_7")
    carrier = inject(ctx, {"custom": "kept"})
    assert carrier["custom"] == "kept"
    restored = extract(carrier)
    assert restored is not None
    assert restored.trace_id == ctx.trace_id
    assert restored.span_id == ctx.span_id
    assert restored.run_id == "run_9"
    assert restored.job_id == "job_3"
    assert restored.message_id == "msg_7"


def test_context_extract_traceparent_only():
    ctx = ObservationContext(run_id="r")
    restored = extract({"traceparent": ctx.traceparent()})
    assert restored is not None
    assert restored.trace_id == ctx.trace_id


def test_context_extract_none_without_identity():
    assert extract({}) is None
    assert extract(None) is None


def test_bind_context_isolated():
    outer = ObservationContext(run_id="outer")
    with bind_context(outer):
        assert current_context().run_id == "outer"
        inner = outer.child()
        with bind_context(inner):
            assert current_context().span_id == inner.span_id
        assert current_context().span_id == outer.span_id


def _tracer() -> Tracer:
    return Tracer(store=SpanStore(max_spans=100, max_traces=10))


def test_tracer_parent_child_tree_and_trajectory():
    tracer = _tracer()
    ctx = ObservationContext(run_id="run_t")
    with bind_context(ctx):
        with tracer.start("eclipse.run", kind="server") as root:
            root_span_id = root.span_id
            with tracer.start("eclipse.tool.search", kind="tool") as tool:
                tool.set_attribute("tool", "web_search")
            with tracer.start("eclipse.llm", kind="llm") as llm:
                llm.set_attribute("tokens", 42)
    trajectory = tracer.store.trajectory(ctx.trace_id)
    assert trajectory["found"]
    assert trajectory["spanCount"] == 3
    assert trajectory["roots"][0]["spanId"] == root_span_id
    children = {c["name"] for c in trajectory["roots"][0]["children"]}
    assert children == {"eclipse.tool.search", "eclipse.llm"}


def test_tracer_records_error_status():
    tracer = _tracer()
    ctx = ObservationContext()
    with bind_context(ctx):
        with pytest.raises(ValueError):
            with tracer.start("eclipse.run") as span:
                raise ValueError("boom")
    spans = tracer.store.get_trace(ctx.trace_id)
    assert spans[0]["status"] == STATUS_ERROR
    assert spans[0]["errorType"] == "ValueError"


def test_observer_hub_fail_open_and_quarantine():
    hub = ObserverHub()
    calls = []

    class Good(Observer):
        name = "good"

        def on_run_start(self, event):
            calls.append(event.name)

    class Bad(Observer):
        name = "bad"

        def on_run_start(self, event):
            raise RuntimeError("nope")

    hub.register(Good())
    hub.register(Bad())
    event = make_event("onRunStart", name="eclipse.run")
    for _ in range(30):
        hub.dispatch(event)
    assert len(calls) == 30
    stats = hub.stats()
    assert stats["errors"] == 25
    assert "bad" in stats["quarantined"]
    assert stats["calls"] == 55


def test_redactor_keys_and_values():
    red = Redactor(enabled=True)
    payload = {
        "authorization": "Bearer abc123",
        "api_key": "sk-secret",
        "message": "call with Authorization: Bearer zzz999 and key=abc",
        "token_count": 42,
        "nested": {"password": "hunter2", "url": "postgres://user:pw@host/db"},
    }
    out = red.redact(payload)
    assert out["authorization"] == REDACTED
    assert out["api_key"] == REDACTED
    assert out["token_count"] == 42
    assert "zzz999" not in out["message"]
    assert out["nested"]["password"] == REDACTED
    assert "pw@" not in out["nested"]["url"]


def test_redactor_jwt_and_private_key():
    red = Redactor(enabled=True)
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
    text = f"token {jwt} and -----BEGIN RSA PRIVATE KEY-----\nSECRET\n-----END RSA PRIVATE KEY-----"
    out = red.redact_text(text)
    assert jwt not in out
    assert "SECRET" not in out


def test_redactor_pii_opt_in():
    pii = "contact a@b.com or 555-123-4567"
    assert "a@b.com" in Redactor(enabled=True).redact_text(pii)
    scrubbed = Redactor(enabled=True, redact_pii=True).redact_text(pii)
    assert "a@b.com" not in scrubbed
    assert "[EMAIL]" in scrubbed


def test_sampler_error_preserving():
    sampler = Sampler(rate=0.0)
    assert sampler.should_sample(new_trace_id()).sampled is False
    assert sampler.should_keep_span("abc" * 16, is_error=True) is True
    assert sampler.is_forced("abc" * 16)
    full = Sampler(rate=1.0)
    assert full.should_sample(new_trace_id()).sampled is True


def test_metrics_registry_and_prometheus():
    metrics = MetricsRegistry()
    metrics.inc_counter("eclipse_runs_total", labels={"status": "ok"})
    metrics.inc_counter("eclipse_runs_total", labels={"status": "ok"})
    metrics.set_gauge("eclipse_active_runs", 3)
    metrics.observe_histogram("eclipse_run_duration_ms", 120.0)
    assert metrics.counter_value("eclipse_runs_total", {"status": "ok"}) == 2
    assert metrics.gauge_value("eclipse_active_runs") == 3
    stats = metrics.histogram_stats("eclipse_run_duration_ms")
    assert stats["count"] == 1
    text = metrics.render_prometheus()
    assert 'eclipse_runs_total{status="ok"} 2' in text
    assert "eclipse_active_runs 3" in text
    assert "# TYPE eclipse_run_duration_ms histogram" in text


def test_cost_engine_priced_and_unknown():
    engine = CostEngine()
    breakdown, _ = engine.compute(provider="openai", model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
    assert breakdown.priced is True
    assert breakdown.input_cost == pytest.approx(0.15, abs=1e-9)
    unknown = engine.compute(provider="acme", model="mystery-model", input_tokens=100)
    assert unknown[0].priced is False

    engine.record(provider="openai", model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000, run_id="r1")
    summary = engine.summary()
    assert summary["total"]["requests"] == 1
    assert summary["total"]["cost"] == pytest.approx(0.75, abs=1e-9)
    assert engine.run_cost("r1")["cost"] == pytest.approx(0.75, abs=1e-9)


def test_cost_engine_custom_pricing():
    pricing = PricingRegistry()
    pricing.register("custom/model", Pricing(input_per_million=10.0, output_per_million=20.0))
    engine = CostEngine(pricing=pricing)
    breakdown, _ = engine.compute(provider="custom", model="model", input_tokens=1_000_000, output_tokens=500_000)
    assert breakdown.total_cost == pytest.approx(20.0, abs=1e-9)


def test_loop_detector():
    detector = LoopDetector(threshold=3, window=8)
    assert detector.observe("search:foo").detected is False
    assert detector.observe("search:foo").detected is False
    assert detector.observe("search:foo").detected is True


def test_anomaly_detector_spike():
    detector = AnomalyDetector(z_threshold=3.0, min_samples=10, absolute_floor={"x": 10})
    for i in range(30):
        detector.observe("x", 100.0 + (i % 3))
    verdict = detector.observe("x", 10_000.0)
    assert verdict.detected is True
    assert verdict.zscore > 3.0


def test_slo_budget_and_burn():
    registry = SLORegistry()
    registry.define("agent_success_rate", 0.99)
    for _ in range(99):
        registry.record("agent_success_rate", good=True)
    registry.record("agent_success_rate", good=False)
    report = registry.report()
    objective = report["objectives"][0]
    assert objective["compliance"] == pytest.approx(0.99)
    assert objective["errorBudgetRemaining"] is not None


def test_health_rollup_worst():
    registry = HealthRegistry()
    registry.register("a", lambda: (HEALTHY, None))
    registry.register("b", lambda: (DEGRADED, "slow"))
    registry.register("c", lambda: (UNHEALTHY, "down"))
    report = registry.report()
    assert report.state == UNHEALTHY
    assert report.subsystems["b"]["state"] == DEGRADED


def test_event_rejects_unknown_hook():
    with pytest.raises(ValueError):
        HookEvent(hook="onNonsense", context=ObservationContext())


def test_event_redacted_hides_secret():
    ctx = ObservationContext()
    event = make_event("onToolEnd", context=ctx, tool_name="http", attributes={"authorization": "Bearer supersecret"})
    payload = event.redacted()
    assert payload["attributes"]["authorization"] == REDACTED
