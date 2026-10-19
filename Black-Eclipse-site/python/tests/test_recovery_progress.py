"""Round 4 (W10): stuck-loop control — no progress is a first-class blocker.

A repeated failed action never repeats unchanged (the hot path refuses to retry
the identical call again), a loop with no progress escalates with the ACTUAL
blocker, and the task scheduler stops spending retries on identical failures.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from types import SimpleNamespace
from typing import Any

import pytest

from harness.persistence import AgentMemoryStore
from harness.recovery import hotpath
from harness.recovery.progress import ProgressTracker, attempt_digest
from harness.tasks.manager import TaskManager
from harness.tasks.model import CreatePlanInput, CreateTaskInput, TaskStatus
from harness.tasks.scheduler import TaskRunOutcome, TaskScheduler
from harness.tasks.store import TaskStore


# ── ProgressTracker (pure) ────────────────────────────────────────────────────


def test_identical_repeats_are_counted_per_exact_attempt():
    tracker = ProgressTracker()
    tracker.note_failure(tool="web_extract", args={"url": "x"}, signature="sig1")
    assert tracker.identical_repeats(tool="web_extract", args={"url": "x"}, signature="sig1") == 1
    assert tracker.identical_repeats(tool="web_extract", args={"url": "y"}, signature="sig1") == 0
    assert tracker.identical_repeats(tool="web_extract", args={"url": "x"}, signature="sig2") == 0


def test_no_progress_needs_the_threshold_and_names_the_blocker():
    tracker = ProgressTracker(max_no_progress=3)
    tracker.note_failure(tool="a", args={}, signature="s1", blocker="timeout on route A")
    tracker.note_failure(tool="b", args={}, signature="s2", blocker="route B refused")
    assert tracker.stuck() is None
    tracker.note_failure(tool="c", args={}, signature="s3", blocker="route C refused")
    reason = tracker.stuck()
    assert reason and "no progress across 3 attempts" in reason
    assert "route C refused" in reason


def test_a_success_is_progress_and_resets_the_counter():
    tracker = ProgressTracker(max_no_progress=3)
    tracker.note_failure(tool="a", args={}, signature="s1")
    tracker.note_failure(tool="b", args={}, signature="s2")
    tracker.note_success()
    assert tracker.stuck() is None
    tracker.note_failure(tool="c", args={}, signature="s3")
    assert tracker.stuck() is None  # one failure after the success


def test_attempt_digest_is_stable_and_argument_sensitive():
    assert attempt_digest("t", {"a": 1, "b": 2}) == attempt_digest("t", {"b": 2, "a": 1})
    assert attempt_digest("t", {"a": 1}) != attempt_digest("t", {"a": 2})


# ── Hot path ──────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, ok: bool, text: str = "", code: str | None = None) -> None:
        self.ok = ok
        self.text = text
        self.data = None
        self.error = SimpleNamespace(code=code) if code else None
        self.tool_call_id = "c1"
        self.name = "t"
        self.duration_ms = 1
        self.truncated = False
        self.shown_chars = 0
        self.total_chars = 0


class _Registry:
    def __init__(self, results: list[_Result], permission: str = "read") -> None:
        self._results = list(results)
        self.permission = permission
        self.calls = 0

    async def execute(self, name, call_id, args, ctx, *, allowed=None, timeout_ms=None):
        self.calls += 1
        return self._results.pop(0)

    def get(self, name):
        return SimpleNamespace(permission=self.permission)


class _Service:
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision

    def record_failure(self, **kwargs):
        return {
            "incidentId": "rec_test",
            "decision": self.decision,
            "failure": {"kind": "network", "retryability": "retryable"},
        }

    def record_outcome(self, incident_id, *, outcome, detail=None):
        return None


def _install(monkeypatch: Any, service: Any) -> None:
    monkeypatch.setattr(hotpath, "get_recovery_service", lambda: service)
    monkeypatch.setattr(hotpath, "recovery_enabled", lambda: True)


def _call(registry: _Registry, ctx: Any, *, tool: str = "web_extract", args: Any = None) -> Any:
    return asyncio.run(hotpath.run_tool_with_recovery(
        registry, tool, "c1", args or {"url": "x"}, ctx, set(), 1000,
        SimpleNamespace(runId="run_1"),
    ))


_RETRY = {"action": "recover", "strategy": "retry", "reason": "transient", "backoffMs": 0}


def test_the_identical_failed_call_is_never_retried_again(monkeypatch) -> None:
    service = _Service(_RETRY)
    _install(monkeypatch, service)
    ctx = SimpleNamespace()

    first = _Registry([_Result(False, "timeout", "ETIMEDOUT"), _Result(False, "timeout", "ETIMEDOUT")])
    _call(first, ctx)
    assert first.calls == 2  # the first failure earned ONE retry

    second = _Registry([_Result(False, "timeout", "ETIMEDOUT"), _Result(True, "would-be-repeat")])
    result = _call(second, ctx)
    assert second.calls == 1  # the identical attempt is NOT retried again
    assert result.ok is False
    assert "Do NOT repeat" in result.text


def test_a_stuck_loop_reports_the_actual_blocker(monkeypatch) -> None:
    service = _Service({"action": "stop", "strategy": "stop_and_report", "reason": "no strategy"})
    _install(monkeypatch, service)
    ctx = SimpleNamespace()
    for index, tool in enumerate(("tool_a", "tool_b")):
        result = _call(_Registry([_Result(False, f"route {tool} refused", "TOOL_ERROR")]),
                       ctx, tool=tool, args={"i": index})
        assert "STUCK LOOP" not in result.text
    third = _call(_Registry([_Result(False, "route tool_c refused", "TOOL_ERROR")]),
                  ctx, tool="tool_c", args={"i": 2})
    assert "STUCK LOOP" in third.text
    assert "no progress across 3 attempts" in third.text
    assert "route tool_c refused" in third.text


def test_a_success_resets_the_stuck_loop(monkeypatch) -> None:
    service = _Service({"action": "stop", "strategy": "stop_and_report", "reason": "no strategy"})
    _install(monkeypatch, service)
    ctx = SimpleNamespace()
    for index, tool in enumerate(("tool_a", "tool_b")):
        _call(_Registry([_Result(False, "refused", "TOOL_ERROR")]), ctx, tool=tool, args={"i": index})
    _call(_Registry([_Result(True, "data")]), ctx, tool="tool_c", args={"i": 2})
    after = _call(_Registry([_Result(False, "refused", "TOOL_ERROR")]), ctx, tool="tool_d", args={"i": 3})
    assert "STUCK LOOP" not in after.text


# ── Task scheduler ────────────────────────────────────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + _dt.timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_the_scheduler_stops_retrying_identical_failures(tmp_path):
    manager = TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))

    async def executor(task, context, run_id):
        return TaskRunOutcome(status="failed", error="timeout",
                              error_class="TOOL_TIMEOUT", run_id=run_id)

    clock = Clock()
    scheduler = TaskScheduler(manager, executor=executor, clock=clock)
    plan = manager.create_plan(CreatePlanInput(name="stuck"))
    task = manager.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=5))
    manager.start_plan(plan.id)
    for _ in range(6):
        await scheduler.tick()
        await scheduler.wait_idle()
        clock.advance(600)

    live = manager.get_task(task.id)
    assert live.status == TaskStatus.FAILED
    # The budget was NOT spent on identical repeats: one retry, then the stop.
    assert live.retry_count == 1
    assert "no progress" in (live.error or "")
    assert "TOOL_TIMEOUT" in (live.error or "")
