"""Integration tests — the event bus projects into spans, hooks, metrics, cost."""

from __future__ import annotations

import time

import pytest

from harness.events import EventBus
from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.integration import (
    ModelObserverBridge,
    RunEventProjector,
    install_observability,
    stop_observability,
)


class _FakeService:
    def __init__(self) -> None:
        self.bus = EventBus()

    def _observe_model_event(self, event_type, data):
        self.forwarded = getattr(self, "forwarded", [])
        self.forwarded.append((event_type, data))


def _hub() -> ObservabilityHub:
    return ObservabilityHub(
        ObservabilityConfig(trace_sample_rate=1.0, jsonl_dir=""),
        capture_inmemory=True,
        start_exporters=True,
    )


@pytest.fixture
def wired():
    from harness.model_runtime import get_runtime

    previous = get_runtime()._observer  # noqa: SLF001
    service = _FakeService()
    hub = install_observability(service, hub=_hub())
    yield service, hub
    stop_observability(service)
    get_runtime().set_observer(previous)


def _publish(service, etype, data, run_id=None):
    event = {"type": etype, "data": data, "at": time.time()}
    if run_id:
        event["runId"] = run_id
    service.bus.publish(event)


def test_run_projects_llm_and_tool_spans(wired):
    service, hub = wired
    _publish(service, "run.created", {"agentId": "finance"}, run_id="run_1")
    _publish(service, "run.started", {"maxSteps": 8, "provider": "openai"}, run_id="run_1")
    _publish(service, "model.requested", {"step": 1, "messages": 3}, run_id="run_1")
    _publish(service, "model.request.completed", {"provider": "openai", "model": "gpt-4o-mini",
                                                  "latencyMs": 250.0, "runId": "run_1",
                                                  "inputTokens": 100, "outputTokens": 50, "totalTokens": 150})
    _publish(service, "model.completed", {"step": 1, "promptTokens": 100, "completionTokens": 50, "totalTokens": 150}, run_id="run_1")
    _publish(service, "tool.requested", {"name": "web_search", "toolCallId": "c1", "step": 1}, run_id="run_1")
    _publish(service, "tool.completed", {"name": "web_search", "toolCallId": "c1", "durationMs": 120.0}, run_id="run_1")
    _publish(service, "run.completed", {"steps": 2}, run_id="run_1")

    trace_ids = hub.recent_traces(10)
    assert trace_ids, "a trace was recorded"
    trajectory = hub.trajectory(trace_ids[0])
    assert trajectory["found"]
    root = trajectory["roots"][0]
    assert root["name"] == "eclipse.run"
    names = {c["name"] for c in root["children"]}
    assert "eclipse.llm" in names
    assert any(n.startswith("eclipse.tool") for n in names)
    # cost recorded for the priced model
    assert hub.costs.summary()["total"]["requests"] == 1
    assert hub.costs.summary()["total"]["cost"] > 0
    # metrics recorded
    assert hub.metrics.counter_value("eclipse_runs_total", {"agent": "finance", "status": "completed"}) == 1
    assert hub.metrics.counter_value("eclipse_tool_calls_total", {"tool": "web_search", "status": "ok"}) == 1
    # LLM telemetry is recorded exactly once (no double-count from the bus).
    assert hub.metrics.counter_value(
        "eclipse_llm_requests_total", {"provider": "openai", "model": "gpt-4o-mini", "status": "ok"}
    ) == 1


def test_run_failure_records_error_and_status(wired):
    service, hub = wired
    _publish(service, "run.created", {"agentId": "finance"}, run_id="run_fail")
    _publish(service, "run.started", {"provider": "openai"}, run_id="run_fail")
    _publish(service, "model.requested", {"step": 1}, run_id="run_fail")
    _publish(service, "run.failed", {"error": {"code": "PROVIDER_TIMEOUT", "message": "timed out"}}, run_id="run_fail")
    time.sleep(0.05)
    assert hub.errors(), "error captured"
    assert hub.errors()[0]["runId"] == "run_fail"
    trace_ids = hub.recent_traces(10)
    trajectory = hub.trajectory(trace_ids[0])
    assert trajectory["status"] == "ERROR"
    hook_counts = hub.status()["observers"]
    assert hook_counts["errors"] == 0


def test_job_and_plugin_and_a2a_events(wired):
    service, hub = wired
    _publish(service, "job.started", {"jobId": "job_1", "queue": "default", "workerId": "w1"})
    _publish(service, "job.succeeded", {"jobId": "job_1", "durationMs": 55})
    _publish(service, "plugin.tool.started", {"pluginId": "acme", "tool": "calc"})
    _publish(service, "plugin.tool.completed", {"pluginId": "acme", "tool": "calc"})
    _publish(service, "agent.spawned", {"agentId": "researcher"}, run_id="run_a2a")
    time.sleep(0.05)
    assert hub.metrics.counter_value("eclipse_jobs_total", {"status": "succeeded"}) >= 1
    assert hub.metrics.counter_value("eclipse_plugin_operations_total", {"plugin": "acme", "status": "ok"}) >= 1
    observed = hub.diagnostics()["observedHooks"]
    assert observed.get("onJobEnd", 0) >= 1
    assert observed.get("onPluginEnd", 0) >= 1


def test_model_observer_bridge_forwards_to_both():
    hub = _hub()
    forwarded = []

    def existing(event_type, data):
        forwarded.append(event_type)

    bridge = ModelObserverBridge(hub, existing)
    bridge("model.request.completed", {"provider": "openai", "model": "gpt-4o-mini",
                                       "runId": "r", "inputTokens": 10, "outputTokens": 5, "totalTokens": 15})
    assert forwarded == ["model.request.completed"]
    assert hub.metrics.counter_value("eclipse_llm_requests_total", {"provider": "openai", "model": "gpt-4o-mini", "status": "ok"}) == 1


def test_model_observer_bridge_survives_broken_existing():
    hub = _hub()

    def broken(event_type, data):
        raise RuntimeError("legacy observer broke")

    bridge = ModelObserverBridge(hub, broken)
    bridge("model.request.failed", {"provider": "openai", "model": "gpt-4o-mini", "errorClass": "TIMEOUT"})
    assert hub.metrics.counter_value("eclipse_llm_requests_total", {"provider": "openai", "model": "gpt-4o-mini", "status": "error"}) == 1


def test_projector_ignores_malformed_event():
    hub = _hub()
    projector = RunEventProjector(hub)
    projector.handle(None)  # type: ignore[arg-type]
    projector.handle({"type": "run.started"})  # no run id
    projector.handle({"type": "tool.requested", "runId": "unknown"})
    assert projector.stats()["activeRuns"] == 0


def test_trace_integrity_parent_child(wired):
    service, hub = wired
    _publish(service, "run.created", {}, run_id="run_tree")
    _publish(service, "run.started", {}, run_id="run_tree")
    _publish(service, "model.requested", {"step": 1}, run_id="run_tree")
    _publish(service, "model.request.completed", {"provider": "openai", "model": "gpt-4o-mini", "runId": "run_tree"})
    _publish(service, "model.completed", {"promptTokens": 1, "completionTokens": 1}, run_id="run_tree")
    _publish(service, "run.completed", {}, run_id="run_tree")
    trace = hub.recent_traces(1)[0]
    spans = hub.get_trace(trace)
    root = next(s for s in spans if s["name"] == "eclipse.run")
    llm = next(s for s in spans if s["name"] == "eclipse.llm")
    assert llm["parentSpanId"] == root["spanId"]
    assert llm["traceId"] == root["traceId"]
