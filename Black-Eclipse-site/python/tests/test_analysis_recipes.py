"""Phase 8 G6 — recipes, each with its honest missing-input path.

A missing input must ASK (a refusal carrying a plain prompt), never substitute a
default or a silently shorter period. Every executed recipe carries computed
provenance.
"""

from __future__ import annotations

import pytest

from harness.code import sandbox as sandbox_mod
from harness.code.execution import INPUT_INVALID, interpreter_path
from harness.code.recipes import RECIPES, get_recipe, list_recipes, run_recipe

_NAMES = {r.name for r in RECIPES}

_VALID_INPUTS: dict[str, dict] = {
    "returns_series": {"prices": [100, 101, 103, 102, 105]},
    "drawdown_profile": {"prices": [100, 90, 95, 80, 120]},
    "correlation_matrix": {"returns": [
        {"name": "a", "values": [1, 2, 3, 4, 5]},
        {"name": "b", "values": [2, 4, 6, 8, 10]},
        {"name": "c", "values": [5, 4, 3, 2, 1]},
    ]},
    "contribution_to_return": {"holdings": [
        {"name": "AAPL", "value": 50}, {"name": "MSFT", "value": 30}, {"name": "VOO", "value": 20},
    ]},
    "reconciliation": {
        "left": [{"key": "a", "value": 1}, {"key": "b", "value": 2}, {"key": "c", "value": 3}],
        "right": [{"key": "a", "value": 1}, {"key": "b", "value": 9}, {"key": "d", "value": 4}],
    },
    "period_comparison": {"current": 120.0, "previous": 100.0},
    "scenario_shock": {"values": [{"name": "AAPL", "value": 100}, {"name": "MSFT", "value": 200}], "shockPct": -20.0},
}


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


requires_runner = pytest.mark.skipif(not _has_runner(), reason="sandbox/interpreter unavailable")


def test_the_seven_named_recipes_are_shipped():
    assert _NAMES == {
        "returns_series", "drawdown_profile", "correlation_matrix",
        "contribution_to_return", "reconciliation", "period_comparison", "scenario_shock",
    }
    assert len(list_recipes()) == 7


@pytest.mark.parametrize("name", sorted(_NAMES))
def test_missing_input_asks_rather_than_guesses(name):
    result = run_recipe(name, {})
    assert result.status == "refused"
    assert result.code == INPUT_INVALID
    prompt = result.outputs.get("_prompt")
    assert prompt and prompt.endswith(("?", "."))
    # A refusal never carries computed provenance (it would render as a number).
    assert result.provenance is None


@requires_runner
@pytest.mark.parametrize("name", sorted(_NAMES))
def test_each_recipe_runs_and_carries_computed_provenance(name):
    result = run_recipe(name, _VALID_INPUTS[name])
    assert result.status == "ok", result.stderr
    assert result.provenance is not None and result.provenance.kind == "computed"


@requires_runner
def test_returns_series_computes_returns():
    result = run_recipe("returns_series", {"prices": [100, 110, 121]})
    assert result.status == "ok"
    returns = result.outputs["returns"]
    assert len(returns) == 2
    assert abs(returns[0] - 0.1) < 1e-6


@requires_runner
def test_drawdown_profile_reports_the_worst_fall():
    result = run_recipe("drawdown_profile", {"prices": [100, 80, 120]})
    assert result.status == "ok"
    assert result.outputs["maxDrawdownPct"] == -20.0


@requires_runner
def test_correlation_of_identical_series_is_one():
    result = run_recipe("correlation_matrix", _VALID_INPUTS["correlation_matrix"])
    assert result.status == "ok"
    matrix = result.outputs["matrix"]
    assert matrix[0][1] == 1.0  # a vs b (perfectly correlated)


@requires_runner
def test_reconciliation_reports_disagreements():
    result = run_recipe("reconciliation", _VALID_INPUTS["reconciliation"])
    assert result.status == "ok"
    assert result.outputs["agree"] is False
    assert "c" in result.outputs["onlyLeft"]
    assert "d" in result.outputs["onlyRight"]
    assert "b" in result.outputs["mismatched"]


@requires_runner
def test_scenario_shock_applies_the_move():
    result = run_recipe("scenario_shock", _VALID_INPUTS["scenario_shock"])
    assert result.status == "ok"
    assert result.outputs["shockedValues"]["AAPL"] == 80.0


def test_unknown_recipe_is_refused():
    result = run_recipe("does_not_exist", {})
    assert result.status == "refused"
    assert result.code == "RECIPE_NOT_FOUND"


def test_get_recipe_returns_a_declared_input_set():
    recipe = get_recipe("correlation_matrix")
    assert recipe is not None
    assert any(i.name == "returns" for i in recipe.inputs)
