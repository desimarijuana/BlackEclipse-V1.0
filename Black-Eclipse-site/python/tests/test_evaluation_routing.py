"""Round 4 (W3.2/W3.3) — routing metrics on the standing gate.

The classifier benchmark is a deterministic second measurement source. It must
pass at 0 misroutes / 1.0 escalation correctness, and a regression in either must
fail the same threshold check as the agent suite.
"""

from __future__ import annotations

import json

from harness.evaluation.regression import detect_regressions
from harness.evaluation.routing import run_routing_evaluation
from harness.evaluation.scoring import check_thresholds


def test_the_recorded_routing_benchmark_passes():
    result = run_routing_evaluation()
    assert result["cases"] == 8
    assert result["misroute_rate"] == 0.0
    assert result["escalation_correct"] == 1.0
    assert result["failures"] == []
    assert result["passed"] is True


def test_a_wrong_recorded_verdict_is_measured(tmp_path):
    dataset = {
        "datasetId": "routing-negative",
        "version": 1,
        "cases": [
            {
                    "id": "ribbon-must-escalate",
                    "text": "add a multi-zone latency ribbon to my dashboard",
                "expectedMode": "compose",
                "expectedGap": False,
            },
            {
                "id": "layout-composes",
                "text": "move the latency chart below the timeline",
                "expectedMode": "compose",
                "expectedGap": False,
            },
        ],
    }
    path = tmp_path / "routing.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    result = run_routing_evaluation(path)
    assert result["cases"] == 2
    assert result["misroute_rate"] == 0.5
    assert result["escalation_correct"] is None  # no escalation cases recorded
    assert result["passed"] is False
    assert result["failures"][0]["id"] == "ribbon-must-escalate"
    assert result["failures"][0]["actualMode"] == "engineer"


def test_the_gate_thresholds_fail_on_a_routing_regression():
    outcome = check_thresholds({"misroute_rate": 0.125, "escalation_correct": 0.5})
    assert outcome["passed"] is False
    assert any("misroute_rate" in failure for failure in outcome["failures"])
    assert any("escalation_correct" in failure for failure in outcome["failures"])


def test_regression_detection_treats_routing_as_critical():
    outcome = detect_regressions(
        {"misroute_rate": 0.0, "escalation_correct": 1.0},
        {"misroute_rate": 0.125, "escalation_correct": 0.875},
    )
    dimensions = {row["dimension"] for row in outcome["regressions"]}
    assert {"misroute_rate", "escalation_correct"} <= dimensions
    assert outcome["passed"] is False
