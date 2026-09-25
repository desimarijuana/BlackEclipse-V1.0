"""Memory lifecycle — temporal state, expiry, archive/restore, supersession,
confirmation refresh, last-used tracking, authority, and migration from an
existing database.

These tests exercise the real store/service, never a classifier alone, and never
touch the developer's runtime database (every fixture uses a temp file).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.db import now_iso
from harness.eclipse_memory.schema import SCHEMA_VERSION


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-life-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _write(service, content="A durable fact about the reporting currency", **kw):
    kw.setdefault("memory_type", "semantic")
    kw.setdefault("source", "manual")
    kw.setdefault("scope", "general")
    return service.write_memory(content=content, **kw)


# ── Lifecycle fields / authority ────────────────────────────────────────────


def test_new_memory_carries_lifecycle_fields(service):
    memory = _write(service)
    assert memory["createdAt"]
    assert memory["updatedAt"]
    assert memory["status"] == "active"
    assert memory["accessCount"] == 0
    # Manual/operator writes are explicit authority.
    assert memory["authority"] == "explicit"


def test_automatic_and_explicit_authority(service):
    explicit = _write(service, content="Explicit operator fact", source="manual")
    automatic = _write(service, content="Learned lesson from a run", source="execution_lesson")
    assert explicit["authority"] == "explicit"
    assert automatic["authority"] == "automatic"


def test_explicit_memory_is_stronger_than_automatic():
    directory = tempfile.mkdtemp(prefix="be-life-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        explicit = svc.write_memory(
            memory_type="semantic", content="Explicit fact", source="manual",
            scope="general",
        )
        automatic = svc.write_memory(
            memory_type="semantic", content="Automatic fact",
            source="execution_lesson", scope="general",
        )
        assert explicit["authority"] == "explicit"
        assert automatic["authority"] == "automatic"
        assert explicit["id"] != automatic["id"]
    finally:
        svc.close()


# ── Confirmation refresh ────────────────────────────────────────────────────


def test_restating_a_memory_refreshes_confirmation_not_duplicates(service):
    first = _write(service, content="I prefer concise answers")
    assert first.get("lastConfirmedAt") is None
    # Re-state the same durable fact: a duplicate save refreshes confirmation.
    again = service.write_memory(
        memory_type="semantic", content="I prefer concise answers",
        source="manual", scope="general",
    )
    assert again["id"] == first["id"]
    assert again["lastConfirmedAt"] is not None
    assert len([m for m in service.store.list_memories(include_inactive=False)]) == 1


def test_confirm_memory_is_auditable(service):
    memory = _write(service)
    updated = service.store.confirm_memory(memory["id"])
    assert updated["lastConfirmedAt"] is not None
    events = [e["type"] for e in service.store.list_memory_events()]
    assert "memory.confirmed" in events


# ── Last-used tracking ──────────────────────────────────────────────────────


def test_record_access_updates_last_used(service):
    memory = _write(service)
    assert memory["lastUsedAt"] is None
    service.store.record_access([memory["id"]])
    refreshed = service.store.get_memory(memory["id"])
    assert refreshed["accessCount"] == 1
    assert refreshed["lastUsedAt"] is not None


# ── Expiry exclusion ────────────────────────────────────────────────────────


def test_expired_memory_is_never_recalled(service):
    memory = service.write_memory(
        memory_type="semantic", content="An automatic fact about shipping lanes",
        source="execution_lesson", scope="general",
        expires_at="2000-01-01T00:00:00.000Z",
    )
    result = service.retrieve(query="shipping lanes", actor_scope="user", limit=8)
    assert all(m["id"] != memory["id"] for m in result.memories)
    excluded = {e["id"]: e["reason"] for e in result.diagnostics["excluded"]}
    assert excluded.get(memory["id"]) == "expired"


def test_retention_sweep_expires_only_automatic_memories(service):
    service.policy.set("retention_days", 1)
    automatic = service.write_memory(
        memory_type="semantic", content="Automatic lesson",
        source="execution_lesson", scope="general",
    )
    explicit = service.write_memory(
        memory_type="semantic", content="Explicit user fact",
        source="manual", scope="general",
    )
    # Explicit has no retention expiry.
    assert explicit["expiresAt"] is None
    # Force the automatic one due, then sweep.
    service.store.update_memory(automatic["id"], expiresAt="2000-01-01T00:00:00.000Z")
    result = service.expire_due_memories()
    assert result["ok"] is True
    assert result["inspected"] == 1
    assert result["expired"] == 1
    assert service.store.get_memory(automatic["id"])["status"] == "expired"
    assert service.store.get_memory(explicit["id"])["status"] == "active"


def test_renew_memory_extends_retention(service):
    memory = service.write_memory(
        memory_type="semantic", content="Automatic lesson",
        source="execution_lesson", scope="general",
    )
    renewed = service.renew_memory(memory["id"], days=30)
    assert renewed["expiresAt"] is not None
    assert renewed["lastConfirmedAt"] is not None


# ── Archive / restore ───────────────────────────────────────────────────────


def test_archive_then_restore_preserves_history(service):
    memory = _write(service)
    archived = service.store.archive_memory(memory["id"], status="archived", reason="user archived")
    assert archived["status"] == "archived"
    assert archived["statusReason"] == "user archived"
    # Archived is never recalled.
    result = service.retrieve(query="reporting currency", actor_scope="user")
    assert all(m["id"] != memory["id"] for m in result.memories)
    restored = service.store.restore_memory(memory["id"])
    assert restored["status"] == "active"
    assert restored["statusReason"] == "restored"
    result2 = service.retrieve(query="reporting currency", actor_scope="user")
    assert any(m["id"] == memory["id"] for m in result2.memories)


def test_review_rejection_is_inert(service):
    memory = service.propose_memory(
        memory_type="semantic", content="A proposed fact", source="execution_lesson",
    )
    assert memory["status"] == "proposed"
    rejected = service.review_memory(memory["id"], approve=False, reviewed_by="operator")
    assert rejected["status"] == "rejected"
    assert rejected["lastReviewedAt"] is not None
    result = service.retrieve(query="proposed fact", actor_scope="user")
    assert all(m["id"] != memory["id"] for m in result.memories)


# ── Supersession ────────────────────────────────────────────────────────────


def test_supersession_links_and_excludes_old(service):
    old = _write(service, content="I prefer concise answers")
    new = _write(service, content="I prefer detailed answers")
    service.store.supersede_memory(old["id"], new["id"], reason="user changed preference")
    old_now = service.store.get_memory(old["id"])
    assert old_now["status"] == "superseded"
    assert old_now["supersededBy"] == new["id"]
    assert old_now["statusReason"] == "user changed preference"
    links = service.store.list_links(old["id"])
    assert any(link["relation"] == "superseded" and link["toId"] == new["id"] for link in links)
    result = service.retrieve(query="prefer answers", actor_scope="user")
    assert all(m["id"] != old["id"] for m in result.memories)


# ── Lifecycle views ─────────────────────────────────────────────────────────


def test_lifecycle_counts_and_views(service):
    active = _write(service, content="Active fact")
    never_used = _write(service, content="Never used fact")
    service.store.record_access([active["id"]])
    archived = _write(service, content="Archived fact")
    service.store.archive_memory(archived["id"], status="archived")

    counts = service.store.memory_lifecycle_counts()
    assert counts["active"] == 2
    assert counts["archived"] == 1
    assert counts["neverUsed"] == 1

    never_used_view = service.store.list_lifecycle_memories("never-used")
    assert {m["id"] for m in never_used_view} == {never_used["id"]}
    archived_view = service.store.list_lifecycle_memories("archived")
    assert {m["id"] for m in archived_view} == {archived["id"]}


# ── Migration from an existing database ─────────────────────────────────────


def test_migration_from_existing_v9_database_preserves_rows():
    """A pre-lifecycle (schema v9) database opens and gains the new columns
    without losing data; existing rows read as explicit authority."""
    directory = tempfile.mkdtemp(prefix="be-mig-")
    path = os.path.join(directory, "eclipse-memory.db")

    # Build a v9-shaped database: apply all migrations below 10 and record their
    # versions, then insert a row. The store's migration runner must then apply
    # only migration 10.
    from harness.eclipse_memory.schema import MIGRATIONS

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS SchemaMigration (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL)"
    )
    for version, statements in MIGRATIONS:
        if version >= 10:
            break
        for statement in statements:
            conn.executescript(statement)
        conn.execute(
            "INSERT OR REPLACE INTO SchemaMigration (version, appliedAt) VALUES (?, ?)",
            (version, now_iso()),
        )
    conn.execute(
        """INSERT INTO MemoryRecord
           (id, memoryType, scope, content, confidence, importance, status,
            verification, createdAt, updatedAt, accessCount)
           VALUES ('mem_legacy', 'semantic', 'general', 'Legacy fact', 0.6, 0.5,
                   'active', 'unverified', ?, ?, 0)""",
        (now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()

    # Open through the normal store: migration 10 must apply.
    store = EclipseMemoryStore(path)
    try:
        assert store.migration_status()["upToDate"] is True
        legacy = store.get_memory("mem_legacy")
        assert legacy is not None
        assert legacy["content"] == "Legacy fact"
        # Unknown-provenance legacy rows are conservatively explicit (never
        # silently auto-expired).
        assert legacy["authority"] == "explicit"
        assert legacy.get("lastConfirmedAt") is None
    finally:
        store.close()


def test_schema_version_includes_migration_10():
    assert SCHEMA_VERSION >= 10


def test_migration_from_existing_v10_database_preserves_rows_and_reopens():
    """A v10 database (pre-maintenance) opens, gains migration 11, and reopens
    without loss; the maintenance table is available and empty."""
    directory = tempfile.mkdtemp(prefix="be-mig10-")
    path = os.path.join(directory, "eclipse-memory.db")

    from harness.eclipse_memory.schema import MIGRATIONS

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS SchemaMigration (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL)"
    )
    for version, statements in MIGRATIONS:
        if version >= 11:
            break
        for statement in statements:
            conn.executescript(statement)
        conn.execute(
            "INSERT OR REPLACE INTO SchemaMigration (version, appliedAt) VALUES (?, ?)",
            (version, now_iso()),
        )
    conn.execute(
        """INSERT INTO MemoryRecord
           (id, memoryType, scope, content, confidence, importance, status,
            verification, createdAt, updatedAt, accessCount, authority)
           VALUES ('mem_v10', 'semantic', 'general', 'V10 fact', 0.6, 0.5,
                   'active', 'unverified', ?, ?, 0, 'automatic')""",
        (now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()

    store = EclipseMemoryStore(path)  # applies migration 11
    try:
        assert store.migration_status()["upToDate"] is True
        assert store.get_memory("mem_v10")["content"] == "V10 fact"
        # Maintenance table exists and reads as "never run".
        assert store.maintenance_status() is None
    finally:
        store.close()

    # Reopening after the migration is safe and idempotent.
    reopened = EclipseMemoryStore(path)
    try:
        assert reopened.migration_status()["upToDate"] is True
        assert reopened.get_memory("mem_v10")["authority"] == "automatic"
    finally:
        reopened.close()
