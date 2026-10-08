"""Regression detection and baseline comparison."""

from __future__ import annotations

import os
import tempfile

from harness.persistence import AgentMemoryStore
from harness.evaluation.regression import (
    DEFAULT_GATES,
    RegressionGate,
    detect_regressions,
    evaluate_and_record,
)
from harness.evaluation.store import EvaluationStore


def _metrics(**aggregates):
    return {"aggregates": aggregates}


def test_tool_accuracy_drop_over_threshold_is_a_regression():
    outcome = detect_regressions(_metrics(tool_accuracy=0.90), _metrics(tool_accuracy=0.85))
    assert not outcome["passed"]
    assert outcome["regressions"][0]["dimension"] == "tool_accuracy"


def test_small_drop_is_within_tolerance():
    outcome = detect_regressions(_metrics(tool_accuracy=0.90), _metrics(tool_accuracy=0.89))
    assert outcome["passed"]


def test_financial_drop_over_1pct_is_a_regression():
    outcome = detect_regressions(_metrics(financial_accuracy=1.0), _metrics(financial_accuracy=0.98))
    assert outcome["regressions"][0]["dimension"] == "financial_accuracy"


def test_cost_increase_is_a_warning_not_a_regression():
    outcome = detect_regressions(_metrics(cost=1.0), _metrics(cost=1.3))
    assert outcome["passed"]  # warning does not fail the gate
    assert outcome["warnings"][0]["dimension"] == "cost"


def test_safety_any_degradation_is_a_regression():
    outcome = detect_regressions(_metrics(safety_score=1.0), _metrics(safety_score=0.99))
    assert not outcome["passed"]
    assert outcome["regressions"][0]["dimension"] == "safety_score"


def test_hallucination_increase_is_a_regression():
    outcome = detect_regressions(_metrics(hallucination_rate=0.0), _metrics(hallucination_rate=0.01))
    assert not outcome["passed"]
    assert outcome["regressions"][0]["dimension"] == "hallucination_rate"


def test_custom_gate_tolerance():
    gate = RegressionGate("tool_accuracy", tolerance=0.10)
    assert detect_regressions(_metrics(tool_accuracy=0.9), _metrics(tool_accuracy=0.85),
                              (gate,))["passed"]


def test_evaluate_and_record_persists_regressions():
    directory = tempfile.mkdtemp(prefix="be-eval-reg-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    eval_store = EvaluationStore(store)
    baseline = {"id": "b1", "metrics": _metrics(tool_accuracy=0.9, task_success=0.9)}
    outcome = evaluate_and_record(eval_store, "run9", baseline,
                                  _metrics(tool_accuracy=0.8, task_success=0.9))
    assert not outcome["passed"]
    assert eval_store.list_regressions(run_id="run9")
    store.close()
