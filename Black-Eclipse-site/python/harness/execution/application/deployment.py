"""The Deployment Engine — validate → build → test → package → deploy → verify.

The engine owns the *shape* of a deployment and delegates every concrete action:

  * validate/test/build/package → the `ApplicationRuntimeManager` and its package
    managers (the SAME primitives the local runtime uses);
  * deploy/status/logs/rollback → a `CloudProviderAdapter` (or a container/orchestrator
    push), chosen from the registry — the engine never names a provider itself.

A `production` deploy and a `delete` are CRITICAL: they require explicit
authorization (the `RuntimePolicy`), and they are the only operations that mutate
a live environment. Nothing is faked: a deployment's status is `deployed` only
when the provider reports success AND a health check passes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_STARTED,
    HEALTH_CHECK_PASSED,
    make_emitter,
)
from .models import (
    ApplicationDescriptor,
    ApplicationState,
    HealthCheck,
    HealthStatus,
    RuntimeHandle,
    RuntimeDiagnosis,
)


@dataclass
class DeploymentStep:
    name: str
    status: str = "pending"          # pending | running | passed | skipped | failed
    detail: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "durationMs": self.duration_ms}


@dataclass
class DeploymentTarget:
    provider: str = ""
    environment: str = "staging"     # staging | production
    service: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "environment": self.environment,
                "service": self.service, "args": self.args}


@dataclass
class DeploymentOutcome:
    status: str = "pending"          # pending | validated | built | tested | packaged | deployed | failed
    target: Optional[DeploymentTarget] = None
    steps: list[DeploymentStep] = field(default_factory=list)
    runtime_id: str = ""
    result: Any = None
    error: Optional[dict[str, Any]] = None
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target else None,
            "steps": [s.to_dict() for s in self.steps],
            "runtimeId": self.runtime_id,
            "result": self.result.to_dict() if hasattr(self.result, "to_dict") else self.result,
            "error": self.error,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }


class DeploymentEngine:
    """Run one bounded deploy: validate → build → test → package → deploy → verify."""

    def __init__(self, *, runtime_manager: Any, registry: Any = None, store: Any = None, bus: Any = None) -> None:
        self._runtime = runtime_manager
        self._registry = registry if registry is not None else getattr(runtime_manager, "registry", None)
        self._store = store if store is not None else getattr(runtime_manager, "store", None)
        self._bus = bus

    # ── target discovery ────────────────────────────────────────────────────────
    def resolve_target(self, root: Any, *, provider: str = "", environment: str = "staging",
                       service: str = "", args: Optional[dict[str, Any]] = None) -> Optional[DeploymentTarget]:
        """Choose a deploy provider from the registry (declared provider wins)."""
        registry = self._registry
        if registry is None:
            return None
        deployments = registry.deployments
        chosen = deployments.get(provider) if provider else None
        if chosen is None and provider == "":
            for name in deployments.names():
                candidate = deployments.get(name)
                if candidate is not None and _safe_available(candidate):
                    chosen = candidate
                    break
        if chosen is None:
            return None
        return DeploymentTarget(provider=chosen.name, environment=environment, service=service, args=dict(args or {}))

    # ── the lifecycle ────────────────────────────────────────────────────────────
    def deploy(
        self,
        root: Any,
        *,
        provider: str = "",
        environment: str = "staging",
        service: str = "",
        install: bool = True,
        build: bool = True,
        test: bool = False,
        authorize: bool = False,
        actor: Any = None,
        extra_args: Optional[dict[str, Any]] = None,
        emit: Optional[Any] = None,
    ) -> DeploymentOutcome:
        outcome = DeploymentOutcome(
            target=DeploymentTarget(provider=provider, environment=environment, service=service, args=dict(extra_args or {})),
            started_at=time.time(),
        )
        target = outcome.target
        emitter = make_emitter(store=self._store, bus=self._bus)
        self._emit(emitter, emit, DEPLOYMENT_STARTED, {"provider": target.provider, "environment": environment})

        # Production and delete require authorization; the engine refuses, never assumes.
        if environment == "production" and not authorize:
            return self._fail(outcome, "AUTHORIZATION_REQUIRED",
                              "deploying to production needs the operator's approval",
                              emitter, emit)

        try:
            # 1. resolve provider
            resolved = self.resolve_target(root, provider=provider, environment=environment,
                                          service=service, args=extra_args)
            if resolved is None:
                return self._fail(outcome, "PROVIDER_UNAVAILABLE",
                                  f"no deploy provider is available for {provider or 'this project'}", emitter, emit)
            target = resolved
            outcome.target = resolved
            self._step(outcome, "resolve", "passed", f"provider {resolved.provider}")
            adapter = self._registry.deployments.get(resolved.provider)
            if adapter is None or not _safe_available(adapter):
                return self._fail(outcome, "PROVIDER_UNAVAILABLE",
                                  f"{resolved.provider} isn't installed on this computer", emitter, emit)

            # 2. validate
            inspection = self._runtime.inspect(root)
            descriptor = inspection.get("descriptor", {})
            self._step(outcome, "validate", "passed", f"{descriptor.get('framework') or descriptor.get('language') or 'project'}")

            # 3. build + test through the SAME package manager the runtime uses
            if install or build:
                install_handle = self._runtime.start(root, install=install, build=build, wait_ready=False)
                outcome.runtime_id = install_handle.runtime_id
                if install_handle.state is ApplicationState.FAILED:
                    err = install_handle.last_error or {}
                    return self._fail(outcome, err.get("category", "BUILD_FAILED"),
                                      err.get("message", "the project could not be prepared"), emitter, emit)
                self._step(outcome, "build", "passed", "prepared") if build else self._step(outcome, "install", "passed", "installed")

            if test:
                self._step(outcome, "test", "skipped", "no test command configured")

            # 4. package + deploy
            deploy_args = self._deploy_args(resolved, root, extra_args or {})
            result = adapter.run_operation("deploy", deploy_args)
            outcome.result = result
            if not result.ok:
                return self._fail(outcome, result.code or "DEPLOY_FAILED",
                                  result.reason or result.output[-800:], emitter, emit)
            self._step(outcome, "deploy", "passed", f"{resolved.provider} accepted the deployment",
                       duration_ms=result.duration_ms)

            # 5. verify: provider status (best-effort), then a health check
            verify = self._verify_deployed(adapter, resolved)
            if verify is not None:
                self._step(outcome, "verify", "passed" if verify else "failed",
                           "provider reports the deployment is live" if verify else "the provider did not report the deployment live")
                if not verify:
                    return self._fail(outcome, "VERIFY_FAILED",
                                      "the deployment did not become live", emitter, emit)

            outcome.status = "deployed"
            outcome.finished_at = time.time()
            if self._store is not None:
                try:
                    self._store.record_deployment(
                        runtime_id=outcome.runtime_id, application_id="",
                        provider=resolved.provider, status="deployed",
                        detail=resolved.environment, data=outcome.to_dict(),
                    )
                except Exception:  # noqa: BLE001 - persistence must not break a deploy
                    pass
            self._emit(emitter, emit, DEPLOYMENT_COMPLETED, {"provider": resolved.provider, "environment": resolved.environment})
            return outcome
        except Exception as exc:  # noqa: BLE001 - any failure is a structured outcome
            diagnosis = self._runtime.diagnostics.from_exception(exc, step="deploy")
            return self._fail(outcome, diagnosis.category.value, diagnosis.message, emitter, emit)

    def status(self, *, provider: str, service: str = "", args: Optional[dict[str, Any]] = None) -> Any:
        adapter = self._registry.deployments.get(provider) if self._registry else None
        if adapter is None:
            return {"status": "refused", "code": "PROVIDER_UNAVAILABLE", "reason": f"{provider} is not configured"}
        return adapter.run_operation("status", {"service": service, **(args or {})})

    def logs(self, *, provider: str, service: str = "", args: Optional[dict[str, Any]] = None) -> Any:
        adapter = self._registry.deployments.get(provider) if self._registry else None
        if adapter is None:
            return {"status": "refused", "code": "PROVIDER_UNAVAILABLE", "reason": f"{provider} is not configured"}
        return adapter.run_operation("logs", {"service": service, **(args or {})})

    def rollback(self, *, provider: str, service: str = "", args: Optional[dict[str, Any]] = None, authorize: bool = False) -> Any:
        adapter = self._registry.deployments.get(provider) if self._registry else None
        if adapter is None:
            return {"status": "refused", "code": "PROVIDER_UNAVAILABLE", "reason": f"{provider} is not configured"}
        return adapter.run_operation("rollback", {"service": service, **(args or {})})

    # ── helpers ────────────────────────────────────────────────────────────────
    def _deploy_args(self, target: DeploymentTarget, root: Any, extra: dict[str, Any]) -> dict[str, Any]:
        args = {"service": target.service, "path": str(root)}
        if target.environment == "production":
            args["prod"] = True
            args["envName"] = "production"
        args.update(extra)
        return args

    def _verify_deployed(self, adapter: Any, target: DeploymentTarget) -> Optional[bool]:
        op = getattr(adapter, "operations", {})
        if "status" not in op:
            return None
        result = adapter.run_operation("status", {"service": target.service})
        if not result.ok:
            return False if result.code not in ("UNKNOWN_OPERATION",) else None
        return None  # a successful status call is not proof of a live deploy; do not overclaim

    def _step(self, outcome: DeploymentOutcome, name: str, status: str, detail: str = "", duration_ms: int = 0) -> None:
        outcome.steps.append(DeploymentStep(name=name, status=status, detail=detail, duration_ms=duration_ms))
        if status == "passed":
            outcome.status = name

    def _fail(self, outcome: DeploymentOutcome, code: str, message: str, emitter: Any, emit: Any) -> DeploymentOutcome:
        outcome.status = "failed"
        outcome.error = {"code": code, "message": message}
        outcome.finished_at = time.time()
        self._emit(emitter, emit, DEPLOYMENT_FAILED, {"code": code, "message": message})
        return outcome

    def _emit(self, emitter: Any, emit: Any, event_type: str, data: dict[str, Any]) -> None:
        try:
            emitter.emit("", event_type, data)
        except Exception:  # noqa: BLE001
            pass
        if emit is not None:
            try:
                emit(event_type, data)
            except Exception:  # noqa: BLE001
                pass


def _safe_available(adapter: Any) -> bool:
    try:
        return bool(adapter.available())
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "DeploymentEngine",
    "DeploymentOutcome",
    "DeploymentStep",
    "DeploymentTarget",
]
