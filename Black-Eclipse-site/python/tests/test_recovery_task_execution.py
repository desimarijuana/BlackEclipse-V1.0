"""Task-run recovery: the production executor drives runs through the bounded
recovery loop (classify → diagnose → bounded retry → record), and preserves the
pre-recovery behavior when the engine is absent or disabled.

Covers the spec scenarios: F (transient API error succeeds after a retry), G (an
auth failure is never retried indefinitely), I/M (a bounded loop returns a precise
partial result), plus the honesty invariant that a disabled engine changes nothing.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.persistence import AgentMemoryStore
from harness.recovery.execution import TaskRunFailed, run_with_recovery
from harness.recovery.service import RecoveryService
from harness.tasks.bootstrap import build_task_executor
from harness.tasks.context import build_task_context
from harness.tasks.manager import TaskManager
from harness.tasks.model import CreatePlanInput, CreateTaskInput
from harness.tasks.store import TaskStore


def _service(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def _run(coro):
    return asyncio.run(coro)


# ── run_with_recovery: unit behavior ─────────────────────────────────────────


def test_disabled_engine_attempts_once(tmp_path, monkeypatch):
    """No recovery service -> one attempt; a failure propagates unchanged."""
    monkeypatch.delenv("HARNESS_RECOVERY_ENABLED", raising=False)
    calls = {"n": 0}

    async def run_once(attempt, run_id):
        calls["n"] += 1
        raise TaskRunFailed("timeout", "timed out")

    with pytest.raises(TaskRunFailed):
        _run(run_with_recovery(None, run_once, base_run_id="r1"))
    assert calls["n"] == 1


def test_kill_switch_disables_recovery(tmp_path, monkeypatch):
    """`HARNESS_RECOVERY_ENABLED=0` restores the single-attempt behavior."""
    monkeypatch.setenv("HARNESS_RECOVERY_ENABLED", "0")
    svc = _service(tmp_path)
    calls = {"n": 0}

    async def run_once(attempt, run_id):
        calls["n"] += 1
        raise TaskRunFailed("timeout", "timed out")

    with pytest.raises(TaskRunFailed):
        _run(run_with_recovery(svc, run_once, base_run_id="r1"))
    assert calls["n"] == 1


def test_transient_failure_is_retried_then_succeeds(tmp_path):
    svc = _service(tmp_path)
    calls = {"n": 0, "ids": []}

    async def run_once(attempt, run_id):
        calls["n"] += 1
        calls["ids"].append(run_id)
        if calls["n"] < 3:
            raise TaskRunFailed("timeout", "timed out")
        return {"status": "completed", "runId": run_id}

    result = _run(run_with_recovery(
        svc, run_once, base_run_id="run-1", task_id="t1", max_attempts=4,
        sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is True
    assert result.attempts == 3
    assert result.incident_id
    assert svc.get_incident(result.incident_id)["status"] == "resolved"
    # Each attempt used a distinct run id (no completed run is reused).
    assert calls["ids"] == ["run-1", "run-1_r2", "run-1_r3"]


def test_auth_failure_is_not_retried(tmp_path):
    """A non-retryable class stops immediately (never an indefinite retry)."""
    svc = _service(tmp_path)
    calls = {"n": 0}

    async def run_once(attempt, run_id):
        calls["n"] += 1
        raise TaskRunFailed("auth_error", "unauthorized: invalid api key")

    result = _run(run_with_recovery(
        svc, run_once, base_run_id="r1", task_id="t1",
        sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert calls["n"] == 1
    assert result.stopped_reason in ("stop", "suspend")


def test_budget_exhaustion_returns_precise_partial(tmp_path):
    svc = _service(tmp_path)

    async def run_once(attempt, run_id):
        raise TaskRunFailed("timeout", "timed out")

    result = _run(run_with_recovery(
        svc, run_once, base_run_id="r1", task_id="t1", max_attempts=2,
        sleep=lambda s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert result.attempts == 2
    assert result.stopped_reason in ("budget_exhausted", "stop", "strategy_requires_caller")
    assert result.incident_id
    assert result.decision is not None


def test_verification_failure_is_a_failure(tmp_path):
    """A run that returns but fails verification is not a success."""
    async def run_once(attempt, run_id):
        return {"status": "completed", "runId": run_id}

    with pytest.raises(TaskRunFailed) as excinfo:
        _run(run_with_recovery(
            None, run_once, base_run_id="r1", verify=lambda _v: False,
        ))
    assert excinfo.value.code == "VERIFICATION_FAILED"


# ── Production executor integration ──────────────────────────────────────────


class _FakeService:
    """Stands in for AgenticService.run — the model/run backend only."""

    def __init__(self, recovery, *, fail_times: int, code: str = "timeout"):
        self.recovery = recovery
        self.artifacts = None
        self.store = None
        self._fail_times = fail_times
        self._code = code
        self.run_ids: list[str] = []

    async def run(self, request):
        self.run_ids.append(request.runId)
        assert request.input.context["source"] == "task-scheduler"
        if len(self.run_ids) <= self._fail_times:
            return {
                "status": "failed", "runId": request.runId,
                "error": {"code": self._code, "message": "upstream unavailable"},
            }
        return {"status": "completed", "runId": request.runId, "output": "done"}


@pytest.fixture()
def manager(tmp_path):
    return TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))


def _task(manager):
    plan = manager.create_plan(CreatePlanInput(name="p"))
    task = manager.create_task(CreateTaskInput(title="work", plan_id=plan.id))
    return task


def test_production_executor_recovers_a_transient_run_failure(tmp_path, manager):
    recovery = _service(tmp_path)
    service = _FakeService(recovery, fail_times=2)
    executor = build_task_executor(service, manager)
    task = _task(manager)

    context = build_task_context(manager, task)
    outcome = _run(executor(task, context, "taskrun_1"))

    assert outcome.status == "completed"
    assert len(service.run_ids) == 3
    assert outcome.metrics.get("recoveryIncidentId")
    assert outcome.metrics.get("recoveryAttempts") == 3
    incident = recovery.get_incident(outcome.metrics["recoveryIncidentId"])
    assert incident is not None and incident["status"] == "resolved"


def test_production_executor_does_not_retry_auth_failure(tmp_path, manager):
    recovery = _service(tmp_path)
    service = _FakeService(recovery, fail_times=99, code="auth_error")
    executor = build_task_executor(service, manager)
    task = _task(manager)

    context = build_task_context(manager, task)
    outcome = _run(executor(task, context, "taskrun_2"))

    assert outcome.status == "failed"
    assert outcome.error_class == "auth_error"
    assert len(service.run_ids) == 1


def test_production_executor_without_recovery_engine(tmp_path, manager):
    """No recovery service -> exactly the pre-recovery behavior: one run."""
    service = _FakeService(None, fail_times=1, code="provider_error")
    executor = build_task_executor(service, manager)
    task = _task(manager)

    context = build_task_context(manager, task)
    outcome = _run(executor(task, context, "taskrun_3"))

    assert outcome.status == "failed"
    assert len(service.run_ids) == 1
    assert outcome.error_class == "provider_error"
    assert outcome.metrics.get("recoveryIncidentId") is None


def test_production_executor_hands_repair_strategy_back_to_caller(tmp_path, manager):
    """A provider outage prefers caller-supplied substitution, so the bounded loop
    stops after one decision and reports the strategy — it never invents a repair.

    The scheduler's own retry policy still applies afterwards; the recovery engine
    only adds the classification, diagnosis and durable incident.
    """
    recovery = _service(tmp_path)
    service = _FakeService(recovery, fail_times=99, code="provider_error")
    executor = build_task_executor(service, manager)
    task = _task(manager)

    context = build_task_context(manager, task)
    outcome = _run(executor(task, context, "taskrun_4"))

    assert outcome.status == "failed"
    assert len(service.run_ids) == 1
    assert outcome.metrics.get("recoveryStoppedReason") == "strategy_requires_caller"
    assert outcome.metrics.get("recoveryIncidentId")
