"""C7: run → step → tool/LLM span tree, failure classes, cost and metrics."""

from __future__ import annotations

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.integration import RunEventProjector


def _hub() -> ObservabilityHub:
    return ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )


def _feed(projector: RunEventProjector, *, run_id: str = "run_c7", fail: bool = False) -> None:
    base = 1000.0
    projector.handle({"type": "run.created", "runId": run_id, "at": base, "data": {"agentId": "a"}})
    projector.handle({"type": "step.started", "runId": run_id, "at": base,
                      "data": {"step": 1, "stepId": f"{run_id}:step:1"}})
    projector.handle({"type": "model.requested", "runId": run_id, "at": base + 0.01,
                      "data": {"step": 1, "messages": 2}})
    projector.handle({"type": "model.request.started", "runId": run_id, "at": base + 0.01,
                      "data": {"step": 1, "provider": "p", "model": "m"}})
    projector.handle({"type": "tool.requested", "runId": run_id, "at": base + 0.2,
                      "data": {"name": "probe_tool", "toolCallId": "c1", "step": 1}})
    if fail:
        projector.handle({"type": "tool.failed", "runId": run_id, "at": base + 0.3,
                          "data": {"name": "probe_tool", "toolCallId": "c1", "step": 1,
                                   "code": "TOOL_VALIDATION_FAILED", "durationMs": 4}})
        projector.handle({"type": "model.request.failed", "runId": run_id, "at": base + 0.5,
                          "data": {"step": 1, "provider": "p", "model": "m",
                                   "errorClass": "PROVIDER_TIMEOUT"}})
        projector.handle({"type": "step.completed", "runId": run_id, "at": base + 0.5,
                          "data": {"step": 1, "stepId": f"{run_id}:step:1", "status": "failed",
                                   "error": {"code": "PROVIDER_TIMEOUT"}}})
        projector.handle({"type": "run.failed", "runId": run_id, "at": base + 0.6,
                          "data": {"error": {"code": "PROVIDER_TIMEOUT", "message": "timeout"}}})
    else:
        projector.handle({"type": "tool.completed", "runId": run_id, "at": base + 0.3,
                          "data": {"name": "probe_tool", "toolCallId": "c1", "step": 1,
                                   "durationMs": 4}})
        projector.handle({"type": "model.completed", "runId": run_id, "at": base + 0.5,
                          "data": {"step": 1, "promptTokens": 100, "completionTokens": 50,
                                   "totalTokens": 150}})
        projector.handle({"type": "step.completed", "runId": run_id, "at": base + 0.5,
                          "data": {"step": 1, "stepId": f"{run_id}:step:1", "status": "ok",
                                   "toolCalls": 1, "toolErrors": 0}})
        projector.handle({"type": "run.completed", "runId": run_id, "at": base + 0.6,
                          "data": {"steps": 1}})


def _spans(hub: ObservabilityHub) -> dict[str, dict]:
    trace_id = hub.recent_traces(1)[0]
    return {span["name"]: span for span in hub.get_trace(trace_id)}


def test_a_run_has_a_step_tree_with_tool_and_llm_children():
    hub = _hub()
    _feed(RunEventProjector(hub))
    spans = _spans(hub)
    assert {"eclipse.run", "eclipse.step", "eclipse.llm", "eclipse.tool.probe_tool"} <= set(spans)
    run, step = spans["eclipse.run"], spans["eclipse.step"]
    assert step["parentSpanId"] == run["spanId"]
    assert spans["eclipse.tool.probe_tool"]["parentSpanId"] == step["spanId"]
    assert spans["eclipse.llm"]["parentSpanId"] == step["spanId"]
    assert step["attributes"]["step"] == 1
    assert step["attributes"]["status"] == "ok"


def test_a_failed_step_and_run_carry_the_closed_failure_class():
    hub = _hub()
    _feed(RunEventProjector(hub), fail=True)
    spans = _spans(hub)
    assert spans["eclipse.tool.probe_tool"]["attributes"]["failureClass"] == "validation"
    assert spans["eclipse.llm"]["attributes"]["failureClass"] == "timeout"
    assert spans["eclipse.step"]["attributes"]["failureClass"] == "timeout"
    assert spans["eclipse.run"]["attributes"]["failureClass"] == "timeout"


def test_step_metrics_and_failure_counter_are_recorded():
    hub = _hub()
    _feed(RunEventProjector(hub))
    metrics = hub.metrics.snapshot()
    counters = metrics["counters"]
    steps = counters.get("eclipse_steps_total", {})
    assert any('status="started"' in key for key in steps)
    assert any('status="ok"' in key for key in steps)
    assert metrics["histograms"].get("eclipse_step_duration_ms")
    assert metrics["histograms"].get("eclipse_run_duration_ms")


def test_run_cost_is_attributed_when_pricing_is_known():
    from harness.observability.costs import Pricing

    hub = _hub()
    hub.costs.pricing.register("m", Pricing(input_per_million=1.0, output_per_million=2.0))
    _feed(RunEventProjector(hub))
    report = hub.release_report()
    assert report["cost"]["samples"] == 1
    assert report["cost"]["totalUsd"] > 0
    assert report["cost"]["unpricedRuns"] == 0
    assert hub.metrics.snapshot()["histograms"].get("eclipse_run_cost_usd")
