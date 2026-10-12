"""Task-run recovery — drive a production run THROUGH the recovery executor.

The recovery engine already owns the pieces (`taxonomy` → `policy` → `controller`
→ `store` → `executor`): it normalizes a failure, diagnoses it, decides one
bounded action, records it durably and can run a bounded verify-then-retry loop
(`recover_operation`). What was missing was a *production caller*: the task
scheduler retried blindly on a fixed retryable-error list, and a failed run
produced only a `task.failed` event (captured after the fact) rather than being
actively recovered.

This module is that caller. It wraps the task executor's own `service.run`
call in the bounded recovery loop, so a transient run failure is classified,
diagnosed, retried with the controller's backoff, and recorded as a durable
incident before the scheduler ever sees it. It adds no second execution loop and
no second registry: the run itself is the caller's own callable, repair
strategies are handed back to the caller unless a handler is supplied, and
unattended repair stays gated by the operator's autonomy envelope (the executor
enforces that).

When the recovery engine is absent or disabled, behavior is exactly as before:
the run is attempted once and any failure propagates to the caller.

Spec mapping: autonomous execution loop §2 (RECOVER), failure classification and
recovery controller §6, verification engine §8 (success is verified, never
asserted), and the bounded-retry requirement (a retry always has a recorded
reason and backoff).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .config import recovery_enabled
from .executor import RecoveryRunResult, recover_operation

# A per-attempt run id is generated from the base id so a retried run never
# reuses a completed run's id.
_MAX_RUN_ID_ATTEMPTS = 5


class TaskRunFailed(Exception):
    """A production task run that did not complete.

    Carries the run's own error code/message so the recovery taxonomy can
    classify it, plus the raw result (when there was one) so the caller can still
    build an honest failure outcome and the scheduler's own retry policy applies.
    """

    def __init__(
        self, code: str, message: str = "", *, result: Any = None
    ) -> None:
        super().__init__(message or code or "task run failed")
        self.code = str(code or "TASK_RUN_FAILED")
        self.message = str(message or code or "task run failed")
        self.result = result


@dataclass(frozen=True)
class ClassifiedRunFailure:
    code: str
    message: str


def classify_run_exception(exc: BaseException) -> ClassifiedRunFailure:
    """Map a run exception onto the recovery taxonomy's `(code, message)` shape."""
    if isinstance(exc, TaskRunFailed):
        return ClassifiedRunFailure(exc.code, exc.message)
    return ClassifiedRunFailure(type(exc).__name__, str(exc))


@dataclass
class RunRecovery:
    """What the bounded recovery loop concluded for one task run."""

    ok: bool
    value: Any = None
    attempts: int = 0
    incident_id: Optional[str] = None
    stopped_reason: Optional[str] = None
    decision: Optional[dict[str, Any]] = None
    diagnosis: Optional[dict[str, Any]] = None
    failure: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "attempts": self.attempts,
            "incidentId": self.incident_id,
            "stoppedReason": self.stopped_reason,
            "decision": self.decision,
            "diagnosis": self.diagnosis,
        }


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def run_with_recovery(
    recovery_service: Any,
    run_once: Callable[[int, str], Awaitable[Any]],
    *,
    verify: Optional[Callable[[Any], Any]] = None,
    base_run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    subsystem: str = "tasks",
    source: str = "task-run",
    max_attempts: Optional[int] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    details: Optional[dict[str, Any]] = None,
) -> RunRecovery:
    """Run `run_once(attempt, run_id)` through the bounded recovery executor.

    `run_once` MUST raise `TaskRunFailed` when the run did not complete; the
    recovery loop then classifies it, diagnoses it, and (for a transient failure
    the controller marks retryable) retries it after the controller's backoff.
    `verify(value)` optionally re-checks a postcondition; a run that returns but
    fails verification is treated as a failure.

    A run that exhausts the budget, hits a non-retryable class, or whose chosen
    strategy needs a caller handler returns `ok=False` with the reason and the
    durable `incident_id`; the caller decides what happens next (the scheduler's
    own retry policy is unchanged). When the engine is absent or disabled,
    `run_once(1, base_run_id)` is called exactly once and any exception propagates.
    """
    if recovery_service is None or not recovery_enabled():
        value = await run_once(1, base_run_id or "")
        if verify is not None and not await _maybe_await(verify(value)):
            raise TaskRunFailed(
                "VERIFICATION_FAILED", "run completed but failed verification", result=value
            )
        return RunRecovery(ok=True, value=value, attempts=1)

    state: dict[str, Any] = {"attempt": 0}

    async def _attempt() -> Any:
        state["attempt"] += 1
        attempt = state["attempt"]
        run_id = _attempt_run_id(base_run_id, attempt)
        return await run_once(attempt, run_id)

    result: RecoveryRunResult = await recover_operation(
        recovery_service,
        _attempt,
        verify=verify,
        classifier=classify_run_exception,
        subsystem=subsystem,
        source=source,
        task_id=task_id,
        run_id=base_run_id,
        details=details,
        max_attempts=max_attempts,
        sleep=sleep,
    )
    return RunRecovery(
        ok=result.ok,
        value=result.value,
        attempts=result.attempts,
        incident_id=result.incident_id,
        stopped_reason=result.stopped_reason,
        decision=result.decision,
        diagnosis=result.diagnosis,
    )


def _attempt_run_id(base_run_id: Optional[str], attempt: int) -> str:
    """A distinct run id per attempt; the first attempt keeps the base id."""
    base = (base_run_id or "").strip()
    if not base or attempt <= 1:
        return base
    return f"{base}_r{min(attempt, _MAX_RUN_ID_ATTEMPTS)}"


__all__ = [
    "ClassifiedRunFailure",
    "RunRecovery",
    "TaskRunFailed",
    "classify_run_exception",
    "run_with_recovery",
]
