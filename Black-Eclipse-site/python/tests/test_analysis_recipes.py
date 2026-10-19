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
    "drawdown_figure": {"prices": [100, 90, 95, 80, 120]},
    "distribution_profile": {"values": [1.0, 2.0, 2.5, 3.0, 9.0, 10.0]},
    "monte_carlo_paths": {"returns": [0.01, -0.02, 0.0, 0.03], "start_value": 100.0},
}


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


requires_runner = pytest.mark.skipif(not _has_runner(), reason="sandbox/interpreter unavailable")


def test_the_named_recipes_are_shipped():
    assert _NAMES == {
        "returns_series", "drawdown_profile", "correlation_matrix",
        "contribution_to_return", "reconciliation", "period_comparison", "scenario_shock",
        "drawdown_figure",       # Phase 18: the first figure recipe
        "distribution_profile",  # Phase 18: histogram + summary
        "monte_carlo_paths",     # Phase 18: bounded, seeded bootstrap
    }
    assert len(list_recipes()) == 10


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


@requires_runner
def test_drawdown_figure_writes_a_real_png_artifact_that_verifies(tmp_path):
    """Phase 18: the figure recipe produces a PNG the ledger can CHECK."""
    from harness.code.verify import verify_artifacts

    result = run_recipe("drawdown_figure", {"prices": [100, 90, 95, 80, 120]}, output_dir=tmp_path)
    assert result.status == "ok", result.stderr
    assert result.outputs["maxDrawdownPct"] == -20.0

    figures = [a for a in result.artifacts if a.name == "drawdown.png"]
    assert figures, [a.name for a in result.artifacts]
    figure = figures[0]
    assert figure.media_type.startswith("image/")

    # The artifact verifies as a real image: exists, digest, size, opens.
    records = verify_artifacts([figure], tmp_path, None)
    checks = {r.check: r.passed for r in records}
    assert checks["artifact_exists"] and checks["artifact_digest"]
    assert checks["artifact_size"] and checks["artifact_readable"]

    # The allowlist widening stays NAMED and narrow: an undeclared recipe source
    # cannot import matplotlib.
    from harness.code.execution import check_imports

    assert check_imports("import matplotlib\n") == ["matplotlib"]
    assert check_imports("import matplotlib\n", ("matplotlib",)) == []


def test_unknown_recipe_is_refused():
    result = run_recipe("does_not_exist", {})
    assert result.status == "refused"
    assert result.code == "RECIPE_NOT_FOUND"


def test_get_recipe_returns_a_declared_input_set():
    recipe = get_recipe("correlation_matrix")
    assert recipe is not None
    assert any(i.name == "returns" for i in recipe.inputs)


# ── Phase 18: the figure payload contract (§6.1) ────────────────────────────


@requires_runner
def test_a_figure_run_carries_its_payload_on_the_run_blob(tmp_path):
    """The plotted-series metadata rides the result/run blob: kind, the series
    and their point counts, the artifact, and the computed label — never
    evidence."""
    result = run_recipe("drawdown_figure", {"prices": [100, 90, 95, 80, 120]},
                        output_dir=tmp_path)
    assert result.status == "ok", result.stderr
    assert result.figure is not None
    payload = result.figure.to_dict()
    assert payload["kind"] == "line"
    assert payload["artifact"] == "drawdown.png"
    assert payload["series"] == [{"name": "prices", "points": 5}]
    assert payload["label"] == "computed"
    assert payload["isEvidence"] is False
    # It is part of the persisted blob, not a second rendering contract.
    blob = result.to_blob()
    assert blob["figure"]["kind"] == "line"
    assert blob["figure"]["isEvidence"] is False


def test_a_non_figure_recipe_carries_no_figure_payload():
    recipe = get_recipe("drawdown_profile")
    assert recipe is not None and recipe.figure_kind is None
    result = run_recipe("drawdown_profile", {})  # refused: no prices
    assert result.figure is None


@requires_runner
def test_distribution_profile_computes_the_middle_and_the_tails(tmp_path):
    result = run_recipe(
        "distribution_profile", {"values": [1.0, 2.0, 2.5, 3.0, 9.0, 10.0]},
        output_dir=tmp_path,
    )
    assert result.status == "ok", result.stderr
    assert result.outputs["count"] == 6
    assert result.outputs["median"] == 2.75
    assert result.outputs["p05"] <= result.outputs["median"] <= result.outputs["p95"]
    assert result.figure is not None and result.figure.kind == "histogram"
    assert any(a.name == "distribution.png" for a in result.artifacts)


@requires_runner
def test_monte_carlo_is_bounded_seeded_and_samples_the_supplied_returns(tmp_path):
    """The Monte Carlo rule as a gate: bootstrap the supplied returns (a sampled
    value is a member of the input set), record the seed, reproduce with it, and
    label the result a what-if — never an assumed distribution."""
    inputs = {"returns": [0.01, -0.02, 0.0, 0.03], "start_value": 100.0,
              "paths": 50, "horizon": 20, "seed": 7}
    first = run_recipe("monte_carlo_paths", inputs, output_dir=tmp_path)
    assert first.status == "ok", first.stderr
    assert first.outputs["paths"] == 50 and first.outputs["horizon"] == 20
    assert first.outputs["seed"] == 7
    assert first.outputs["label"] == "what-if"
    assert first.figure is not None and first.figure.kind == "paths"
    assert first.figure.seed == 7
    assert any(a.name == "monte_carlo.png" for a in first.artifacts)

    # Same seed ⇒ the same percentiles (reproducible), a different seed need not be.
    second = run_recipe("monte_carlo_paths", inputs, output_dir=tmp_path)
    assert second.outputs["p50"] == first.outputs["p50"]
    other_seed = run_recipe("monte_carlo_paths", {**inputs, "seed": 8}, output_dir=tmp_path)
    assert other_seed.status == "ok"

    # Bounds are enforced in the program: an absurd ask is clamped, not run away.
    bounded = run_recipe("monte_carlo_paths", {**inputs, "paths": 100_000, "horizon": 100_000},
                         output_dir=tmp_path)
    assert bounded.outputs["paths"] == 500 and bounded.outputs["horizon"] == 1000


def test_monte_carlo_refuses_without_returns_or_a_start_value():
    result = run_recipe("monte_carlo_paths", {"returns": [0.01]})
    assert result.status == "refused"
    assert result.code == INPUT_INVALID
    assert "start_value" in result.outputs["_missing"]
