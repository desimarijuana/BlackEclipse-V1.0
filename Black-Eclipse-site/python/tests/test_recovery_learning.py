"""Incident -> skill candidate promotion via the existing learning store."""

from __future__ import annotations

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.learning import incident_to_candidate, promote_incidents
from harness.recovery.service import RecoveryService


def _service(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def _resolved_recurrent_incident(svc, task_id="t1"):
    svc.record_failure(code="TOOL_TIMEOUT", message="timed out", subsystem="tools", source="tool", task_id=task_id)
    svc.record_failure(code="TOOL_TIMEOUT", message="timed out", subsystem="tools", source="tool", task_id=task_id)
    incident = svc.list_incidents(task_id=task_id)[0]
    svc.store.record_attempt(incident["id"], attempt_no=1, action="recover", strategy="retry", outcome="succeeded")
    svc.store.set_status(incident["id"], "resolved")
    return svc.get_incident(incident["id"])


def test_open_incident_does_not_qualify(tmp_path):
    svc = _service(tmp_path)
    svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    incident = svc.list_incidents(task_id="t1")[0]
    assert incident_to_candidate(incident, svc.store.list_attempts(incident["id"])) is None


def test_single_occurrence_does_not_qualify(tmp_path):
    svc = _service(tmp_path)
    svc.record_failure(code="TOOL_TIMEOUT", message="x", source="tool", task_id="t1")
    incident = svc.list_incidents(task_id="t1")[0]
    svc.store.record_attempt(incident["id"], attempt_no=1, action="recover", strategy="retry", outcome="succeeded")
    svc.store.set_status(incident["id"], "resolved")
    incident = svc.get_incident(incident["id"])
    assert incident_to_candidate(incident, svc.store.list_attempts(incident["id"]), min_occurrences=2) is None


def test_recurrent_resolved_incident_qualifies(tmp_path):
    svc = _service(tmp_path)
    incident = _resolved_recurrent_incident(svc)
    draft = incident_to_candidate(incident, svc.store.list_attempts(incident["id"]))
    assert draft is not None
    assert draft["candidateType"] == "failure_recovery"
    assert draft["proposedProcedure"]
    assert draft["evidenceReferences"]


def test_promote_creates_then_deduplicates(tmp_path):
    svc = _service(tmp_path)
    incident = _resolved_recurrent_incident(svc)
    first = promote_incidents(svc, [incident])
    assert len(first["created"]) == 1
    second = promote_incidents(svc, [svc.get_incident(incident["id"])])
    assert second["created"] == []
    assert len(second["duplicates"]) == 1
    # The candidate is inert: it is 'detected', not an enabled skill.
    assert first["created"][0]["status"] == "detected"
