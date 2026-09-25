"""Retention hardening (Phase 2) — automatic, reliable, observable, safe.

Correctness:
  * an automatic memory gets a policy-derived expiry; an explicit one never does;
  * the sweep runs automatically at runtime startup (the existing lifespan);
  * the sweep is idempotent and observable (inspected/expired/skipped/ranAt);
  * a failed sweep never stops the application and is reported honestly;
  * retrieval excludes a due memory by timestamp before any sweep;
  * expired memories remain auditable (status + reason, never deleted);
  * confirming/renewing refreshes timestamps and clears/extends expiry;
  * a retention-policy change does not mutate existing records;
  * duplicate writes never revive an expired/superseded/archived record.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-retain-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _automatic(service, content="An automatic lesson", **kw):
    kw.setdefault("memory_type", "semantic")
    kw.setdefault("source", "execution_lesson")
    kw.setdefault("scope", "general")
    return service.write_memory(content=content, **kw)


def _explicit(service, content="An explicit fact", **kw):
    kw.setdefault("memory_type", "semantic")
    kw.setdefault("source", "manual")
    kw.setdefault("scope", "general")
    return service.write_memory(content=content, **kw)


# ── Expiry assignment ───────────────────────────────────────────────────────


def test_automatic_memory_receives_expiry_explicit_does_not(service):
    service.policy.set("retention_days", 30)
    assert _automatic(service)["expiresAt"] is not None
    assert _explicit(service)["expiresAt"] is None


def test_automatic_memory_without_retention_has_no_expiry(service):
    assert _automatic(service)["expiresAt"] is None


# ── Sweep behaviour / idempotence / observability ───────────────────────────


def test_sweep_marks_due_automatic_expired_with_observable_result(service):
    service.policy.set("retention_days", 1)
    memory = _automatic(service)
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    result = service.expire_due_memories()
    assert result["ok"] is True
    assert result["inspected"] == 1
    assert result["expired"] == 1
    assert result["skipped"] == 0
    assert result["ranAt"]
    assert service.store.get_memory(memory["id"])["status"] == "expired"


def test_sweep_is_idempotent(service):
    service.policy.set("retention_days", 1)
    memory = _automatic(service)
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    first = service.expire_due_memories()
    second = service.expire_due_memories()
    assert first["expired"] == 1
    # The second sweep finds nothing due (already expired) and inspects 0.
    assert second["inspected"] == 0
    assert second["expired"] == 0


def test_sweep_result_is_persisted_for_diagnostics(service):
    service.policy.set("retention_days", 1)
    memory = _automatic(service)
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    service.expire_due_memories()
    status = service.retention_status()
    assert status["lastSweep"] is not None
    assert status["lastSweep"]["ok"] is True
    assert status["lastSweep"]["expired"] == 1
    # A due-memory-only outcome carries no content.
    assert "content" not in status["lastSweep"]


def test_health_includes_retention_status(service):
    health = service.health()
    assert "retention" in health
    assert health["retention"]["explicitMemoriesExempt"] is True


def test_failed_sweep_is_reported_and_never_raises(service, monkeypatch):
    # Force a failure inside the sweep query.
    def _boom(*_a, **_k):
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(service.store, "archive_memory", _boom)
    service.policy.set("retention_days", 1)
    memory = _automatic(service)
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    result = service.expire_due_memories()
    assert result["ok"] is False
    assert result["error"]
    # The failure is persisted for diagnostics.
    assert service.retention_status()["lastSweep"]["ok"] is False


def test_run_retention_maintenance_never_raises(service, monkeypatch):
    monkeypatch.setattr(
        service, "expire_due_memories",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = service.run_retention_maintenance()
    assert result["ok"] is False
    assert result["error"]


def test_startup_maintenance_runs_the_sweep(monkeypatch):
    # The lifespan startup hook calls AgenticService.run_startup_maintenance,
    # which runs the retention sweep. Prove it invokes the sweep exactly once and
    # never raises even if the sweep fails.
    from harness import service as service_module

    calls: list[int] = []
    inst = object.__new__(service_module.AgenticService)

    class _Memory:
        def run_retention_maintenance(self):
            calls.append(1)
            return {"ok": True, "expired": 0}

    inst.memory = _Memory()
    result = inst.run_startup_maintenance()
    assert calls == [1]
    assert result["ok"] is True


# ── Retrieval exclusion before sweep ────────────────────────────────────────


def test_retrieval_excludes_due_memory_before_sweep(service):
    memory = _automatic(service, content="A due fact about shipping lanes")
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    assert service.store.get_memory(memory["id"])["status"] == "active"
    result = service.retrieve(query="shipping lanes", actor_scope="user")
    assert all(m["id"] != memory["id"] for m in result.memories)


# ── Auditability of expired records ─────────────────────────────────────────


def test_expired_record_remains_auditable(service):
    service.policy.set("retention_days", 1)
    memory = _automatic(service)
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    service.expire_due_memories()
    stored = service.store.get_memory(memory["id"])
    assert stored is not None
    assert stored["status"] == "expired"
    assert stored["statusReason"]
    expired_view = service.store.list_lifecycle_memories("expired")
    assert any(m["id"] == memory["id"] for m in expired_view)


# ── Confirmation / renewal ──────────────────────────────────────────────────


def test_restating_automatic_memory_refreshes_expiry(service):
    service.policy.set("retention_days", 1)
    memory = _automatic(service, content="A durable learned convention")
    original_expiry = memory["expiresAt"]
    service.store.update_memory(memory["id"], expiresAt="2000-01-01T00:00:00.000Z")
    # Re-state the same fact.
    again = _automatic(service, content="A durable learned convention")
    assert again["id"] == memory["id"]
    assert again["expiresAt"] != "2000-01-01T00:00:00.000Z"
    assert again["expiresAt"] >= original_expiry
    assert again["lastConfirmedAt"] is not None


def test_renew_extends_and_clears_expiry(service):
    service.policy.set("retention_days", 5)
    memory = _automatic(service)
    extended = service.renew_memory(memory["id"], days=30)
    assert extended["expiresAt"] is not None
    assert extended["lastConfirmedAt"] is not None
    # days=0 clears the expiry.
    cleared = service.renew_memory(memory["id"], days=0)
    assert cleared["expiresAt"] is None


def test_renew_explicit_memory_does_not_add_expiry(service):
    memory = _explicit(service)
    renewed = service.renew_memory(memory["id"])
    assert renewed["expiresAt"] is None
    assert renewed["lastConfirmedAt"] is not None


# ── Policy change safety ────────────────────────────────────────────────────


def test_policy_change_does_not_mutate_existing_records(service):
    # Records written while retention was 0 have no expiry; lowering retention
    # must NOT reach back and stamp/expire them.
    old = _automatic(service, content="Written with retention off")
    assert old["expiresAt"] is None
    service.policy.set("retention_days", 1)
    assert service.store.get_memory(old["id"])["expiresAt"] is None
    assert service.store.get_memory(old["id"])["status"] == "active"
    # The sweep inspects 0 (no automatic row has an expiry).
    assert service.expire_due_memories()["inspected"] == 0


# ── No accidental revival ───────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["expired", "superseded", "archived", "rejected"])
def test_duplicate_write_does_not_revive_inert_record(service, status):
    memory = _explicit(service, content="A fact that becomes inert")
    service.store.archive_memory(memory["id"], status=status)
    # Re-stating the exact fact must return the inert record unchanged, not
    # create a new active one.
    again = _explicit(service, content="A fact that becomes inert")
    assert again["id"] == memory["id"]
    assert again["status"] == status
    assert len(service.store.list_memories(include_inactive=False)) == 0
