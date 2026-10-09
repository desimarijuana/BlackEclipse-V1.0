"""Recovery persistence + service on eclipse-memory.db (a real temp database)."""

from __future__ import annotations

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.service import RecoveryService
from harness.recovery.store import FAILED, OPEN, RESOLVED


def _service(tmp_path):
    store = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    return RecoveryService(store), store


def test_records_and_upserts_by_signature(tmp_path):
    svc, _ = _service(tmp_path)
    first = svc.record_failure(code="TOOL_TIMEOUT", message="timed out", subsystem="tools", source="tool", task_id="t1")
    second = svc.record_failure(code="TOOL_TIMEOUT", message="timed out", subsystem="tools", source="tool", task_id="t1")
    assert first["incidentId"] == second["incidentId"]
    assert first["occurrenceCount"] == 1
    assert second["occurrenceCount"] == 2
    assert second["recurrent"] is True


def test_different_messages_are_different_incidents(tmp_path):
    svc, _ = _service(tmp_path)
    a = svc.record_failure(code="TOOL_TIMEOUT", message="alpha failed", source="tool", task_id="t1")
    b = svc.record_failure(code="TOOL_TIMEOUT", message="beta failed", source="tool", task_id="t1")
    assert a["incidentId"] != b["incidentId"]


def test_distinct_tasks_get_distinct_incidents(tmp_path):
    svc, _ = _service(tmp_path)
    a = svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    b = svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t2")
    assert a["incidentId"] != b["incidentId"]


def test_attempts_are_recorded_and_outcome_closes(tmp_path):
    svc, _ = _service(tmp_path)
    result = svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    incident_id = result["incidentId"]
    assert svc.get_incident(incident_id)["attempts"] == 1

    svc.record_outcome(incident_id, outcome="succeeded", detail={"note": "recovered"})
    incident = svc.get_incident(incident_id)
    assert incident["status"] == RESOLVED
    outcomes = [a["outcome"] for a in svc.incident_attempts(incident_id)]
    assert outcomes == ["planned", "succeeded"]


def test_exhausted_stop_marks_incident_failed(tmp_path):
    from harness.recovery.controller import RecoveryController
    from harness.recovery.policy import RecoveryBudget

    store = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    svc = RecoveryService(store, controller=RecoveryController(budget=RecoveryBudget(max_attempts=0)))
    result = svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    assert result["decision"]["action"] == "stop"
    assert svc.get_incident(result["incidentId"])["status"] == FAILED


def test_summary_and_health(tmp_path):
    svc, _ = _service(tmp_path)
    svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    svc.record_failure(code="authentication_error", message="y", source="provider", task_id="t1")
    summary = svc.summary()
    assert summary["incidents"] == 2
    assert summary["attempts"] >= 2
    assert svc.health()["status"] == "ok"


def test_incidents_never_touch_agent_memory_db(tmp_path):
    # The recovery store must ride eclipse-memory.db, never agent-memory.db.
    store = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    svc = RecoveryService(store)
    svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    tables = {
        row["name"]
        for row in store._db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "RecoveryIncident" in tables
    assert "RecoveryAttempt" in tables


def test_open_status_default(tmp_path):
    svc, _ = _service(tmp_path)
    r = svc.record_failure(code="TOOL_ERROR", message="boom", source="tool", task_id="t1")
    assert svc.get_incident(r["incidentId"])["status"] == OPEN


def test_envelope_persists_across_service_instances(tmp_path):
    svc, store = _service(tmp_path)
    from harness.recovery.envelope import AutonomyEnvelope, ActionClass

    svc.set_envelope(AutonomyEnvelope(action_classes=frozenset({ActionClass.FIX_DEPENDENCY}), risk_ceiling="medium"))
    # A fresh service over the same db loads the durable envelope.
    from harness.recovery.service import RecoveryService

    reopened = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    assert reopened.envelope.risk_ceiling == "medium"
    assert ActionClass.FIX_DEPENDENCY in reopened.envelope.action_classes


def test_repair_lease_is_exclusive_and_reclaims_on_expiry(tmp_path):
    svc, _ = _service(tmp_path)
    store = svc.store
    assert store.acquire_lease("sig1", "holderA", ttl_s=120) is True
    assert store.acquire_lease("sig1", "holderB", ttl_s=120) is False  # held
    store.release_lease("sig1", "holderA")
    assert store.acquire_lease("sig1", "holderB", ttl_s=120) is True
    # An already-expired lease is reclaimable.
    assert store.acquire_lease("sig2", "holderA", ttl_s=0) is True
    assert store.acquire_lease("sig2", "holderB", ttl_s=120) is True


def test_approvals_round_trip(tmp_path):
    svc, _ = _service(tmp_path)
    r = svc.record_failure(code="TOOL_ERROR", message="x", source="tool", task_id="t1")
    incident_id = r["incidentId"]
    assert svc.has_approval(incident_id, "substitute_provider") is False
    svc.approve(incident_id, "substitute_provider", approved_by="alice")
    assert svc.has_approval(incident_id, "substitute_provider") is True
    assert svc.approvals(incident_id)[0]["approvedBy"] == "alice"
    # Approving a missing incident is refused.
    assert svc.approve("nope", "retry") is None
