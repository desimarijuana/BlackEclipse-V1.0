"""Artifact revision comparison: deterministic, record-only, no byte diffing."""

from __future__ import annotations

from harness.artifacts import compare as C
from harness.artifacts.model import ArtifactVersion


def _v(**over):
    base = dict(
        id="v1", artifact_id="a1", version_number=1,
        checksum="sha256:aaa", size_bytes=100, mime_type="text/csv",
        created_by="local", agent_id=None, task_id=None, run_id=None,
        change_note=None, metadata={"source": "run-1", "rows": 10},
        created_at="2026-01-01T00:00:00Z",
    )
    base.update(over)
    return ArtifactVersion(**base)


def test_identical_revisions_report_no_change():
    report = C.compare_versions(_v(), _v(id="v2", version_number=2))
    assert report["changed"] is False
    assert report["bytes"]["checksumChanged"] is False
    assert report["bytes"]["sizeDeltaBytes"] == 0
    assert "No difference" in C.to_markdown(report)


def test_bytes_are_compared_by_checksum_and_size():
    left = _v()
    right = _v(id="v2", version_number=2, checksum="sha256:bbb", size_bytes=160)
    report = C.compare_versions(left, right)
    assert report["changed"] is True
    assert report["bytes"]["checksumChanged"] is True
    assert report["bytes"]["sizeDeltaBytes"] == 60
    assert "- Size: +60 bytes" in C.to_markdown(report)


def test_metadata_is_split_into_added_removed_and_changed():
    left = _v(metadata={"source": "run-1", "rows": 10, "drop": 1})
    right = _v(id="v2", version_number=2, metadata={"source": "run-2", "rows": 10, "new": True},
               checksum="sha256:bbb")
    meta = C.compare_versions(left, right)["metadata"]
    assert meta["added"] == ["new"]
    assert meta["removed"] == ["drop"]
    assert meta["changed"] == ["source"]
    assert meta["changedValues"]["source"] == {"from": "run-1", "to": "run-2"}


def test_provenance_changes_are_reported_separately():
    left = _v()
    right = _v(id="v2", version_number=2, run_id="run-9", checksum="sha256:bbb")
    report = C.compare_versions(left, right)
    assert report["provenance"]["run_id"]["changed"] is True
    assert report["provenance"]["agent_id"]["changed"] is False


def test_change_note_is_compared():
    left = _v()
    right = _v(id="v2", version_number=2, change_note="fixed split adjustment",
               checksum="sha256:bbb")
    assert C.compare_versions(left, right)["fields"]["change_note"]["changed"] is True


def test_long_metadata_values_are_bounded():
    long_value = "x" * 2_000
    left = _v(metadata={"notes": "short"})
    right = _v(id="v2", version_number=2, metadata={"notes": long_value}, checksum="sha256:bbb")
    report = C.compare_versions(left, right)
    value = report["metadata"]["changedValues"]["notes"]["to"]
    assert len(value) <= C.MAX_VALUE_CHARS


def test_compare_versions_accepts_camel_case_dicts():
    left = {"artifactId": "a1", "versionNumber": 1, "checksum": "x", "sizeBytes": 10,
            "metadata": {"a": 1}}
    right = {"artifactId": "a1", "versionNumber": 2, "checksum": "y", "sizeBytes": 11,
             "metadata": {"a": 1}}
    report = C.compare_versions(left, right)
    assert report["bytes"]["checksumChanged"] is True
    assert report["bytes"]["sizeDeltaBytes"] == 1


class _Store:
    def __init__(self, versions):
        self._versions = versions

    def get_version(self, artifact_id, number):
        return self._versions.get((artifact_id, number))


def test_compare_revisions_reads_both_versions_from_the_store():
    store = _Store({("a1", 1): _v(), ("a1", 2): _v(id="v2", version_number=2,
                                                    checksum="sha256:bbb")})
    report = C.compare_revisions(store, "a1", 1, 2)
    assert report is not None
    assert report["fromVersion"] == 1 and report["toVersion"] == 2


def test_compare_revisions_returns_none_when_a_version_is_missing():
    store = _Store({("a1", 1): _v()})
    assert C.compare_revisions(store, "a1", 1, 7) is None
