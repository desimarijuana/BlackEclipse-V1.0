"""Ensembles: blending registered models without re-fitting anything.

The risk in an ensemble is silent misalignment — averaging predictions from
different test rows or different tasks. These tests make that impossible to miss.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from harness.ml import service as S
from harness.ml.ensemble import align_out_of_fold, blend
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


def test_regression_blend_is_the_mean() -> None:
    out = blend("regression", [[1.0, 2.0], [3.0, 4.0]])
    assert out["pred"] == [2.0, 3.0]
    assert out["proba"] is None


def test_classification_averages_probabilities_and_takes_the_argmax() -> None:
    out = blend("classification", [[0.0, 1.0], [1.0, 0.0]],
                [[[0.2, 0.8], [0.6, 0.4]], [[0.9, 0.1], [0.3, 0.7]]])
    assert out["proba"][0] == pytest.approx([0.55, 0.45])
    assert out["proba"][1] == pytest.approx([0.45, 0.55])
    assert out["pred"] == [0.0, 1.0]


def test_classification_without_probabilities_is_a_majority_vote() -> None:
    out = blend("classification",
                [[0.0, 0.0, 0.0], [0.0, 1.0, 1.0], [1.0, 1.0, 2.0]],
                [None, None, None])
    # row 0: 0 wins 2-1; row 1: 1 wins 2-1; row 2: a 0-1-2 tie → the lowest class wins
    assert out["pred"] == [0.0, 1.0, 0.0]


def test_alignment_uses_only_shared_rows_and_refuses_an_empty_intersection() -> None:
    a = {"rowIndex": [0, 1, 2], "pred": [0.0, 1.0, 2.0], "proba": None}
    b = {"rowIndex": [1, 2, 3], "pred": [10.0, 20.0, 30.0], "proba": None}
    rows, preds, _ = align_out_of_fold([a, b])
    assert rows == [1, 2]
    assert preds == [[1.0, 2.0], [10.0, 20.0]]

    with pytest.raises(Exception):
        align_out_of_fold([{"rowIndex": [0], "pred": [1.0]},
                           {"rowIndex": [9], "pred": [1.0]}])


# ── through the real service ────────────────────────────────────────────────


@pytest.fixture()
def stored(tmp_path):
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rng = np.random.default_rng(3)
        rows = [{"a": float(rng.normal()), "b": float(rng.normal()),
                 "label": "up" if (rng.normal() > 0) else "down"} for _ in range(200)]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "ens", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
        }, name="ens"))
        yield built["datasetId"], built["version"]
    finally:
        S.set_ml_store(None)


def _train(dataset_id: str, version: str, family: str) -> str:
    run = asyncio.run(S.execute_experiment({
        "datasetId": dataset_id, "datasetVersion": version, "modelFamily": family,
        "split": {"method": "walk_forward", "nSplits": 3}, "seed": 11,
        "registerModel": True, "name": f"{family}-member",
    }))
    return run["registered"]["modelId"]


def test_an_ensemble_registers_and_predicts_by_blending(stored) -> None:
    dataset_id, version = stored
    logistic = _train(dataset_id, version, "logistic")
    forest = _train(dataset_id, version, "random_forest")

    result = S.create_ensemble({"name": "committee",
                                "members": [{"modelId": logistic}, {"modelId": forest}]})
    assert result["modelId"] and result["task"] == "classification"
    assert len(result["members"]) == 2
    assert "accuracy" in result["metrics"]

    # prediction by NAME (what chat says), and the blend matches the member mean
    model_id = S.resolve_model_id("committee")
    X = np.array([[0.5, -0.2], [1.0, 1.0]])
    blended = S.predict_with_model(model_id, X)
    assert blended["ensemble"] is True and blended["members"] == 2
    assert len(blended["pred"]) == 2

    member_probas = []
    for member in (logistic, forest):
        member_probas.append(S.predict_with_model(member, X)["proba"])
    expected = np.mean(np.asarray(member_probas, dtype=float), axis=0)
    assert np.allclose(np.asarray(blended["proba"], dtype=float), expected, atol=1e-9)


def test_an_ensemble_refuses_members_from_different_datasets(stored) -> None:
    dataset_id, version = stored
    first = _train(dataset_id, version, "logistic")
    other = asyncio.run(S.build_dataset_version(None, {
        "name": "other", "source": "records",
        "records": [{"a": float(i), "b": float(i % 3),
                     "label": "up" if i % 2 else "down"} for i in range(150)],
        "featureNames": ["a", "b"],
        "target": {"kind": "column", "column": "label", "task": "classification"},
    }, name="other"))
    second = _train(other["datasetId"], other["version"], "logistic")

    with pytest.raises(Exception) as exc:
        S.create_ensemble({"members": [{"modelId": first}, {"modelId": second}]})
    assert "SAME dataset" in str(exc.value)


def test_an_ensemble_needs_two_members(stored) -> None:
    dataset_id, version = stored
    only = _train(dataset_id, version, "logistic")
    with pytest.raises(Exception):
        S.create_ensemble({"members": [{"modelId": only}]})
