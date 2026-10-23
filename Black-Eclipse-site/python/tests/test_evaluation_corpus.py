"""The corpus manifest and the authoring audit."""

from __future__ import annotations

import json

from harness.evaluation.corpus import (
    build_manifest,
    read_manifest,
    validate_tasks,
    verify_manifest,
    write_manifest,
)


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


def test_the_audit_reports_legacy_gaps_without_failing():
    report = validate_tasks(strict=False)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["counts"]["tasks"] == build_manifest()["taskCount"]
    # The legacy corpus predates the oracle rule; the audit reports it honestly.
    assert any(item["issue"] == "missing_oracle" for item in report["issues"])


def test_strict_audit_fails_on_the_legacy_oracle_gap():
    report = validate_tasks(strict=True)
    assert report["ok"] is False
    assert any(item["issue"] == "missing_oracle" for item in report["errors"])
