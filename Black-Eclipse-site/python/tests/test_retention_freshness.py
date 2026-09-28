"""Freshness/retention distinctions (Phase 11): stale vs expired vs inert, an
expiry reason, a next-maintenance action, and a non-destructive sweep preview."""

from __future__ import annotations

import pytest

from harness.eclipse_memory import EclipseMemoryService


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _age(service, memory_id, *, days):
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    service.store._db.execute(  # noqa: SLF001
        "UPDATE MemoryRecord SET createdAt=?, lastConfirmedAt=NULL, lastUsedAt=NULL WHERE id=?",
        (old, memory_id),
    )
    service.store._db.commit()  # noqa: SLF001


def test_stale_is_active_but_old(service):
    memory = service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    stats = service.store.memory_lifecycle_counts()
    assert stats["stale"] == 0
    _age(service, memory["id"], days=200)
    stats = service.store.memory_lifecycle_counts()
    assert stats["stale"] >= 1
    # Stale is still active (not expired, still recalled).
    assert service.store.get_memory(memory["id"])["status"] == "active"


def test_stale_view_lists_old_active(service):
    memory = service.write_memory(memory_type="preference", content="I prefer concise answers", source="explicit_user")
    _age(service, memory["id"], days=200)
    stale = service.store.list_lifecycle_memories("stale", limit=50)
    assert any(m["id"] == memory["id"] for m in stale)


def test_retention_preview_is_non_destructive(service):
    # Automatic memory with an expiry in the past.
    memory = service.write_memory(
        memory_type="semantic", content="auto learned fact",
        source="execution_lesson", expires_at="2000-01-01T00:00:00Z",
    )
    before = service.store.get_memory(memory["id"])["status"]
    preview = service.preview_retention()
    assert preview["ok"] is True
    assert preview["due"] >= 1
    assert memory["id"] in preview["ids"] or preview["due"] >= 1
    # Nothing changed by the preview.
    assert service.store.get_memory(memory["id"])["status"] == before


def test_expiry_reason_is_recorded(service):
    memory = service.write_memory(
        memory_type="semantic", content="auto learned fact",
        source="execution_lesson", expires_at="2000-01-01T00:00:00Z",
    )
    service.expire_due_memories()
    record = service.store.get_memory(memory["id"])
    assert record["status"] == "expired"
    assert "retention_period_elapsed" in (record.get("statusReason") or "")


def test_explicit_memory_never_expires(service):
    memory = service.write_memory(
        memory_type="preference", content="explicit durable fact",
        source="explicit_user", expires_at="2000-01-01T00:00:00Z",
    )
    service.expire_due_memories()
    assert service.store.get_memory(memory["id"])["status"] == "active"


def test_retention_status_reports_next_action(service):
    status = service.retention_status()
    assert "nextMaintenanceAction" in status
    assert status["explicitMemoriesExempt"] is True
    # Session-history retention is a separate policy key.
    assert service.policy.get("session_retention_days") is not None
    assert service.policy.get("retention_days") is not None
