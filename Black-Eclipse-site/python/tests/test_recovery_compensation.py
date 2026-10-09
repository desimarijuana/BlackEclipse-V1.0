"""Compensating actions — undo a side effect, bounded by the envelope."""

from __future__ import annotations

import asyncio

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.compensation import compensate_pending
from harness.recovery.envelope import ActionClass, AutonomyEnvelope
from harness.recovery.service import RecoveryService


def _service(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def _run(coro):
    return asyncio.run(coro)


def test_compensates_a_pending_operation_with_a_handler(tmp_path):
    svc = _service(tmp_path)
    svc.operations.begin("k1", "external_call", compensating_action="refund")
    seen: list[str] = []

    async def refund(op):
        seen.append(op["id"])

    result = _run(compensate_pending(svc, {"refund": refund}))
    assert result["compensated"]
    assert len(seen) == 1
    assert svc.operations.pending_compensations() == []


def test_skips_without_a_handler(tmp_path):
    svc = _service(tmp_path)
    svc.operations.begin("k2", "external_call", compensating_action="refund")
    result = _run(compensate_pending(svc, {}))
    assert result["compensated"] == []
    assert result["skipped"][0]["reason"] == "no handler"
    assert len(svc.operations.pending_compensations()) == 1


def test_failed_compensation_stays_pending(tmp_path):
    svc = _service(tmp_path)
    svc.operations.begin("k3", "external_call", compensating_action="refund")

    async def refund(_op):
        raise RuntimeError("refund API down")

    result = _run(compensate_pending(svc, {"refund": refund}))
    assert result["compensated"] == []
    assert len(svc.operations.pending_compensations()) == 1


def test_envelope_can_forbid_compensation(tmp_path):
    svc = _service(tmp_path)
    svc.operations.begin("k4", "external_call", compensating_action="refund")
    called = {"n": 0}

    async def refund(_op):
        called["n"] += 1

    envelope = AutonomyEnvelope(action_classes=frozenset())  # nothing allowed
    result = _run(compensate_pending(svc, {"refund": refund}, envelope=envelope))
    assert result["compensated"] == []
    assert called["n"] == 0
    assert result["skipped"][0]["reason"] == "outside envelope"


def test_compensation_is_idempotent_across_calls(tmp_path):
    svc = _service(tmp_path)
    svc.operations.begin("k5", "external_call", compensating_action="refund")
    calls = {"n": 0}

    async def refund(_op):
        calls["n"] += 1

    _run(compensate_pending(svc, {"refund": refund}))
    _run(compensate_pending(svc, {"refund": refund}))
    assert calls["n"] == 1  # a compensated operation is never compensated twice