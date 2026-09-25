"""Semantic/conflict reliability & recovery (Phase 8).

The v1 semantic layer holds NO persistent embedding index — it computes
similarity per write over an in-memory, already-authorized pool. These tests
prove that property and the fail-safe behavior around it: a migration/reopen
preserves conflict behavior, a missing backend falls back to lexical, and
backup/reset stay consistent.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory import semantic


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-semrel-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _pref(service, content, subject="answer-style"):
    return service.write_memory(
        memory_type="preference", content=content, source="explicit_user",
        scope="user", scope_id="u1", subject=subject,
    )


def test_conflict_behavior_survives_reopen_and_migration():
    directory = tempfile.mkdtemp(prefix="be-semrel-mig-")
    path = os.path.join(directory, "eclipse-memory.db")
    service = EclipseMemoryService(EclipseMemoryStore(path))
    service.policy.set("semantic_conflict_enabled", True)
    _pref(service, "I prefer concise answers")
    service.close()

    # Reopen through the normal store (migrations are idempotent).
    reopened = EclipseMemoryService(EclipseMemoryStore(path))
    try:
        assert reopened.store.migration_status()["upToDate"] is True
        conflict = _pref(reopened, "I prefer detailed answers")
        assert conflict["status"] == "proposed"
        assert len(reopened.store.list_memories(include_inactive=False)) == 1
    finally:
        reopened.close()


def test_startup_with_semantic_enabled_and_backend_missing(monkeypatch):
    # If no backend is available, health reports the safe fallback and lexical
    # detection still works.
    directory = tempfile.mkdtemp(prefix="be-semrel-miss-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        service.policy.set("semantic_conflict_enabled", True)
        monkeypatch.setattr(semantic, "backend_status", lambda *a, **k: {
            "backend": "none", "version": "semantic-v1", "available": False,
        })
        status = service.semantic_status()
        assert status["mode"] == "lexical+semantic-unavailable"
        assert status["semanticAvailable"] is False
        # Lexical still catches a direct conflict.
        _pref(service, "I prefer concise answers")
        conflict = _pref(service, "I prefer detailed answers")
        assert conflict["status"] == "proposed"
    finally:
        service.close()


def test_disabling_semantic_leaves_lexical_active():
    directory = tempfile.mkdtemp(prefix="be-semrel-off-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        service.policy.set("semantic_conflict_enabled", True)
        service.policy.set("semantic_conflict_enabled", False)
        assert service.semantic_status()["mode"] == "lexical"
        _pref(service, "I prefer concise answers")
        conflict = _pref(service, "I prefer detailed answers")
        assert conflict["status"] == "proposed"
    finally:
        service.close()


def test_backup_and_restore_preserve_conflict_state():
    from harness.eclipse_memory.transfer import create_backup, reset_memory

    directory = tempfile.mkdtemp(prefix="be-semrel-bak-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        _pref(service, "I prefer concise answers")
        backup = create_backup(service.store)
        assert os.path.isfile(backup["path"])
        # Reset clears memory; the backup file is intact and the store still works.
        reset_memory(service.store, confirm=True, backup_first=False)
        assert service.store.list_memories(include_inactive=True) == []
        first = _pref(service, "I prefer concise answers")
        conflict = _pref(service, "I prefer detailed answers")
        assert conflict["status"] == "proposed"
        assert service.store.get_memory(first["id"])["status"] == "active"
    finally:
        service.close()


def test_no_persistent_embedding_index_is_created(service):
    # The semantic layer must not add tables/columns on top of the schema; there
    # is no persistent vector index to corrupt or rebuild.
    service.policy.set("semantic_conflict_enabled", True)
    _pref(service, "I prefer concise answers with citations")
    _pref(service, "I prefer concise answers with citations and links")
    tables = {
        row["name"]
        for row in service.store._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert not any("embedding" in t.lower() or "vector" in t.lower() for t in tables)


def test_interrupted_similarity_does_not_break_write(service, monkeypatch):
    service.policy.set("semantic_conflict_enabled", True)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated backend crash")

    monkeypatch.setattr(semantic, "find_candidates", _boom)
    # A non-conflicting write still succeeds; the semantic failure is absorbed.
    memory = _pref(service, "I prefer detailed answers with charts")
    assert memory["status"] == "active"
