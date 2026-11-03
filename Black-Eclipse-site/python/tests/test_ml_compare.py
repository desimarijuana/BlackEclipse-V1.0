"""The model arena: one dataset, one validation design, several families.

The value of a comparison is that it can be TRUSTED, so the tests focus on the
ways a naive comparison lies: treating an unmeasured metric as zero, crowning a
winner whose margin is inside the fold noise, and ranking a task that has no
ground truth at all.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.ml import service as S
from harness.ml.compare import MAX_FAMILIES, build_comparison
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


def _run(family: str, pooled: dict | None, *, std: dict | None = None,
         status: str = "completed", task: str = "classification") -> dict:
    return {
        "runId": f"run_{family}", "experimentId": f"exp_{family}", "status": status,
        "result": {"modelFamily": family, "task": task,
                   "pooledMetrics": pooled or {}, "foldMetricsMean": pooled or {},
                   "foldMetricsStd": std or {}},
    }


def test_the_best_measured_family_wins() -> None:
    comparison = build_comparison([
        _run("logistic", {"macroF1": 0.61, "accuracy": 0.62}, std={"macroF1": 0.02}),
        _run("random_forest", {"macroF1": 0.78, "accuracy": 0.79}, std={"macroF1": 0.03}),
        _run("dummy", {"macroF1": 0.33, "accuracy": 0.5}, std={"macroF1": 0.0}),
    ], "classification")
    assert [row["modelFamily"] for row in comparison["ranking"]] == [
        "random_forest", "logistic", "dummy"]
    assert comparison["winner"]["modelFamily"] == "random_forest"
    assert "leads" in comparison["note"]


def test_a_null_metric_is_excluded_never_read_as_zero() -> None:
    comparison = build_comparison([
        _run("ridge", {"rmse": None}, std={"rmse": None}),
        _run("logistic", {"rmse": 0.4}, std={"rmse": 0.01}),
    ], "regression")
    assert [r["modelFamily"] for r in comparison["ranking"]] == ["logistic"]
    assert comparison["unmeasured"][0]["modelFamily"] == "ridge"
    assert comparison["unmeasured"][0]["reason"] == "unmeasured"


def test_a_failed_run_is_listed_but_cannot_be_ranked() -> None:
    comparison = build_comparison([
        _run("lightgbm", {}, status="failed"),
        _run("logistic", {"macroF1": 0.7}, std={"macroF1": 0.01}),
    ], "classification")
    assert comparison["unmeasured"][0]["reason"] == "failed"
    assert comparison["winner"]["modelFamily"] == "logistic"


def test_a_margin_inside_the_fold_noise_is_not_a_winner() -> None:
    comparison = build_comparison([
        _run("logistic", {"macroF1": 0.700}, std={"macroF1": 0.04}),
        _run("random_forest", {"macroF1": 0.703}, std={"macroF1": 0.05}),
    ], "classification")
    assert comparison["winner"] is None
    assert "no clear winner" in comparison["note"]


def test_anomaly_is_never_ranked() -> None:
    comparison = build_comparison([
        _run("mad_z", {"anomalyRate": 0.05}, task="anomaly"),
    ], "anomaly")
    assert comparison["ranking"] == []
    assert comparison["winner"] is None
    assert "no ground truth" in comparison["note"]


# ── the same thing through the real service ────────────────────────────────


@pytest.fixture()
def env(tmp_path):
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rows = [{"a": float(i % 5), "b": float((i * 7) % 11),
                 "label": "up" if (i % 5) >= 2 else "down"} for i in range(150)]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "arena", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
        }, name="arena"))
        yield built["datasetId"], built["version"]
    finally:
        S.set_ml_store(None)


def test_the_arena_runs_every_family_on_the_same_folds(env) -> None:
    dataset_id, version = env
    result = asyncio.run(S.compare_models({
        "datasetId": dataset_id, "datasetVersion": version,
        "families": ["dummy", "logistic", "random_forest"],
        "split": {"method": "walk_forward", "nSplits": 3}, "seed": 9,
    }))
    comparison = result["comparison"]
    assert len(comparison["rows"]) == 3
    assert {r["modelFamily"] for r in comparison["rows"]} == {
        "dummy", "logistic", "random_forest"}
    # every family ran, and each is a normal persisted run
    assert all(run["status"] == "completed" for run in result["runs"])
    assert len({run["experimentId"] for run in result["runs"]}) == 3
    # the SAME folds for every family: same count, same test windows
    fold_shapes = set()
    for run in result["runs"]:
        recorded = S.get_run_result(run["runId"])
        folds = recorded["result"]["folds"]
        fold_shapes.add(tuple((f.get("testStart"), f.get("testEnd")) for f in folds))
    assert len(fold_shapes) == 1, "families were validated on different folds"
    assert comparison["primaryMetric"]["key"] == "macroF1"


def test_the_arena_refuses_an_empty_or_oversized_grid(env) -> None:
    dataset_id, version = env
    with pytest.raises(Exception):
        asyncio.run(S.compare_models({"datasetId": dataset_id,
                                      "datasetVersion": version, "families": []}))
    with pytest.raises(Exception):
        asyncio.run(S.compare_models({
            "datasetId": dataset_id, "datasetVersion": version,
            "families": ["dummy"] * (MAX_FAMILIES + 1)}))
