"""Hyperparameter search: deterministic trial planning + an honest ranking.

The search reuses the arena's rules, so the tests focus on what could mislead:
non-deterministic trial order, a duplicate config, a best score quoted without the
selection-on-the-same-folds caveat, and a budget that silently overruns.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.ml import service as S
from harness.ml.search import DEFAULT_SPACES, MAX_TRIALS, expand_grid, plan_trials, sample_configs
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


def test_grid_expansion_is_a_stable_cartesian_product() -> None:
    configs = expand_grid({"b": [1, 2], "a": ["x", "y"]})
    assert configs == [
        {"a": "x", "b": 1}, {"a": "x", "b": 2},
        {"a": "y", "b": 1}, {"a": "y", "b": 2},
    ]
    assert expand_grid({}) == [{}]


def test_a_grid_with_an_empty_axis_is_refused() -> None:
    with pytest.raises(Exception):
        expand_grid({"alpha": []})


def test_sampling_is_seeded_unique_and_within_the_grid() -> None:
    grid = {"alpha": [0.1, 1.0, 10.0], "l2": [1e-3, 1e-2]}
    a = sample_configs(grid, 3, seed=7)
    b = sample_configs(grid, 3, seed=7)
    assert a == b
    assert len({tuple(sorted(c.items())) for c in a}) == len(a)
    universe = {tuple(sorted(c.items())) for c in expand_grid(grid)}
    assert all(tuple(sorted(c.items())) in universe for c in a)


def test_plan_uses_the_family_defaults_and_caps_the_trials() -> None:
    configs, sampled = plan_trials("ridge")
    assert configs and sampled is False
    assert configs == expand_grid(DEFAULT_SPACES["ridge"])

    capped, sampled = plan_trials("random_forest", n_trials=2)
    assert len(capped) == 2 and sampled is True

    huge, _ = plan_trials("ridge", grid={"alpha": list(range(100))}, n_trials=None)
    assert len(huge) == MAX_TRIALS


# ── through the real service ────────────────────────────────────────────────


@pytest.fixture()
def stored(tmp_path):
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        import numpy as np

        rng = np.random.default_rng(5)
        rows = [{"a": float(i % 7), "b": float((i * 3) % 11),
                 "y": float((i % 7) * 2 + (i % 3) + rng.normal(0, 0.4))} for i in range(220)]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "tunable", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "y", "task": "regression"},
        }, name="tunable"))
        yield built["datasetId"], built["version"]
    finally:
        S.set_ml_store(None)


def test_the_search_runs_every_trial_and_names_the_best_config(stored) -> None:
    dataset_id, version = stored
    result = asyncio.run(S.search_hyperparameters({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "ridge", "grid": {"alpha": [0.01, 1.0, 100.0]},
        "split": {"method": "walk_forward", "nSplits": 3}, "maxTrials": 3,
    }))
    assert len(result["trials"]) == 3
    assert all(t["status"] == "completed" for t in result["trials"])
    assert result["stoppedReason"] == "maxTrials"
    assert result["best"] is not None
    assert result["best"]["hyperparameters"]["alpha"] in (0.01, 1.0, 100.0)
    assert result["best"]["metric"] == "rmse"
    # the caveat is mandatory, not optional prose
    assert "optimistic" in result["note"]
    # adjacent regularisation strengths are inside the fold noise: that is stated
    assert result["best"]["withinNoise"] is True


def test_a_clear_winner_is_flagged_as_such(stored) -> None:
    dataset_id, version = stored
    result = asyncio.run(S.search_hyperparameters({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "ridge", "grid": {"alpha": [0.01, 5000.0]},
        "split": {"method": "walk_forward", "nSplits": 3}, "maxTrials": 2,
    }))
    assert result["best"] is not None
    assert result["best"]["hyperparameters"]["alpha"] == 0.01
    assert result["best"]["withinNoise"] is False


def test_the_search_respects_the_trial_budget_and_says_why_it_stopped(stored) -> None:
    dataset_id, version = stored
    result = asyncio.run(S.search_hyperparameters({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "ridge", "grid": {"alpha": [0.01, 1.0, 100.0]},
        "split": {"method": "walk_forward", "nSplits": 3}, "maxTrials": 1,
    }))
    assert len(result["trials"]) == 1
    assert result["stoppedReason"] == "maxTrials"


def test_the_search_refuses_a_trial_count_outside_the_guardrail(stored) -> None:
    dataset_id, version = stored
    with pytest.raises(Exception):
        asyncio.run(S.search_hyperparameters({
            "datasetId": dataset_id, "datasetVersion": version,
            "modelFamily": "ridge", "maxTrials": MAX_TRIALS + 1,
        }))
