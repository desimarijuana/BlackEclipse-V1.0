"""Phase 7 (final hardening) — import/export recovery hardening.

Covers checksum/integrity validation, atomic import + rollback on failure,
conflict/duplicate preview, partial restore by category and scope, v1/v2
compatibility, schema/version negotiation, and preservation of provenance,
trust, bundles, evaluations and audit. jdds.db is never involved.
"""

from __future__ import annotations

import json

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.eclipse_memory.transfer import (
    EXPORT_SCHEMA,
    EXPORT_VERSION,
    _content_checksum,
    export_payload,
    import_payload,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _seed(service):
    service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    service.write_memory(
        memory_type="constraint", content="Always include sources",
        source="explicit_user", scope="user", scope_id="u1", subject="sources",
    )
    service.write_memory(
        memory_type="semantic", content="Project uses PostgreSQL 16",
        source="explicit_user", scope="project", scope_id="proj-a", subject="database",
    )


def test_export_is_v3_and_checksummed(service):
    _seed(service)
    document = export_payload(service.store)
    assert document["schema"] == EXPORT_SCHEMA
    assert document["version"] == EXPORT_VERSION >= 3
    assert document["checksum"]
    assert document["checksum"] == _content_checksum(
        {k: v for k, v in document.items() if k != "checksum"}
    )
    assert "evaluations" in document and "audit" in document


def test_tamper_is_refused(service):
    _seed(service)
    document = export_payload(service.store)
    document["memories"][0]["content"] = "tampered content"
    with pytest.raises(ValueError, match="checksum"):
        import_payload(service, document)


def test_newer_schema_is_refused(service):
    document = {"schema": EXPORT_SCHEMA, "version": EXPORT_VERSION + 1, "memories": []}
    with pytest.raises(ValueError, match="newer version"):
        import_payload(service, document)


def test_preview_classifies_without_writing(service, tmp_path):
    _seed(service)
    document = export_payload(service.store)
    before = len(service.store.list_memories(limit=1000, include_inactive=True))
    report = import_payload(service, document, dry_run=True)
    after = len(service.store.list_memories(limit=1000, include_inactive=True))
    assert before == after
    # Every existing memory is a duplicate on re-import.
    assert report["preview"]["duplicate"] >= 3
    assert report["preview"]["new"] == 0
    assert report["dryRun"] is True


def test_preview_reports_new_records_against_empty(service, tmp_path):
    other_db = tmp_path / "other.db"
    from harness.eclipse_memory.store import EclipseMemoryStore

    source = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "src.db")))
    _seed(source)
    document = export_payload(source.store)
    report = import_payload(service, document, dry_run=True)
    assert report["preview"]["new"] >= 3
    assert service.store.list_memories(limit=1000, include_inactive=True) == []


def test_v1_and_v2_still_import(service):
    v1 = {
        "schema": EXPORT_SCHEMA, "version": 1,
        "memories": [{"content": "I prefer concise answers", "memoryType": "preference",
                      "scope": "user", "scopeId": "u1"}],
    }
    assert import_payload(service, v1)["imported"] == 1
    v2 = {
        "schema": EXPORT_SCHEMA, "version": 2,
        "memories": [{"content": "I prefer detailed answers", "memoryType": "preference",
                      "scope": "user", "scopeId": "u9", "subject": "answer-style"}],
        "bundles": [], "projectTrust": [],
    }
    assert import_payload(service, v2)["imported"] >= 1


def test_partial_restore_by_scope(service, tmp_path):
    source = EclipseMemoryService(
        __import__("harness.eclipse_memory.store", fromlist=["EclipseMemoryStore"])
        .EclipseMemoryStore(str(tmp_path / "src.db"))
    )
    _seed(source)
    document = export_payload(source.store)
    report = import_payload(service, document, scope_filter="project")
    imported = service.store.list_memories(limit=1000)
    assert all(m["scope"] == "project" for m in imported)
    assert report["imported"] >= 1
    source.close()


def test_partial_restore_by_type(service, tmp_path):
    from harness.eclipse_memory.store import EclipseMemoryStore

    source = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "src.db")))
    _seed(source)
    document = export_payload(source.store)
    report = import_payload(service, document, type_filter="constraint")
    imported = service.store.list_memories(limit=1000)
    assert all(m["memoryType"] == "constraint" for m in imported)
    assert report["imported"] == 1
    source.close()


def test_preserves_bundles_trust_evaluations_and_audit(service, tmp_path):
    from harness.eclipse_memory.store import EclipseMemoryStore

    source = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "src.db")))
    source.write_memory(memory_type="preference", content="I prefer concise answers",
                        source="explicit_user", scope="user", scope_id="u1")
    source.store.save_skill_bundle({"id": "research", "name": "R", "skills": ["research.a"]})
    source.store.set_project_trust("/tmp/proj", True, note="n", content_hash="hash1",
                                   content_hashes={"research.a": "h1"})
    source.store.save_evaluation(skill_id="research.a", version="1.0.0", status="passed",
                                 dimensions=[{"name": "manifest"}])
    document = export_payload(source.store)
    assert len(document["evaluations"]) == 1
    assert document["audit"]

    report = import_payload(service, document)
    assert report["importedBundles"] == 1
    assert report["importedProjectTrust"] == 1
    assert report["importedEvaluations"] == 1
    assert report["auditRestored"] >= 1
    trust = service.store.get_project_trust("/tmp/proj")
    assert trust["trusted"] is True
    assert trust["contentHashes"] == {"research.a": "h1"}
    source.close()


def test_failed_import_leaves_no_partial_state(service, tmp_path, monkeypatch):
    from harness.eclipse_memory.store import EclipseMemoryStore
    import harness.eclipse_memory.transfer as transfer

    source = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "src.db")))
    _seed(source)
    document = export_payload(source.store)
    before = len(service.store.list_memories(limit=1000, include_inactive=True))

    original_signature = transfer._signature
    # Force an UNEXPECTED failure mid-import after at least one write commits.
    # `_signature` is called at the TOP of the per-record loop, OUTSIDE the
    # per-record try/except, so raising from it propagates. The preview phase
    # consumes the first three calls (caught internally); the apply loop then
    # writes one record and fails on the second, exercising rollback.
    calls = {"n": 0}

    def flaky_signature(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 5:
            raise RuntimeError("boom")
        return original_signature(*args, **kwargs)

    monkeypatch.setattr(transfer, "_signature", flaky_signature)
    with pytest.raises(RuntimeError):
        import_payload(service, document)
    after = len(service.store.list_memories(limit=1000, include_inactive=True))
    assert after == before, "a failed import must not leave partial state"
    source.close()


def test_jdds_never_involved(service):
    # The transfer module only ever touches the eclipse-memory db.
    import harness.eclipse_memory.transfer as transfer

    source = open(transfer.__file__, encoding="utf-8").read()
    assert "jdds" not in source.lower()
