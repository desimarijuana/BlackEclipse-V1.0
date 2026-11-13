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
    # ── W8 signals ──────────────────────────────────────────────────────────
    events.extend([
        {"type": "model.candidate_plan", "runId": run_id, "at": base + 8,
         "data": {"step": 1, "candidates": [{"provider": PROBE_PROVIDER, "model": PROBE_MODEL}],
                  "excluded": [], "fallbackDepth": 0}},
        {"type": "model.first_token", "runId": run_id, "at": base + 20,
         "data": {"ttftMs": 120 + (index % 7) * 30, "finalizing": False}},
        {"type": "memory.history_bounded", "runId": run_id, "at": base + 21,
         "data": {"keptTurns": 6, "droppedTurns": 0, "droppedTokensEstimate": 0,
                  "window": 200_000, "windowKnown": True, "tighterRetry": False,
                  "usageRatio": 0.30 + (index % 8) * 0.05, "gate": "continue"}},
        {"type": "context.compressed", "runId": run_id, "at": base + 22,
         "data": {"stage": "summary" if index % 6 == 0 else "none",
                  "ok": index % 6 == 0, "reason": None, "droppedTurns": 3,
                  "prunedToolResults": 1, "summaryChars": 1200, "usedModel": index % 6 == 0}},
    ])
    if index == 7:
        events.append({"type": "model.attempt.failed", "runId": run_id, "at": base + 23,
                       "data": {"provider": PROBE_PROVIDER, "model": PROBE_MODEL, "outcome": "failed",
                                "errorClass": "PROVIDER_TIMEOUT", "latencyMs": 400,
                                "willRetry": True, "willFallback": True, "priced": False}})
    elif index % 4 == 0:
        events += [
            {"type": "model.attempt.failed", "runId": run_id, "at": base + 23,
             "data": {"provider": PROBE_PROVIDER, "model": PROBE_MODEL, "outcome": "failed",
                      "errorClass": "SERVER_ERROR", "latencyMs": 300,
                      "willRetry": False, "willFallback": True, "priced": False}},
            {"type": "model.attempt.completed", "runId": run_id, "at": base + 23.5,
             "data": {"provider": PROBE_PROVIDER, "model": PROBE_MODEL, "outcome": "completed",
                      "latencyMs": 700, "ttftMs": 150, "priced": True, "willFallback": False}},
            {"type": "model.fallback", "runId": run_id, "at": base + 24,
             "data": {"attempts": 2, "fallbackUsed": True}},
        ]
    else:
        events.append({"type": "model.attempt.completed", "runId": run_id, "at": base + 23,
                       "data": {"provider": PROBE_PROVIDER, "model": PROBE_MODEL, "outcome": "completed",
                                "latencyMs": 600, "ttftMs": 120 + (index % 7) * 30,
                                "priced": True, "willFallback": False}})
    if index % 3 == 0:
        events += [
            {"type": "tool.batch_plan", "runId": run_id, "at": base + 24,
             "data": {"calls": 2, "batches": [[0, 1]], "parallelSafe": [True, True], "wouldSaveMs": 40}},
            {"type": "tool.batch", "runId": run_id, "at": base + 25,
             "data": {"calls": 2, "batches": 1, "maxConcurrency": 2,
                      "orderingViolations": 0, "durationMs": 140, "mode": "on"}},
        ]
    if index % 5 == 0:
        events.append({"type": "tool.guardrail", "runId": run_id, "at": base + 26,
                       "data": {"name": "probe_tool", "rule": "identical_call", "count": 3, "action": "warn"}})
    if index % 5 == 0:
        events.append({"type": "goal.verdict", "runId": run_id, "at": base + 27,
                       "data": {"goalId": f"goal_{index}", "turn": 2,
                                "verdict": "blocked" if index == 10 else "done",
                                "reason": "probe", "downgraded": False, "gateOk": True}})
    if index % 8 == 0:
        events.append({"type": "checkpoint.write", "runId": run_id, "at": base + 28,
                       "data": {"ok": True, "kind": "agent_step", "durationMs": 8}})
    if index % 9 == 0:
        events.append({"type": "checkpoint.created", "runId": run_id, "at": base + 29,
                       "data": {"op": "created", "files": 2, "bytes": 4096, "reason": "before-write"}})
    if index % 11 == 0:
        events += [
            {"type": "delegation.async.started", "runId": run_id, "at": base + 30,
             "data": {"op": "started", "children": 2, "strategy": "parallel"}},
            {"type": "delegation.child.completed", "runId": run_id, "at": base + 31,
             "data": {"op": "completed", "childIndex": 0, "status": "ok"}},
        ]
    for event in events:
        projector.handle(event)


_PROBE_CAPABILITIES = {
    "modelGateway": True, "contextLadder": True, "parallelTools": True,
    "autonomy": True, "learningEval": True, "runKernelIntegrity": True,
    "fileCheckpoints": True, "asyncDelegation": True,
}

#: Metrics an alert rule may reference. Zero-recording them keeps the
#: `contract.alert_metric_names` case meaningful without inventing a violation.
_ZERO_METRICS = (
    "eclipse_context_overflow_total",
    "eclipse_effect_unknown_total", "eclipse_lease_lost_total",
    "eclipse_checkpoint_write_failures_total", "eclipse_event_seq_retries_total",
    "eclipse_event_seq_collisions_total", "eclipse_tool_batch_ordering_violations_total",
    "eclipse_skill_enabled_without_eval_total", "eclipse_hardline_blocked_total",
    "eclipse_file_checkpoint_failures_total", "eclipse_delegation_repairs_total",
)


def _run_probe(*, runs: int = 40) -> tuple[ObservabilityHub, dict[str, Any]]:
    hub = _hub()
    projector = RunEventProjector(hub)
    for index in range(max(1, int(runs))):
        _emit_run(projector, index=index, resumed=(index % 5 == 0))
    # W5 signals are not run-scoped; emit one of each so the report is complete.
    projector.handle({"type": "skill.evaluation_completed", "at": 2_000_000.0,
                      "data": {"ok": True, "status": "passed", "cases": 3}})
    projector.handle({"type": "skill.curator_run", "at": 2_000_001.0,
                      "data": {"ok": True, "status": "completed", "mode": "dry_run",
                               "proposals": 2, "applied": 0}})
    for name in _ZERO_METRICS:
        hub.metrics.inc_counter(name, 0.0)
    hub.refresh_use_metrics()
    report = hub.release_report(capabilities_override=_PROBE_CAPABILITIES)
    report["probe"] = {
        "runs": int(runs), "provider": PROBE_PROVIDER, "model": PROBE_MODEL,
        "schema": 2, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return hub, report


def run_probe(*, runs: int = 40) -> dict[str, Any]:
    """Run the fixed workload and return its release report."""
    return _run_probe(runs=runs)[1]


def probe_metric_names(*, runs: int = 6) -> set[str]:
    """Metric families the shipped probe actually records."""
    names = _run_probe(runs=runs)[0].metrics.names()
    return {name for group in names.values() for name in group}


__all__ = ["PROBE_MODEL", "PROBE_PROVIDER", "probe_metric_names", "run_probe"]
