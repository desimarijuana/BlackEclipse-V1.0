"""Bounded auto-reproduction — timeout-guarded, evidence-feeding."""

from __future__ import annotations

import asyncio

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.reproduction import ReproducerRegistry, reproduce
from harness.recovery.service import RecoveryService
from harness.recovery.taxonomy import FailureKind, normalize_failure


def _run(coro):
    return asyncio.run(coro)


def test_no_reproducer_is_not_attempted():
    result = _run(reproduce(ReproducerRegistry(), normalize_failure(code="TOOL_TIMEOUT", message="x")))
    assert result.attempted is False
    assert result.reproduced is False


def test_sync_reproducer_true_and_false():
    registry = ReproducerRegistry()
    registry.register(FailureKind.TIMEOUT, "re-run", lambda _f: True)
    assert _run(reproduce(registry, normalize_failure(code="TOOL_TIMEOUT", message="x"))).reproduced is True
    registry.register(FailureKind.TIMEOUT, "re-run", lambda _f: False)
    assert _run(reproduce(registry, normalize_failure(code="TOOL_TIMEOUT", message="x"))).reproduced is False


def test_async_reproducer_timeout_is_errored_not_fatal():
    registry = ReproducerRegistry()

    async def slow(_f):
        await asyncio.sleep(5)
        return True

    registry.register(FailureKind.TIMEOUT, "slow", slow)
    result = _run(reproduce(registry, normalize_failure(code="TOOL_TIMEOUT", message="x"), timeout_s=0.01))
    assert result.attempted is True
    assert result.reproduced is False
    assert result.errored is True


def test_raising_reproducer_is_errored():
    registry = ReproducerRegistry()

    def boom(_f):
        raise RuntimeError("cannot repro")

    registry.register(FailureKind.TIMEOUT, "boom", boom)
    result = _run(reproduce(registry, normalize_failure(code="TOOL_TIMEOUT", message="x")))
    assert result.errored is True


def test_reproduce_incident_makes_diagnosis_decisive(tmp_path):
    svc = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    recorded = svc.record_failure(code="TOOL_TIMEOUT", message="timed out", source="tool", task_id="t1")
    incident_id = recorded["incidentId"]
    # Before reproduction the leading hypothesis is undetermined for a bare timeout.
    assert svc.get_incident(incident_id)["diagnosis"]["decisive"] is False

    svc.register_reproducer(FailureKind.TIMEOUT, "re-run", lambda _f: True)
    result = _run(svc.reproduce_incident(incident_id))
    assert result["reproduction"]["reproduced"] is True
    assert result["diagnosis"]["decisive"] is True
    # The stored diagnosis is updated.
    assert svc.get_incident(incident_id)["diagnosis"]["decisive"] is True


def test_reproduce_incident_missing_is_none(tmp_path):
    svc = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    assert _run(svc.reproduce_incident("nope")) is None