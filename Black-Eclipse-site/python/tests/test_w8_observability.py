"""W8: eager objectives, signal projection, schema v2, gate and alerts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.dashboard import render_dashboard
from harness.observability.gate import GateError, evaluate_gate, load_json
from harness.observability.integration import RunEventProjector
from harness.observability.probe import probe_metric_names, run_probe
from harness.observability.slo import SLORegistry

ROOT = Path(__file__).resolve().parents[2]


def _hub():
    hub = ObservabilityHub(
        ObservabilityConfig(jsonl_dir="", otel_enabled=False, langfuse_enabled=False, sentry_enabled=False),
        capture_inmemory=False, start_exporters=False,
    )
    return hub, RunEventProjector(hub)


def test_every_objective_is_registered_before_any_event():
    hub, _ = _hub()
    names = {item["name"] for item in hub.release_report()["slos"]["objectives"]}
    assert {
        "terminal_correctness", "run_p95_latency", "resume_p95", "cost_per_task",
        "orphan_rate", "ttft_p95", "model_fallback_success_rate",
        "context_overflow_rate", "compression_failure_rate", "resume_success_rate",
        "goal_completion_rate", "goal_blocked_rate", "file_checkpoint_failure_rate",
    } <= names


def test_unmeasured_is_not_healthy_and_not_breaching():
    hub, _ = _hub()
    report = hub.release_report()
    ttft = next(item for item in report["slos"]["objectives"] if item["name"] == "ttft_p95")
    assert ttft["measured"] is False
    assert ttft["healthy"] is None
    assert "ttft_p95" in report["slos"]["unmeasured"]
    assert report["slos"]["allHealthy"] is True


def test_ensure_keeps_counters_across_events():
    registry = SLORegistry()
    registry.ensure("success", 0.9)
    registry.record("success", good=True)
    registry.ensure("success", 0.9)
    registry.record("success", good=True)
    assert registry.get("success").total == 2


def test_run_derived_terminal_and_orphan_override_the_runtime_view():
    hub, projector = _hub()
    projector.handle({"type": "run.created", "runId": "r1", "at": 1.0, "data": {}})
    projector.handle({"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}})
    projector.handle({"type": "run.created", "runId": "r2", "at": 3.0, "data": {}})
    hub.sweep_orphans(max_age_s=0)
    report = hub.release_report()
    terminal = next(item for item in report["slos"]["objectives"] if item["name"] == "terminal_correctness")
    orphan = next(item for item in report["slos"]["objectives"] if item["name"] == "orphan_rate")
    assert terminal["compliance"] == 0.5
    assert terminal["healthy"] is False
    assert orphan["healthy"] is False


def test_model_and_context_signals_reach_the_report():
    hub, projector = _hub()
    for event in (
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "model.first_token", "runId": "r1", "at": 1.1, "data": {"ttftMs": 250}},
        {"type": "model.attempt.completed", "runId": "r1", "at": 1.2,
         "data": {"outcome": "completed", "latencyMs": 500, "priced": True}},
        {"type": "model.attempt.failed", "runId": "r1", "at": 1.3,
         "data": {"outcome": "failed", "willFallback": True}},
        {"type": "model.fallback", "runId": "r1", "at": 1.4, "data": {"attempts": 2}},
        {"type": "memory.history_bounded", "runId": "r1", "at": 1.5,
         "data": {"usageRatio": 0.4, "gate": "continue", "window": 200000}},
        {"type": "context.compressed", "runId": "r1", "at": 1.6,
         "data": {"stage": "summary", "ok": True}},
        {"type": "run.completed", "runId": "r1", "at": 2.0, "data": {}},
    ):
        projector.handle(event)
    report = hub.release_report()
    assert report["schema"] == 2
    assert report["model"]["attempts"] == 2
    assert report["model"]["fallbacks"] == 1
    assert report["model"]["fallbackSuccessRate"] == 1.0
    assert report["latency"]["ttft"]["samples"] == 1
    assert report["context"]["usageRatio"]["samples"] == 1
    assert report["context"]["compactions"]["samples"] == 1


def test_integrity_signals_are_counted():
    hub, projector = _hub()
    for event in (
        {"type": "run.created", "runId": "r1", "at": 1.0, "data": {}},
        {"type": "effect.unknown", "runId": "r1", "at": 1.1, "data": {"name": "broker_order"}},
        {"type": "run.lease_lost", "runId": "r1", "at": 1.2, "data": {}},
        {"type": "event.seq_collision", "runId": "r1", "at": 1.3, "data": {}},
        {"type": "security.hardline.blocked", "runId": "r1", "at": 1.4,
         "data": {"pattern": "root_wipe"}},
    ):
        projector.handle(event)
    integrity = hub.release_report()["integrity"]
    assert integrity["effectUnknown"] == 1
    assert integrity["leaseLost"] == 1
    assert integrity["eventSeqCollisions"] == 1
    assert integrity["hardlineBlocked"] == 1


def test_the_probe_exercises_every_w8_section():
    report = run_probe(runs=40)
    assert report["schema"] == 2
    assert report["model"]["attempts"] > 0
    assert report["latency"]["ttft"]["samples"] > 0
    assert report["context"]["usageRatio"]["samples"] > 0
    assert report["tools"]["batches"]["count"] > 0
    assert report["goals"]["samples"] > 0
    assert report["learning"]["executionEvals"]["total"] > 0
    assert report["integrity"]["effectUnknown"] == 0
    assert all("measured" in item for item in report["slos"]["objectives"])


def _budgets() -> dict:
    return load_json(ROOT / "docs" / "harness" / "slo-budgets.json")


def test_the_shipped_gate_passes_the_probe():
    result = evaluate_gate(run_probe(runs=40), _budgets())
    assert result.ok, result.to_dict()
    names = {check.name for check in result.checks}
    assert {"ttft_p95", "context_overflow_rate", "effect_unknown"} <= names


def test_the_declarative_gate_rejects_a_breach_and_an_invariant():
    report = run_probe(runs=40)
    report["integrity"]["effectUnknown"] = 1
    result = evaluate_gate(report, {"checks": [
        {"name": "effect_unknown", "path": "integrity.effectUnknown", "kind": "invariant", "max": 0},
    ]})
    assert result.ok is False
    assert result.checks[0].status == "fail"


def test_the_gate_skips_a_disabled_capability():
    report = run_probe(runs=10)
    report["capabilities"]["parallelTools"] = False
    result = evaluate_gate(report, {"checks": [
        {"name": "ordering", "path": "integrity.toolBatchOrderingViolations",
         "kind": "invariant", "max": 0, "requires": "parallelTools"},
    ]})
    assert result.ok is True
    assert result.checks[0].status == "skipped"


def test_the_gate_rejects_an_unknown_path_and_enforce_false_observes():
    report = run_probe(runs=10)
    with pytest.raises(GateError):
        evaluate_gate(report, {"checks": [
            {"name": "typo", "path": "integrity.notAField", "kind": "invariant"},
        ]})
    result = evaluate_gate(report, {"checks": [
        {"name": "effect_unknown", "path": "integrity.effectUnknown", "kind": "invariant",
         "max": 0, "enforce": False},
    ]})
    assert result.ok is True
    assert result.checks[0].status == "observed"


def test_alert_rules_reference_metrics_the_probe_records():
    text = (ROOT / "deploy" / "prometheus" / "blackeclipse.rules.yml").read_text(encoding="utf-8")
    import re

    referenced = {
        re.sub(r"_(bucket|sum|count)$", "", name)
        for name in re.findall(r"\beclipse_[a-zA-Z0-9_]+", text)
    }
    assert referenced
    assert referenced <= probe_metric_names(runs=6)


def test_dashboard_renders_an_unmeasured_card_without_breaching():
    hub, _ = _hub()
    empty = render_dashboard(hub.release_report())
    letters = empty.count("unmeasured")
    assert letters >= 5
    assert "breaching" not in empty

    report = run_probe(runs=5)
    html = render_dashboard(report)
    assert "Integrity" in html
    assert "Model" in html
    # No unescaped injection from a label.
    assert "<script>" not in html


def test_the_budget_file_is_valid_json_v2():
    budgets = json.loads((ROOT / "docs" / "harness" / "slo-budgets.json").read_text(encoding="utf-8"))
    assert budgets["version"] == 2
    assert budgets["checks"]
    assert all("path" in check and "kind" in check for check in budgets["checks"])
