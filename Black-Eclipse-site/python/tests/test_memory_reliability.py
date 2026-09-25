"""Memory reliability and recovery (Phase 8).

Failure modes that must be honest, never fabricated:
  * a corrupt database makes memory unavailable (503) rather than answering;
  * a locked database waits (busy timeout) instead of failing immediately;
  * a partial/interrupted backup leaves no partial file at the destination;
  * malformed imports are rejected with reasons;
  * duplicates do not accumulate;
  * retrieval failure is diagnostics, not a crash, and never invents context;
  * the agent does not claim a memory was saved when the write was refused.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.transfer import create_backup, import_payload


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-reliab-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


# ── Corrupt database ────────────────────────────────────────────────────────


def test_corrupt_database_is_detected():
    directory = tempfile.mkdtemp(prefix="be-corrupt-")
    path = os.path.join(directory, "eclipse-memory.db")
    # A file that is not a valid SQLite database.
    with open(path, "wb") as handle:
        handle.write(b"this is not a sqlite database at all" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        EclipseMemoryStore(path)


def test_health_reports_unhealthy_for_a_broken_connection(service):
    # A closed connection is unreadable; health must report failure, not raise.
    service.store._db.close()
    health = service.store.health()
    assert health["ok"] is False
    assert "error" in health


def test_retrieval_failure_returns_diagnostics_not_a_crash(service):
    # Closing the connection mid-life makes retrieval fail; it must be reported
    # as diagnostics with ok=False, never raise, and never fabricate memories.
    service.store._db.close()
    result = service.retrieve(query="anything", actor_scope="user")
    assert result.memories == []
    assert result.diagnostics["ok"] is False
    assert result.diagnostics["error"]


# ── Locked database ─────────────────────────────────────────────────────────


def test_busy_timeout_is_configured(service):
    value = service.store._db.execute("PRAGMA busy_timeout").fetchone()[0]
    assert int(value) >= 1000


# ── Interrupted backup ──────────────────────────────────────────────────────


def test_interrupted_backup_leaves_no_partial_at_destination_and_no_temp(service):
    target = os.path.join(os.path.dirname(service.store.path), "interrupted-backup.db")
    # Simulate a failure during the copy by pointing at a source that vanishes
    # is not easy; instead pre-create the destination and assert refusal, then
    # assert an explicit failing copy leaves no `.partial` behind.
    import harness.eclipse_memory.transfer as transfer

    original_copy = transfer.shutil.copy2

    def _fail(src, dst, *a, **k):
        raise OSError("simulated interruption")

    transfer.shutil.copy2 = _fail
    try:
        with pytest.raises(OSError):
            create_backup(service.store, target)
    finally:
        transfer.shutil.copy2 = original_copy
    assert not os.path.exists(target)
    assert not os.path.exists(f"{target}.partial")


def test_backup_never_overwrites_existing(service):
    target = os.path.join(os.path.dirname(service.store.path), "existing.db")
    open(target, "wb").close()
    with pytest.raises(FileExistsError):
        create_backup(service.store, target)


# ── Malformed imports / duplicates ──────────────────────────────────────────


def test_malformed_import_is_rejected_with_reasons(service):
    from harness.eclipse_memory.transfer import EXPORT_SCHEMA

    report = import_payload(service, {
        "schema": EXPORT_SCHEMA, "version": 1,
        "memories": [{"content": "", "memoryType": "semantic"}, "not-an-object"],
    })
    assert report["imported"] == 0
    assert len(report["rejected"]) == 2


def test_duplicate_import_does_not_accumulate(service):
    from harness.eclipse_memory.transfer import EXPORT_SCHEMA

    document = {
        "schema": EXPORT_SCHEMA, "version": 1,
        "memories": [{"content": "A durable fact", "memoryType": "semantic", "scope": "general"}],
    }
    import_payload(service, document)
    import_payload(service, document)
    assert len(service.store.list_memories(include_inactive=True)) == 1


# ── Honest outcome when memory is unavailable ───────────────────────────────


def test_commit_decision_reports_refusal_not_success_when_disabled(service):
    service.policy.set("memory_enabled", False)
    decision = service.decide_turn("remember that I prefer concise answers", user_id="u1")
    outcome = service.commit_decision(decision, user_id="u1")
    assert outcome["ok"] is False
    assert outcome["action"] == "refused"
    assert service.store.list_memories(include_inactive=True) == []


# ── API 503 on unavailable memory ───────────────────────────────────────────


def test_api_retrieve_returns_503_when_memory_unavailable(monkeypatch):
    os.environ.setdefault(
        "AGENT_MEMORY_DB_PATH",
        os.path.join(tempfile.mkdtemp(prefix="be-rel-run-"), "agent-memory.db"),
    )
    os.environ.setdefault(
        "ECLIPSE_MEMORY_DB_PATH",
        os.path.join(tempfile.mkdtemp(prefix="be-rel-em-"), "eclipse-memory.db"),
    )
    from harness import main as main_module

    with TestClient(main_module.app) as client:
        # Force the availability guard to report unavailable.
        monkeypatch.setattr(main_module, "_memory_available", lambda: False)
        res = client.post("/eclipse-memory/retrieve", json={"query": "x", "actorScope": "user"})
    assert res.status_code == 503
    assert "unavailable" in res.json()["detail"].lower()
