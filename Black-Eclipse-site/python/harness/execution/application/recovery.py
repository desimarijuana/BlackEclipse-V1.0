"""Bounded recovery — diagnose, choose one strategy, retry, re-check. Never a loop.

There is no `while true: retry()`. A recovery run is bounded by
`max_attempts` (configurable via `HARNESS_APP_RECOVERY_MAX_ATTEMPTS`, default 3),
records EVERY attempt, and stops the moment health passes or the budget is spent.
A `NONE`/irrecoverable diagnosis (a permission denial, a security block) is never
retried — the engine reports it honestly and stops.

The recovery strategies are data: `RETRY`, `RESTART`, `REINSTALL_DEPENDENCIES`,
`REBUILD`, `SELECT_ALTERNATIVE_PORT`, `RESTART_DEPENDENCY`, `RELOAD_ENVIRONMENT`,
`RECREATE_CONTAINER`. Which strategy fits is decided by the diagnostics engine, not
by free text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import RecoveryAttempt, RecoveryStrategy, RuntimeDiagnosis

DEFAULT_MAX_ATTEMPTS = 3


def recovery_budget() -> int:
    """The maximum recovery attempts, from the environment (bounded 1..10)."""
    try:
        value = int(os.environ.get("HARNESS_APP_RECOVERY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ATTEMPTS
    return max(1, min(value, 10))


def strategy_for(diagnosis: RuntimeDiagnosis, *, attempt: int = 0) -> RecoveryStrategy:
    """Pick the recovery strategy for a diagnosis.

    The FIRST suggested strategy is preferred; on a later attempt the next one is
    used so the engine does not repeat the same failing action. An irrecoverable
    diagnosis yields `NONE`.
    """
    if not diagnosis.recoverable or not diagnosis.suggested_actions:
        return RecoveryStrategy.NONE
    actions = diagnosis.suggested_actions
    return actions[min(attempt, len(actions) - 1)]


@dataclass
class RecoveryOutcome:
    """The result of a bounded recovery run."""

    recovered: bool = False
    attempts: int = 0
    strategy: RecoveryStrategy = RecoveryStrategy.NONE
    diagnosis: Optional[RuntimeDiagnosis] = None
    history: list[RecoveryAttempt] = field(default_factory=list)
    stopped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered, "attempts": self.attempts,
            "strategy": self.strategy.value,
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "history": [h.to_dict() for h in self.history],
            "stoppedReason": self.stopped_reason,
        }


class RecoveryEngine:
    """Run a bounded diagnose → strategy → action → re-check loop.

    The caller supplies a `diagnose` callable (returns a `RuntimeDiagnosis`) and an
    `act` callable (performs one strategy, returns success). The engine enforces
    the budget and records every attempt; it never acts on an irrecoverable
    diagnosis.
    """

    def __init__(self, *, max_attempts: Optional[int] = None) -> None:
        self.max_attempts = int(max_attempts or recovery_budget())

    def run(
        self,
        *,
        diagnose: Callable[[int, Optional[RecoveryStrategy]], RuntimeDiagnosis],
        act: Callable[[RecoveryStrategy, RuntimeDiagnosis], bool],
        verify: Callable[[], bool],
        on_attempt: Optional[Callable[[RecoveryAttempt], None]] = None,
        max_attempts: Optional[int] = None,
    ) -> RecoveryOutcome:
        budget = int(max_attempts or self.max_attempts)
        outcome = RecoveryOutcome()
        last_strategy = RecoveryStrategy.NONE
        for attempt in range(1, budget + 1):
            diagnosis = diagnose(attempt, last_strategy if attempt > 1 else None)
            outcome.diagnosis = diagnosis
            strategy = strategy_for(diagnosis, attempt=attempt - 1)
            last_strategy = strategy
            outcome.strategy = strategy
            if strategy is RecoveryStrategy.NONE:
                outcome.stopped_reason = (
                    "this failure can't be fixed automatically"
                    if not diagnosis.recoverable else "no recovery action applies"
                )
                return outcome
            try:
                success = bool(act(strategy, diagnosis))
            except Exception as exc:  # noqa: BLE001 - a failed action is a recorded attempt
                success = False
                detail = f"{type(exc).__name__}: {exc}"
            else:
                detail = "recovery action ran" if success else "recovery action did not succeed"
            record = RecoveryAttempt(attempt=attempt, strategy=strategy, diagnosis=diagnosis,
                                     success=success, detail=detail)
            outcome.history.append(record)
            outcome.attempts = attempt
            if on_attempt is not None:
                try:
                    on_attempt(record)
                except Exception:  # noqa: BLE001 - observability must not break recovery
                    pass
            # Verify after the action; a passing check ends the run.
            try:
                ok = bool(verify())
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                outcome.recovered = True
                return outcome
        outcome.stopped_reason = f"the recovery budget of {budget} attempt(s) was used up"
        return outcome


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "RecoveryEngine",
    "RecoveryOutcome",
    "recovery_budget",
    "strategy_for",
]
