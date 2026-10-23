"""The corpus bundle: export, import and tamper verification."""

from __future__ import annotations

import json

import pytest

from harness.evaluation.export import (
    build_corpus,
    import_corpus,
    verify_corpus,
    write_corpus,
)


def test_the_bundle_carries_every_builtin_dataset_with_its_checksum():
    payload = build_corpus()
    assert payload["bundleVersion"]
    assert payload["taskCount"] == sum(
        entry["taskCount"] for entry in payload["datasets"]
    )
    assert payload["taskCount"] >= 60
    for entry in payload["datasets"]:
        assert entry["checksum"]
        assert entry["taskCount"] == len(entry["tasks"])


def test_a_bundle_round_trips_through_the_task_schema(tmp_path):
    path = str(tmp_path / "corpus.json")
    written = write_corpus(path)
    datasets = import_corpus(path)
    assert sum(len(dataset.tasks) for dataset in datasets) == written["taskCount"]
    # Every task keeps its own version and category.
    for dataset in datasets:
        for task in dataset.tasks:
            assert task.version >= 1
            assert task.category


def test_a_bundle_can_be_verified_and_a_edited_task_is_detected(tmp_path):
    path = str(tmp_path / "corpus.json")
    write_corpus(path)
    assert verify_corpus(path)["ok"] is True

    payload = json.loads(open(path, encoding="utf-8").read())
    payload["datasets"][0]["tasks"][0]["description"] = "edited in flight"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    report = verify_corpus(path)
    assert report["ok"] is False
    assert report["mismatches"]
    assert "recomputed" in report["mismatches"][0]


def test_one_split_can_be_exported_alone(tmp_path):
    full = build_corpus()
    payload = build_corpus(splits=("optimization",))
    assert payload["taskCount"] > 0
    assert payload["taskCount"] < full["taskCount"]
