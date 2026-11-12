"""C8.5: scorecard metrics come from runs, never from hand-typed values."""

from __future__ import annotations

from types import SimpleNamespace

from harness.evaluation.scorecard import regenerate


def _base() -> dict:
    return {
        "generated": "old",
        "dimensions": [
            {"id": "eval", "label": "Evaluation", "status": "partial", "evidence": ["a"], "note": "old"},
            {"id": "aci", "label": "Tool contract", "status": "partial", "evidence": ["b"], "note": "old"},
            {"id": "safety", "label": "Safety", "status": "partial", "evidence": ["c"], "note": "old"},
            {"id": "ext", "label": "Extension", "status": "partial", "evidence": ["d"], "note": "old"},
            {"id": "ops", "label": "Ops", "status": "unmeasured", "evidence": [], "note": "old"},
            {"id": "context", "label": "Context", "status": "partial", "evidence": ["e"], "note": "old"},
        ],
    }


def _suite(**aggregates):
    return SimpleNamespace(run_id="run_c85", aggregates=aggregates)


def test_measured_dimensions_get_a_sourced_metric():
    result = regenerate(
        _base(),
        suite=_suite(task_success=0.91, tool_accuracy=0.97, safety_score=1.0, misroute_rate=0.02),
        release={"runs": {"created": 50, "terminal": 50}},
        generated_at="2026-11-11T00:00:00Z",
    )
    by_id = {d["id"]: d for d in result["dimensions"]}
    for dimension_id, value in (
        ("eval", 0.91), ("aci", 0.97), ("safety", 1.0), ("ext", 0.02), ("ops", 1.0),
    ):
        dimension = by_id[dimension_id]
        assert dimension["status"] == "measured"
        assert dimension["metric"]["value"] == value
        assert dimension["metric"]["source"]
        assert dimension["metric"]["generatedAt"] == "2026-11-11T00:00:00Z"
    assert by_id["ext"]["metric"]["direction"] == "lower"


def test_a_dimension_without_a_measurement_stays_honest():
    result = regenerate(_base(), suite=_suite(task_success=0.9), generated_at="now")
    by_id = {d["id"]: d for d in result["dimensions"]}
    assert by_id["context"]["status"] == "partial"
    assert "metric" not in by_id["context"]
    # No release report -> ops stays unmeasured rather than inventing 1.0.
    assert by_id["ops"]["status"] == "unmeasured"


def test_regeneration_is_deterministic_and_does_not_mutate_the_base():
    base = _base()
    first = regenerate(base, suite=_suite(task_success=0.9), generated_at="t")
    second = regenerate(base, suite=_suite(task_success=0.9), generated_at="t")
    assert first == second
    assert "metric" not in base["dimensions"][0]
