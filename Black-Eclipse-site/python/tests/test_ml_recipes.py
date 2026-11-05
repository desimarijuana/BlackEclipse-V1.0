"""The model-recipe planner: deterministic, explainable, and honest about absence.

A plan is a proposal — it must never carry a metric, never pick a family the
runtime cannot import, and never claim a deep model when torch is missing.
"""

from __future__ import annotations

import pytest

from harness.ml import recipes
from harness.ml.recipes import DataProfile, plan_recipe, profile_from_manifest, to_experiment_payload


def _avail(**overrides: bool) -> dict[str, bool]:
    base = {"dummy": True, "ridge": True, "logistic": True, "random_forest": True,
            "kmeans": True, "mad_z": True,
            "sklearn_forest": True, "sklearn_extra_trees": True,
            "lightgbm": True, "xgboost": True, "torch_mlp": False}
    base.update(overrides)
    return base


def test_the_plan_is_deterministic() -> None:
    profile = DataProfile(rows=5_000, features=12, task="classification")
    a = plan_recipe(profile, available=_avail()).to_dict()
    b = plan_recipe(profile, available=_avail()).to_dict()
    assert a == b


def test_small_data_gets_an_interpretable_linear_model() -> None:
    plan = plan_recipe(DataProfile(rows=300, features=4, task="classification"),
                       available=_avail())
    assert plan.model_family == "logistic"
    assert plan.scale is True
    assert plan.split.n_splits == 3
    assert any("linear" in line for line in plan.rationale)


def test_large_data_prefers_a_boosted_ensemble_when_available() -> None:
    plan = plan_recipe(DataProfile(rows=20_000, features=60, task="regression"),
                       available=_avail())
    assert plan.model_family == "lightgbm"
    assert plan.selection["method"] == "correlation"
    assert plan.selection["topK"] == 20
    assert plan.split.n_splits == 5


def test_an_unavailable_family_is_never_planned() -> None:
    plan = plan_recipe(
        DataProfile(rows=20_000, features=6, task="classification"),
        available=_avail(lightgbm=False, xgboost=False, sklearn_forest=False),
    )
    assert plan.model_family == "random_forest"


def test_deep_preference_without_torch_is_a_warning_not_a_lie() -> None:
    plan = plan_recipe(DataProfile(rows=5_000, features=8, task="classification"),
                       preference="deep", available=_avail())
    assert plan.model_family != "torch_mlp"
    assert any("torch is not installed" in w for w in plan.warnings)


def test_deep_preference_with_torch_plans_the_mlp() -> None:
    plan = plan_recipe(DataProfile(rows=5_000, features=8, task="classification"),
                       preference="deep", available=_avail(torch_mlp=True))
    assert plan.model_family == "torch_mlp"
    assert plan.hyperparameters["hiddenSizes"] == [64, 32]


def test_unsupervised_plans_pick_their_own_family() -> None:
    cluster = plan_recipe(DataProfile(rows=800, features=5, task="clustering"),
                          available=_avail())
    assert cluster.model_family == "kmeans"
    assert 2 <= cluster.hyperparameters["nClusters"] <= 8

    anomaly = plan_recipe(DataProfile(rows=800, features=5, task="anomaly"),
                          available=_avail())
    assert anomaly.model_family == "mad_z"
    assert any("no ground truth" in w for w in anomaly.warnings)


def test_a_tiny_sample_is_a_warning_and_a_nonstarter_is_an_error() -> None:
    plan = plan_recipe(DataProfile(rows=120, features=3, task="regression"),
                       available=_avail())
    assert any("noisy" in w for w in plan.warnings)
    with pytest.raises(Exception):
        plan_recipe(DataProfile(rows=3, features=3, task="regression"), available=_avail())


def test_unknown_preference_is_refused() -> None:
    with pytest.raises(Exception):
        plan_recipe(DataProfile(rows=500, features=3, task="classification"),
                    preference="fastest", available=_avail())


def test_profile_from_a_records_manifest() -> None:
    manifest = {"rows": 900, "featureNames": ["a", "b", "c"],
                "target": {"task": "classification", "nClasses": 2}}
    profile = profile_from_manifest(manifest)
    assert profile.rows == 900 and profile.features == 3
    assert profile.task == "classification" and profile.class_count == 2


def test_the_experiment_payload_matches_the_service_contract() -> None:
    plan = plan_recipe(DataProfile(rows=2_000, features=5, task="classification"),
                       available=_avail())
    body = to_experiment_payload(plan, dataset_id="mld_x", dataset_version="1.0.0", seed=7)
    assert body["datasetId"] == "mld_x" and body["datasetVersion"] == "1.0.0"
    assert body["modelFamily"] == plan.model_family
    assert body["split"]["nSplits"] == plan.split.n_splits
    assert body["seed"] == 7 and body["scale"] is True
    # a plan carries no metric claim
    assert not any(k in body for k in ("metrics", "accuracy", "score"))


def test_the_service_plans_for_a_real_dataset_version(tmp_path) -> None:
    """The whole path the agent/UI uses: build a version, then plan against it."""
    import asyncio

    from harness.ml import service as S
    from harness.ml.store import MLStore
    from harness.persistence import AgentMemoryStore

    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rows = [{"a": float(i % 5), "b": float(i % 3), "label": "up" if i % 2 else "down"}
                for i in range(120)]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "planned", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
        }, name="planned"))

        result = S.plan_model({"datasetId": built["datasetId"],
                               "datasetVersion": built["version"]})
        assert result["profile"]["rows"] == 120
        assert result["experiment"]["datasetId"] == built["datasetId"]
        assert result["plan"]["split"]["nSplits"] == 3  # small sample → 3 folds
    finally:
        S.set_ml_store(None)
