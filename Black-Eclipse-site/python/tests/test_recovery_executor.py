"""Automatic strategy execution — bounded loop, real persistence, verify-gated."""

from __future__ import annotations

import asyncio

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.executor import recover_operation
from harness.recovery.service import RecoveryService


def _service(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def _run(coro):
    return asyncio.run(coro)


def test_success_on_first_attempt(tmp_path):
    svc = _service(tmp_path)

    async def op():
        return "ok"

    result = _run(recover_operation(svc, op, sleep=lambda s: asyncio.sleep(0)))
    assert result.ok is True
    assert result.value == "ok"
    assert result.attempts == 1
    assert result.incident_id is None  # no failure -> no incident


def test_retries_then_succeeds(tmp_path):
    svc = _service(tmp_path)
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timed out")
        return "ok"

    result = _run(recover_operation(
        svc, op, verify=lambda v: v == "ok", subsystem="tools", source="tool",
        task_id="t1", max_attempts=4, sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is True
    assert result.attempts == 3
    assert result.incident_id
    assert svc.get_incident(result.incident_id)["status"] == "resolved"


def test_budget_exhaustion_stops(tmp_path):
    svc = _service(tmp_path)

    async def op():
        raise TimeoutError("always")

    result = _run(recover_operation(
        svc, op, subsystem="tools", source="tool", task_id="t1",
        max_attempts=2, sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert result.stopped_reason in ("stop", "budget_exhausted")


def test_verification_failure_is_a_failure(tmp_path):
    svc = _service(tmp_path)

    async def op():
        return "wrong"

    result = _run(recover_operation(
        svc, op, verify=lambda v: v == "ok", subsystem="tools", source="tool",
        task_id="t1", max_attempts=1, sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert result.incident_id


def test_auth_failure_suspends_and_does_not_retry(tmp_path):
    svc = _service(tmp_path)
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        raise RuntimeError("401 invalid api key unauthorized")

    result = _run(recover_operation(
        svc, op, subsystem="provider", source="provider", task_id="t1",
        max_attempts=4, sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert result.decision["action"] == "suspend"
    assert calls["n"] == 1  # never retried an auth failure


def test_strategy_handler_is_executed_when_envelope_allows(tmp_path):
    svc = _service(tmp_path)
    calls = {"n": 0}
    handled = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("ModuleNotFoundError: no module named 'x'")
        return "ok"

    async def fix(decision):
        handled["n"] += 1

    from harness.recovery.envelope import ActionClass, AutonomyEnvelope

    envelope = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.FIX_DEPENDENCY}),
        require_reversible=False, risk_ceiling="high",
    )
    result = _run(recover_operation(
        svc, op, subsystem="execution", source="tool", task_id="t1",
        max_attempts=3, sleep=lambda s: asyncio.sleep(0),
        strategy_handlers={"fix_dependency": fix},
        envelope=envelope,
    ))
    assert result.ok is True
    assert handled["n"] == 1  # the repair strategy ran before the retry


def test_strategy_handler_blocked_outside_envelope(tmp_path):
    svc = _service(tmp_path)
    handled = {"n": 0}

    async def op():
        raise RuntimeError("ModuleNotFoundError: no module named 'x'")

    async def fix(decision):
        handled["n"] += 1

    # The default envelope does not enable fix_dependency.
    result = _run(recover_operation(
        svc, op, subsystem="execution", source="tool", task_id="t1",
        max_attempts=3, sleep=lambda s: asyncio.sleep(0),
        strategy_handlers={"fix_dependency": fix},
    ))
    assert result.ok is False
    assert result.stopped_reason == "outside_autonomy_envelope"
    assert handled["n"] == 0  # never ran unattended


def test_operator_approval_authorizes_a_one_off_action(tmp_path):
    svc = _service(tmp_path)

    async def op():
        raise RuntimeError("ModuleNotFoundError: no module named 'x'")

    handled = {"n": 0}

    async def fix(_decision):
        handled["n"] += 1

    # First run is denied by the envelope and hands back the incident id.
    first = _run(recover_operation(
        svc, op, subsystem="execution", source="tool", task_id="t1",
        max_attempts=1, sleep=lambda s: asyncio.sleep(0),
        strategy_handlers={"fix_dependency": fix},
    ))
    assert first.stopped_reason in ("outside_autonomy_envelope", "budget_exhausted")
    if first.stopped_reason == "outside_autonomy_envelope":
        svc.approve(first.incident_id, "fix_dependency", approved_by="alice")
        _run(recover_operation(
            svc, op, subsystem="execution", source="tool", task_id="t1",
            max_attempts=1, sleep=lambda s: asyncio.sleep(0),
            strategy_handlers={"fix_dependency": fix},
        ))
    assert handled["n"] == 1  # the approval let the handler run


def test_repair_lease_prevents_duplicate_repair(tmp_path):
    svc = _service(tmp_path)
    pre = svc.record_failure(
        code="RuntimeError", message="ModuleNotFoundError: no module named 'x'",
        subsystem="execution", source="tool", task_id="t1",
    )
    signature = svc.get_incident(pre["incidentId"])["signature"]
    assert svc.store.acquire_lease(signature, "other-worker", ttl_s=120) is True

    handled = {"n": 0}

    async def op():
        raise RuntimeError("ModuleNotFoundError: no module named 'x'")

    async def fix(_decision):
        handled["n"] += 1

    from harness.recovery.envelope import ActionClass, AutonomyEnvelope

    envelope = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.FIX_DEPENDENCY}),
        require_reversible=False, risk_ceiling="high",
    )
    result = _run(recover_operation(
        svc, op, subsystem="execution", source="tool", task_id="t1",
        max_attempts=2, sleep=lambda s: asyncio.sleep(0),
        strategy_handlers={"fix_dependency": fix}, envelope=envelope,
    ))
    assert result.stopped_reason == "repair_lease_held"
    assert handled["n"] == 0
