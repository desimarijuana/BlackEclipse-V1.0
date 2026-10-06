"""The execution orchestrator — the one lifecycle every execution follows.

It owns the sequence the capability contract names: validate → resolve project →
detect language → resolve runtime → create context → prepare → run/build/test →
collect diagnostics/artifacts/metrics → cleanup → store result. It never
implements a language itself: it asks the runtime registry for an adapter and runs
the adapter's argv through the ONE sandbox primitive (`code/sandbox.py`).

Cleanup is guaranteed by a `finally` that always removes the staged working
directory and always forces the state machine to a terminal state, whatever
happened (crash, timeout, cancellation, sandbox failure, build failure). There is
no path that leaves a staged file behind or a state machine mid-flight.

The orchestrator is synchronous (run it in a worker thread via
`asyncio.to_thread`); it holds no asyncio primitives so a test can drive it
directly. `cancel_event` is a `threading.Event` the sandbox honours.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..code import sandbox
from ..code.policy import WorkspaceBinding
from .artifacts import ArtifactManager
from .build import BuildEngine, DependencyManager
from .diagnostics import DiagnosticEngine
from .models import (
    ErrorClass,
    ExecutionContext,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    NetworkPolicy,
    ResourceUsage,
    new_execution_id,
)
from .policy import ExecutionPolicyEngine
from .projects import ProjectDetector
from .state import ExecutionState, StateMachine
from .testing import TestEngine

Emit = Callable[[str, dict[str, Any]], None]


def _noop_emit(event_type: str, data: dict[str, Any]) -> None:
    return None


class ExecutionOrchestrator:
    """Run one `ExecutionRequest` end-to-end through the sandbox."""

    def __init__(
        self,
        registry: Any,
        *,
        policy_engine: Optional[ExecutionPolicyEngine] = None,
        diagnostics: Optional[DiagnosticEngine] = None,
        build_engine: Optional[BuildEngine] = None,
        test_engine: Optional[TestEngine] = None,
        detector: Optional[ProjectDetector] = None,
        dependency_manager: Optional[DependencyManager] = None,
        artifact_factory: Optional[Callable[[Path, str], ArtifactManager]] = None,
        scratch_root: Optional[Path] = None,
    ) -> None:
        self.registry = registry
        self.policy = policy_engine or ExecutionPolicyEngine()
        self.sandbox = sandbox
        self.diagnostics = diagnostics or DiagnosticEngine()
        self.detector = detector or ProjectDetector()
        self.build_engine = build_engine or BuildEngine(self.diagnostics)
        self.test_engine = test_engine or TestEngine(self.diagnostics)
        self.dependencies = dependency_manager or DependencyManager()
        self._artifact_factory = artifact_factory or (
            lambda root, execution_id: ArtifactManager(root=root, execution_id=execution_id)
        )
        self._scratch_root = scratch_root

    # ── public API ───────────────────────────────────────────────────────────

    def run(
        self,
        request: ExecutionRequest,
        *,
        actor: Any = None,
        cancel_event: Optional[threading.Event] = None,
        emit: Optional[Emit] = None,
        execution_enabled: bool = True,
    ) -> ExecutionResult:
        emit = emit or _noop_emit
        execution_id = new_execution_id()
        machine = StateMachine(ExecutionState.QUEUED)
        started = time.time()
        workdir: Optional[Path] = None
        result: Optional[ExecutionResult] = None
        binding: Optional[WorkspaceBinding] = request.workspace
        try:
            machine.to(ExecutionState.VALIDATING)
            result, context = self._validate(request, actor, execution_id, binding, execution_enabled, emit)
            if result is not None:
                return self._finish(result, machine, emit)
            assert context is not None
            workdir = self._make_workdir(execution_id)
            machine.to(ExecutionState.PREPARING)
            return self._finish(
                self._execute(request, context, machine, workdir, cancel_event, emit, started),
                machine, emit,
            )
        except BaseException as exc:  # noqa: BLE001 - any failure lands on a terminal state
            result = result or self._infrastructure_failure(request, execution_id, started, exc)
            return self._finish(result, machine, emit)
        finally:
            if workdir is not None:
                self._cleanup(workdir)

    # ── stages ──────────────────────────────────────────────────────────────

    def _validate(
        self,
        request: ExecutionRequest,
        actor: Any,
        execution_id: str,
        binding: Optional[WorkspaceBinding],
        execution_enabled: bool,
        emit: Emit,
    ) -> tuple[Optional[ExecutionResult], Optional[ExecutionContext]]:
        """Return `(early_result, context)`. `early_result` short-circuits a refusal."""
        root = self._workspace_root(binding)
        if root is None:
            return (
                self._refusal(request, execution_id, "WORKSPACE_UNBOUND", ErrorClass.SECURITY_ERROR, emit),
                None,
            )
        # Defense in depth: an entrypoint must resolve INSIDE the workspace. The
        # runtime adapters join it onto the root, so a `..`/absolute/symlink escape
        # is refused here before any adapter sees it.
        if request.entrypoint:
            from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

            try:
                resolve_within(root, request.entrypoint)
            except PolicyDenial as denial:
                emit("execution.blocked", {"executionId": execution_id, "code": denial.code})
                return (
                    self._refusal(request, execution_id, denial.code, ErrorClass.SECURITY_ERROR, emit,
                                  reason=denial.reason),
                    None,
                )
        decision = self.policy.evaluate_request(
            actor, binding, request, execution_enabled=execution_enabled,
        )
        if not decision.allowed:
            emit("execution.blocked", {"executionId": execution_id, "code": decision.code, "risk": decision.risk.value})
            error_class = (
                ErrorClass(decision.error_class)
                if decision.error_class and decision.error_class != ErrorClass.NONE.value
                else ErrorClass.SECURITY_ERROR
            )
            return (
                self._refusal(request, execution_id, decision.code, error_class, emit, risk=decision.risk.value),
                None,
            )
        project = self.detector.detect(root)
        language = self.registry.resolve_language(
            explicit=request.language, entrypoint=request.entrypoint, code=request.code,
            project=project, runtime=request.runtime,
        )
        adapter = self.registry.get(language)
        if adapter is None:
            emit("execution.blocked", {"executionId": execution_id, "code": "UNKNOWN_LANGUAGE"})
            return self._refusal(request, execution_id, "UNKNOWN_LANGUAGE", ErrorClass.RUNTIME_ERROR, emit), None
        runtime_name = adapter.resolve(project) or adapter.name
        context = ExecutionContext(
            execution_id=execution_id,
            language=language,
            runtime=runtime_name,
            binding=binding,  # type: ignore[arg-type]
            cwd=str(root),
            mode=request.mode,
            environment={k: v for k, v in (request.environment or {}).items()},
            network_policy=decision.network_policy,
            filesystem_policy=decision.filesystem_policy,
            limits=request.limits(),
            created_at=time.time(),
            run_id=request.run_id,
            agent_id=request.agent_id,
            workspace_id=getattr(binding, "id", None),
            project_id=request.project_id,
            secrets_policy=("injected" if decision.secrets else "none"),
            reproducible=self._reproducible(root, project, runtime_name, request, decision),
        )
        request.metadata["_adapter"] = adapter
        request.metadata["_project"] = project
        request.metadata["_root"] = str(root)
        request.metadata["_decision"] = decision.to_dict()
        request.metadata["_risk"] = decision.risk.value
        return None, context

    def _execute(
        self,
        request: ExecutionRequest,
        context: ExecutionContext,
        machine: StateMachine,
        workdir: Path,
        cancel_event: Optional[threading.Event],
        emit: Emit,
        started: float,
    ) -> ExecutionResult:
        adapter = request.metadata["_adapter"]
        project = request.metadata["_project"]
        root = Path(request.metadata["_root"])
        emit("execution.started", {
            "executionId": context.execution_id, "language": context.language,
            "runtime": context.runtime, "mode": context.mode.value,
        })
        if adapter.available() is False:
            machine.to(ExecutionState.FAILED)
            return self._refusal(
                request, context.execution_id, "SANDBOX_UNAVAILABLE", ErrorClass.INFRASTRUCTURE_ERROR, emit,
                context=context, reason=f"{context.language} isn't available on this computer.",
            )
        artifact_manager = self._artifact_factory(root, context.execution_id)
        baseline = artifact_manager.snapshot()
        machine.to(ExecutionState.STARTING)
        machine.to(ExecutionState.RUNNING)

        mode = context.mode
        build_result: Optional[dict[str, Any]] = None
        test_result = None
        run_raw = None
        run_prepared = None

        if mode in (ExecutionMode.BUILD, ExecutionMode.BUILD_AND_TEST):
            build = self.build_engine.run(
                adapter, root, project, workdir, language=context.language,
                limits=context.limits, cancel_event=cancel_event,
            )
            build_result = build.to_dict()
            emit("execution.build", {"executionId": context.execution_id, "success": build.success,
                                     "exitCode": build.exit_code, "errors": len(build.errors)})
            if not build.success and not build.skipped:
                machine.to(ExecutionState.BUILD_ERROR)
                return self._from_build(request, context, build, artifact_manager, baseline, started, emit)

        if mode in (ExecutionMode.TEST, ExecutionMode.BUILD_AND_TEST):
            test_result = self.test_engine.run(
                adapter, root, project, workdir,
                test_policy=request.test_policy, language=context.language,
                limits=context.limits, cancel_event=cancel_event,
            )
            emit("execution.test", {"executionId": context.execution_id, "success": test_result.success,
                                    "passed": test_result.passed, "failed": test_result.failed})
            if not test_result.success:
                machine.to(ExecutionState.TEST_ERROR)
                return self._from_test(request, context, test_result, build_result, artifact_manager, baseline, started, emit)

        if mode in (ExecutionMode.RUN, ExecutionMode.WORKFLOW):
            try:
                run_prepared = adapter.prepare_run(request, root, workdir)
            except Exception as exc:  # noqa: BLE001 - adapter refusal is a structured failure
                machine.to(ExecutionState.FAILED)
                return self._refusal(
                    request, context.execution_id, getattr(exc, "code", "RUNTIME_ERROR"),
                    ErrorClass.RUNTIME_ERROR, emit, context=context, reason=str(exc),
                )
            run_raw = self._run_prepared(run_prepared, context, cancel_event, network=context.network_policy != NetworkPolicy.NONE)
            if run_raw.launch_error:
                machine.to(ExecutionState.RUNTIME_ERROR)
                return self._from_raw_failure(request, context, run_raw, artifact_manager, baseline, started, emit)

        machine.to(self._terminal_state(run_raw, build_result, test_result))
        return self._success_result(
            request, context, run_raw, run_prepared, build_result, test_result,
            artifact_manager, baseline, started, emit,
        )

    # ── sandbox invocation ────────────────────────────────────────────────────

    def _run_prepared(self, prepared: Any, context: ExecutionContext, cancel_event: Optional[threading.Event], *, network: bool) -> Any:
        env = sandbox.build_env({**prepared.env, **context.environment})
        from .models import resource_run_kwargs  # noqa: PLC0415

        spec = sandbox.RunSpec(
            argv=list(prepared.argv), cwd=Path(prepared.cwd), env=env,
            timeout_s=max(1, int(context.limits.timeout_ms // 1000)),
            output_cap_bytes=context.limits.max_stdout_bytes,
            network=network,
            **resource_run_kwargs(context.limits),
        )
        return sandbox.run(spec, cancel_event=cancel_event)

    # ── result builders ────────────────────────────────────────────────────────

    def _success_result(
        self, request, context, run_raw, run_prepared, build_result, test_result,
        artifact_manager, baseline, started, emit,
    ) -> ExecutionResult:
        artifacts, truncated = artifact_manager.collect(baseline=baseline)
        diagnostics = self.diagnostics.normalize(
            (run_raw.output if run_raw else ""), language=context.language, source="run",
        ) if (run_raw and run_raw.exit_code not in (0, None)) else []
        tests = _tests_to_results(test_result)
        usage = _usage_from(run_raw, context)
        status = self._terminal_state(run_raw, build_result, test_result).value
        result = ExecutionResult(
            execution_id=context.execution_id,
            status=status,
            exit_code=(run_raw.exit_code if run_raw else (build_result or {}).get("exitCode") if build_result else 0),
            language=context.language,
            runtime=context.runtime,
            duration_ms=int((time.time() - started) * 1000),
            stdout=(run_raw.output if run_raw else _first_output(build_result, test_result)),
            stderr="",
            artifacts=artifacts,
            diagnostics=diagnostics,
            tests=tests,
            resource_usage=usage,
            truncated=bool(run_raw.truncated if run_raw else truncated),
            error_class=ErrorClass.NONE.value if status == "COMPLETED" else _error_class(run_raw, build_result, test_result),
            context=context.to_dict(),
            build=build_result,
            started_at=started,
            finished_at=time.time(),
            metadata={"testSummary": (test_result.to_dict() if test_result else None),
                      "risk": request.metadata.get("_risk")},
        )
        emit("execution.completed", {"executionId": context.execution_id, "status": status,
                                     "exitCode": result.exit_code, "durationMs": result.duration_ms})
        return result

    def _from_build(self, request, context, build, artifact_manager, baseline, started, emit) -> ExecutionResult:
        artifacts, _ = artifact_manager.collect(baseline=baseline)
        result = ExecutionResult(
            execution_id=context.execution_id, status="BUILD_ERROR", exit_code=build.exit_code,
            language=context.language, runtime=context.runtime,
            duration_ms=int((time.time() - started) * 1000),
            stdout=build.stdout, diagnostics=build.errors, artifacts=artifacts,
            error_class=ErrorClass.BUILD_ERROR.value, context=context.to_dict(),
            build=build.to_dict(), started_at=started, finished_at=time.time(),
            error={"code": "BUILD_FAILED", "message": f"the build failed with exit code {build.exit_code}"},
        )
        emit("execution.failed", {"executionId": context.execution_id, "status": "BUILD_ERROR", "errors": len(build.errors)})
        return result

    def _from_test(self, request, context, test_result, build_result, artifact_manager, baseline, started, emit) -> ExecutionResult:
        artifacts, _ = artifact_manager.collect(baseline=baseline)
        failures = [f for f in test_result.failures]
        diagnostics = [
            d for f in failures if f.error
            for d in self.diagnostics.normalize(f.error, language=context.language, source="test")
        ]
        result = ExecutionResult(
            execution_id=context.execution_id, status="TEST_ERROR", exit_code=test_result.exit_code,
            language=context.language, runtime=context.runtime,
            duration_ms=int((time.time() - started) * 1000),
            stdout=test_result.stdout, diagnostics=diagnostics, tests=_tests_to_results(test_result),
            artifacts=artifacts, error_class=ErrorClass.TEST_ERROR.value, context=context.to_dict(),
            build=build_result, started_at=started, finished_at=time.time(),
            error={"code": "TESTS_FAILED",
                   "message": test_result.note or f"{test_result.failed} test(s) failed"},
            metadata={"testSummary": test_result.to_dict()},
        )
        emit("execution.failed", {"executionId": context.execution_id, "status": "TEST_ERROR",
                                  "failed": test_result.failed})
        return result

    def _from_raw_failure(self, request, context, raw, artifact_manager, baseline, started, emit) -> ExecutionResult:
        artifacts, _ = artifact_manager.collect(baseline=baseline)
        diagnostics = self.diagnostics.normalize(raw.output, language=context.language, source="runtime")
        result = ExecutionResult(
            execution_id=context.execution_id, status="RUNTIME_ERROR", exit_code=raw.exit_code,
            language=context.language, runtime=context.runtime,
            duration_ms=raw.duration_ms or int((time.time() - started) * 1000),
            stdout=raw.output, diagnostics=diagnostics, artifacts=artifacts,
            error_class=ErrorClass.RUNTIME_ERROR.value, context=context.to_dict(),
            started_at=started, finished_at=time.time(),
            error={"code": "PROCESS_LAUNCH_FAILED", "message": raw.launch_error or "the process could not start"},
        )
        emit("execution.failed", {"executionId": context.execution_id, "status": "RUNTIME_ERROR"})
        return result

    def _refusal(self, request, execution_id, code, error_class, emit, *, context=None, reason="", risk="") -> ExecutionResult:
        from .policy import refusal_copy  # noqa: PLC0415

        message = reason or refusal_copy(code)["reason"]
        status = "SECURITY_BLOCKED" if error_class in (ErrorClass.SECURITY_ERROR, ErrorClass.SECURITY_ERROR.value) else "FAILED"
        result = ExecutionResult(
            execution_id=execution_id, status=status, exit_code=None,
            language=request.language, runtime=request.runtime or "",
            duration_ms=0, error_class=error_class.value if isinstance(error_class, ErrorClass) else str(error_class),
            context=context.to_dict() if context else None,
            error={"code": code, "message": message, "recovery": refusal_copy(code).get("recovery", "")},
            started_at=time.time(), finished_at=time.time(), metadata={"risk": risk},
        )
        emit("execution.failed", {"executionId": execution_id, "status": status, "code": code})
        return result

    def _infrastructure_failure(self, request, execution_id, started, exc: BaseException) -> ExecutionResult:
        return ExecutionResult(
            execution_id=execution_id, status="FAILED", exit_code=None,
            language=request.language, runtime=request.runtime or "",
            duration_ms=int((time.time() - started) * 1000),
            error_class=ErrorClass.INFRASTRUCTURE_ERROR.value,
            error={"code": "INFRASTRUCTURE_ERROR", "message": f"{type(exc).__name__}: {exc}"},
            started_at=started, finished_at=time.time(),
        )

    def _finish(self, result: ExecutionResult, machine: StateMachine, emit: Emit) -> ExecutionResult:
        """Ensure the state machine is terminal and mirror the state on the result."""
        if not machine.terminal:
            try:
                machine.force_terminal(_state_for(result.status))
            except Exception:  # noqa: BLE001 - a terminal force must never raise from finally
                pass
        result.metadata.setdefault("stateHistory", [s.value for s in machine.history])
        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    def _workspace_root(self, binding: Optional[WorkspaceBinding]) -> Optional[Path]:
        if binding is None:
            return None
        import os

        root = Path(os.path.realpath(binding.root))
        return root if root.is_dir() else None

    def _make_workdir(self, execution_id: str) -> Path:
        base = self._scratch_root
        if base is not None:
            base.mkdir(parents=True, exist_ok=True)
            path = base / execution_id
            path.mkdir(parents=True, exist_ok=True)
            return path
        return Path(tempfile.mkdtemp(prefix=f"eclipse-exec-{execution_id}-"))

    def _cleanup(self, workdir: Path) -> None:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:  # noqa: BLE001 - cleanup must never raise
            pass

    def _reproducible(self, root, project, runtime_name, request, decision) -> dict[str, Any]:
        import os

        return {
            "os": os.name,
            "platform": __import__("sys").platform,
            "runtime": runtime_name,
            "language": project.primary_language,
            "packageManager": project.package_manager,
            "lockfile": project.lockfile,
            "baseRevision": getattr(request.workspace, "base_revision", ""),
            "networkPolicy": decision.network_policy.value,
            "filesystemPolicy": decision.filesystem_policy.value,
            "limits": request.limits().to_dict(),
        }

    def _run_ok(self, run_raw, build_result, test_result) -> bool:
        if build_result is not None and not build_result.get("success") and not build_result.get("skipped"):
            return False
        if test_result is not None and not test_result.success:
            return False
        if run_raw is not None and (run_raw.exit_code not in (0, None) or run_raw.timed_out or run_raw.cancelled):
            return False
        return True

    def _terminal_state(self, run_raw, build_result, test_result) -> ExecutionState:
        """The most specific terminal state for an outcome."""
        if test_result is not None and not test_result.success and run_raw is None:
            return ExecutionState.TEST_ERROR
        if build_result is not None and not build_result.get("success") and not build_result.get("skipped"):
            return ExecutionState.BUILD_ERROR
        if run_raw is not None:
            if run_raw.cancelled:
                return ExecutionState.CANCELLED
            if run_raw.timed_out:
                return ExecutionState.TIMED_OUT
            if run_raw.exit_code not in (0, None):
                return ExecutionState.FAILED
        if test_result is not None and not test_result.success:
            return ExecutionState.TEST_ERROR
        if build_result is not None and not build_result.get("success") and not build_result.get("skipped"):
            return ExecutionState.BUILD_ERROR
        return ExecutionState.COMPLETED


def _first_output(build_result, test_result) -> str:
    if test_result is not None:
        return test_result.stdout
    if build_result is not None:
        return build_result.get("stdout", "")
    return ""


def _tests_to_results(test_result) -> list:
    if test_result is None:
        return []
    return list(test_result.failures)


def _usage_from(run_raw, context) -> ResourceUsage:
    if run_raw is None:
        return ResourceUsage()
    return ResourceUsage(
        cpu_ms=None,  # wall-clock is not CPU time; reported honestly as unknown
        memory_peak_mb=None,
        process_count=None,
        stdout_bytes=len(run_raw.output.encode("utf-8", "replace")),
        stderr_bytes=0,
    )


def _error_class(run_raw, build_result, test_result) -> str:
    if test_result is not None and not test_result.success:
        return ErrorClass.TEST_ERROR.value
    if build_result is not None and not build_result.get("success") and not build_result.get("skipped"):
        return ErrorClass.BUILD_ERROR.value
    if run_raw is not None:
        if run_raw.timed_out:
            return ErrorClass.TIMEOUT.value
        if run_raw.cancelled:
            return ErrorClass.CANCELLED.value
        return ErrorClass.USER_CODE_ERROR.value
    return ErrorClass.NONE.value


def _state_for(status: str) -> ExecutionState:
    mapping = {
        "COMPLETED": ExecutionState.COMPLETED,
        "FAILED": ExecutionState.FAILED,
        "BUILD_ERROR": ExecutionState.BUILD_ERROR,
        "TEST_ERROR": ExecutionState.TEST_ERROR,
        "RUNTIME_ERROR": ExecutionState.RUNTIME_ERROR,
        "TIMED_OUT": ExecutionState.TIMED_OUT,
        "CANCELLED": ExecutionState.CANCELLED,
        "RESOURCE_LIMIT": ExecutionState.RESOURCE_LIMIT,
        "SECURITY_BLOCKED": ExecutionState.SECURITY_BLOCKED,
    }
    return mapping.get(status, ExecutionState.FAILED)


__all__ = ["ExecutionOrchestrator"]
