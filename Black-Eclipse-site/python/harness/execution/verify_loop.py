"""The autonomous verification loop — build → test → fix → rebuild → retest.

Bounded by `max_iterations` and `max_total_time_s`, exactly as the contract
requires: the loop can never spin forever. Each iteration produces evidence (the
`ExecutionResult` of the build and test run) so a final "all green" claim is only
ever made from an actual passing execution, never inferred from code that "looks
right".

The `fix` callback is the seam where the coding agent applies a change; it
receives the failing `ExecutionResult` and returns a short description of what it
changed (or None to stop). The loop is deliberately synchronous and deterministic
so it can be tested without a model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import ExecutionMode, ExecutionRequest, ExecutionResult

FixFn = Callable[[ExecutionResult, int], Optional[str]]
Emit = Callable[[str, dict[str, Any]], None]


@dataclass
class RepairOutcome:
    """The result of a bounded verification/repair loop."""

    status: str                       # passed | unrepairable | budget_exhausted | refused | no_checks
    iterations: int = 0
    max_iterations: int = 0
    build: Optional[dict[str, Any]] = None
    test: Optional[dict[str, Any]] = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "iterations": self.iterations,
            "maxIterations": self.max_iterations, "build": self.build, "test": self.test,
            "evidence": self.evidence, "stoppedReason": self.stopped_reason,
            "elapsedMs": self.elapsed_ms,
        }


def _noop_emit(event_type: str, data: dict[str, Any]) -> None:
    return None


class ExecutionVerifier:
    """Run build+test to green, letting the agent fix between attempts."""

    def __init__(self, orchestrator: Any, *, max_iterations: int = 5, max_total_time_s: int = 900) -> None:
        self._orchestrator = orchestrator
        self.max_iterations = max(1, int(max_iterations))
        self.max_total_time_s = max(1, int(max_total_time_s))

    def run(
        self,
        base_request: ExecutionRequest,
        *,
        actor: Any = None,
        fix: Optional[FixFn] = None,
        emit: Optional[Emit] = None,
        cancel_event: Optional[Any] = None,
    ) -> RepairOutcome:
        emit = emit or _noop_emit
        started = time.monotonic()
        evidence: list[dict[str, Any]] = []
        last_build: Optional[dict[str, Any]] = None
        last_test: Optional[dict[str, Any]] = None

        for iteration in range(1, self.max_iterations + 1):
            if cancel_event is not None and cancel_event.is_set():
                return RepairOutcome("refused", iteration - 1, self.max_iterations,
                                      last_build, last_test, evidence, "cancelled",
                                      int((time.monotonic() - started) * 1000))
            if time.monotonic() - started > self.max_total_time_s:
                return RepairOutcome("budget_exhausted", iteration - 1, self.max_iterations,
                                      last_build, last_test, evidence, "wall-clock budget exceeded",
                                      int((time.monotonic() - started) * 1000))
            emit("execution.verify.iteration", {"iteration": iteration, "max": self.max_iterations})
            request = _clone_for(base_request, ExecutionMode.BUILD_AND_TEST)
            result = self._orchestrator.run(request, actor=actor, cancel_event=cancel_event, emit=emit)
            evidence.append({"iteration": iteration, **result.to_dict()})
            last_build = result.build
            last_test = (result.metadata or {}).get("testSummary")

            if result.status == "COMPLETED":
                emit("execution.verify.passed", {"iteration": iteration,
                                                 "executionId": result.execution_id})
                return RepairOutcome("passed", iteration, self.max_iterations,
                                      last_build, last_test, evidence, "",
                                      int((time.monotonic() - started) * 1000))

            if result.error_class in ("SECURITY_ERROR", "INFRASTRUCTURE_ERROR"):
                # Never "fix" a security block or an infrastructure failure by editing code.
                return RepairOutcome("refused", iteration, self.max_iterations,
                                      last_build, last_test, evidence,
                                      f"{result.error_class}: {result.status}",
                                      int((time.monotonic() - started) * 1000))

            if fix is None:
                return RepairOutcome("unrepairable", iteration, self.max_iterations,
                                      last_build, last_test, evidence,
                                      "no fix step is available",
                                      int((time.monotonic() - started) * 1000))

            emit("execution.verify.fixing", {"iteration": iteration, "status": result.status})
            summary = fix(result, iteration)
            if not summary:
                return RepairOutcome("unrepairable", iteration, self.max_iterations,
                                      last_build, last_test, evidence,
                                      "the fix step made no change",
                                      int((time.monotonic() - started) * 1000))

        return RepairOutcome("budget_exhausted", self.max_iterations, self.max_iterations,
                              last_build, last_test, evidence, "iteration budget exhausted",
                              int((time.monotonic() - started) * 1000))


def _clone_for(request: ExecutionRequest, mode: ExecutionMode) -> ExecutionRequest:
    import copy

    clone = copy.copy(request)
    clone.mode = mode
    clone.metadata = dict(request.metadata or {})
    clone.metadata.pop("_adapter", None)
    clone.metadata.pop("_project", None)
    return clone


__all__ = ["ExecutionVerifier", "RepairOutcome"]
