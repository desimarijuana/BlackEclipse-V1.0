"""Phase 1 hygiene — a full migration reopen matrix.

Proves the eclipse-memory database opens cleanly at every prior migration level
(1..N), that a pre-change database reopens with NO data loss, and that new
additive state (skill pin, maintenance ledger) survives a reopen. This is the
regression net for every additive migration.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.db import add_column_already_present, now_iso
from harness.eclipse_memory.schema import MIGRATIONS, SCHEMA_VERSION


def _fresh_path() -> str:
    return os.path.join(tempfile.mkdtemp(prefix="be-mig-"), "eclipse-memory.db")


def test_schema_version_is_highest_migration():
    assert SCHEMA_VERSION == max(v for v, _ in MIGRATIONS)


def test_every_prior_version_reopens_without_error():
    """Open a db at each historical version, then reopen at the latest."""
    for version, _ in MIGRATIONS:
        path = _fresh_path()
        db = sqlite3.connect(path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE IF NOT EXISTS SchemaMigration (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL)"
        )
        for v, statements in MIGRATIONS:
            if v > version:
                break
            for statement in statements:
                # Mirror the production runner: a base CREATE may already declare
                # a column a later migration adds.
                if add_column_already_present(db, statement):
                    continue
                db.executescript(statement)
            db.execute(
                "INSERT OR REPLACE INTO SchemaMigration (version, appliedAt) VALUES (?, ?)",
                (v, now_iso()),
            )
        db.commit()
        db.close()

        store = EclipseMemoryStore(path)
        try:
            status = store.migration_status()
            assert status["upToDate"] is True
            assert status["schemaVersion"] == SCHEMA_VERSION
        finally:
            store.close()


def test_pre_change_db_reopens_with_no_data_loss():
    """A database written at the previous schema keeps its memory + skills when
    opened by the new code (additive-only migrations)."""
    path = _fresh_path()
    first = EclipseMemoryService(EclipseMemoryStore(path))
    first.write_memory(
        memory_type="preference", content="I prefer concise answers",
        source="explicit_user", scope="user", scope_id="u1",
    )
    memory_id = first.store.list_memories(include_inactive=True)[0]["id"]
    # Rewind one migration to simulate an older database.
    top = max(v for v, _ in MIGRATIONS)
    first.store._db.execute("DELETE FROM SchemaMigration WHERE version=?", (top,))
    first.store._db.commit()
    first.close()

    reopened = EclipseMemoryService(EclipseMemoryStore(path))
    try:
        memories = reopened.store.list_memories(include_inactive=True)
        assert len(memories) == 1
        assert memories[0]["id"] == memory_id
        assert reopened.store.migration_status()["upToDate"] is True
    finally:
        reopened.close()


def test_pin_and_ledger_survive_reopen():
    path = _fresh_path()
    first = EclipseMemoryService(EclipseMemoryStore(path))
    first.store.upsert_skill(
        skill_id="p.skill", name="p", description="d", category="research",
        latest_version="1.0.0", status="enabled", tags=[],
    )
    from harness.skills.manifest import SkillManifest

    manifest = SkillManifest(
        id="p.skill", name="p", version="1.0.0", description="d", category="research",
        status="enabled", inputSchema={"type": "object", "properties": {}},
        requiredTools=[], permissions=["data.read"],
    )
    first.store.save_version(manifest.model_dump(), manifest.content_hash(), instructions="x")
    first.store.set_version_pinned("p.skill", "1.0.0", True)
    first.store.record_skill_maintenance("skill_maintenance", ok=True, inspected=3, archived=1)
    first.close()

    reopened = EclipseMemoryStore(path)
    try:
        assert reopened.is_version_pinned("p.skill", "1.0.0") is True
        status = reopened.skill_maintenance_status("skill_maintenance")
        assert status is not None and status["archived"] == 1
    finally:
        reopened.close()


def test_agent_memory_db_reopens_cleanly():
    """The separate agent-memory.db (runs/events) reopens with its rows intact."""
    from harness.persistence import AgentMemoryStore

    directory = tempfile.mkdtemp(prefix="be-agentdb-")
    path = os.path.join(directory, "agent-memory.db")
    first = AgentMemoryStore(path)
    first.create_run(
        "run_1", "eclipse-agent", {"query": "hello"}, None, "openai", "test",
    )
    first.close()

    reopened = AgentMemoryStore(path)
    try:
        run = reopened.get_run("run_1")
        assert run is not None and run["id"] == "run_1"
    finally:
        reopened.close()


def test_transition_cas_is_additive_and_safe():
    """The compare-and-set transition only fires on the expected state."""
    path = _fresh_path()
    store = EclipseMemoryStore(path)
    try:
        store.upsert_skill(
            skill_id="t.skill", name="t", description="d", category="research",
            latest_version="1.0.0", status="enabled", tags=[],
        )
        from harness.skills.manifest import SkillManifest

        manifest = SkillManifest(
            id="t.skill", name="t", version="1.0.0", description="d", category="research",
            status="enabled", inputSchema={"type": "object", "properties": {}},
            requiredTools=[], permissions=["data.read"],
        )
        store.save_version(manifest.model_dump(), manifest.content_hash(), instructions="x")
        # Wrong expected status → no change.
        assert store.transition_version_status(
            "t.skill", "1.0.0", "archived", expect_status="draft",
        ) is False
        assert store.transition_version_status(
            "t.skill", "1.0.0", "archived", expect_status="enabled",
        ) is True
    finally:
        store.close()
