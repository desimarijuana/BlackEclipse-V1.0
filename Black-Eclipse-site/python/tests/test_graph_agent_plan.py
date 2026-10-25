"""Structured step planning: ids, dependencies and honest refusals."""

from __future__ import annotations

import pytest

from harness.graph_runtime.agent_plan import MAX_STEPS, validate_step_plan


def test_assigns_stable_ids_and_keeps_earlier_dependencies():
    plan = validate_step_plan({
        "rationale": "two steps",
        "steps": [
            {"title": "Fetch", "objective": "Fetch the filings."},
            {"title": "Read", "objective": "Read the filings.", "dependsOn": ["Fetch"]},
        ],
    })
    assert plan["stepCount"] == 2
    assert [step["id"] for step in plan["steps"]] == ["step_1", "step_2"]
    assert plan["steps"][1]["dependsOn"] == ["Fetch"]


def test_rejects_empty_duplicate_or_forward_dependencies():
    with pytest.raises(ValueError, match="no steps"):
        validate_step_plan({"steps": []})
    with pytest.raises(ValueError, match="duplicate"):
        validate_step_plan({"steps": [
            {"title": "A", "objective": "a"},
            {"title": "A", "objective": "b"},
        ]})
    with pytest.raises(ValueError, match="does not exist"):
        validate_step_plan({"steps": [
            {"title": "A", "objective": "a", "dependsOn": ["B"]},
            {"title": "B", "objective": "b"},
        ]})


def test_rejects_more_than_the_step_cap():
    steps = [{"title": f"S{i}", "objective": "x"} for i in range(MAX_STEPS + 1)]
    with pytest.raises(ValueError, match="exceeds"):
        validate_step_plan({"steps": steps})
