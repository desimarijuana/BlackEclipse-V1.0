"""R3-03 — bounded recovery in the run hot path.

`run_tool_with_recovery` wraps one tool call: a retryable failure of a READ-ONLY
tool is retried once inside the recovery budget; every other failure carries the
engine's decision back to the model as a next-step directive ("do NOT repeat the
same call"). It is fail-open — no engine means the original result is returned
unchanged — and it keeps its counters PER RUN, so a failure seen in a past
session cannot exhaust a fresh run's allowance.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from harness.recovery import hotpath
from harness.recovery.controller import RecoveryAction, RecoveryController
from harness.recovery.policy import RecoveryBudget
from harness.recovery.taxonomy import normalize_failure


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
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[tuple] = []

    def record_failure(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "incidentId": "rec_test",
            "decision": self.decision,
            "failure": {"kind": "network", "retryability": "retryable"},
        }

    def record_outcome(self, incident_id, *, outcome, detail=None):
        self.outcomes.append((incident_id, outcome, detail))


def _install(monkeypatch: Any, service: Any) -> None:
    monkeypatch.setattr(hotpath, "get_recovery_service", lambda: service)
    monkeypatch.setattr(hotpath, "recovery_enabled", lambda: True)


def _call(registry: _Registry, ctx: Any = None) -> Any:
    return asyncio.run(hotpath.run_tool_with_recovery(
        registry, "web_extract", "c1", {"url": "x"}, ctx or SimpleNamespace(),
        set(), 1000, SimpleNamespace(runId="run_1"),
    ))


_RETRY = {"action": "recover", "strategy": "retry", "reason": "transient", "backoffMs": 0}
_STOP = {"action": "stop", "strategy": "stop_and_report", "reason": "no permitted strategy"}


def test_a_successful_call_never_touches_recovery(monkeypatch) -> None:
    _install(monkeypatch, _Service(_RETRY))
    registry = _Registry([_Result(True, "data")])
    result = _call(registry)
    assert result.ok is True and result.text == "data"
    assert registry.calls == 1


def test_a_retryable_read_tool_retries_once_and_succeeds(monkeypatch) -> None:
    service = _Service(_RETRY)
    _install(monkeypatch, service)
    registry = _Registry([_Result(False, "timeout", "ETIMEDOUT"), _Result(True, "data")])
    result = _call(registry)
    assert result.ok is True
    assert registry.calls == 2
    assert len(service.calls) == 1
    assert service.outcomes and service.outcomes[0][1] == "succeeded"
    assert "a retry succeeded" in result.text


def test_an_effectful_tool_is_never_retried(monkeypatch) -> None:
    service = _Service(_RETRY)
    _install(monkeypatch, service)
    registry = _Registry(
        [_Result(False, "boom", "TOOL_ERROR"), _Result(True, "would-be-retry")],
        permission="write",
    )
    result = _call(registry)
    assert registry.calls == 1
    assert result.ok is False
    assert "Do NOT repeat" in result.text


def test_a_deterministic_failure_is_not_retried(monkeypatch) -> None:
    service = _Service(_STOP)
    _install(monkeypatch, service)
    registry = _Registry([_Result(False, "bad input", "INPUT_INVALID")])
    result = _call(registry)
    assert registry.calls == 1
    assert "stop retrying" in result.text


def test_no_recovery_engine_leaves_the_result_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(hotpath, "get_recovery_service", lambda: None)
    monkeypatch.setattr(hotpath, "recovery_enabled", lambda: True)
    registry = _Registry([_Result(False, "raw failure", "TOOL_ERROR")])
    result = _call(registry)
    assert registry.calls == 1
    assert result.text == "raw failure"


def test_disabled_recovery_leaves_the_result_unchanged(monkeypatch) -> None:
    _install(monkeypatch, _Service(_RETRY))
    monkeypatch.setattr(hotpath, "recovery_enabled", lambda: False)
    registry = _Registry([_Result(False, "raw failure", "TOOL_ERROR")])
    result = _call(registry)
    assert result.text == "raw failure"


def test_counters_are_run_scoped_and_recurrence_demotes_retry(monkeypatch) -> None:
    service = _Service(_RETRY)
    _install(monkeypatch, service)
    ctx = SimpleNamespace()
    # Two failures of the SAME signature inside one run: the first may retry,
    # the second is recurrent (attempts and signature attempts are per run).
    first = _Registry([_Result(False, "timeout", "ETIMEDOUT"), _Result(False, "timeout", "ETIMEDOUT")])
    _call(first, ctx=ctx)
    second = _Registry([_Result(False, "timeout", "ETIMEDOUT"), _Result(False, "timeout", "ETIMEDOUT")])
    _call(second, ctx=ctx)

    assert service.calls[0]["recovery_state"]["signature_attempts"] == 0
    state = service.calls[1]["recovery_state"]
    assert state["signature_attempts"] == 1
    assert state["recurrent"] is True
    assert state["attempts"] == 1  # one retry consumed
    # Persistence is untouched by the override: both incidents were recorded.
    assert len(service.calls) == 2


def test_the_controller_enforces_the_total_time_budget() -> None:
    controller = RecoveryController(budget=RecoveryBudget(max_total_ms=1000))
    failure = normalize_failure(
        code="ETIMEDOUT", message="timed out", subsystem="web_extract", source="hotpath"
    )
    decision = controller.decide(failure, elapsed_ms=1500)
    assert decision.action == RecoveryAction.STOP
    assert decision.exhausted is True
    assert "time" in decision.reason
