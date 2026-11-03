"""Explainability and portability: permutation importance + dataset export.

Both exist so a model is not a black box the user cannot take with them: any
family gets a measured feature ranking, and any dataset version leaves as CSV or
JSONL with its labels and timestamps.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from harness.ml import importance
from harness.ml.importance import permutation_importance


def test_importance_ranks_a_real_feature_above_noise() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 2))
    y = (3.0 * X[:, 0] > 0).astype(float)          # only feature 0 matters

    def predict(matrix: np.ndarray) -> np.ndarray:
        return (3.0 * matrix[:, 0] > 0).astype(float)

    result = permutation_importance(predict, X, y, task="classification",
                                     seed=1, feature_names=["signal", "noise"])
    assert result is not None
    assert result["metric"] == "accuracy"
    assert result["features"]["signal"]["mean"] > result["features"]["noise"]["mean"]
    assert result["features"]["noise"]["mean"] == pytest.approx(0.0, abs=0.02)


def test_importance_is_deterministic_and_bounded() -> None:
    rng = np.random.default_rng(2)
    X = rng.normal(size=(120, 3))
    y = (X[:, 0] - X[:, 1] > 0).astype(float)

    def predict(matrix: np.ndarray) -> np.ndarray:
        return (matrix[:, 0] - matrix[:, 1] > 0).astype(float)

    a = permutation_importance(predict, X, y, task="classification", seed=7,
                                feature_names=["a", "b", "c"])
    b = permutation_importance(predict, X, y, task="classification", seed=7,
                                feature_names=["a", "b", "c"])
    assert a == b


def test_a_tiny_holdout_gets_no_importance_rather_than_a_guess() -> None:
    X = np.zeros((10, 2))
    y = np.zeros(10)
    assert permutation_importance(lambda m: np.zeros(len(m)), X, y,
                                  task="classification") is None
    assert importance.MIN_ROWS == 30


# ── export ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def stored(tmp_path):
    from harness.ml import service as S
    from harness.ml.store import MLStore
    from harness.persistence import AgentMemoryStore

    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rows = [{"a": float(i), "b": float(i % 3),
                 "label": "up" if i % 2 else "down"} for i in range(200)]
        built = __import__("asyncio").run(S.build_dataset_version(None, {
            "name": "exportable", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
        }, name="exportable"))
        yield S, built["datasetId"], built["version"]
    finally:
        S.set_ml_store(None)


def test_csv_export_carries_features_labels_and_timestamps(stored) -> None:
    S, dataset_id, version = stored
    out = S.export_dataset(dataset_id, version, fmt="csv")
    lines = out["content"].strip().splitlines()
    assert lines[0] == "a,b,label,labelLabel,timestamp"
    assert len(lines) == 201                      # header + 200 rows
    assert lines[1].endswith(",down,0")           # row 0 → "down", timestamp "0"
    assert out["truncated"] is False


def test_jsonl_export_is_machine_readable(stored) -> None:
    S, dataset_id, version = stored
    out = S.export_dataset(dataset_id, version, fmt="jsonl")
    first = json.loads(out["content"].splitlines()[0])
    assert first["label"] == 0.0 and first["labelLabel"] == "down"
    assert first["timestamp"] == "0"
    assert out["contentType"].startswith("application/x-ndjson")


def test_export_truncates_loudly_and_refuses_an_unknown_format(stored) -> None:
    S, dataset_id, version = stored
    out = S.export_dataset(dataset_id, version, fmt="csv", limit=5)
    assert out["rows"] == 5 and out["totalRows"] == 200 and out["truncated"] is True
    with pytest.raises(Exception):
        S.export_dataset(dataset_id, version, fmt="parquet")


def test_a_run_reports_permutation_importance(stored) -> None:
    S, dataset_id, version = stored
    run = __import__("asyncio").run(S.execute_experiment({
        "datasetId": dataset_id, "datasetVersion": version,
        "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
        "seed": 3,
    }))
    perm = run["result"]["finalPermutationImportance"]
    assert perm is not None
    assert perm["method"] == "permutation" and perm["metric"] == "accuracy"
    assert set(perm["features"]) <= {"a", "b"}
    assert perm["rows"] >= 30
