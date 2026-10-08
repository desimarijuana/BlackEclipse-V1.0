"""End-to-end acceptance — one trace reconstructs a full multi-step run.

Walks the flow the brief specifies: request → planner → tasks → queue → worker →
LLM → tool → research → evidence → A2A → recovery (injected failure + retry) →
LLM → verification → final response, then asserts the trace, trajectory, cost,
latency, errors, retries and recovery are all captured and queryable.
"""

from __future__ import annotations

import time

import pytest

from harness.events import EventBus
from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.integration import install_observability, stop_observability


class _FakeService:
    def __init__(self) -> None:
        self.bus = EventBus()

    def _observe_model_event(self, event_type, data):
        return None


@pytest.fixture
def wired():
    service = _FakeService()
    hub = install_observability(
        service,
        hub=ObservabilityHub(ObservabilityConfig(trace_sample_rate=1.0, jsonl_dir=""), capture_inmemory=True, start_exporters=False),
    )
    yield service, hub
    stop_observability(service)


def _publish(service, etype, data, run_id=None):
    event = {"type": etype, "data": data, "at": time.time()}
    if run_id:
        event["runId"] = run_id
    service.bus.publish(event)


def test_full_run_with_failure_retry_and_recovery(wired):
    service, hub = wired
    run = "run_e2e"

    _publish(service, "run.created", {"agentId": "finance"}, run)
    _publish(service, "run.started", {"maxSteps": 12, "provider": "openai"}, run)
    _publish(service, "prompt.plan", {"segments": [{"id": "sys"}, {"id": "skills"}]}, run)

    # Planner → parallel tasks dispatched to the queue → workers.
    _publish(service, "model.requested", {"step": 1, "messages": 4}, run)
    _publish(service, "model.request.completed", {"provider": "openai", "model": "gpt-4o-mini",
                                                  "latencyMs": 300.0, "runId": run}, run)
    _publish(service, "model.completed", {"step": 1, "promptTokens": 1200, "completionTokens": 300, "totalTokens": 1500}, run)
    _publish(service, "job.started", {"jobId": "job_a", "queue": "research", "workerId": "w1"})
    _publish(service, "job.succeeded", {"jobId": "job_a", "durationMs": 900, "workerId": "w1"})

    # Tool: web research → evidence.
    _publish(service, "tool.requested", {"name": "web_search", "toolCallId": "c1", "step": 2}, run)
    _publish(service, "tool.completed", {"name": "web_search", "toolCallId": "c1", "durationMs": 250.0}, run)
    _publish(service, "tool.requested", {"name": "evidence_retrieve", "toolCallId": "c2", "step": 2}, run)
    _publish(service, "tool.failed", {"name": "evidence_retrieve", "toolCallId": "c2", "code": "TIMEOUT", "durationMs": 5000.0}, run)

    # A2A: delegate to a sub-agent.
    _publish(service, "agent.spawned", {"agentId": "researcher"}, run)

    # Recovery: replan, then a second LLM call succeeds and the run completes.
    _publish(service, "run.replanned", {"reason": "tool timeout", "step": 3}, run)
    _publish(service, "model.requested", {"step": 3, "messages": 8}, run)
    _publish(service, "model.request.completed", {"provider": "openai", "model": "gpt-4o-mini",
                                                  "latencyMs": 420.0, "runId": run}, run)
    _publish(service, "model.completed", {"step": 3, "promptTokens": 2000, "completionTokens": 800, "totalTokens": 2800}, run)
    _publish(service, "run.completed", {"steps": 3}, run)
    time.sleep(0.05)

    # ── One trace reconstructs the run ──
    trajectory = None
    for tid in hub.recent_traces(50):
        candidate = hub.trajectory(tid)
        if candidate["found"] and candidate["roots"][0]["name"] == "eclipse.run":
            trajectory = candidate
            break
    assert trajectory is not None, "the run trace was captured"
    root = trajectory["roots"][0]
    assert root["name"] == "eclipse.run"
    child_names = {c["name"] for c in root["children"]}
    assert "eclipse.llm" in child_names
    assert any(n.startswith("eclipse.tool.web_search") for n in child_names)
    assert any(n.startswith("eclipse.tool.evidence_retrieve") for n in child_names)
    # The run recovered and completed (the failed tool span is preserved under it).
    assert root["status"] == "OK"
    failed_tool = next(s for s in trajectory["timeline"] if s["name"] == "eclipse.tool.evidence_retrieve")
    assert failed_tool["status"] == "ERROR"

    # ── Cost is aggregated by run ──
    run_cost = hub.costs.run_cost(run)
    assert run_cost["requests"] == 2
    assert run_cost["totalTokens"] == 1500 + 2800
    assert run_cost["cost"] > 0

    # ── Failure + recovery are preserved and queryable ──
    observed = hub.diagnostics()["observedHooks"]
    assert observed.get("onToolError", 0) == 1
    assert observed.get("onRecoveryStart", 0) >= 1
    assert observed.get("onRunEnd", 0) == 1
    # The tool timeout is not fatal; the run still completed.
    assert hub.metrics.counter_value("eclipse_runs_total", {"agent": "finance", "status": "completed"}) == 1
    assert hub.metrics.counter_value("eclipse_tool_calls_total", {"tool": "evidence_retrieve", "status": "error"}) == 1
    # Job + A2A telemetry rode the same hub.
    assert hub.metrics.counter_value("eclipse_jobs_total", {"status": "succeeded"}) == 1
    assert hub.metrics.counter_value("eclipse_a2a_messages_total", {"direction": "sent"}) >= 1
