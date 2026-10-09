"""Recovery operation ledger — idempotency and compensation bookkeeping."""

from __future__ import annotations

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.operations import BEGIN, COMPENSATED, COMPLETED, FAILED, OperationLedger
from harness.recovery.store import RecoveryStore


def _ledger(tmp_path) -> OperationLedger:
    return OperationLedger(RecoveryStore(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))))


def test_begin_is_idempotent_on_the_key(tmp_path):
    ledger = _ledger(tmp_path)
    first = ledger.begin("k1", "fix_dependency", request={"strategy": "fix_dependency"})
    assert first["created"] is True
    assert first["status"] == BEGIN
    second = ledger.begin("k1", "fix_dependency")
    assert second["created"] is False
    assert second["id"] == first["id"]


def test_lifecycle_states(tmp_path):
    ledger = _ledger(tmp_path)
    op = ledger.begin("k2", "worktree_edit")
    assert ledger.complete(op["id"], result={"applied": True})["status"] == COMPLETED
    op2 = ledger.begin("k3", "worktree_edit")
    assert ledger.fail(op2["id"], result={"error": "boom"})["status"] == FAILED
    op3 = ledger.begin("k4", "worktree_edit")
    assert ledger.compensate(op3["id"])["status"] == COMPENSATED


def test_pending_compensations_lists_uncompensated(tmp_path):
    ledger = _ledger(tmp_path)
    begun = ledger.begin("k5", "external_call", compensating_action="refund")
    done = ledger.begin("k6", "external_call", compensating_action="refund")
    ledger.compensate(done["id"])
    plain = ledger.begin("k7", "external_call")  # no compensating action
    _, _, _ = begun, done, plain
    pending = ledger.pending_compensations()
    ids = {row["id"] for row in pending}
    assert begun["id"] in ids
    assert done["id"] not in ids
    assert plain["id"] not in ids


def test_list_by_incident(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.begin("k8", "worktree_edit", incident_id="inc_1")
    ledger.begin("k9", "worktree_edit", incident_id="inc_1")
    ledger.begin("k10", "worktree_edit", incident_id="inc_2")
    assert len(ledger.list_by_incident("inc_1")) == 2
    assert len(ledger.list_by_incident("inc_2")) == 1