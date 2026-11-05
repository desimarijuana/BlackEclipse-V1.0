"""Records datasets — operator-supplied rows, same contracts and same gates.

The point of this source is breadth: Eclipse can train on ANY tabular data a user
has, not only market series. What must NOT change is the correctness discipline —
strictly chronological folds, a declared label column, no fabricated values, and
an honest error for anything that does not parse.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from harness.ml.datasets import build_dataset, build_records_dataset
from harness.ml.models import (
    CONTRACT_SCHEMA_VERSION,
    DatasetSpec,
    MLError,
    SplitSpec,
    TargetSpec,
    ExperimentConfig,
)
from harness.ml.training import run_experiment


def _dates(n: int) -> list[str]:
    start = dt.date(2024, 1, 1)
    return [(start + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _rows(n: int = 80) -> list[dict[str, object]]:
    dates = _dates(n)
    rows: list[dict[str, object]] = []
    for i, day in enumerate(dates):
        label = "up" if (i % 3) else "down"
        rows.append({
            "date": day,
            "id": f"r{i}",
            "a": float(i % 7),
            "b": float((i * 3) % 11) - 5.0,
            # a label that is learnable from `a` so the model is not noise
            "label": label if (i % 7) else ("up" if i % 2 else "down"),
        })
    return rows


def _spec(**overrides: object) -> DatasetSpec:
    base: dict[str, object] = {
        "source": "records",
        "feature_names": ["a", "b"],
        "target": TargetSpec(kind="column", column="label", task="classification"),
        "time_column": "date",
        "id_column": "id",
    }
    base.update(overrides)
    return DatasetSpec(**base)  # type: ignore[arg-type]


def test_records_manifest_records_its_source_and_classes() -> None:
    built = build_records_dataset(_spec(), _rows())
    manifest, arrays = built["manifest"], built["arrays"]

    assert manifest["source"] == "records"
    assert manifest["schemaVersion"] == CONTRACT_SCHEMA_VERSION
    assert manifest["rows"] == 80
    assert manifest["featureNames"] == ["a", "b"]
    assert manifest["target"]["task"] == "classification"
    assert manifest["target"]["classLabels"] == ["down", "up"]
    assert manifest["timeColumn"] == "date"
    assert manifest["timestampRange"] == ["2024-01-01", "2024-03-20"]
    assert manifest["dataHash"]

    # codes follow the SORTED label order, so "down" -> 0 and "up" -> 1
    assert arrays["y"][0] == 0.0  # row 0 is labelled "down"
    assert arrays["classLabels"] == ["down", "up"]
    assert arrays["X"].shape == (80, 2)
    assert arrays["timestamps"] == _dates(80)


def test_regression_target_parses_numbers_and_keeps_missing_as_nan() -> None:
    rows = _rows()
    for i, row in enumerate(rows):
        row["ret"] = (float(i) / 10.0 - 3.0) if i % 9 else None
    spec = _spec(target=TargetSpec(kind="column", column="ret", task="regression"))
    built = build_records_dataset(spec, rows)
    y = built["arrays"]["y"]
    assert built["manifest"]["target"]["task"] == "regression"
    assert np.isnan(y[0])  # missing stays missing, never imputed
    assert y[1] == pytest.approx(-2.9)


def test_non_numeric_regression_label_is_an_honest_error() -> None:
    rows = _rows()
    for i, row in enumerate(rows):
        row["ret"] = float(i)
    rows[5]["ret"] = "n/a"
    spec = _spec(target=TargetSpec(kind="column", column="ret", task="regression"))
    with pytest.raises(MLError) as exc:
        build_records_dataset(spec, rows)
    assert "non-numeric" in str(exc.value)
    assert "row 5" in str(exc.value)


def test_non_numeric_feature_is_an_honest_error() -> None:
    rows = _rows()
    rows[3]["a"] = "abc"
    with pytest.raises(MLError) as exc:
        build_records_dataset(_spec(), rows)
    assert "'a'" in str(exc.value) and "row 3" in str(exc.value)


def test_unsorted_time_column_is_refused_not_reordered() -> None:
    rows = _rows(20)
    rows[4], rows[5] = rows[5], rows[4]
    with pytest.raises(MLError) as exc:
        build_records_dataset(_spec(), rows)
    assert "sorted ascending" in str(exc.value)


def test_time_column_is_optional() -> None:
    spec = _spec(time_column=None, id_column=None)
    built = build_records_dataset(spec, _rows(10))
    assert built["arrays"]["timestamps"] == [str(i) for i in range(10)]
    assert built["manifest"]["timestampRange"] == ["0", "9"]


def test_classification_needs_two_classes() -> None:
    rows = _rows(10)
    for row in rows:
        row["label"] = "only"
    with pytest.raises(MLError) as exc:
        build_records_dataset(_spec(), rows)
    assert "at least two classes" in str(exc.value)


def test_market_kinds_are_refused_on_a_records_source() -> None:
    spec = _spec(target=TargetSpec(kind="direction_binary"))
    with pytest.raises(MLError) as exc:
        build_records_dataset(spec, _rows(10))
    assert "target.kind='column'" in str(exc.value)


async def test_unknown_source_is_refused() -> None:
    spec = _spec(source="s3")
    with pytest.raises(MLError) as exc:
        await build_dataset(None, spec, records=_rows(10))
    assert "unknown dataset source" in str(exc.value)


def test_fill_zero_policy_applies_to_features_only() -> None:
    rows = _rows(20)
    rows[2]["a"] = None
    built = build_records_dataset(_spec(missing_policy="fill_zero"), rows)
    assert built["arrays"]["X"][2, 0] == 0.0
    assert np.isfinite(built["arrays"]["y"]).all()


def test_forward_fill_policy_carries_the_previous_row() -> None:
    rows = _rows(20)
    rows[2]["a"] = None
    built = build_records_dataset(_spec(missing_policy="forward_fill"), rows)
    assert built["arrays"]["X"][2, 0] == built["arrays"]["X"][1, 0]


def test_data_hash_covers_the_labels_not_just_the_features() -> None:
    first = _rows(30)
    second = [dict(row) for row in first]
    for row in second:
        row["label"] = "up" if row["label"] == "down" else "down"
    a = build_records_dataset(_spec(), first)["manifest"]["dataHash"]
    b = build_records_dataset(_spec(), second)["manifest"]["dataHash"]
    assert a != b


def test_row_ids_are_provenance_not_artifact_payload() -> None:
    built = build_records_dataset(_spec(), _rows(10))
    assert built["arrays"]["symbols"] == []
    assert built["manifest"]["idColumn"] == "id"


def test_records_dataset_trains_end_to_end() -> None:
    built = build_records_dataset(_spec(), _rows(80))
    config = ExperimentConfig(
        dataset_id="mld_test",
        dataset_version="1.0.0",
        model_family="logistic",
        split=SplitSpec(method="walk_forward", n_splits=3, test_size=10),
        seed=7,
    )
    result = run_experiment(built["arrays"], built["manifest"], config)
    assert result["task"] == "classification"
    assert any(f["status"] == "ok" for f in result["folds"])
    assert result["finalModel"] is not None
    assert "accuracy" in result["pooledMetrics"]


def test_service_persists_and_trains_a_records_dataset(tmp_path) -> None:
    """The whole service path: payload -> immutable version -> experiment -> registry."""
    from harness.ml import service as S
    from harness.ml.store import MLStore
    from harness.persistence import AgentMemoryStore

    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        payload = {
            "name": "uploaded table",
            "source": "records",
            "records": _rows(80),
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
            "timeColumn": "date",
        }
        # The records path never touches the gateway, so None is honest here.
        import asyncio

        built = asyncio.run(S.build_dataset_version(None, payload, name="uploaded table"))
        assert built["quality"] is not None
        dataset_id, version = built["datasetId"], built["version"]

        run = asyncio.run(S.execute_experiment({
            "datasetId": dataset_id, "datasetVersion": version,
            "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
            "seed": 3, "registerModel": True, "name": "uploaded-model",
        }))
        assert run["result"]["task"] == "classification"
        assert run["result"]["classLabels"] == ["down", "up"]
        assert run["registered"]["modelId"]

        # Prediction returns NUMERIC codes; the label mapping travels with the
        # model so the operator's own vocabulary can be recovered.
        pred = S.predict_with_model(run["registered"]["modelId"], [[1.0, 0.5], [6.0, -4.0]])
        assert pred["classLabels"] == ["down", "up"]
        assert all(v is None or 0.0 <= v < 2.0 for v in pred["pred"])
    finally:
        S.set_ml_store(None)
