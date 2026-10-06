"""Multi-step execution workflows, parallel groups, and retry policy.

`ExecutionWorkflow` runs a named sequence of `ExecutionStep`s, each of which is one
`ExecutionRequest`, and produces a machine-readable `ExecutionPlan` plus a step
tree of results. It supports:

  * sequential steps (each sees the previous step's result);
  * an explicitly-marked parallel group (run with the scheduler, bounded);
  * conditional steps (`run_if` on the prior result);
  * a per-step timeout and a workflow-wide deadline;
  * cancellation (a cancel event stops subsequent steps).

`RetryPolicy` is category-driven, exactly as the contract requires: a network
timeout may retry; a compiler error must not be blindly retried; a permission or
sandbox violation stops.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import ErrorClass, ExecutionRequest, ExecutionResult

# Failure classes a retry policy distinguishes.
RETRYABLE = frozenset({ErrorClass.TIMEOUT.value, ErrorClass.INFRASTRUCTURE_ERROR.value})
NEVER_RETRY = frozenset({ErrorClass.SECURITY_ERROR.value, ErrorClass.BUILD_ERROR.value, ErrorClass.TEST_ERROR.value})


@dataclass
class RetryPolicy:
    """How many times a step may retry, and for which failure classes."""

    max_attempts: int = 2
    retry_on: frozenset[str] = field(default_factory=lambda: RETRYABLE)
    backoff_s: float = 0.5

    def should_retry(self, error_class: str, attempt: int) -> bool:
        if attempt >= self.max_attempts:
            return False
        if error_class in NEVER_RETRY:
            return False
        return error_class in self.retry_on


@dataclass
class ExecutionStep:
    """One step of a plan. A step is either a single request or a parallel group."""

    name: str
    request: Optional[ExecutionRequest] = None
    parallel: list["ExecutionStep"] = field(default_factory=list)
    run_if: str = ""                     # a prior step name whose success gates this step
    retry: Optional[RetryPolicy] = None
    timeout_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "runIf": self.run_if,
            "parallel": [s.to_dict() for s in self.parallel],
            "timeoutMs": self.timeout_ms,
        }


@dataclass
class ExecutionPlan:
    """A machine-readable, observable plan."""

    name: str
    steps: list[ExecutionStep]
    max_total_time_s: int = 900

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "maxTotalTimeS": self.max_total_time_s,
        }


@dataclass
class WorkflowResult:
    """The result of a whole workflow: one entry per step, plus an overall status."""

    name: str
    status: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    stopped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "steps": self.steps,
            "durationMs": self.duration_ms, "stoppedReason": self.stopped_reason,
        }


class ExecutionWorkflow:
    """Run an `ExecutionPlan` through the orchestrator (sequential + parallel)."""

    def __init__(self, orchestrator: Any, *, scheduler: Optional[Any] = None) -> None:
        self._orchestrator = orchestrator
        self._scheduler = scheduler

    def run(
        self,
        plan: ExecutionPlan,
        *,
        actor: Any = None,
        emit: Optional[Callable[[str, dict[str, Any]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> WorkflowResult:
        started = time.monotonic()
        deadline = started + max(1, plan.max_total_time_s)
        results: dict[str, ExecutionResult] = {}
        step_rows: list[dict[str, Any]] = []
        status = "COMPLETED"
        stopped = ""

        for step in plan.steps:
            if cancel_event is not None and cancel_event.is_set():
                status = "CANCELLED"
                stopped = "cancelled"
                break
            if time.monotonic() > deadline:
                status = "TIMED_OUT"
                stopped = "workflow deadline exceeded"
                break
            if step.run_if and not results.get(step.run_if, None):
                step_rows.append({"name": step.name, "status": "SKIPPED", "reason": f"{step.run_if} did not pass"})
                continue
            if step.run_if and results.get(step.run_if) is not None and not results[step.run_if].ok:
                step_rows.append({"name": step.name, "status": "SKIPPED", "reason": f"{step.run_if} failed"})
                continue

            if step.parallel:
                row, parallel_results = self._run_parallel(step, actor=actor, emit=emit, cancel_event=cancel_event)
                step_rows.append(row)
                results.update(parallel_results)
                if row["status"] != "COMPLETED":
                    status = "FAILED"
                    stopped = f"parallel group {step.name} failed"
                    break
                continue

            result = self._run_one(step, actor=actor, emit=emit, cancel_event=cancel_event)
            results[step.name] = result
            step_rows.append(_step_row(step.name, result))
            if not result.ok:
                status = "FAILED"
                stopped = f"step {step.name} failed ({result.status})"
                break

        return WorkflowResult(
            name=plan.name, status=status, steps=step_rows,
            duration_ms=int((time.monotonic() - started) * 1000), stopped_reason=stopped,
        )

    def _run_one(self, step: ExecutionStep, *, actor, emit, cancel_event) -> ExecutionResult:
        policy = step.retry or RetryPolicy(max_attempts=1)
        attempt = 0
        result: Optional[ExecutionResult] = None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                break
            request = step.request
            if step.timeout_ms and request is not None:
                limits = request.limits()
                request.resource_limits = _with_timeout(limits, step.timeout_ms)
            result = self._orchestrator.run(request, actor=actor, cancel_event=cancel_event, emit=emit)
            if result.ok:
                return result
            attempt += 1
            if not policy.should_retry(result.error_class, attempt):
                return result
            time.sleep(policy.backoff_s * attempt)
        return result  # type: ignore[return-value]

    def _run_parallel(self, step: ExecutionStep, *, actor, emit, cancel_event) -> tuple[dict[str, Any], dict[str, ExecutionResult]]:
        if self._scheduler is None:
            # No scheduler: run sequentially, honestly (never a fake parallel).
            out: dict[str, ExecutionResult] = {}
            for child in step.parallel:
                out[child.name] = self._run_one(child, actor=actor, emit=emit, cancel_event=cancel_event)
            status = "COMPLETED" if all(r.ok for r in out.values()) else "FAILED"
            return {"name": step.name, "status": status, "parallel": [_step_row(n, r) for n, r in out.items()]}, out
        submission_ids: dict[str, str] = {}
        for child in step.parallel:
            submission_ids[child.name] = self._scheduler.submit(
                child.request, actor=actor, emit=emit, run_id=getattr(child.request, "run_id", ""),
            )
        out: dict[str, ExecutionResult] = {}
        for name, submission_id in submission_ids.items():
            result = self._scheduler.wait(submission_id, timeout=None)
            if result is not None and not isinstance(result, type) and hasattr(result, "ok"):
                out[name] = result
        status = "COMPLETED" if out and all(r.ok for r in out.values()) else "FAILED"
        return {"name": step.name, "status": status, "parallel": [_step_row(n, r) for n, r in out.items()]}, out


def _step_row(name: str, result: Any) -> dict[str, Any]:
    if result is None:
        return {"name": name, "status": "MISSING"}
    return {
        "name": name,
        "executionId": getattr(result, "execution_id", None),
        "status": getattr(result, "status", None),
        "exitCode": getattr(result, "exit_code", None),
        "durationMs": getattr(result, "duration_ms", 0),
        "errorClass": getattr(result, "error_class", None),
    }


def _with_timeout(limits: Any, timeout_ms: int) -> Any:
    from dataclasses import replace

    try:
        return replace(limits, timeout_ms=int(timeout_ms))
    except (TypeError, ValueError):
        return limits


__all__ = [
    "ExecutionPlan",
    "ExecutionStep",
    "ExecutionWorkflow",
    "NEVER_RETRY",
    "RETRYABLE",
    "RetryPolicy",
    "WorkflowResult",
]
