"""C7: SLO v2 kinds, the deterministic probe and the release gate."""

from __future__ import annotations

import copy
import json

import pytest

from harness.observability.gate import GateError, evaluate_gate, validate_report
from harness.observability.probe import run_probe
from harness.observability.slo import SLORegistry


def test_ratio_slo_is_unchanged():
    registry = SLORegistry()
    registry.define("success", 0.99)
    registry.record("success", good=True)
    result = registry.record("success", good=False)
    assert result["kind"] == "ratio"
    assert result["compliance"] == 0.5
    assert result["healthy"] is False
    assert result["errorBudgetRemaining"] == 0.0


def test_percentile_slo_uses_p95_and_the_share_within_threshold():
    registry = SLORegistry()
    registry.define("latency", 0.95, kind="percentile", threshold=100.0, unit="ms")
    for value in (10, 20, 30, 40, 50, 60, 70, 80, 90, 1000):
        registry.record_value("latency", value)
    result = registry.get("latency").evaluate()
    assert result["kind"] == "percentile"
    assert result["p50"] == 60.0
    assert result["p95"] == 1000.0
    assert result["healthy"] is False
    assert result["compliance"] == 0.9


def test_rate_slo_treats_threshold_as_the_max_failure_ratio():
    registry = SLORegistry()
    registry.define("orphans", 1.0, kind="rate", threshold=0.0)
    registry.record("orphans", good=True)
    healthy = registry.get("orphans").evaluate()
    assert healthy["healthy"] is True
    registry.record("orphans", good=False)
    breached = registry.get("orphans").evaluate()
    assert breached["healthy"] is False
    assert breached["compliance"] == 0.5


def test_the_probe_exercises_the_whole_path():
    report = run_probe(runs=20)
    assert report["runs"]["created"] == 20
    assert report["runs"]["terminal"] == 20
    assert report["runs"]["orphaned"] == 0
    assert report["latency"]["samples"] == 20
    assert report["latency"]["p95"] < 120_000
    assert report["resume"]["samples"] > 0
    assert report["cost"]["samples"] > 0
    assert set(report["failures"]) >= {"timeout", "validation"}
    names = {slo["name"] for slo in report["slos"]["objectives"]}
    assert {"agent_success_rate", "run_p95_latency", "cost_per_task", "orphan_rate"} <= names


def _budgets() -> dict:
    return json.loads(json.dumps({
        "budgets": {
            "terminal_correctness": {"target": 0.999},
            "run_p95_latency": {"thresholdMs": 120_000, "maxRegression": 0.1},
            "resume_p95": {"thresholdMs": 10_000, "maxRegression": 0.1},
            "orphan_rate": {"max": 0.0},
            "cost_per_task": {"thresholdUsd": 1.0, "maxRegression": 0.3},
        }
    }))


def test_the_gate_passes_a_healthy_report():
    report = run_probe(runs=20)
    result = evaluate_gate(report, _budgets())
    assert result.ok, result.to_dict()
    assert {check.name for check in result.checks} >= {
        "terminal_correctness", "orphan_rate", "run_p95_latency", "cost_per_task",
    }


def test_the_gate_fails_on_a_terminal_correctness_breach():
    report = run_probe(runs=20)
    report["runs"]["terminal"] -= 1
    result = evaluate_gate(report, _budgets())
    assert result.ok is False
    assert any(check.name == "terminal_correctness" and not check.ok for check in result.checks)


def test_the_gate_fails_on_an_orphan():
    report = run_probe(runs=20)
    report["runs"]["orphaned"] = 1
    result = evaluate_gate(report, _budgets())
    assert result.ok is False
    assert any(check.name == "orphan_rate" and not check.ok for check in result.checks)


def test_the_gate_fails_on_a_latency_regression_vs_baseline():
    report = run_probe(runs=20)
    baseline = copy.deepcopy(report)
    report["latency"]["p95"] = baseline["latency"]["p95"] * 1.5
    result = evaluate_gate(report, _budgets(), baseline)
    assert result.ok is False
    assert any(check.name == "run_p95_latency_regression" and not check.ok for check in result.checks)


def test_the_gate_fails_on_a_cost_regression_vs_baseline():
    report = run_probe(runs=20)
    baseline = copy.deepcopy(report)
    report["cost"]["perTaskP95"] = baseline["cost"]["perTaskP95"] * 2
    result = evaluate_gate(report, _budgets(), baseline)
    assert any(check.name == "cost_per_task_regression" and not check.ok for check in result.checks)


def test_the_gate_rejects_a_malformed_report():
    with pytest.raises(GateError):
        validate_report({"runs": {"created": "x"}})
    with pytest.raises(GateError):
        evaluate_gate({"runs": {}}, _budgets())


def test_the_gate_rejects_missing_budgets():
    with pytest.raises(GateError):
        evaluate_gate(run_probe(runs=5), {"budgets": {}})
