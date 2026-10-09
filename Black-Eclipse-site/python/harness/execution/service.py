"""The execution service facade + tool registry + the public tool surface.

This is the ONE object the agent tools and the HTTP surface share. It owns:

  * the `RuntimeRegistry` (language adapters),
  * the `ExecutionOrchestrator` (the lifecycle),
  * the `ExecutionScheduler` (bounded concurrency + cancellation),
  * the `ExecutionWorkflow` (multi-step plans),
  * the `ServiceManager` (long-running services over the terminal),
  * the `ExecutionStore` (history + evidence),
  * the `ExecutionVerifier` (the bounded build→test→fix loop).

Every tool handler is a thin adapter over it: it resolves the workspace binding,
the actor (from the run's autonomy), builds a typed `ExecutionRequest`, runs it,
records the evidence, and returns a structured result. The model-facing text is
plain; the structured `data` carries the full result.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from ..tools import ToolContext
from .models import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    FilesystemPolicy,
    NetworkPolicy,
    ResourceLimits,
)
from .orchestrator import ExecutionOrchestrator
from .runtimes import build_runtime_registry
from .scheduler import ExecutionScheduler, PENDING
from .services import ServiceManager
from .store import ExecutionStore
from .verify_loop import ExecutionVerifier
from .workflow import ExecutionWorkflow


def _enabled() -> bool:
    """Whether execution is enabled (operator flag; default ON, since the whole
    layer is opt-in at the tool/allowlist level). Set to 0 to hard-disable."""
    import os

    return os.environ.get("HARNESS_EXECUTION_ENABLED", "1") in ("1", "true", "True")


class ExecutionService:
    """The process-wide execution layer."""

    def __init__(self, *, store: Any = None, terminal: Any = None) -> None:
        self.registry = build_runtime_registry()
        self.orchestrator = ExecutionOrchestrator(self.registry)
        self.store: Optional[ExecutionStore] = ExecutionStore(store) if store is not None else None
        self.scheduler = ExecutionScheduler(self.orchestrator, self.store)
        self.workflow = ExecutionWorkflow(self.orchestrator, scheduler=self.scheduler)
        self.terminal = terminal
        self.services = ServiceManager(terminal)
        self.ports = self.services.ports
        self.verifier = ExecutionVerifier(self.orchestrator)

    # ── one-shot run (synchronous) ─────────────────────────────────────────────

    def run(
        self,
        request: ExecutionRequest,
        *,
        actor: Any = None,
        cancel_event: Optional[threading.Event] = None,
        emit: Optional[Any] = None,
        run_id: str = "",
    ) -> ExecutionResult:
        result = self.orchestrator.run(
            request, actor=actor, cancel_event=cancel_event, emit=emit,
            execution_enabled=_enabled(),
        )
        if self.store is not None:
            try:
                self.store.save_execution(result, run_id=run_id or request.run_id,
                                          agent_id=request.agent_id)
            except Exception:  # noqa: BLE001 - persistence must not break a call
                pass
        return result

    # ── async submit / query ───────────────────────────────────────────────────

    def submit(self, request: ExecutionRequest, *, actor: Any = None, emit: Optional[Any] = None) -> str:
        return self.scheduler.submit(request, actor=actor, emit=emit, run_id=request.run_id)

    def get_execution(self, submission_or_execution_id: str) -> Optional[dict[str, Any]]:
        pending = self.scheduler.get(submission_or_execution_id)
        if pending is not None and pending is not PENDING and hasattr(pending, "to_dict"):
            return pending.to_dict()
        if self.store is not None:
            return self.store.get_execution(submission_or_execution_id)
        return None

    def get_execution_logs(self, execution_id: str) -> dict[str, Any]:
        row = self.store.get_execution(execution_id) if self.store else None
        if row is None:
            return {"status": "not_found", "executionId": execution_id}
        return {"status": "ok", "executionId": execution_id,
                "stdout": row.get("stdout", ""), "stderr": row.get("stderr", "")}

    def get_execution_artifacts(self, execution_id: str) -> dict[str, Any]:
        row = self.store.get_execution(execution_id) if self.store else None
        if row is None:
            return {"status": "not_found", "executionId": execution_id}
        return {"status": "ok", "executionId": execution_id, "artifacts": row.get("artifacts", [])}

    def get_execution_metrics(self, execution_id: str) -> dict[str, Any]:
        row = self.store.get_execution(execution_id) if self.store else None
        if row is None:
            return {"status": "not_found", "executionId": execution_id}
        return {"status": "ok", "executionId": execution_id, "metrics": row.get("metrics", [])}

    def cancel_execution(self, submission_or_execution_id: str) -> bool:
        return self.scheduler.cancel(submission_or_execution_id)

    def list_executions(self, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_executions(run_id=run_id, limit=limit) if self.store else []

    def list_active(self) -> list[dict[str, Any]]:
        return self.scheduler.list()

    # ── services ────────────────────────────────────────────────────────────────

    def start_service(self, **kwargs: Any) -> dict[str, Any]:
        return self.services.start_service(**kwargs)

    def stop_service(self, service_id: str) -> dict[str, Any]:
        return self.services.stop_service(service_id)

    def restart_service(self, service_id: str) -> dict[str, Any]:
        return self.services.restart_service(service_id)

    def get_service_status(self, service_id: str) -> dict[str, Any]:
        return self.services.get_service_status(service_id)

    def get_service_logs(self, service_id: str, *, tail: int = 200) -> dict[str, Any]:
        return self.services.get_service_logs(service_id, tail=tail)

    def list_services(self) -> list[dict[str, Any]]:
        return self.services.list_services()

    # ── lifecycle ────────────────────────────────────────────────────────────────

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": _enabled(),
            "runtimes": self.registry.describe(),
            "maxConcurrency": self.scheduler.max_concurrent,
            "active": self.scheduler.active_count(),
            "services": len(self.services.list_services()),
        }

    def stop(self) -> None:
        try:
            self.services.stop_all()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            pass
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


# ── workspace/actor helpers used by the tools ────────────────────────────────


def _active_code_workspace(ctx: ToolContext) -> Any:
    """The run's disposable code workspace, if one has been allocated.

    The code-editing tools allocate ONE per-run worktree and cache it on the
    context (`ctx._code_workspace`). When it exists, verification/build/test MUST
    run against that same tree — otherwise a run could edit a copy and verify the
    untouched original. Returns the `(code_workspace, binding, resolved, actor)`
    bundle, or None.
    """
    bundle = getattr(ctx, "_code_workspace", None)
    if bundle is None:
        return None
    try:
        return bundle if bundle[1] is not None else None
    except (TypeError, IndexError):
        return None


def make_actor(ctx: ToolContext) -> Any:
    """The Actor for a run's autonomy profile (mirrors `analysis_tools._actor`)."""
    from ..skills.permissions import Actor  # noqa: PLC0415

    bundle = _active_code_workspace(ctx)
    workspace_id = (
        bundle[0].id if bundle is not None
        else getattr(getattr(ctx, "workspace", None), "id", None)
    )
    return Actor(
        id=getattr(ctx, "user_id", None) or "local",
        operator=False,
        workspace_id=workspace_id,
        autonomy=getattr(ctx, "autonomy", None),
    )


def workspace_binding(ctx: ToolContext) -> Any:
    """The run's workspace binding.

    Prefers the run's allocated code workspace (the worktree the agent actually
    edited) so execution/verification acts on the same tree; falls back to the
    request's resolved workspace binding for read-only or non-code runs.
    """
    bundle = _active_code_workspace(ctx)
    if bundle is not None:
        return bundle[1]
    ws = getattr(ctx, "workspace", None)
    if ws is None:
        return None
    return getattr(ws, "binding", None) or ws


def build_request(
    ctx: ToolContext,
    *,
    language: str,
    binding: Any = None,
    code: str = "",
    entrypoint: str = "",
    mode: str = "RUN",
    args: Optional[list[str]] = None,
    environment: Optional[dict[str, str]] = None,
    secrets: Optional[dict[str, str]] = None,
    cwd: str = "",
    runtime: str = "",
    timeout_ms: Optional[int] = None,
    network_policy: str = "NONE",
    filesystem_policy: str = "WORKSPACE_READ_WRITE",
    test_policy: Optional[dict[str, Any]] = None,
    build_policy: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> ExecutionRequest:
    """Build a typed `ExecutionRequest` from a run's context and tool arguments."""
    if binding is None:
        binding = workspace_binding(ctx)
    limits = ResourceLimits.from_env()
    if timeout_ms:
        from dataclasses import replace

        limits = replace(limits, timeout_ms=int(timeout_ms))
    return ExecutionRequest(
        language=language,
        workspace=binding,
        code=code,
        entrypoint=entrypoint,
        cwd=cwd,
        args=list(args or []),
        environment=dict(environment or {}),
        secrets=dict(secrets or {}),
        runtime=runtime,
        mode=ExecutionMode(mode),
        network_policy=NetworkPolicy(network_policy),
        filesystem_policy=FilesystemPolicy(filesystem_policy),
        resource_limits=limits,
        test_policy=test_policy,
        build_policy=build_policy,
        run_id=str(getattr(ctx, "run_id", "")),
        agent_id=getattr(ctx, "agent_id", None),
        workspace_id=getattr(binding, "id", None) if binding is not None else None,
        metadata=dict(metadata or {}),
    )


__all__ = ["ExecutionService", "build_request", "make_actor", "workspace_binding"]
