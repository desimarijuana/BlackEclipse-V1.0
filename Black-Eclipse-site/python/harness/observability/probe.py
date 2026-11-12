"""Deterministic C7 telemetry probe.

Feeds the real `RunEventProjector` a synthetic bus stream (run → step → model →
tool → step → run) through a private `ObservabilityHub`, then returns the same
release report a live deployment exposes at `GET /observability/release-report`.

It is not a fake agent: every span, metric, cost, failure class and SLO is
computed by the shipped observability code. It is the release gate's fixed
workload, so a regression in the telemetry path or the budget math fails CI
without needing a provider or network.
"""

from __future__ import annotations

import time
from typing import Any

from .core import ObservabilityHub
from .costs import Pricing
from .integration import RunEventProjector

PROBE_MODEL = "eclipse-probe"
PROBE_PROVIDER = "probe"


def _hub() -> ObservabilityHub:
    hub = ObservabilityHub(capture_inmemory=False, start_exporters=False)
    hub.costs.pricing.register(
        PROBE_MODEL,
        Pricing(input_per_million=0.50, output_per_million=1.50),
    )
    return hub


def _emit_run(projector: RunEventProjector, *, index: int, resumed: bool = False) -> None:
    run_id = f"probe_run_{index:03d}"
    base = 1_000_000.0 + index * 10.0
    latency_ms = 800.0 + (index % 10) * 120.0
    latency = latency_ms / 1000.0
    start_type = "run.resumed" if resumed else "run.created"
    events: list[dict[str, Any]] = [
        {"type": start_type, "runId": run_id, "at": base, "data": {"agentId": "probe-agent"}},
        {"type": "step.started", "runId": run_id, "at": base,
         "data": {"step": 1, "stepId": f"{run_id}:step:1", "agentId": "probe-agent"}},
        {"type": "model.requested", "runId": run_id, "at": base + 10,
         "data": {"step": 1, "messages": 2}},
        {"type": "model.request.started", "runId": run_id, "at": base + 10,
         "data": {"step": 1, "provider": PROBE_PROVIDER, "model": PROBE_MODEL, "task": "probe"}},
        {"type": "tool.requested", "runId": run_id, "at": base + latency * 0.4,
         "data": {"name": "probe_tool", "toolCallId": "call_1", "step": 1}},
    ]
    if index == 3:
        events.append({
            "type": "tool.failed", "runId": run_id, "at": base + latency * 0.6,
            "data": {"name": "probe_tool", "toolCallId": "call_1", "step": 1,
                     "code": "TOOL_VALIDATION_FAILED", "durationMs": 12},
        })
    else:
        events.append({
            "type": "tool.completed", "runId": run_id, "at": base + latency * 0.6,
            "data": {"name": "probe_tool", "toolCallId": "call_1", "step": 1,
                     "durationMs": 12, "truncated": False},
        })
    if index == 7:
        events += [
            {"type": "model.request.failed", "runId": run_id, "at": base + latency,
             "data": {"step": 1, "provider": PROBE_PROVIDER, "model": PROBE_MODEL,
                      "errorClass": "PROVIDER_TIMEOUT"}},
            {"type": "step.completed", "runId": run_id, "at": base + latency,
             "data": {"step": 1, "stepId": f"{run_id}:step:1", "status": "failed",
                      "toolCalls": 1, "toolErrors": 0,
                      "error": {"code": "PROVIDER_TIMEOUT", "message": "probe timeout"}}},
            {"type": "run.failed", "runId": run_id, "at": base + latency + 0.005,
             "data": {"error": {"code": "PROVIDER_TIMEOUT", "message": "probe timeout"}}},
        ]
    else:
        events += [
            {"type": "model.completed", "runId": run_id, "at": base + latency,
             "data": {"step": 1, "promptTokens": 800, "completionTokens": 200, "totalTokens": 1000}},
            {"type": "step.completed", "runId": run_id, "at": base + latency,
             "data": {"step": 1, "stepId": f"{run_id}:step:1", "status": "ok",
                      "toolCalls": 1, "toolErrors": 1 if index == 3 else 0}},
            {"type": "run.completed", "runId": run_id, "at": base + latency + 0.005,
             "data": {"steps": 1}},
        ]
    for event in events:
        projector.handle(event)


def run_probe(*, runs: int = 40) -> dict[str, Any]:
    """Run the fixed workload and return its release report."""
    hub = _hub()
    projector = RunEventProjector(hub)
    for index in range(max(1, int(runs))):
        _emit_run(projector, index=index, resumed=(index % 5 == 0))
    hub.refresh_use_metrics()
    report = hub.release_report()
    report["probe"] = {
        "runs": int(runs), "provider": PROBE_PROVIDER, "model": PROBE_MODEL,
        "schema": 1, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return report


__all__ = ["PROBE_MODEL", "PROBE_PROVIDER", "run_probe"]
