"""The corpus manifest and the authoring audit."""

from __future__ import annotations

import json

import harness.evaluation.corpus as corpus_module
from harness.evaluation.corpus import (
    build_manifest,
    read_manifest,
    validate_tasks,
    verify_manifest,
    write_manifest,
)
from harness.evaluation.tasks import Dataset, EvaluationTask


def _only_dataset(monkeypatch, *, metadata, task_metadata, task_id="fixture.task"):
    task = EvaluationTask.from_dict({
        "id": task_id,
        "version": 1,
        "name": task_id,
        "description": "corpus fixture",
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "Say READY."},
        "expected_output": {"equals": "READY"},
        "graders": [{"name": "exact"}],
        "metadata": task_metadata,
    })
    dataset = Dataset(
        name="fixture", version="1", tasks=[task], metadata=metadata,
        reviewed=True, reviewer="test",
    )
    monkeypatch.setattr(corpus_module, "available_datasets", lambda: ["fixture"])
    monkeypatch.setattr(corpus_module, "load_builtin_dataset", lambda name: dataset)
    return dataset


def test_manifest_totals_agree_with_the_datasets():
    manifest = build_manifest(recorded_at="2026-10-22T00:00:00.000Z")
    assert manifest["datasetCount"] == len(manifest["datasets"])
    assert manifest["taskCount"] == sum(
        entry["taskCount"] for entry in manifest["datasets"]
    )
    assert sum(manifest["bySplit"].values()) == manifest["taskCount"]
    assert manifest["oracleCoverage"] == round(
        manifest["oracleCount"] / manifest["taskCount"], 6,
    )


def test_a_written_manifest_verifies_against_the_current_corpus(tmp_path):
    path = tmp_path / "corpus_manifest.json"
    write_manifest(str(path))
    report = verify_manifest(str(path))
    assert report["ok"] is True
    assert report["mismatches"] == []
    assert report["taskCount"] == build_manifest()["taskCount"]


def test_a_tampered_checksum_is_detected(tmp_path):
    path = tmp_path / "corpus_manifest.json"
    write_manifest(str(path))
    payload = read_manifest(str(path))
    payload["datasets"][0]["checksum"] = "deadbeef"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = verify_manifest(str(path))
    assert report["ok"] is False
    assert any(
        item.get("field") == "checksum" for item in report["mismatches"]
    )


def test_a_tampered_task_count_is_detected(tmp_path):
    path = tmp_path / "corpus_manifest.json"
    write_manifest(str(path))
    payload = read_manifest(str(path))
    payload["taskCount"] = int(payload["taskCount"]) + 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = verify_manifest(str(path))
    assert report["ok"] is False
    assert any(
        item.get("field") == "taskCount" and item.get("dataset") == "*"
        for item in report["mismatches"]
    )


def test_the_audit_counts_documented_exemptions_without_failing():
    manifest = build_manifest()
    report = validate_tasks(strict=False)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["counts"]["tasks"] == manifest["taskCount"]
    assert report["counts"]["oracleExempt"] == manifest["oracleExemptCount"]
    # Exempt legacy fixtures are intentional, not an unreported gap.
    assert not any(
        item["issue"] in ("missing_oracle", "missing_contamination")
        for item in report["issues"]
    )


def test_strict_audit_passes_once_exemptions_and_oracles_are_recorded():
    report = validate_tasks(strict=True)
    assert report["ok"] is True
    assert report["errors"] == []
    manifest = build_manifest()
    assert manifest["oracleCount"] >= 250
    assert manifest["oracleExemptCount"] == 76
    assert manifest["oracleCount"] + manifest["oracleExemptCount"] <= manifest["taskCount"]


def test_a_non_exempt_missing_oracle_still_fails(monkeypatch):
    _only_dataset(monkeypatch, metadata={}, task_metadata={})
    report = validate_tasks(strict=True)
    assert report["ok"] is False
    assert any(item["issue"] == "missing_oracle" for item in report["errors"])


def test_an_exemption_without_a_reason_is_flagged(monkeypatch):
    _only_dataset(
        monkeypatch,
        metadata={"oracleExempt": True},
        task_metadata={"contamination": {"source": "authored"}},
    )
    report = validate_tasks(strict=True)
    assert report["ok"] is False
    assert any(
        item["issue"] == "missing_oracle_reason" for item in report["errors"]
    )


def test_a_reasoned_exempt_dataset_passes_strict(monkeypatch):
    _only_dataset(
        monkeypatch,
        metadata={
            "oracleExempt": True,
            "oracleReason": "a frozen fixture with no recomputable value",
            "contamination": {"source": "authored", "authoredAt": "2026-10-23"},
        },
        task_metadata={},
    )
    report = validate_tasks(strict=True)
    assert report["ok"] is True
    assert report["counts"]["oracleExempt"] == 1
