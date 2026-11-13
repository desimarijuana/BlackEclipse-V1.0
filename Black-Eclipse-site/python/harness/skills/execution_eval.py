"""Behavioural skill evaluation — the execution tier (W5.1).

The static evaluator in ``skills/evaluation.py`` proves a skill's *shape*
(manifest, schema, permissions, tools). It does not prove it *behaves*. This
module adds the missing tier: run the skill on real cases through the existing
runtime and grade the trajectory with the existing grader engine.

Design rules:

* **No second executor.** The default invoker calls ``skills.runtime.execute_skill``
  in ``ExecutionMode="evaluation"``; the module itself is invoker-agnostic so a
  test (or an offline tier) can supply a deterministic fake.
* **A skill with no cases is ``needs_review``, never ``passed``.** Absence of
  evidence is not evidence.
* **Unmeasured is not a pass.** A grader that cannot measure contributes
  ``unmeasured``; a mandatory grader that is unmeasured fails the case.
* **Cheap and cacheable.** The caller supplies a fingerprint; an unchanged
  fingerprint is served from the stored evaluation instead of re-running.
* **Never enables anything.** This module only returns evidence. Promotion is a
  separate operator action.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .manifest import SkillManifest

# Case kinds that require a real execution. The deterministic kinds
# (`schema`, `input_validation`, `output_shape`, `output_validation`) stay in
# `evaluation._run_cases` and are never sent to a runner.
EXECUTION_KINDS = frozenset({
    "execution", "tool_trace", "artifact", "citation", "financial", "honesty",
})

# Default graders by skill category. A case may override with `graders`.
DEFAULT_GRADERS = {
    "finance": ["financial", "honesty"],
    "research": ["research", "citation"],
    "quality": ["tool", "honesty"],
    "system": ["tool", "exact"],
}


@dataclass(frozen=True)
class InvocationResult:
    """One skill invocation, normalized for grading.

    ``tool_calls`` is the structured trajectory (name/args/status), never prose.
    """

    ok: bool
    runId: str
    status: str
    output: str = ""
    toolCalls: tuple[dict[str, Any], ...] = ()
    error: Optional[str] = None


class SkillInvoker(Protocol):
    def invoke(
        self, manifest: SkillManifest, case: dict[str, Any], *, run_id: str,
    ) -> InvocationResult:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class ExecutionCaseResult:
    caseId: str
    passed: bool
    runId: str
    scores: dict[str, float] = field(default_factory=dict)
    failures: tuple[str, ...] = ()
    unmeasured: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.caseId, "passed": self.passed, "runId": self.runId,
            "scores": dict(self.scores), "failures": list(self.failures),
            "unmeasured": list(self.unmeasured),
        }


@dataclass(frozen=True)
class ExecutionEvalResult:
    ok: bool
    cases: int
    passed: int
    failed: int
    runIds: tuple[str, ...]
    graderScores: dict[str, float]
    reason: str
    fingerprint: str = ""
    results: tuple[ExecutionCaseResult, ...] = ()

    @property
    def status(self) -> str:
        if self.ok:
            return "passed"
        # No case ran (none attached, too few, or no runner): this is missing
        # evidence, not a behavioural failure. A real failed case sets `failed`.
        if self.failed == 0:
            return "needs_review"
        return "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "status": self.status,
            "cases": self.cases, "passed": self.passed, "failed": self.failed,
            "runIds": list(self.runIds), "graderScores": dict(self.graderScores),
            "reason": self.reason, "fingerprint": self.fingerprint,
            "results": [r.to_dict() for r in self.results],
        }


class _TaskView:
    """The minimal task shape the grader engine reads."""

    def __init__(self, case: dict[str, Any], manifest: SkillManifest) -> None:
        self.id = f"skill:{manifest.id}:{case.get('caseId', 'case')}"
        self.category = manifest.category
        expected = case.get("expected")
        self.expected_output = (
            expected.get("output") if isinstance(expected, dict) else expected
        )
        self.expected_tools = tuple(case.get("expectedTools") or ())
        self.required_tools = tuple(case.get("requiredTools") or ())
        self.forbidden_tools = tuple(case.get("forbiddenTools") or ())
        self.constraints = dict(case.get("constraints") or {})
        self.metadata = dict(case.get("metadata") or {})
        self.graders = list(case.get("graders") or ())


def _grade(
    manifest: SkillManifest, case: dict[str, Any], invocation: InvocationResult,
) -> tuple[bool, dict[str, float], tuple[str, ...], tuple[str, ...]]:
    """Grade one invocation. Returns (passed, scores, failures, unmeasured)."""
    from ..evaluation.graders import (
        GradeContext, build_grader, default_graders_for,
    )

    task = _TaskView(case, manifest)
    specs = case.get("graders")
    if not specs:
        names = default_graders_for(task) or DEFAULT_GRADERS.get(manifest.category, ["exact"])
        specs = [{"name": name} for name in names]

    ctx = GradeContext(
        task=task,
        trajectory=None,
        final_output=invocation.output or "",
        env_state=dict(case.get("envState") or {}),
        tool_calls=[dict(call) for call in invocation.toolCalls],
        outcome={"status": invocation.status, "error": invocation.error},
        config=dict(case.get("graderConfig") or {}),
    )

    scores: dict[str, float] = {}
    failures: list[str] = []
    unmeasured: list[str] = []
    measured = 0
    mandatory = {str(name) for name in (case.get("mandatoryGraders") or [])}
    for spec in specs:
        if isinstance(spec, str):
            spec = {"name": spec}
        name = str(spec.get("name") or "")
        if not name:
            continue
        try:
            grader = build_grader(name, spec.get("config"))
            result = grader.grade(ctx)
        except KeyError as exc:
            unmeasured.append(f"{name}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - a grader crash is unmeasured, not a pass
            unmeasured.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if result.unmeasured:
            unmeasured.append(f"{name}: {'; '.join(result.failures) or 'unmeasured'}")
            scores[name] = float("nan")
            continue
        measured += 1
        scores[name] = float(result.score)
        if not result.passed:
            failures.extend(f"{name}: {failure}" for failure in result.failures)

    missing_mandatory = [name for name in mandatory if name not in scores or scores.get(name) != scores.get(name)]
    if missing_mandatory:
        failures.append(f"mandatory grader unmeasured: {', '.join(sorted(missing_mandatory))}")

    if not invocation.ok:
        failures.append(invocation.error or f"execution status {invocation.status!r}")
    if measured == 0 and not failures:
        failures.append("no grader could measure the execution")
    if not invocation.ok:
        return False, scores, tuple(failures), tuple(unmeasured)
    return (not failures) and measured > 0, scores, tuple(failures), tuple(unmeasured)


def evaluate_skill_execution(
    manifest: SkillManifest,
    cases: list[dict[str, Any]],
    *,
    invoker: Optional[SkillInvoker],
    min_cases: int = 3,
    min_pass_rate: float = 0.8,
    fingerprint: str = "",
) -> ExecutionEvalResult:
    """Run the execution tier for one skill version.

    ``invoker=None`` is an honest ``needs_review``: a configured model/runtime is
    required to produce behavioural evidence, and no configured model must not
    be simulated into a pass.
    """
    execution_cases = [
        case for case in cases
        if str(case.get("kind") or "") in EXECUTION_KINDS
    ]
    if not execution_cases:
        return ExecutionEvalResult(
            ok=False, cases=0, passed=0, failed=0, runIds=(),
            graderScores={}, reason="no execution cases attached",
            fingerprint=fingerprint,
        )
    if len(execution_cases) < max(1, int(min_cases)):
        return ExecutionEvalResult(
            ok=False, cases=len(execution_cases), passed=0, failed=0, runIds=(),
            graderScores={},
            reason=f"needs at least {min_cases} execution cases; found {len(execution_cases)}",
            fingerprint=fingerprint,
        )
    if invoker is None:
        return ExecutionEvalResult(
            ok=False, cases=len(execution_cases), passed=0, failed=0, runIds=(),
            graderScores={}, reason="no execution runner configured",
            fingerprint=fingerprint,
        )

    results: list[ExecutionCaseResult] = []
    all_scores: dict[str, list[float]] = {}
    for index, case in enumerate(execution_cases):
        case_id = str(case.get("caseId") or f"case_{index + 1}")
        run_id = f"skileval_{manifest.id.replace('.', '_')}_{uuid.uuid4().hex[:12]}"
        try:
            invocation = invoker.invoke(manifest, case, run_id=run_id)
        except Exception as exc:  # noqa: BLE001 - an invocation crash is a failed case
            invocation = InvocationResult(
                ok=False, runId=run_id, status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        passed, scores, failures, unmeasured = _grade(manifest, case, invocation)
        for name, score in scores.items():
            if score == score:  # skip NaN
                all_scores.setdefault(name, []).append(score)
        results.append(ExecutionCaseResult(
            caseId=case_id, passed=passed, runId=invocation.runId or run_id,
            scores=scores, failures=failures, unmeasured=unmeasured,
        ))

    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    pass_rate = passed / len(results) if results else 0.0
    aggregate = {
        name: round(sum(values) / len(values), 4)
        for name, values in all_scores.items() if values
    }
    ok = pass_rate >= float(min_pass_rate)
    reason = (
        f"{passed}/{len(results)} execution cases passed "
        f"({pass_rate:.0%}; required {float(min_pass_rate):.0%})"
    )
    return ExecutionEvalResult(
        ok=ok, cases=len(results), passed=passed, failed=failed,
        runIds=tuple(result.runId for result in results),
        graderScores=aggregate, reason=reason,
        fingerprint=fingerprint, results=tuple(results),
    )


class RuntimeSkillInvoker:
    """The production invoker: the real skill runtime in evaluation mode.

    All dependencies are injected; nothing here constructs a model. The caller
    supplies the resolved ``model_settings`` and a run id factory.
    """

    def __init__(
        self,
        *,
        registry: Any,
        tool_registry: Any,
        data_bridge: Any,
        memory_store: Any,
        model_settings: Any,
        bus: Any = None,
        memory_service: Any = None,
        timeout_ms: int = 120_000,
    ) -> None:
        self.registry = registry
        self.tool_registry = tool_registry
        self.data_bridge = data_bridge
        self.memory_store = memory_store
        self.model_settings = model_settings
        self.bus = bus
        self.memory_service = memory_service
        self.timeout_ms = timeout_ms

    def _tool_calls(self, run_id: str) -> tuple[dict[str, Any], ...]:
        try:
            events = self.memory_store.list_events(run_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - trajectory is best-effort evidence
            return ()
        calls: list[dict[str, Any]] = []
        for event in events:
            kind = str(event.get("type") or "")
            if not kind.startswith("tool."):
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            name = data.get("toolName") or data.get("name")
            if not name:
                continue
            calls.append({
                "name": name,
                "args": data.get("args") or data.get("input") or {},
                "status": "completed" if kind == "tool.completed" else (
                    "failed" if kind == "tool.failed" else kind.split(".", 1)[1]
                ),
            })
        return tuple(calls)

    def invoke(
        self, manifest: SkillManifest, case: dict[str, Any], *, run_id: str,
    ) -> InvocationResult:
        from .runtime import SkillExecutionRequest, execute_skill  # noqa: PLC0415

        request = SkillExecutionRequest(
            skillId=manifest.id,
            version=manifest.version,
            input=dict(case.get("input") or {}),
            modelSettings=self.model_settings,
            executionMode="evaluation",
            runId=run_id,
            timeoutMs=self.timeout_ms,
        )
        coro = execute_skill(
            request, self.registry, self.tool_registry, self.data_bridge,
            self.memory_store, self.bus, memory_service=self.memory_service,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(coro)
        else:
            # The evaluator is normally called from a sync endpoint/boot hook,
            # but never assume: a caller inside an event loop gets a dedicated
            # thread+loop instead of `asyncio.run` raising.
            import concurrent.futures  # noqa: PLC0415

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(asyncio.run, coro).result()
        return InvocationResult(
            ok=result.status in ("completed", "ok", "passed", "succeeded", "success"),
            runId=result.runId or run_id,
            status=result.status,
            output=result.output or "",
            toolCalls=self._tool_calls(result.runId or run_id),
            error=(result.error or {}).get("message") if isinstance(result.error, dict) else None,
        )


__all__ = [
    "DEFAULT_GRADERS",
    "EXECUTION_KINDS",
    "ExecutionCaseResult",
    "ExecutionEvalResult",
    "InvocationResult",
    "RuntimeSkillInvoker",
    "SkillInvoker",
    "evaluate_skill_execution",
]
