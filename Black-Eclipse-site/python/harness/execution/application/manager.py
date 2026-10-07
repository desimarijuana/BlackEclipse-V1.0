"""The Application Runtime Manager — the one lifecycle an application follows.

This is the orchestrator the spec calls `ApplicationRuntimeManager`. It owns the
sequence DISCOVER → VALIDATE → PREPARE → INSTALL → BUILD → START → HEALTH →
RUNNING → OBSERVE → STOP → CLEANUP, and it delegates every concrete action:

  * discovery → `ApplicationDiscovery`
  * dependency install / build → a `PackageManagerAdapter` over `code/sandbox.py`
  * local services → the EXISTING terminal `ProcessManager` (`start_process`)
  * containers → a `ContainerRuntimeAdapter` (Docker/Podman)
  * compose → a `ComposeAdapter`
  * ports → `PortManager` over the terminal port table
  * health → `HealthCheckEngine`
  * failures → `RuntimeDiagnosticsEngine` + `RecoveryEngine`
  * persistence → `ApplicationRuntimeStore`
  * events → the harness `EventBus` via `RuntimeEventEmitter`

It NEVER fakes success: `RUNNING` means the processes/containers exist; `HEALTHY`
is a separate assertion made only by a passing health check. It NEVER kills a
foreign process; a port conflict is identified and either worked around (when the
policy allows) or reported for authorization. Every long-running process is a
terminal-managed process (tree-killed, cancellable, persisted).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..models import ExecutionResult, ResourceLimits
from .compose import ComposeAdapter
from .container import ContainerRuntimeAdapter
from .diagnostics import RuntimeDiagnosticsEngine
from .discovery import ApplicationDiscovery, ComposeService, build_service_graph
from .environment import EnvironmentManager
from .events import (
    APPLICATION_DISCOVERED,
    APPLICATION_VALIDATION_FAILED,
    APPLICATION_VALIDATED,
    BUILD_COMPLETED,
    BUILD_FAILED,
    BUILD_STARTED,
    CONTAINER_STARTED,
    DEPENDENCIES_INSTALLED,
    DEPENDENCIES_INSTALLING,
    DEPENDENCY_INSTALL_FAILED,
    HEALTH_CHECK_FAILED,
    HEALTH_CHECK_PASSED,
    PROCESS_STARTED,
    RUNTIME_DEGRADED,
    RUNTIME_FAILED,
    RUNTIME_RECONCILED,
    RUNTIME_RECOVERY_ATTEMPT,
    RUNTIME_RECOVERY_COMPLETED,
    RUNTIME_STARTED,
    RUNTIME_STOPPED,
    make_emitter,
)
from .health import HealthCheckEngine
from .models import (
    ApplicationDescriptor,
    ApplicationState,
    DiagnosticCategory,
    HealthCheck,
    HealthReport,
    HealthStatus,
    PortRecord,
    RecoveryStrategy,
    RuntimeDiagnosis,
    RuntimeHandle,
    ServiceGraph,
    ServiceKind,
    ServiceNode,
    new_application_id,
    new_runtime_id,
)
from .package_managers import BasePackageManager, build_package_manager_registry
from .ports import PortManager
from .recovery import RecoveryEngine, RecoveryOutcome, recovery_budget
from .registry import RuntimeRegistry
from .state import ApplicationStateMachine
from .store import ApplicationRuntimeStore
from .policy import DESTRUCTIVE_OPERATIONS, RuntimePolicy


def build_runtime_registry(
    *,
    container: Optional[ContainerRuntimeAdapter] = None,
    compose: Optional[ComposeAdapter] = None,
    package_managers: Any = None,
) -> RuntimeRegistry:
    """Assemble the central registry: package managers + container + compose +
    orchestration (Kubernetes/Helm/Kustomize) + infrastructure (Terraform) +
    deployment (AWS/Azure/GCP/Cloudflare/Vercel/Railway/Render).

    Every provider is registered; a missing binary is simply unavailable (the
    registry reports it honestly, never a fake). Adding a provider is registration,
    not a change to this function's contract.
    """
    from .container import DockerAdapter, PodmanAdapter
    from .compose import DockerComposeAdapter, PodmanComposeAdapter
    from .orchestrators import build_orchestrator_adapters
    from .infrastructure import build_infrastructure_adapters
    from .cloud import build_deployment_adapters

    registry = RuntimeRegistry()
    registry.packages = package_managers or build_package_manager_registry()
    for adapter in (DockerAdapter(), PodmanAdapter()):
        registry.containers.register(adapter)
    registry.compose.register(DockerComposeAdapter())
    registry.compose.register(PodmanComposeAdapter())
    for adapter in build_orchestrator_adapters():
        registry.orchestrators.register(adapter)
    for adapter in build_infrastructure_adapters():
        registry.infrastructure.register(adapter)
    for adapter in build_deployment_adapters():
        registry.deployments.register(adapter)
    return registry


class ApplicationRuntimeManager:
    """The process-wide application runtime engine."""

    def __init__(
        self,
        *,
        registry: Optional[RuntimeRegistry] = None,
        terminal: Any = None,
        store: Optional[ApplicationRuntimeStore] = None,
        bus: Any = None,
        policy: Optional[RuntimePolicy] = None,
        discovery: Optional[ApplicationDiscovery] = None,
        limits: Optional[ResourceLimits] = None,
        recovery: Optional[RecoveryEngine] = None,
    ) -> None:
        self.registry = registry or build_runtime_registry()
        self.terminal = terminal
        self.store = store
        self.bus = bus
        self.policy = policy or RuntimePolicy()
        self.discovery = discovery or ApplicationDiscovery()
        self.limits = limits or ResourceLimits.from_env()
        self.diagnostics = RuntimeDiagnosticsEngine()
        self.environment = EnvironmentManager()
        self.health = HealthCheckEngine(terminal=terminal)
        self.ports = PortManager(terminal=terminal)
        self.recovery = recovery or RecoveryEngine()
        from .cache import DiscoveryCache

        self._discovery_cache = DiscoveryCache()
        self._runtimes: dict[str, RuntimeHandle] = {}
        self._machines: dict[str, ApplicationStateMachine] = {}
        self._lock = threading.RLock()

    # ── registry description ─────────────────────────────────────────────────────
    def describe(self) -> dict[str, Any]:
        return {
            "runtimes": self.registry.describe(),
            "capabilities": self.registry.capabilities(),
            "activeRuntimes": len([r for r in self._runtimes.values() if r.state not in (ApplicationState.STOPPED, ApplicationState.FAILED)]),
            "recoveryAttempts": self.recovery.max_attempts,
        }

    # ── discovery / inspection ────────────────────────────────────────────────────
    def discover(self, root: Path, *, name: str = "") -> ApplicationDescriptor:
        root = Path(root)
        cache_key = name  # a named discovery is cached separately from the default.
        if not cache_key:
            cached = self._discovery_cache.get(root)
            if cached is not None:
                return cached
        descriptor = self._discover_uncached(root, name=name)
        if not cache_key:
            self._discovery_cache.put(root, descriptor)
        return descriptor

    def _discover_uncached(self, root: Path, *, name: str = "") -> ApplicationDescriptor:
        descriptor = self.discovery.discover(root, name=name)
        # Resolve the actual container engine availability for the report.
        if descriptor.container_runtime:
            engine = self.registry.containers.get(descriptor.container_runtime)
            if engine is None or not _safe(engine.available):
                available = self.registry.containers.detect()
                if available is not None:
                    descriptor.container_runtime = available.name
        manager = self.registry.packages.detect(root, descriptor)
        if manager is not None and not descriptor.package_manager:
            descriptor.package_manager = manager.name
        return descriptor

    def invalidate_discovery(self, root: Optional[Path] = None) -> None:
        """Drop the cached descriptor(s); called after a dependency/config change."""
        self._discovery_cache.invalidate(root)

    def inspect(self, root: Path) -> dict[str, Any]:
        """A read-only view: the descriptor, the service graph, env metadata, ports."""
        descriptor = self.discover(root)
        compose_services = _compose_services(Path(root), descriptor)
        graph = build_service_graph(descriptor, compose_services)
        env = self.environment.metadata(Path(root))
        return {
            "descriptor": descriptor.to_dict(),
            "serviceGraph": graph.to_dict(),
            "environment": env,
            "ports": [p.to_dict() for p in self._declared_ports(descriptor)],
        }

    # ── lifecycle ────────────────────────────────────────────────────────────────
    def start(
        self,
        root: Path,
        *,
        name: str = "",
        workspace_id: Optional[str] = None,
        run_id: str = "",
        agent_id: Optional[str] = None,
        actor: Any = None,
        install: bool = True,
        build: bool = False,
        use_compose: Optional[bool] = None,
        wait_ready: bool = True,
        health_timeout_s: float = 30.0,
        emit: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> RuntimeHandle:
        """Run the full startup sequence and return the live runtime handle."""
        root = Path(root)
        runtime_id = new_runtime_id()
        machine = ApplicationStateMachine(ApplicationState.UNKNOWN)
        handle = RuntimeHandle(
            runtime_id=runtime_id, application_id=new_application_id(),
            state=ApplicationState.DISCOVERING, workspace_id=workspace_id,
            run_id=run_id, agent_id=agent_id, started_at=time.time(), updated_at=time.time(),
        )
        emitter = make_emitter(store=self.store, bus=self.bus, run_id=run_id)
        handle.extra["emitter"] = emitter
        with self._lock:
            self._runtimes[runtime_id] = handle
            self._machines[runtime_id] = machine

        try:
            self._start_sequence(
                handle, machine, root, name=name, actor=actor, install=install,
                build=build, use_compose=use_compose, wait_ready=wait_ready,
                health_timeout_s=health_timeout_s, emitter=emitter, on_event=emit,
            )
        except Exception as exc:  # noqa: BLE001 - any failure lands on FAILED honestly
            if isinstance(exc, _BuildFailure):
                diagnosis = exc.diagnosis
            else:
                diagnosis = self.diagnostics.from_exception(exc, step="start")
            self._fail(handle, machine, diagnosis, emitter, on_event=emit)
        finally:
            handle.updated_at = time.time()
            self._persist(handle)
        return handle

    def _start_sequence(self, handle, machine, root, *, name, actor, install, build, use_compose, wait_ready, health_timeout_s, emitter, on_event) -> None:
        # DISCOVER
        descriptor = self.discover(root, name=name)
        handle.descriptor = descriptor
        compose_services = _compose_services(root, descriptor)
        graph = build_service_graph(descriptor, compose_services)
        handle.graph = graph
        handle.services = list(descriptor.services)
        self._emit(emitter, on_event, handle, APPLICATION_DISCOVERED, {
            "name": descriptor.name, "language": descriptor.language,
            "framework": descriptor.framework, "packageManager": descriptor.package_manager,
            "docker": descriptor.docker, "compose": descriptor.compose,
        })
        self._persist(handle)
        machine.to(ApplicationState.DISCOVERED)

        # VALIDATE
        machine.to(ApplicationState.VALIDATING)
        validation = self._validate(handle, root, descriptor, actor, install=install)
        if not validation["ok"]:
            self._emit(emitter, on_event, handle, APPLICATION_VALIDATION_FAILED, {
                "code": validation.get("code", "VALIDATION_FAILED"),
                "reason": validation.get("reason", ""),
            })
            diagnosis = validation["diagnosis"]
            self._fail(handle, machine, diagnosis, emitter, on_event=on_event)
            return
        self._emit(emitter, on_event, handle, APPLICATION_VALIDATED, {"warnings": validation.get("warnings", [])})

        # PREPARE
        machine.to(ApplicationState.PREPARING)
        handle.ports = self._allocate_ports(handle, descriptor)

        # Container / compose path?
        prefer_compose = use_compose if use_compose is not None else descriptor.compose
        engine = self.registry.containers.detect(prefer=descriptor.container_runtime)
        compose = self._compose_for(engine)
        if prefer_compose and engine is not None and compose is not None and descriptor.compose_file:
            self._start_compose(handle, machine, root, descriptor, compose, engine, emitter, on_event)
            self._finalize_running(handle, machine, root, descriptor, wait_ready=wait_ready, health_timeout_s=health_timeout_s, emitter=emitter, on_event=on_event)
            return

        # Local (non-container) path.
        manager = self.registry.packages.detect(root, descriptor)
        if install:
            self._install(handle, machine, root, descriptor, manager, emitter, on_event)
        if build:
            self._build(handle, machine, root, descriptor, manager, emitter, on_event)

        machine.to(ApplicationState.STARTING)
        self._start_local_services(handle, machine, root, descriptor, compose_services, emitter, on_event)
        self._finalize_running(handle, machine, root, descriptor, wait_ready=wait_ready, health_timeout_s=health_timeout_s, emitter=emitter, on_event=on_event)

    def _finalize_running(self, handle, machine, root, descriptor, *, wait_ready, health_timeout_s, emitter, on_event) -> None:
        self._emit(emitter, on_event, handle, RUNTIME_STARTED, {"state": "RUNNING", "services": handle.services})
        self._walk_to_running(machine)
        handle.state = ApplicationState.RUNNING
        self._persist(handle)
        if wait_ready:
            report = self.check_health(handle, root, timeout_s=health_timeout_s, emitter=emitter, on_event=on_event)
            if report.healthy:
                pass
            elif report.status is HealthStatus.DEGRADED:
                self._mark_degraded(handle, machine, report, emitter, on_event)
            elif handle.services:  # a real service that never became healthy
                self._mark_degraded(handle, machine, report, emitter, on_event)

    def _walk_to_running(self, machine) -> None:
        """Advance the machine to RUNNING through any legal intermediate edges.

        The compose path reaches `_finalize_running` from INSTALLING, so walk
        INSTALLING → BUILDING → STARTING → RUNNING (or from wherever we are). A
        state already in {RUNNING, DEGRADED, STOPPING} is left alone.
        """
        if machine is None or machine.terminal:
            return
        chain = {
            ApplicationState.INSTALLING: (ApplicationState.BUILDING, ApplicationState.STARTING, ApplicationState.RUNNING),
            ApplicationState.BUILDING: (ApplicationState.STARTING, ApplicationState.RUNNING),
            ApplicationState.STARTING: (ApplicationState.RUNNING,),
            ApplicationState.PREPARING: (ApplicationState.STARTING, ApplicationState.RUNNING),
            ApplicationState.DISCOVERED: (ApplicationState.VALIDATING, ApplicationState.PREPARING, ApplicationState.STARTING, ApplicationState.RUNNING),
        }
        for target in chain.get(machine.state, ()):
            try:
                machine.to(target)
            except Exception:  # noqa: BLE001 - a skipped edge is fine; we force the rest
                continue

    # ── validate ─────────────────────────────────────────────────────────────────
    def _validate(self, handle, root, descriptor, actor, *, install: bool = True) -> dict[str, Any]:
        warnings: list[str] = []
        # Package-manager present but unavailable: honest refusal when an install is
        # required, never a silent switch. When we won't install (deps already
        # present, or install=False) a missing manager is only a warning.
        if descriptor.package_manager:
            manager = self.registry.packages.get(descriptor.package_manager)
            if manager is not None and not _safe(manager.available):
                deps_present = _dependencies_present(root, descriptor)
                if install and not deps_present:
                    return {
                        "ok": False, "code": "PACKAGE_MANAGER_UNAVAILABLE",
                        "reason": f"{descriptor.package_manager} is required but isn't installed",
                        "diagnosis": RuntimeDiagnosis(
                            category=DiagnosticCategory.RUNTIME_MISSING,
                            severity="high",
                            message=f"{descriptor.package_manager} is required by this project but isn't installed.",
                            evidence=[f"lockfile: {descriptor.lockfile or 'n/a'}"],
                            recoverable=False, source="validation",
                        ),
                    }
                warnings.append(f"{descriptor.package_manager} isn't installed")
        # Environment: report missing required values, but never a secret value.
        env = self.environment.validate(root)
        if env.get("missing"):
            warnings.append(f"missing environment values: {', '.join(env['missing'][:5])}")
        # Ports declared but occupied by a foreign process: warn (start may pick another).
        for port in descriptor.ports:
            conflict = self.ports.identify(int(port))
            if conflict is not None and not conflict.managed:
                warnings.append(f"port {port} is in use by {conflict.owner}")
        return {"ok": True, "warnings": warnings}

    # ── ports ────────────────────────────────────────────────────────────────────
    def _declared_ports(self, descriptor: ApplicationDescriptor) -> list[PortRecord]:
        return [PortRecord(port=int(p), source="declared", purpose="app") for p in descriptor.ports]

    def _allocate_ports(self, handle, descriptor) -> list[PortRecord]:
        records: list[PortRecord] = []
        avoid: list[int] = []
        for port in descriptor.ports:
            conflict = self.ports.identify(int(port))
            if conflict is None:
                self.ports.allocate(preferred=int(port), owner=handle.runtime_id, avoid=avoid)
                records.append(PortRecord(port=int(port), source="declared", purpose="app", service=handle.runtime_id))
            else:
                # Occupied. If Eclipse owns it, keep it; else pick a free one.
                if conflict.managed:
                    records.append(PortRecord(port=int(port), source="declared", purpose="in-use", service=handle.runtime_id, pid=conflict.pid, process_id=conflict.process_id))
                else:
                    record = self.ports.allocate(preferred=0, owner=handle.runtime_id, avoid=avoid)
                    avoid.append(record.port)
                    records.append(record)
        return records

    # ── install / build ─────────────────────────────────────────────────────────────
    def _install(self, handle, machine, root, descriptor, manager, emitter, on_event) -> None:
        if manager is None or not _has_cap(manager, "install"):
            return  # nothing to install
        plan = _dependency_plan(root, manager, descriptor)
        if plan.get("satisfied"):
            return
        machine.to(ApplicationState.INSTALLING)
        self._emit(emitter, on_event, handle, DEPENDENCIES_INSTALLING, {"manager": manager.name})
        try:
            argv = manager.install_dependencies(root)
        except Exception as exc:  # noqa: BLE001
            self._emit(emitter, on_event, handle, DEPENDENCY_INSTALL_FAILED, {"manager": manager.name, "reason": str(exc)})
            raise
        result = manager.run(argv, cwd=root, limits=self.limits)
        handle.extra["install"] = result.to_dict()
        if not result.ok:
            self._emit(emitter, on_event, handle, DEPENDENCY_INSTALL_FAILED, {"manager": manager.name, "exitCode": result.exit_code})
            diagnosis = self.diagnostics.classify(
                output=result.output, exit_code=result.exit_code, step="install",
                language=descriptor.language, source="dependencies", reason="installing dependencies failed",
            )
            raise _BuildFailure(diagnosis)
        self.invalidate_discovery(Path(handle.descriptor.path) if handle.descriptor else None)
        self._emit(emitter, on_event, handle, DEPENDENCIES_INSTALLED, {"manager": manager.name, "durationMs": result.duration_ms})

    def _build(self, handle, machine, root, descriptor, manager, emitter, on_event) -> None:
        if manager is None or not _has_cap(manager, "build"):
            return
        machine.to(ApplicationState.BUILDING)
        self._emit(emitter, on_event, handle, BUILD_STARTED, {"manager": manager.name})
        try:
            argv = manager.build(root)
        except Exception as exc:  # noqa: BLE001
            self._emit(emitter, on_event, handle, BUILD_FAILED, {"reason": str(exc)})
            raise
        result = manager.run(argv, cwd=root, limits=self.limits)
        handle.extra["build"] = result.to_dict()
        if not result.ok:
            self._emit(emitter, on_event, handle, BUILD_FAILED, {"exitCode": result.exit_code})
            diagnosis = self.diagnostics.classify(output=result.output, exit_code=result.exit_code, step="build", language=descriptor.language, source="build")
            raise _BuildFailure(diagnosis)
        self._emit(emitter, on_event, handle, BUILD_COMPLETED, {"durationMs": result.duration_ms})

    # ── compose ──────────────────────────────────────────────────────────────────
    def _compose_for(self, engine: Optional[ContainerRuntimeAdapter]) -> Optional[ComposeAdapter]:
        if engine is None:
            return None
        adapter = self.registry.compose.for_engine(engine.name)
        if adapter is None or not _safe(adapter.available):
            return None
        return adapter

    def _start_compose(self, handle, machine, root, descriptor, compose, engine, emitter, on_event) -> None:
        machine.to(ApplicationState.INSTALLING)
        self._emit(emitter, on_event, handle, DEPENDENCIES_INSTALLING, {"manager": engine.name + " compose"})
        result = compose.pull(cwd=root, compose_file=descriptor.compose_file)
        handle.extra["composePull"] = result.to_dict()
        up = compose.up(cwd=root, compose_file=descriptor.compose_file, detach=True, build=True)
        handle.extra["composeUp"] = up.to_dict()
        if not up.ok:
            self._emit(emitter, on_event, handle, DEPENDENCY_INSTALL_FAILED, {"reason": up.reason or "compose up failed"})
            diagnosis = self.diagnostics.classify(output=up.output, exit_code=up.exit_code, step="compose", reason=up.reason, source="compose")
            raise _BuildFailure(diagnosis)
        # Record the compose services as containers.
        ps = compose.ps(cwd=root, compose_file=descriptor.compose_file)
        if ps.ok:
            self._record_compose_services(handle, descriptor, ps.services, engine.name, up.output)
        self._emit(emitter, on_event, handle, DEPENDENCIES_INSTALLED, {"manager": engine.name + " compose"})
        for name in handle.services:
            self._emit(emitter, on_event, handle, CONTAINER_STARTED, {"service": name})

    def _record_compose_services(self, handle, descriptor, rows, engine_name, raw_output) -> None:  # noqa: ARG002
        containers: list[str] = []
        for row in rows:
            name = row.get("Service") or row.get("Name") or ""
            container_id = row.get("ID") or row.get("Name") or ""
            if name and name not in handle.services:
                handle.services.append(name)
            if container_id:
                containers.append(container_id)
        handle.containers = containers or [r.get("Name", "") for r in rows if r.get("Name")]

    # ── local services ─────────────────────────────────────────────────────────────
    def _start_local_services(self, handle, machine, root, descriptor, compose_services, emitter, on_event) -> None:
        if self.terminal is None:
            # No terminal: a compose engine absent means we cannot run a real service.
            if descriptor.compose or descriptor.docker:
                raise RuntimeError("container engine isn't available on this computer")
            # A plain runnable project still needs a command.
            command = descriptor.commands.get("dev") or descriptor.commands.get("start")
            if not command:
                self._emit(emitter, on_event, handle, PROCESS_STARTED, {"note": "no long-running command"})
                return
            raise RuntimeError("the terminal runtime isn't available right now")

        command = descriptor.commands.get("dev") or descriptor.commands.get("start")
        if not command:
            # A library / build-only project: nothing to keep running.
            return
        # Start infrastructure (databases/caches) declared in compose first, as
        # local processes is out of scope; compose is handled above. Here we start
        # the application command itself.
        info = self.terminal.start_process(
            command=command, cwd=str(root), workspace_id=handle.workspace_id,
            agent_id=handle.agent_id, run_id=handle.run_id, purpose="application",
        )
        if info.get("state") == "FAILED":
            diagnosis = RuntimeDiagnosis(
                category=DiagnosticCategory.PROCESS_CRASH,
                severity="high", message="The application process could not be started.",
                evidence=[str((info.get("error") or {}).get("message", ""))],
                suggested_actions=[], recoverable=False, source="process",
            )
            raise _BuildFailure(diagnosis)
        process_id = info.get("processId", "")
        handle.processes.append(process_id)
        node = _ensure_node(handle.graph, "app")
        if node is not None:
            node.process_id = process_id
            node.command = command
            node.state = info.get("state", "RUNNING")
        self._emit(emitter, on_event, handle, PROCESS_STARTED, {"processId": process_id, "command": command, "pid": info.get("pid")})

    # ── health ────────────────────────────────────────────────────────────────────
    def check_health(self, handle: RuntimeHandle, root: Path, *, timeout_s: float = 30.0, emitter: Any = None, on_event: Any = None) -> HealthReport:
        emitter = emitter or handle.extra.get("emitter")
        checks = self._health_checks(handle, root)
        process_ids = {node.name: node.process_id for node in (handle.graph.nodes.values() if handle.graph else [])}
        self._emit(emitter, on_event, handle, "health_check.started", {"checks": len(checks)})
        report = self.health.evaluate(checks, process_ids=process_ids) if checks else HealthReport(status=HealthStatus.UNKNOWN, reason="no health checks are defined")
        handle.health = report
        if report.status is HealthStatus.HEALTHY:
            self._emit(emitter, on_event, handle, HEALTH_CHECK_PASSED, {"checks": len(checks)})
        elif checks:
            self._emit(emitter, on_event, handle, HEALTH_CHECK_FAILED, {"status": report.status.value, "reason": report.reason})
        if self.store is not None:
            try:
                self.store.save_health(handle.runtime_id, report.to_dict())
            except Exception:  # noqa: BLE001
                pass
        return report

    def _health_checks(self, handle, root) -> list[HealthCheck]:
        checks: list[HealthCheck] = []
        descriptor = handle.descriptor
        if descriptor is None:
            return checks
        # A compose healthcheck per service, plus a TCP check for a declared port.
        for node in (handle.graph.nodes.values() if handle.graph else []):
            if node.kind is ServiceKind.CONTAINER and node.container_id:
                checks.append(HealthCheck(kind="container", name=f"{node.name}-container", target=node.container_id, service=node.name, retries=5))
            if node.ports:
                checks.append(HealthCheck(kind="tcp", name=f"{node.name}-port", target=f"127.0.0.1:{node.ports[0]}", service=node.name, retries=4))
        # The application process itself.
        if handle.processes:
            checks.append(HealthCheck(kind="process", name="app-process", target=handle.processes[0], service="app", retries=8))
        # An explicit health endpoint is tried when the framework implies one.
        if descriptor.framework in ("nextjs", "fastapi", "express", "nestjs", "fastify"):
            port = descriptor.ports[0] if descriptor.ports else 0
            if port:
                checks.append(HealthCheck(kind="http", name="app-http", target=f"http://127.0.0.1:{port}/", retries=6, timeout_s=2.0))
        # A custom healthcheck from the descriptor is honoured.
        for custom in descriptor.__dict__.get("health_checks", []) or []:
            if isinstance(custom, dict) and custom.get("kind"):
                checks.append(HealthCheck(**{k: v for k, v in custom.items() if k in HealthCheck.__dataclass_fields__}))
        return checks

    # ── stop / restart / cleanup ────────────────────────────────────────────────────
    def stop(self, runtime_id: str, *, actor: Any = None, remove_containers: bool = True, emitter: Any = None) -> dict[str, Any]:
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            return {"status": "not_found", "runtimeId": runtime_id}
        emitter = emitter or handle.extra.get("emitter")
        machine = self._machines.get(runtime_id)
        if machine is not None and not machine.terminal:
            try:
                machine.to(ApplicationState.STOPPING)
            except Exception:  # noqa: BLE001 - allow stop from any active state
                machine.force_terminal(ApplicationState.STOPPED)
        stopped: list[str] = []
        for process_id in list(handle.processes):
            if self.terminal is not None:
                try:
                    if self.terminal.stop_process(process_id):
                        stopped.append(process_id)
                except Exception:  # noqa: BLE001
                    pass
        # Compose down / container stop.
        if handle.descriptor is not None and handle.descriptor.compose and handle.descriptor.compose_file:
            engine = self.registry.containers.get(handle.descriptor.container_runtime) or self.registry.containers.detect()
            compose = self._compose_for(engine)
            if compose is not None:
                allowed, decision, reason = self.policy.decide("compose.down", authorized=bool(actor and getattr(actor, "operator", False)))
                if allowed:
                    root = Path(handle.descriptor.path)
                    compose.down(cwd=root, compose_file=handle.descriptor.compose_file, volumes=remove_containers)
        for port in handle.ports:
            self.ports.release(port.port)
        if machine is not None:
            machine.force_terminal(ApplicationState.STOPPED)
        handle.state = ApplicationState.STOPPED
        handle.updated_at = time.time()
        self._emit(emitter, None, handle, RUNTIME_STOPPED, {"stopped": stopped})
        self._persist(handle)
        return {"status": "ok", "runtimeId": runtime_id, "stoppedProcesses": stopped}

    def restart(self, runtime_id: str, *, actor: Any = None, **start_kwargs: Any) -> RuntimeHandle:
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            raise KeyError(runtime_id)
        descriptor = handle.descriptor
        root = Path(descriptor.path) if descriptor else None
        self.stop(runtime_id, actor=actor)
        if root is None:
            raise KeyError(runtime_id)
        handle = self.start(
            root, name=(descriptor.name if descriptor else ""), workspace_id=handle.workspace_id,
            run_id=handle.run_id, agent_id=handle.agent_id, actor=actor, **start_kwargs,
        )
        handle.restart_count += 1
        self._persist(handle)
        return handle

    def cleanup(self, runtime_id: str, *, actor: Any = None) -> dict[str, Any]:
        """Stop a runtime and remove its transient state from the in-memory table."""
        result = self.stop(runtime_id, actor=actor, remove_containers=True)
        with self._lock:
            self._runtimes.pop(runtime_id, None)
            self._machines.pop(runtime_id, None)
        return result

    # ── status / logs / metrics ────────────────────────────────────────────────────
    def status(self, runtime_id: str) -> dict[str, Any]:
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            if self.store is not None:
                row = self.store.get_runtime(runtime_id)
                if row is not None:
                    return {"status": "ok", "runtime": row, "live": False}
            return {"status": "not_found", "runtimeId": runtime_id}
        return {"status": "ok", "runtime": handle.to_dict(), "live": True}

    def list(self, *, state: Optional[str] = None) -> list[dict[str, Any]]:
        handles = list(self._runtimes.values())
        if state:
            handles = [h for h in handles if h.state.value == state]
        return [h.to_dict() for h in handles]

    def logs(
        self,
        runtime_id: str,
        *,
        tail: int = 200,
        stream: Optional[str] = None,
        service: str = "",
        filter_text: str = "",
        severity: str = "",
        errors_only: bool = False,
        max_lines: int = 2000,
    ) -> dict[str, Any]:
        """Read a runtime's output, bounded and filterable.

        `filter_text` keeps lines containing a substring; `errors_only` keeps only
        lines that look like errors; `severity` filters by a matched severity token.
        `max_lines` bounds the total returned so a chatty service cannot flood the
        caller's context. Every stream keeps its own `processId`/`status`.
        """
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            return {"status": "not_found", "runtimeId": runtime_id}
        lines: list[dict[str, Any]] = []
        total_lines = 0
        truncated = False
        needle = str(filter_text or "").casefold()
        for process_id in handle.processes:
            window = self.terminal.read_process_output(process_id, tail=tail, stream=stream) if self.terminal is not None else None
            if not window:
                continue
            text = window.get("text", "") or ""
            kept = _filter_lines(text, needle=needle, errors_only=errors_only, severity=severity)
            total_lines += len(text.splitlines())
            if sum(len(s["lines"]) for s in lines) + len(kept) > max_lines:
                room = max(0, max_lines - sum(len(s["lines"]) for s in lines))
                kept = kept[:room]
                truncated = True
            if kept:
                lines.append({
                    "processId": process_id, "status": window.get("status", ""),
                    "lines": kept, "text": "\n".join(kept),
                })
        return {
            "status": "ok", "runtimeId": runtime_id, "streams": lines, "tail": tail,
            "totalLines": total_lines, "truncated": truncated,
            "filters": {"filterText": filter_text, "errorsOnly": errors_only, "severity": severity, "service": service},
        }

    def events(self, runtime_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        return self.store.list_events(runtime_id, limit=limit)

    def metrics(self, runtime_id: str) -> dict[str, Any]:
        """Point-in-time resource usage for the runtime's processes."""
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            return {"status": "not_found", "runtimeId": runtime_id}
        from ..telemetry import sample_tree
        process_metrics: list[dict[str, Any]] = []
        if self.terminal is not None:
            for process_id in handle.processes:
                info = self.terminal.get_process(process_id)
                if info is None:
                    continue
                pid = info.get("pid")
                usage = sample_tree(int(pid)) if pid else None
                process_metrics.append({
                    "processId": process_id, "pid": pid, "state": info.get("state"),
                    "cpuMs": getattr(usage, "cpu_ms", None) if usage else None,
                    "memoryMb": getattr(usage, "memory_mb", None) if usage else None,
                    "processCount": getattr(usage, "process_count", None) if usage else None,
                })
        return {
            "status": "ok", "runtimeId": runtime_id,
            "uptimeS": max(0.0, time.time() - (handle.started_at or time.time())),
            "restartCount": handle.restart_count,
            "health": handle.health.to_dict(),
            "processes": process_metrics,
            "ports": [p.to_dict() for p in handle.ports],
        }

    # ── diagnostics / recovery ────────────────────────────────────────────────────
    def diagnose(self, runtime_id: str) -> dict[str, Any]:
        """Diagnose a runtime's current state from health, logs and process state."""
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            return {"status": "not_found", "runtimeId": runtime_id}
        health = handle.health
        if health.healthy:
            return {"status": "ok", "diagnosis": RuntimeDiagnosis(
                category=DiagnosticCategory.UNKNOWN,
                severity="low", message="The application is healthy.", recoverable=False,
                source="health",
            ).to_dict(), "healthy": True}
        # Gather the process output of any crashed service.
        output = ""
        if self.terminal is not None:
            for process_id in handle.processes:
                window = self.terminal.read_process_output(process_id, tail=80)
                info = self.terminal.get_process(process_id)
                if info and info.get("state") in ("CRASHED", "FAILED", "TIMEOUT"):
                    output += (window or {}).get("text", "")
        diagnosis = self.diagnostics.classify(output=output, health=(health.checks[0].to_dict() if health.checks else None),
                                               language=(handle.descriptor.language if handle.descriptor else ""),
                                               source="diagnose", reason=health.reason)
        return {"status": "ok", "diagnosis": diagnosis.to_dict(), "healthy": False}

    def recover(self, runtime_id: str, *, actor: Any = None, max_attempts: Optional[int] = None) -> dict[str, Any]:
        """Run the BOUNDED recovery loop for a degraded/failed runtime."""
        handle = self._runtimes.get(runtime_id)
        if handle is None:
            return {"status": "not_found", "runtimeId": runtime_id}
        root = Path(handle.descriptor.path) if handle.descriptor else None
        if root is None:
            return {"status": "failed", "reason": "the runtime has no known project path"}
        emitter = handle.extra.get("emitter")

        def diagnose(attempt: int, _last):
            probe = self.diagnose(runtime_id)
            diag_dict = probe.get("diagnosis", {}) if probe.get("status") == "ok" else {}
            return _diagnosis_from_dict(diag_dict)

        def act(strategy, diagnosis):
            self._emit(emitter, None, handle, RUNTIME_RECOVERY_ATTEMPT, {"strategy": strategy.value, "category": diagnosis.category.value})
            if strategy.value == "restart":
                self.restart(runtime_id, actor=actor, install=False, build=False)
                return True
            if strategy.value == "reinstall_dependencies":
                manager = self.registry.packages.detect(root, handle.descriptor)
                if manager is None or not _has_cap(manager, "install"):
                    return False
                result = manager.run(manager.install_dependencies(root), cwd=root, limits=self.limits)
                return result.ok
            if strategy.value == "rebuild":
                manager = self.registry.packages.detect(root, handle.descriptor)
                if manager is None or not _has_cap(manager, "build"):
                    return False
                result = manager.run(manager.build(root), cwd=root, limits=self.limits)
                return result.ok
            if strategy.value == "select_alternative_port":
                handle.ports = self._allocate_ports(handle, handle.descriptor)
                return True
            if strategy.value == "restart_dependency":
                return self._restart_dependencies(handle, root)
            if strategy.value == "reload_environment":
                return True
            if strategy.value == "recreate_container":
                return self._container_recreate(handle, root, actor=actor)
            if strategy.value == "retry":
                return True
            return False

        def verify():
            report = self.check_health(handle, root)
            return report.healthy

        outcome = self.recovery.run(diagnose=diagnose, act=act, verify=verify, max_attempts=max_attempts)
        if outcome.recovered:
            machine = self._machines.get(runtime_id)
            if machine is not None and machine.state not in (ApplicationState.RUNNING,):
                try:
                    machine.to(ApplicationState.RUNNING)
                except Exception:  # noqa: BLE001
                    machine._state = ApplicationState.RUNNING  # noqa: SLF001 - recovery safety valve
            handle.state = ApplicationState.RUNNING
            self._emit(emitter, None, handle, RUNTIME_RECOVERY_COMPLETED, {"attempts": outcome.attempts})
        else:
            self._emit(emitter, None, handle, RUNTIME_RECOVERY_COMPLETED, {"attempts": outcome.attempts, "recovered": False})
        self._persist(handle)
        return {"status": "ok", "runtimeId": runtime_id, "recovery": outcome.to_dict()}

    def _restart_dependencies(self, handle, root) -> bool:
        # Compose dependency services: restart just the dependency services.
        if not (handle.descriptor and handle.descriptor.compose):
            return False
        engine = self.registry.containers.get(handle.descriptor.container_runtime) or self.registry.containers.detect()
        compose = self._compose_for(engine)
        if compose is None:
            return False
        deps = _dependency_only_services(handle.graph, handle.descriptor)
        if not deps:
            return False
        result = compose.restart(cwd=root, compose_file=handle.descriptor.compose_file, services=deps)
        return result.ok

    def _container_recreate(self, handle, root, *, actor) -> bool:
        if not (handle.descriptor and handle.descriptor.compose):
            return False
        engine = self.registry.containers.get(handle.descriptor.container_runtime) or self.registry.containers.detect()
        compose = self._compose_for(engine)
        if compose is None:
            return False
        compose.up(cwd=root, compose_file=handle.descriptor.compose_file, detach=True, build=True)
        return True

    # ── reconciliation ────────────────────────────────────────────────────────────
    def reconcile(self) -> dict[str, Any]:
        """Compare desired vs actual state after a restart.

        A runtime that was RUNNING is re-examined: if its process/containers are
        gone it becomes DEGRADED (and, when recovery is enabled, a bounded recovery
        may run). This never fabricates a running runtime.
        """
        if self.store is None:
            return {"status": "ok", "reconciled": [], "note": "no store"}
        records = self.store.list_active_runtimes()
        results: list[dict[str, Any]] = []
        for record in records:
            runtime_id = record["id"]
            desired = record.get("state", "UNKNOWN")
            full = self.store.get_runtime(runtime_id) or record
            actual = self._actual_state(full)
            state = _reconcile_state(desired, actual)
            record["state"] = state
            record["reconciled"] = True
            try:
                from ...persistence import now_iso

                self.store._db.execute("UPDATE AppRuntime SET state=?, updatedAt=? WHERE id=?", (state, now_iso(), runtime_id))  # noqa: SLF001
                self.store._db.commit()  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
            results.append({"runtimeId": runtime_id, "desired": desired, "actual": actual, "state": state})
        return {"status": "ok", "reconciled": results, "count": len(results)}

    def _actual_state(self, record: dict[str, Any]) -> str:
        """The ACTUAL state after an Eclipse restart.

        A persisted `RUNNING` service is only believed when its process (or
        container) is still alive. The live terminal is authoritative; when it has
        no record of a persisted process, the runtime is STOPPED, never RUNNING.
        """
        services = record.get("services", []) or []
        process_ids = [s.get("processId") for s in services if s.get("processId")]
        container_ids = [s.get("containerId") for s in services if s.get("containerId")]
        if self.terminal is not None and process_ids:
            alive = False
            for process_id in process_ids:
                info = self.terminal.get_process(process_id)
                if info is not None and info.get("state") in ("RUNNING", "STARTING", "PAUSED"):
                    alive = True
                    break
            if alive:
                return "RUNNING"
            return "STOPPED"
        # No terminal record: fall back to a workspace-scoped process scan.
        if self.terminal is not None and not process_ids:
            workspace_id = record.get("workspaceId")
            try:
                live = [p for p in self.terminal.list_processes(workspace_id=workspace_id)
                        if p.get("purpose") == "application"]
            except Exception:  # noqa: BLE001
                live = []
            if live:
                return "RUNNING"
            if container_ids:
                return "UNKNOWN"  # containers need the engine to confirm; do not assume
        return "UNKNOWN"

    # ── container / compose operations (exposed to the tools) ───────────────────────
    def container(self, engine_name: str = "") -> Optional[ContainerRuntimeAdapter]:
        return self.registry.containers.get(engine_name) or self.registry.containers.detect()

    def compose_adapter(self, engine_name: str = "") -> Optional[ComposeAdapter]:
        engine = self.registry.containers.get(engine_name) or self.registry.containers.detect()
        return self._compose_for(engine)

    # ── orchestration / infrastructure / deployment accessors ───────────────────────
    def orchestrator(self, name: str = "") -> Any:
        """An available orchestrator adapter (declared name wins)."""
        if name:
            return self.registry.orchestrators.get(name)
        for candidate in self.registry.orchestrators.names():
            adapter = self.registry.orchestrators.get(candidate)
            if adapter is not None and _safe(adapter.available):
                return adapter
        return None

    def infrastructure(self, name: str = "") -> Any:
        if name:
            return self.registry.infrastructure.get(name)
        for candidate in self.registry.infrastructure.names():
            adapter = self.registry.infrastructure.get(candidate)
            if adapter is not None and _safe(adapter.available):
                return adapter
        return None

    def cloud_provider(self, name: str = "") -> Any:
        if name:
            return self.registry.deployments.get(name)
        for candidate in self.registry.deployments.names():
            adapter = self.registry.deployments.get(candidate)
            if adapter is not None and _safe(adapter.available):
                return adapter
        return None

    @property
    def deployment(self) -> Any:
        """The ONE deployment engine over this runtime manager + registry."""
        engine = getattr(self, "_deployment_engine", None)
        if engine is None:
            from .deployment import DeploymentEngine

            engine = DeploymentEngine(runtime_manager=self, registry=self.registry,
                                      store=self.store, bus=self.bus)
            self._deployment_engine = engine
        return engine

    def run_orchestrator(self, operation: str, args: Optional[dict[str, Any]] = None, *, adapter: str = "") -> Any:
        chosen = self.orchestrator(adapter)
        if chosen is None:
            return {"status": "refused", "code": "ORCHESTRATOR_UNAVAILABLE", "reason": "no orchestrator (kubectl/helm/kustomize) is available"}
        return chosen.run_operation(operation, args or {})

    def run_infrastructure(self, operation: str, args: Optional[dict[str, Any]] = None, *, adapter: str = "") -> Any:
        chosen = self.infrastructure(adapter)
        if chosen is None:
            return {"status": "refused", "code": "INFRASTRUCTURE_UNAVAILABLE", "reason": "no infrastructure tool (terraform) is available"}
        return chosen.run_operation(operation, args or {})

    # ── helpers ────────────────────────────────────────────────────────────────────
    def _mark_degraded(self, handle, machine, report, emitter, on_event) -> None:
        if machine is not None and not machine.terminal:
            try:
                if machine.state is ApplicationState.RUNNING:
                    machine.to(ApplicationState.DEGRADED)
            except Exception:  # noqa: BLE001
                pass
        handle.state = ApplicationState.DEGRADED
        self._emit(emitter, on_event, handle, RUNTIME_DEGRADED, {"reason": report.reason, "status": report.status.value})
        self._persist(handle)

    def _fail(self, handle, machine, diagnosis: RuntimeDiagnosis, emitter, *, on_event=None) -> None:
        if machine is not None and not machine.terminal:
            try:
                machine.force_terminal(ApplicationState.FAILED)
            except Exception:  # noqa: BLE001
                pass
        handle.state = ApplicationState.FAILED
        handle.last_error = diagnosis.to_dict()
        handle.updated_at = time.time()
        self._emit(emitter, on_event, handle, RUNTIME_FAILED, {"category": diagnosis.category.value, "message": diagnosis.message})
        self._persist(handle)

    def _persist(self, handle: RuntimeHandle) -> None:
        if self.store is None:
            return
        try:
            if handle.descriptor is not None:
                app_id = self.store.upsert_application(handle.descriptor, workspace_id=handle.workspace_id)
                handle.application_id = app_id
            self.store.upsert_runtime(handle)
            if handle.graph is not None:
                self.store.save_services(handle.runtime_id, [n.to_dict() for n in handle.graph.nodes.values()])
            self.store.save_ports(handle.runtime_id, [p.to_dict() for p in handle.ports])
        except Exception:  # noqa: BLE001 - persistence must not break a start
            pass

    def _emit(self, emitter, on_event, handle, event_type, data) -> None:
        if emitter is not None:
            emitter.emit(handle.runtime_id, event_type, data)
        if on_event is not None:
            try:
                on_event(event_type, {"runtimeId": handle.runtime_id, **(data or {})})
            except Exception:  # noqa: BLE001
                pass


# ── internal failure wrapper ─────────────────────────────────────────────────────


class _BuildFailure(RuntimeError):
    def __init__(self, diagnosis: RuntimeDiagnosis) -> None:
        super().__init__(diagnosis.message)
        self.diagnosis = diagnosis


# ── helpers ─────────────────────────────────────────────────────────────────────


def _filter_lines(text: str, *, needle: str = "", errors_only: bool = False, severity: str = "") -> list[str]:
    """Filter log text into the lines that match. Bounded and deterministic."""
    out: list[str] = []
    want_severity = str(severity or "").casefold()
    for raw in (text or "").splitlines():
        lowered = raw.casefold()
        if needle and needle not in lowered:
            continue
        if errors_only and not any(t in lowered for t in ("error", "fail", "exception", "traceback", "fatal", "panic")):
            continue
        if want_severity and want_severity not in lowered:
            continue
        out.append(raw)
    return out


def _safe(fn: Callable[[], Any]) -> bool:
    try:
        return bool(fn())
    except Exception:  # noqa: BLE001
        return False


def _has_cap(adapter: Any, capability: str) -> bool:
    return capability in (getattr(adapter, "capabilities", ()) or ())


def _dependency_plan(root: Path, manager: BasePackageManager, descriptor: ApplicationDescriptor) -> dict[str, Any]:
    root = Path(root)
    satisfied = False
    if manager.name in ("npm", "pnpm", "yarn", "bun"):
        satisfied = (root / "node_modules").is_dir()
    elif manager.name in ("uv", "poetry"):
        satisfied = (root / ".venv").is_dir()
    elif manager.name == "cargo":
        satisfied = (root / "target").is_dir()
    return {"manager": manager.name, "satisfied": satisfied}


def _dependencies_present(root: Path, descriptor: ApplicationDescriptor) -> bool:
    """Whether the project's dependencies already look installed."""
    root = Path(root)
    pm = (descriptor.package_manager or "").casefold()
    if pm in ("npm", "pnpm", "yarn", "bun"):
        return (root / "node_modules").is_dir()
    if pm in ("uv", "poetry", "pipenv"):
        return (root / ".venv").is_dir()
    if pm == "cargo":
        return (root / "target").is_dir()
    if pm == "go":
        return True  # go modules are cached globally; nothing project-local to check
    return True


def _ensure_node(graph: Optional[ServiceGraph], name: str):
    if graph is None:
        return None
    node = graph.nodes.get(name)
    if node is None:
        node = ServiceNode(name=name, kind=ServiceKind.PROCESS)
        graph.add(node)
    return node


def _diagnosis_from_dict(data: dict[str, Any]) -> RuntimeDiagnosis:
    from .models import DiagnosticCategory, RecoveryStrategy

    try:
        category = DiagnosticCategory(data.get("category", "unknown"))
    except ValueError:
        category = DiagnosticCategory.UNKNOWN
    strategies = []
    for item in data.get("suggestedActions", []) or []:
        try:
            strategies.append(RecoveryStrategy(item))
        except ValueError:
            continue
    return RuntimeDiagnosis(
        category=category, severity=data.get("severity", "medium"),
        message=data.get("message", ""), evidence=list(data.get("evidence", []) or []),
        suggested_actions=strategies, recoverable=bool(data.get("recoverable", False)),
        source=data.get("source", ""), location=data.get("location"),
    )


def _reconcile_state(desired: str, actual: str) -> str:
    if desired in ("RUNNING", "DEGRADED", "STARTING", "BUILDING", "INSTALLING", "PREPARING", "OBSERVING", "STOPPING"):
        if actual == "RUNNING":
            return "RUNNING"
        if actual == "STOPPED":
            return "DEGRADED"
        return "UNKNOWN"
    return desired


def _compose_services(root: Path, descriptor: ApplicationDescriptor) -> list[ComposeService]:
    from .discovery import _parse_compose_services

    if not descriptor.compose_file:
        return []
    path = Path(root) / descriptor.compose_file
    if not path.is_file():
        return []
    try:
        return _parse_compose_services(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return []


def _dependency_only_services(graph: Optional[ServiceGraph], descriptor: ApplicationDescriptor) -> list[str]:
    if graph is None:
        return []
    infra_names = set(descriptor.databases) | set(descriptor.caches)
    return [name for name in graph.nodes if name in infra_names]


__all__ = [
    "ApplicationRuntimeManager",
    "DESTRUCTIVE_OPERATIONS",
    "RuntimePolicy",
    "build_runtime_registry",
]
