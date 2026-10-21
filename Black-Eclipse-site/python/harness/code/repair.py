"""Plan → edit → check → (fail) → repair → check, bounded and honest.

EXTRACTED out of graph.py on purpose: graph.py is at its file-size ratchet
(README §3.7) and this is policy, not loop mechanics. `execute_run` CALLS
`run_verify_repair`; it does not gain a node. On exhaustion the loop STOPS and
reports the failing check with its output digest — it never keeps trying.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_MAX_REPAIR_ATTEMPTS = 2
DEFAULT_MAX_WALL_CLOCK_S = 900          # 15 min for the whole sub-flow
DEFAULT_MAX_COST_USD = 1.50             # per-run ceiling; None = no cost bound

#: The module's own outcome vocabulary.
RepairStatus = Literal[
    "passed", "unrepairable", "budget_exhausted", "refused", "no_checks", "not_run",
]

#: The vocabulary the ANSWER SEAM speaks (Round 3 / W1, ADR-H281). The seam must
#: be able to say, in one word, whether a repair happened and how it ended - and
#: `None` must never be ambiguous between "did not run" and "ran and passed".
RepairRunStatus = Literal[
    "REPAIR_NOT_RUN",
    "REPAIR_PASSED",
    "REPAIR_EXHAUSTED",
    "REPAIR_NOT_APPLICABLE",
    "REPAIR_REFUSED",
]

#: The mapping from the module's outcome to the answer seam's word.
_REPAIR_RUN_STATUS: dict[str, str] = {
    "passed": "REPAIR_PASSED",
    "unrepairable": "REPAIR_EXHAUSTED",
    "budget_exhausted": "REPAIR_EXHAUSTED",
    "refused": "REPAIR_REFUSED",
    "no_checks": "REPAIR_NOT_APPLICABLE",
    "not_run": "REPAIR_NOT_RUN",
}


def repair_run_status(status: Optional[str]) -> str:
    """The answer seam's word for a repair outcome.

    An unknown or missing status is `REPAIR_NOT_RUN` - never "passed". A repair
    that did not happen is not a repair that succeeded.
    """
    if not status:
        return "REPAIR_NOT_RUN"
    return _REPAIR_RUN_STATUS.get(str(status), "REPAIR_NOT_RUN")


@dataclass(frozen=True)
class RepairBudget:
    max_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    max_wall_clock_s: int = DEFAULT_MAX_WALL_CLOCK_S
    max_cost_usd: Optional[float] = DEFAULT_MAX_COST_USD
    #: How many times the checks may RUN in one run. `None` derives it from
    #: `max_attempts` (one run to find the failure, one per repair). Without
    #: this a run that writes on every turn would execute the test suite once
    #: per turn - bounded, but not obviously so.
    max_check_runs: Optional[int] = None

    @property
    def check_run_limit(self) -> int:
        """The hard cap on check executions for one run."""
        if self.max_check_runs is not None:
            return max(0, int(self.max_check_runs))
        return max(0, int(self.max_attempts)) + 1

    def exceeded(self, *, attempts: int, elapsed_s: float, cost_usd: float) -> Optional[str]:
        """The reason the budget is spent ("attempts"|"wall_clock"|"cost"), or None.

        Checked BEFORE each attempt, so the bound is never crossed.
        """
        if attempts >= max(0, int(self.max_attempts)):
            return "attempts"
        if elapsed_s >= max(0, int(self.max_wall_clock_s)):
            return "wall_clock"
        if self.max_cost_usd is not None and cost_usd >= float(self.max_cost_usd):
            return "cost"
        return None


class RepairAttempt(BaseModel):
    attempt: int
    failingClass: Optional[str] = None  # noqa: N815
    exitCode: Optional[int] = None  # noqa: N815
    outputDigest: Optional[str] = None  # noqa: N815
    commandExecutionId: Optional[str] = None  # noqa: N815
    editSummary: Optional[str] = None  # noqa: N815
    outcome: Literal["passed", "still_failing", "edit_refused", "check_unavailable"] = "still_failing"


class RepairOutcome(BaseModel):
    status: RepairStatus
    repairAttempts: int = 0  # noqa: N815
    maxAttempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS  # noqa: N815
    checks: list[str] = Field(default_factory=list)
    attempts: list[RepairAttempt] = Field(default_factory=list)
    failedClass: Optional[str] = None  # noqa: N815
    failedExitCode: Optional[int] = None  # noqa: N815
    failedOutputDigest: Optional[str] = None  # noqa: N815
    stoppedReason: Optional[str] = None  # noqa: N815
    note: Optional[str] = None


@dataclass
class CheckResult:
    """The seam return: an execution's outcome, or `available=False` (no sandbox)."""

    command_execution_id: str
    command_class: str
    exit_code: int
    duration_ms: int
    output: str = ""
    available: bool = True


# The two seams this module calls. Both already exist as Phase 1–3 surfaces.
CheckFn = Callable[[str], Awaitable[CheckResult]]
EditFn = Callable[[RepairAttempt, str], Awaitable[Optional[str]]]


async def run_verify_repair(
    *,
    run_id: str,
    binding: Any,
    checks: list[str],
    ledger: Any,
    run_check: CheckFn,
    make_edit: EditFn,
    budget: RepairBudget = RepairBudget(),
    emitter: Any = None,
    clock: Callable[[], float] = time.monotonic,
) -> RepairOutcome:
    """Run the checks; if one fails, edit and re-check, bounded by `budget`.

    NEVER loops past the budget; NEVER swallows a refusal as a pass.
    """
    checks = list(checks or [])
    outcome = RepairOutcome(
        status="no_checks", maxAttempts=max(0, int(budget.max_attempts)), checks=checks,
    )
    if not checks:
        return outcome

    started = clock()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        if emitter is None:
            return
        try:
            await emitter.emit(event, data)
        except Exception:  # noqa: BLE001 - an event must never break the loop
            pass

    attempt_number = 0
    # attempt_number counts REPAIRS, so the first check pass is attempt 0.
    while True:
        # 1. Check every class; record pass AND fail on the ledger.
        failing: Optional[CheckResult] = None
        for command_class in checks:
            result = await run_check(command_class)
            if not result.available:
                outcome.status = "refused"
                outcome.note = "SANDBOX_UNAVAILABLE"
                outcome.failedClass = command_class
                await _emit("code.repair.attempt", {
                    "attempt": attempt_number, "failingClass": command_class,
                    "outcome": "check_unavailable",
                })
                return outcome
            try:
                ledger.record(
                    command_execution_id=result.command_execution_id,
                    command_class=result.command_class,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    output=result.output,
                )
            except Exception:  # noqa: BLE001 - a record failure must not pass a check
                pass
            await _emit("code.verify.recorded", {
                "commandExecutionId": result.command_execution_id,
                "commandClass": result.command_class,
                "exitCode": result.exit_code,
                "durationMs": result.duration_ms,
            })
            if result.exit_code != 0:
                failing = result
                break

        # 2. All green.
        if failing is None:
            if attempt_number == 0 and not outcome.attempts:
                outcome.status = "passed"
            else:
                outcome.status = "passed"
            outcome.repairAttempts = attempt_number
            await _emit("code.repair.passed", {"repairAttempts": attempt_number})
            return outcome

        # 3. A check failed. Consult the budget BEFORE editing.
        outcome.failedClass = failing.command_class
        outcome.failedExitCode = failing.exit_code
        outcome.failedOutputDigest = _digest(failing.output)
        reason = budget.exceeded(
            attempts=attempt_number, elapsed_s=clock() - started, cost_usd=_cost(ledger, budget),
        )
        if reason is not None:
            outcome.status = "budget_exhausted" if reason in ("wall_clock", "cost") else "unrepairable"
            outcome.stoppedReason = reason
            outcome.repairAttempts = attempt_number
            await _emit("code.repair.exhausted", {
                "repairAttempts": attempt_number, "maxAttempts": outcome.maxAttempts,
                "stoppedReason": reason, "failedClass": failing.command_class,
                "failedOutputDigest": outcome.failedOutputDigest,
            })
            return outcome

        attempt_number += 1
        attempt = RepairAttempt(
            attempt=attempt_number, failingClass=failing.command_class,
            exitCode=failing.exit_code, outputDigest=_digest(failing.output),
            commandExecutionId=failing.command_execution_id,
        )
        edit_summary = await make_edit(attempt, "check failed")
        attempt.editSummary = edit_summary
        if not edit_summary:
            attempt.outcome = "edit_refused"
        outcome.attempts.append(attempt)
        outcome.repairAttempts = attempt_number
        await _emit("code.repair.attempt", {
            "attempt": attempt_number, "failingClass": failing.command_class,
            "exitCode": failing.exit_code, "outputDigest": attempt.outputDigest,
            "editSummary": edit_summary, "outcome": attempt.outcome,
        })
        # Loop again: re-run the SAME check set. The budget guard at the top of
        # the next failing branch bounds the loop.


def _digest(output: str) -> str:
    from .verify import output_digest  # noqa: PLC0415

    return output_digest(output)


def _cost(ledger: Any, budget: RepairBudget) -> float:
    """The run's recorded cost, when the ledger/caller exposes one; else 0.0.

    No fabricated cost: without a real signal the cost bound simply never fires.
    """
    value = getattr(ledger, "cost_usd", None)
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "CheckFn",
    "CheckResult",
    "DEFAULT_MAX_COST_USD",
    "DEFAULT_MAX_REPAIR_ATTEMPTS",
    "DEFAULT_MAX_WALL_CLOCK_S",
    "EditFn",
    "RepairAttempt",
    "RepairBudget",
    "RepairOutcome",
    "RepairRunStatus",
    "RepairStatus",
    "repair_run_status",
    "run_verify_repair",
]
