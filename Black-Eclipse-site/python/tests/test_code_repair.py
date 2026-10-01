"""Phase 4 — the bounded verify-and-repair loop (repair.py).

Proves the loop cannot cross its budget, never swallows a refusal as a pass, and
records BOTH the failed and the repaired execution for the same class.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.code.repair import CheckResult, RepairBudget, run_verify_repair
from harness.code.verify import VerificationLedger


class _Emitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))


def _run(coro):
    return asyncio.run(coro)


# ── happy path / repair ─────────────────────────────────────────────────────


def test_repairs_within_budget_records_both_executions():
    ledger = VerificationLedger("run_x")
    emitter = _Emitter()
    state = {"n": 0}

    async def check(command_class):
        state["n"] += 1
        # First run fails; second run passes.
        code = 1 if state["n"] == 1 else 0
        return CheckResult(
            command_execution_id=f"cmd_{state['n']}", command_class=command_class,
            exit_code=code, duration_ms=5, output=f"run {state['n']}",
        )

    async def make_edit(attempt, reason):
        return "fixed the import"

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit, emitter=emitter,
    ))
    assert outcome.status == "passed"
    assert outcome.repairAttempts == 1
    # Exactly TWO executions of that class were recorded (fail + pass).
    assert len(ledger.records) == 2
    assert [r.exit_code for r in ledger.records] == [1, 0]
    assert any(e[0] == "code.repair.passed" for e in emitter.events)


def test_all_green_first_time_passes_with_no_repair():
    ledger = VerificationLedger("run_x")

    async def check(command_class):
        return CheckResult(command_execution_id="c1", command_class=command_class, exit_code=0, duration_ms=1)

    async def make_edit(attempt, reason):
        return "should not be called"

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["typecheck", "unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit,
    ))
    assert outcome.status == "passed"
    assert outcome.repairAttempts == 0
    assert len(ledger.records) == 2


# ── exhausted ───────────────────────────────────────────────────────────────


def test_never_passes_stops_at_max_attempts():
    ledger = VerificationLedger("run_x")
    emitter = _Emitter()

    async def check(command_class):
        return CheckResult(command_execution_id="c", command_class=command_class, exit_code=1, duration_ms=1, output="still broken")

    async def make_edit(attempt, reason):
        return "another attempt"

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit, emitter=emitter,
        budget=RepairBudget(max_attempts=2),
    ))
    assert outcome.status in ("unrepairable", "budget_exhausted")
    assert outcome.stoppedReason == "attempts"
    assert outcome.failedClass == "unit_test"
    assert outcome.failedOutputDigest
    assert any(e[0] == "code.repair.exhausted" for e in emitter.events)


def test_wall_clock_budget_checked_before_edit():
    ledger = VerificationLedger("run_x")
    edits = {"n": 0}

    async def check(command_class):
        return CheckResult(command_execution_id="c", command_class=command_class, exit_code=1, duration_ms=1)

    async def make_edit(attempt, reason):
        edits["n"] += 1
        return "edit"

    # A zero-second budget means the FIRST failure is already over budget, so no
    # edit is ever attempted.
    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit,
        budget=RepairBudget(max_attempts=5, max_wall_clock_s=0),
    ))
    assert outcome.status == "budget_exhausted"
    assert outcome.stoppedReason == "wall_clock"
    assert edits["n"] == 0


# ── refusals ────────────────────────────────────────────────────────────────


def test_unavailable_check_is_refused_never_passed():
    ledger = VerificationLedger("run_x")

    async def check(command_class):
        return CheckResult(
            command_execution_id="", command_class=command_class, exit_code=-1,
            duration_ms=0, available=False,
        )

    async def make_edit(attempt, reason):
        return "nope"

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit,
    ))
    assert outcome.status == "refused"
    assert outcome.note == "SANDBOX_UNAVAILABLE"
    # A refused check is NOT recorded as a proof.
    assert ledger.records == []


def test_no_checks():
    ledger = VerificationLedger("run_x")

    async def check(command_class):
        raise AssertionError("should not run")

    async def make_edit(attempt, reason):
        return None

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=[], ledger=ledger,
        run_check=check, make_edit=make_edit,
    ))
    assert outcome.status == "no_checks"


def test_edit_refused_still_counts_against_attempts():
    ledger = VerificationLedger("run_x")

    async def check(command_class):
        return CheckResult(command_execution_id="c", command_class=command_class, exit_code=1, duration_ms=1)

    async def make_edit(attempt, reason):
        return None  # a no-op/refused edit

    outcome = _run(run_verify_repair(
        run_id="run_x", binding=None, checks=["unit_test"], ledger=ledger,
        run_check=check, make_edit=make_edit, budget=RepairBudget(max_attempts=1),
    ))
    assert outcome.repairAttempts == 1
    assert outcome.attempts[0].outcome == "edit_refused"
    assert outcome.status in ("unrepairable", "budget_exhausted")


# ── budget unit ─────────────────────────────────────────────────────────────


def test_budget_exceeded_matches_boundary():
    budget = RepairBudget(max_attempts=2, max_wall_clock_s=10, max_cost_usd=1.0)
    assert budget.exceeded(attempts=0, elapsed_s=0, cost_usd=0) is None
    assert budget.exceeded(attempts=2, elapsed_s=0, cost_usd=0) == "attempts"
    assert budget.exceeded(attempts=0, elapsed_s=10, cost_usd=0) == "wall_clock"
    assert budget.exceeded(attempts=0, elapsed_s=0, cost_usd=1.0) == "cost"
