"""Persistence layer — features, analyses, audit, artifacts, runs."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.stats.store import StatsStore


@pytest.fixture()
def store(tmp_path) -> StatsStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return StatsStore(ams, artifact_root=str(tmp_path / "art"))


def test_feature_metadata_and_immutable_versions(store):
    store.upsert_feature_metadata(feature_id="f1", name="Mom", description=None, owner="me",
                                  visibility="personal", category="momentum", tags=["x"], latest_version="1.0.0")
    store.add_feature_version(feature_id="f1", version="1.0.0", expression="close-1", pipeline=None,
                              param_schema={}, input_schema={}, output_schema={}, dependencies=["close"],
                              changelog="init", pit_safe=True)
    store.add_feature_version(feature_id="f1", version="1.0.1", expression="close-2", pipeline=None,
                              param_schema={}, input_schema={}, output_schema={}, dependencies=["close"],
                              changelog="fix", pit_safe=True)
    versions = store.list_feature_versions("f1")
    assert [v["version"] for v in versions] == ["1.0.0", "1.0.1"]
    # old version is still present and unchanged
    assert store.get_feature_version("f1", "1.0.0")["expression"] == "close-1"


def test_analysis_record_roundtrip(store):
    aid = store.record_analysis(tool="calculate_returns", tool_version="1.0.0", parameters={"m": 1},
                                dataset_ref={"symbols": ["AAPL"]}, status="ok", summary={"n": 3},
                                provenance={"source": "x"}, duration_ms=4, owner="me")
    record = store.get_analysis(aid)
    assert record["tool"] == "calculate_returns"
    assert record["summary"] == {"n": 3}
    assert record["datasetRef"]["symbols"] == ["AAPL"]
    assert len(store.list_analyses()) == 1


def test_audit_trail(store):
    store.audit(action="feature.save", subject_type="feature", subject_id="f1", actor="me", detail={"v": 1})
    events = store.list_audit()
    assert events[0]["action"] == "feature.save"
    assert events[0]["detail"] == {"v": 1}


def test_artifact_checksum_and_content(store):
    ref = store.save_artifact({"series": list(range(5))})
    assert len(ref["sha256"]) == 64
    got = store.get_artifact(ref["id"])
    assert got["content"] == {"series": [0, 1, 2, 3, 4]}
    assert got["sha256"] == ref["sha256"]


def test_validation_records(store):
    store.record_validation(feature_id="f1", version="1.0.0", status="valid", detail={"checks": []})
    rows = store.list_validations("f1")
    assert rows[0]["status"] == "valid"


def test_run_upsert_mirrors_state(store):
    store.upsert_run("r1", kind="analysis", status="running", stage="fetch", done=1, total=3)
    store.upsert_run("r1", kind="analysis", status="completed", stage="done", done=3, total=3,
                     finished_at="2026-01-01T00:00:00Z")
    row = store._db.execute("SELECT status,done,total FROM StatsRun WHERE id='r1'").fetchone()
    assert row["status"] == "completed" and row["done"] == 3
