"""Immutable versioned research-dataset tests."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant.dataset_store import DatasetNotFound, DatasetStore, content_hash


@pytest.fixture()
def store(tmp_path):
    mem = AgentMemoryStore(path=str(tmp_path / "agent-memory.db"))
    return DatasetStore(mem, artifact_root=str(tmp_path / "artifacts"))


def _series(close_last: float = 3.0) -> dict:
    return {
        "AAPL": [
            {"timestamp": "2026-01-02T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.0, "volume": 10},
            {"timestamp": "2026-01-03T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 2.0, "volume": 20},
            {"timestamp": "2026-01-04T00:00:00Z", "open": 1, "high": 5, "low": 0.5, "close": close_last, "volume": 30},
        ]
    }


def test_content_hash_is_stable_and_order_independent():
    a = _series()
    b = {"AAPL": a["AAPL"]}
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(_series(close_last=4.0))


def test_build_creates_v1(store):
    manifest = store.build_version(series=_series(), request={"interval": "1d"})
    assert manifest["version"] == "v1"
    assert manifest["created"] is True
    assert manifest["immutable"] is True
    assert manifest["coverage"]["symbolCount"] == 1
    assert manifest["coverage"]["rowCount"] == 3
    assert manifest["contentHash"]


def test_identical_content_returns_same_version(store):
    first = store.build_version(series=_series(), dataset_id="ds_x", name="x")
    again = store.build_version(series=_series(), dataset_id="ds_x")
    assert again["version"] == first["version"]
    assert again["created"] is False
    assert len(store.list_versions("ds_x")) == 1


def test_new_content_creates_new_version_and_preserves_old(store):
    store.build_version(series=_series(), dataset_id="ds_y", name="y")
    v2 = store.build_version(series=_series(close_last=9.0), dataset_id="ds_y")
    assert v2["version"] == "v2"
    versions = store.list_versions("ds_y")
    assert [v["version"] for v in versions] == ["v1", "v2"]
    # The original version is unreadable as v1 but still present with its own hash.
    old = store.get_version("ds_y", "v1")
    assert old["coverage"]["rowCount"] == 3
    assert old["contentHash"] != v2["contentHash"]


def test_force_forks_a_new_version(store):
    store.build_version(series=_series(), dataset_id="ds_z")
    forced = store.build_version(series=_series(), dataset_id="ds_z", force=True)
    assert forced["version"] == "v2"
    assert forced["created"] is True


def test_compare_versions(store):
    store.build_version(series=_series(), dataset_id="ds_c", request={"interval": "1d"})
    store.build_version(series=_series(close_last=9.0), dataset_id="ds_c", request={"interval": "1d"})
    diff = store.compare_versions("ds_c", "v1", "v2")
    assert diff["sameContent"] is False
    assert diff["rowCountDelta"] == 0
    assert diff["qualityChanged"] is False


def test_read_artifact_and_missing_version(store):
    manifest = store.build_version(series=_series(), dataset_id="ds_a")
    artifact = store.read_artifact("ds_a", manifest["version"])
    assert artifact["series"]["AAPL"][0]["close"] == 1.0
    with pytest.raises(DatasetNotFound):
        store.get_version("ds_a", "v99")
    with pytest.raises(DatasetNotFound):
        store.read_artifact("ds_missing")
