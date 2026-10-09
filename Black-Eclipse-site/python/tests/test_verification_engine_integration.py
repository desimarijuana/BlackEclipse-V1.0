"""Verification-engine integration: the run's claim ledger sees real checks.

Two defects this locks down:

1. The verification-engine tools (`build_project` / `test_project` /
   `run_verification`) execute REAL build/test runs but did not record them in
   the run's `VerificationLedger`, so a truthful "the build succeeded / the tests
   passed" was rendered `[UNVERIFIED]` by `code/verify.py` (the ledger is
   normally fed only by `command_run`). `_record_engine_verification` closes
   that gap.

2. `graph_context._memory_context` hardcoded `budget_chars=4000`, bypassing the
   operator's `context_budget_chars` policy. It now omits the value so
   `EclipseMemoryService.retrieve` applies the policy.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.code.verify import VerificationLedger
from harness.execution.tools import _record_engine_verification
from harness.graph_context import _memory_context
from harness.tools import ToolContext


def _ctx(ledger=None) -> ToolContext:
    return ToolContext(run_id="run-1", log=lambda *_: None, code_ledger=ledger)


# ── ledger integration ──────────────────────────────────────────────────────


def test_engine_verification_supports_a_truthful_claim():
    ledger = VerificationLedger("run-1")
    _record_engine_verification(
        _ctx(ledger), command_class="unit_test", execution_id="exec-1",
        passed=True, output="42 passed", duration_ms=12,
    )
    # A truthful pass-claim is now SUPPORTED by the real engine run.
    assert ledger.unverified_claims("All tests pass.") == []
    assert [r.command_class for r in ledger.verified("unit_test")] == ["unit_test"]


def test_engine_verification_records_a_failure():
    ledger = VerificationLedger("run-1")
    _record_engine_verification(
        _ctx(ledger), command_class="build", execution_id="exec-2",
        passed=False, output="boom", duration_ms=3,
    )
    failed = ledger.failed("build")
    assert len(failed) == 1 and failed[0].exit_code == 1
    # The claim is NOT supported, and the failing record is named as evidence.
    unsupported = ledger.unverified_claims("The build succeeded.")
    assert len(unsupported) == 1
    assert unsupported[0].evidenceExecutionId == "exec-2"


def test_engine_verification_is_a_noop_without_a_ledger():
    # No ledger on the context: recording is best-effort, never a crash.
    _record_engine_verification(
        _ctx(None), command_class="unit_test", execution_id="exec-3", passed=True,
    )


def test_engine_verification_rejects_unknown_class_silently():
    ledger = VerificationLedger("run-1")
    # An unknown class is dropped (VerificationLedger raises); nothing persisted.
    _record_engine_verification(
        _ctx(ledger), command_class="not_a_class", execution_id="exec-4", passed=True,
    )
    assert ledger.records == []


# ── memory recall budget honors operator policy ─────────────────────────────


class _FakeEmitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    async def emit(self, event_type, data=None):  # noqa: ANN001, ANN201
        self.events.append((event_type, data))
        return {"type": event_type}


class _FakeMemory:
    """Records the kwargs `_memory_context` passes to `retrieve`."""

    def __init__(self) -> None:
        self.policy = {"memory_enabled": True, "context_budget_chars": 2500}
        self.calls: list[dict] = []

    def retrieve(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        result = SimpleNamespace(context="", memories=[], diagnostics={})
        return result


async def test_memory_context_defers_budget_to_policy():
    memory = _FakeMemory()
    request = SimpleNamespace(
        input=SimpleNamespace(query="Show me the price of AAPL", ticker=None),
        userId=None,
        runId="run-budget",
    )
    await _memory_context(request, memory, _FakeEmitter())
    assert len(memory.calls) == 1
    # The graph must NOT force a value: the service then applies
    # `context_budget_chars` (here 2500), so the operator's policy is effective.
    assert "budget_chars" not in memory.calls[0]
