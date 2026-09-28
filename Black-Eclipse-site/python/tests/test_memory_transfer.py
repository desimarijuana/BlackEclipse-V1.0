"""Memory export / import / backup / health / reset — round-trip and safety.

Correctness:
  * export is readable, versioned JSON;
  * import goes through the normal write pipeline (privacy/type/scope rules) and
    is idempotent; malformed files are rejected with reasons;
  * backup never overwrites an existing file;
  * reset requires explicit confirmation, backs up first, clears ONLY the memory
    domain (skills survive), and never touches unrelated application data.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.transfer import (
    EXPORT_SCHEMA,
    create_backup,
    database_health,
    export_json,
    export_payload,
    import_payload,
    reset_memory,
)


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-transfer-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _seed(service):
    service.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    service.write_memory(
        memory_type="preference", content="I prefer candlestick charts",
        source="explicit_user", scope="user", scope_id="u1", subject="charts",
    )
    service.write_memory(
        memory_type="semantic", content="Platform convention: report timestamps in UTC.",
        source="manual", scope="general", subject="timestamps",
    )


# ── Export ──────────────────────────────────────────────────────────────────


def test_export_is_readable_versioned_json(service):
    _seed(service)
    document = json.loads(export_json(service.store))
    assert document["schema"] == EXPORT_SCHEMA
    assert document["version"] >= 1
    assert document["counts"]["memories"] == 3
    assert all("content" in m and "memoryType" in m for m in document["memories"])


def test_export_never_contains_secret_shaped_memory(service):
    # A secret is refused by the shared decision gate, so it can never appear in
    # an export.
    from harness.eclipse_memory.decision import authorize_proposal

    decision = authorize_proposal(
        content="api key sk-abcdefghijklmnop1234567890",
        provenance="memory_tool", user_message="remember my api key",
        user_id="u1",
    )
    assert decision.outcome == "ignore"
    document = export_payload(service.store)
    assert document["counts"]["memories"] == 0


# ── Import round-trip ───────────────────────────────────────────────────────


def test_round_trip_export_import(service):
    _seed(service)
    document = export_payload(service.store)
    # Import into a FRESH store (the real restore scenario).
    directory = tempfile.mkdtemp(prefix="be-import-")
    target = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        report = import_payload(target, document)
        assert report["imported"] == 3
        assert report["rejected"] == []
        assert len(target.store.list_memories(include_inactive=True)) == 3
        # Imported records carry import provenance.
        sources = {m["source"] for m in target.store.list_memories(include_inactive=True)}
        assert "imported" in sources
    finally:
        target.close()


def test_reimport_is_idempotent(service):
    _seed(service)
    document = export_payload(service.store)
    first = import_payload(service, document)
    assert first["imported"] == 0  # all already present
    assert first["skipped"] == 3
    assert len(service.store.list_memories(include_inactive=True)) == 3


def test_import_detects_duplicate_within_file():
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(tempfile.mkdtemp(), "eclipse-memory.db")))
    try:
        document = {
            "schema": EXPORT_SCHEMA, "version": 1,
            "memories": [
                {"content": "Same fact", "memoryType": "semantic", "scope": "general"},
                {"content": "Same fact", "memoryType": "semantic", "scope": "general"},
            ],
        }
        report = import_payload(service, document)
        assert report["imported"] == 1
        assert report["skipped"] == 1
    finally:
        service.close()


def test_import_rejects_malformed_document(service):
    with pytest.raises(ValueError):
        import_payload(service, {"schema": "wrong"})
    with pytest.raises(ValueError):
        import_payload(service, {"schema": EXPORT_SCHEMA, "version": 1})
    with pytest.raises(ValueError):
        import_payload(service, {"schema": EXPORT_SCHEMA, "version": 999, "memories": []})


def test_import_rejects_secret_records_with_reasons(service):
    document = {
        "schema": EXPORT_SCHEMA, "version": 1,
        "memories": [
            {"content": "api key sk-abcdefghijklmnop1234567890", "memoryType": "semantic", "scope": "general"},
        ],
    }
    report = import_payload(service, document)
    assert report["imported"] == 0
    assert report["rejected"]


def test_import_dry_run_writes_nothing(service):
    document = {
        "schema": EXPORT_SCHEMA, "version": 1,
        "memories": [{"content": "A new fact", "memoryType": "semantic", "scope": "general"}],
    }
    report = import_payload(service, document, dry_run=True)
    assert report["imported"] == 1
    assert len(service.store.list_memories(include_inactive=True)) == 0


# ── Backup / health ─────────────────────────────────────────────────────────


def test_backup_creates_a_copy_and_never_overwrites(service):
    _seed(service)
    first = create_backup(service.store)
    assert os.path.isfile(first["path"])
    assert first["bytes"] > 0
    # A second backup to the same explicit path must refuse, not overwrite.
    with pytest.raises(FileExistsError):
        create_backup(service.store, first["path"])


def test_database_health_reports_integrity(service):
    health = database_health(service.store)
    assert health["ok"] is True
    assert health["integrity"] == "ok"
    assert health["foreignKeyViolations"] == 0


# ── Reset ───────────────────────────────────────────────────────────────────


def test_reset_requires_confirmation(service):
    _seed(service)
    with pytest.raises(PermissionError):
        reset_memory(service.store, confirm=False)
    assert len(service.store.list_memories(include_inactive=True)) == 3


def test_reset_clears_memory_but_not_skills(service):
    _seed(service)
    service.store.upsert_skill(
        skill_id="test.skill", name="Test", description="d", category="test",
        latest_version="1.0.0", status="enabled", tags=[],
    )
    result = reset_memory(service.store, confirm=True, backup_first=True)
    assert result["ok"] is True
    assert result["backup"] is not None
    assert result["cleared"]["MemoryRecord"] == 3
    assert service.store.list_memories(include_inactive=True) == []
    # Skills are NOT memory and survive a reset.
    assert service.store.list_skills()


def test_reset_does_not_touch_unrelated_tables(service):
    service.store._db.execute("CREATE TABLE IF NOT EXISTS UnrelatedAppData (id TEXT)")
    service.store._db.execute("INSERT INTO UnrelatedAppData (id) VALUES ('x')")
    service.store._db.commit()
    reset_memory(service.store, confirm=True, backup_first=False)
    row = service.store._db.execute("SELECT COUNT(*) FROM UnrelatedAppData").fetchone()
    assert row[0] == 1


# -- Hardening: checksum, dry-run, partial restore (Phase 12) ----------------


def test_export_carries_checksum(service):
    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    from harness.eclipse_memory.transfer import export_payload

    document = export_payload(service.store)
    assert document.get("checksum")


def test_tampered_import_is_refused(service):
    from harness.eclipse_memory.transfer import export_payload, import_payload

    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    document = export_payload(service.store)
    document["memories"][0]["content"] = "I prefer verbose answers"  # tamper
    try:
        import_payload(service, document)
        assert False, "expected a checksum failure"
    except ValueError as exc:
        assert "checksum" in str(exc)


def test_dry_run_writes_nothing(service):
    from harness.eclipse_memory.transfer import export_payload, import_payload

    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    document = export_payload(service.store)
    before = len(service.store.list_memories(limit=100))
    report = import_payload(service, document, dry_run=True)
    after = len(service.store.list_memories(limit=100))
    assert before == after
    assert report["dryRun"] is True
    assert "importable" in report


def test_partial_restore_by_scope(service, tmp_path):
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.eclipse_memory.transfer import export_payload, import_payload

    service.write_memory(memory_type="preference", content="user scoped fact", source="explicit_user", scope="user", scope_id="u1")
    service.write_memory(memory_type="semantic", content="general fact", source="manual", scope="general")
    document = export_payload(service.store)

    from harness.eclipse_memory import EclipseMemoryService

    other = EclipseMemoryService(EclipseMemoryStore(str(tmp_path / "other.db")))
    report = import_payload(other, document, scope_filter="user")
    assert report["filters"]["scope"] == "user"
    assert report["imported"] >= 1
    other.close()


def test_checksum_ok_is_reported(service):
    from harness.eclipse_memory.transfer import export_payload, import_payload

    service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    document = export_payload(service.store)
    report = import_payload(service, document, dry_run=True)
    assert report["checksumOk"] is True
