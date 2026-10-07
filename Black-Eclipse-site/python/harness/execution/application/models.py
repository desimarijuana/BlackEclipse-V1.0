"""Application Runtime domain model — the vocabulary of the runtime layer.

These types describe an *application* (not a language execution): its shape
(language, framework, package manager, commands, containers, services, ports,
environment) and its live *runtime* (state, processes, containers, services,
health). They are dataclasses, deliberately free of any provider SDK, so the
core stays import-light and every adapter speaks the same vocabulary.

Nothing here executes anything. Discovery builds a descriptor; the runtime
manager drives the lifecycle; the adapters only *describe* argv/output. This
mirrors the execution layer's `models.py`, extended one level up: an application
owns one or more services, each of which may be a local process or a container.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── Lifecycle state ───────────────────────────────────────────────────────────
#
# An application's state is explicit and never a boolean. `RUNNING` means the
# application's processes/containers exist; `HEALTHY` is a separate assertion
# made only by a passing health check. The two are never conflated.


class ApplicationState(str, Enum):
    """The lifecycle state of one application runtime."""

    DISCOVERING = "DISCOVERING"
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    PREPARING = "PREPARING"
    INSTALLING = "INSTALLING"
    BUILDING = "BUILDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    OBSERVING = "OBSERVING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


ACTIVE_STATES = frozenset(
    {
        ApplicationState.DISCOVERING,
        ApplicationState.VALIDATING,
        ApplicationState.PREPARING,
        ApplicationState.INSTALLING,
        ApplicationState.BUILDING,
        ApplicationState.STARTING,
        ApplicationState.RUNNING,
        ApplicationState.DEGRADED,
        ApplicationState.OBSERVING,
        ApplicationState.STOPPING,
    }
)

TERMINAL_STATES = frozenset(
    {
        ApplicationState.STOPPED,
        ApplicationState.FAILED,
    }
)


def is_active(state: ApplicationState) -> bool:
    return state in ACTIVE_STATES


def is_terminal(state: ApplicationState) -> bool:
    return state in TERMINAL_STATES


# ── Health ─────────────────────────────────────────────────────────────────────


class HealthStatus(str, Enum):
    """The result of a health check. `process_running != application_healthy`."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


@dataclass
class HealthCheck:
    """A single health check definition."""

    kind: str = "process"              # process | tcp | http | container | database | custom
    name: str = ""
    target: str = ""                   # url, "host:port", pid ref, db dsn alias, or a custom id
    expected_status: int = 0           # for http
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    timeout_s: float = 3.0
    interval_s: float = 0.5
    retries: int = 20
    service: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "name": self.name, "target": self.target,
            "expectedStatus": self.expected_status, "method": self.method,
            "headers": dict(self.headers), "body": self.body,
            "timeoutS": self.timeout_s, "intervalS": self.interval_s,
            "retries": self.retries, "service": self.service,
        }


@dataclass
class HealthResult:
    """The result of one health check attempt."""

    check: str = ""
    kind: str = "process"
    status: HealthStatus = HealthStatus.UNKNOWN
    ok: bool = False
    detail: str = ""
    latency_ms: int = 0
    attempts: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check, "kind": self.kind, "status": self.status.value,
            "ok": self.ok, "detail": self.detail, "latencyMs": self.latency_ms,
            "attempts": self.attempts, "evidence": self.evidence,
        }


@dataclass
class HealthReport:
    """The aggregate health of an application runtime."""

    status: HealthStatus = HealthStatus.UNKNOWN
    checks: list[HealthResult] = field(default_factory=list)
    reason: str = ""

    @property
    def healthy(self) -> bool:
        return self.status is HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "healthy": self.healthy,
            "checks": [c.to_dict() for c in self.checks],
            "reason": self.reason,
        }


# ── Ports ──────────────────────────────────────────────────────────────────────


@dataclass
class PortRecord:
    """One port an application declared or is using."""

    port: int
    host: str = "127.0.0.1"
    purpose: str = ""
    source: str = ""                    # "declared" | "allocated" | "discovered"
    service: str = ""
    pid: Optional[int] = None
    process_id: Optional[str] = None
    protocol: str = "tcp"

    @property
    def known_services(self) -> str:
        return _COMMON_PORT_SERVICES.get(self.port, "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port, "host": self.host, "purpose": self.purpose,
            "source": self.source, "service": self.service, "pid": self.pid,
            "processId": self.process_id, "protocol": self.protocol,
            "likelyService": self.known_services,
        }


#: Ports with well-known owners, used to DECORATE a report (never to filter).
_COMMON_PORT_SERVICES: dict[int, str] = {
    3000: "Next.js / Node dev server", 3001: "Next.js (alt)", 4200: "Angular",
    5173: "Vite", 5432: "PostgreSQL", 3306: "MySQL", 6379: "Redis",
    8000: "FastAPI / Django", 8080: "HTTP alt", 27017: "MongoDB",
    5672: "RabbitMQ", 9200: "Elasticsearch", 1433: "SQL Server",
}


# ── Services / service graph ──────────────────────────────────────────────────


class ServiceKind(str, Enum):
    PROCESS = "process"
    CONTAINER = "container"
    EXTERNAL = "external"


@dataclass
class ServiceNode:
    """One service an application is composed of (a process, container or dependency)."""

    name: str
    kind: ServiceKind = ServiceKind.PROCESS
    command: str = ""
    image: str = ""
    container_id: str = ""
    process_id: str = ""
    ports: list[int] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    state: str = "UNKNOWN"
    health: str = HealthStatus.UNKNOWN.value
    compose: bool = False
    env: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind.value, "command": self.command,
            "image": self.image, "containerId": self.container_id,
            "processId": self.process_id, "ports": list(self.ports),
            "dependsOn": list(self.depends_on), "state": self.state,
            "health": self.health, "compose": self.compose, "notes": self.notes,
        }


@dataclass
class ServiceGraph:
    """A normalized dependency graph over an application's services."""

    nodes: dict[str, ServiceNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)

    def add(self, node: ServiceNode) -> None:
        self.nodes[node.name] = node
        for dep in node.depends_on:
            if (dep, node.name) not in self.edges:
                self.edges.append((dep, node.name))

    def dependencies_of(self, name: str) -> list[str]:
        return [src for src, dst in self.edges if dst == name]

    def dependents_of(self, name: str) -> list[str]:
        return [dst for src, dst in self.edges if src == name]

    def startup_order(self) -> list[str]:
        """A deterministic topological order: dependencies before dependents.

        A cycle is broken honestly: the remaining nodes are appended in sorted
        order rather than looping forever.
        """
        order: list[str] = []
        visited: set[str] = set()
        temp: set[str] = set()

        def visit(name: str) -> None:
            if name in visited or name not in self.nodes:
                return
            if name in temp:
                return  # cycle guard
            temp.add(name)
            for dep in sorted(self.dependencies_of(name)):
                visit(dep)
            temp.discard(name)
            visited.add(name)
            order.append(name)

        for name in sorted(self.nodes):
            visit(name)
        for name in sorted(self.nodes):
            if name not in visited:
                order.append(name)
        return order

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [{"from": a, "to": b} for a, b in self.edges],
            "startupOrder": self.startup_order(),
        }


# ── Discovery descriptor ──────────────────────────────────────────────────────


@dataclass
class ApplicationDescriptor:
    """The normalized shape of a project, as discovered from disk."""

    name: str = ""
    path: str = ""
    language: str = ""
    framework: str = ""
    runtime: str = ""
    package_manager: str = ""
    package_manager_version: str = ""
    lockfile: str = ""
    manifests: list[str] = field(default_factory=list)
    docker: bool = False
    compose: bool = False
    compose_file: str = ""
    dockerfiles: list[str] = field(default_factory=list)
    container_runtime: str = ""        # "docker" | "podman" | ""
    commands: dict[str, str] = field(default_factory=dict)
    services: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    env_files: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    caches: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    test_framework: str = ""
    entrypoint: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "path": self.path, "language": self.language,
            "framework": self.framework, "runtime": self.runtime,
            "packageManager": self.package_manager,
            "packageManagerVersion": self.package_manager_version,
            "lockfile": self.lockfile, "manifests": list(self.manifests),
            "docker": self.docker, "compose": self.compose,
            "composeFile": self.compose_file, "dockerfiles": list(self.dockerfiles),
            "containerRuntime": self.container_runtime,
            "commands": dict(self.commands), "services": list(self.services),
            "ports": list(self.ports), "envFiles": list(self.env_files),
            "requiredEnv": list(self.required_env), "databases": list(self.databases),
            "caches": list(self.caches), "frameworks": list(self.frameworks),
            "testFramework": self.test_framework, "entrypoint": self.entrypoint,
            "description": self.description,
        }


# ── Runtime handle ─────────────────────────────────────────────────────────────


@dataclass
class RuntimeHandle:
    """The live handle of one running application."""

    runtime_id: str
    application_id: str
    state: ApplicationState = ApplicationState.UNKNOWN
    descriptor: Optional[ApplicationDescriptor] = None
    graph: Optional[ServiceGraph] = None
    services: list[str] = field(default_factory=list)
    ports: list[PortRecord] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)
    health: HealthReport = field(default_factory=HealthReport)
    started_at: float = 0.0
    updated_at: float = 0.0
    workspace_id: Optional[str] = None
    run_id: str = ""
    agent_id: Optional[str] = None
    owner: str = ""
    restart_count: int = 0
    last_error: Optional[dict[str, Any]] = None
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtimeId": self.runtime_id,
            "applicationId": self.application_id,
            "state": self.state.value,
            "descriptor": self.descriptor.to_dict() if self.descriptor else None,
            "serviceGraph": self.graph.to_dict() if self.graph else None,
            "services": list(self.services),
            "ports": [p.to_dict() for p in self.ports],
            "processes": list(self.processes),
            "containers": list(self.containers),
            "health": self.health.to_dict(),
            "startedAt": self.started_at,
            "updatedAt": self.updated_at,
            "workspaceId": self.workspace_id,
            "runId": self.run_id,
            "agentId": self.agent_id,
            "owner": self.owner,
            "restartCount": self.restart_count,
            "lastError": self.last_error,
            "warnings": list(self.warnings),
            "extra": dict(self.extra),
        }


def new_runtime_id() -> str:
    return "rt_" + uuid.uuid4().hex[:16]


def new_application_id() -> str:
    return "app_" + uuid.uuid4().hex[:16]


def now() -> float:
    return time.time()


# ── Diagnostics / recovery ─────────────────────────────────────────────────────


class DiagnosticCategory(str, Enum):
    """The classified cause of a runtime failure."""

    COMMAND_NOT_FOUND = "command_not_found"
    RUNTIME_MISSING = "runtime_missing"
    DEPENDENCY_FAILURE = "dependency_failure"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    PORT_CONFLICT = "port_conflict"
    PERMISSION_DENIED = "permission_denied"
    ENVIRONMENT_MISSING = "environment_missing"
    ENVIRONMENT_INVALID = "environment_invalid"
    BUILD_FAILURE = "build_failure"
    PROCESS_CRASH = "process_crash"
    CONTAINER_CRASH = "container_crash"
    CONTAINER_HEALTH_FAILURE = "container_health_failure"
    DATABASE_UNAVAILABLE = "database_unavailable"
    NETWORK_FAILURE = "network_failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    """A bounded recovery action for a diagnosed failure."""

    RETRY = "retry"
    RESTART = "restart"
    REINSTALL_DEPENDENCIES = "reinstall_dependencies"
    REBUILD = "rebuild"
    SELECT_ALTERNATIVE_PORT = "select_alternative_port"
    RESTART_DEPENDENCY = "restart_dependency"
    RELOAD_ENVIRONMENT = "reload_environment"
    RECREATE_CONTAINER = "recreate_container"
    NONE = "none"


@dataclass
class RuntimeDiagnosis:
    """A structured diagnosis of a runtime failure — never just "command failed"."""

    category: DiagnosticCategory = DiagnosticCategory.UNKNOWN
    severity: str = "medium"           # low | medium | high | critical
    message: str = ""
    evidence: list[str] = field(default_factory=list)
    suggested_actions: list[RecoveryStrategy] = field(default_factory=list)
    recoverable: bool = False
    source: str = ""
    location: Optional[dict[str, Any]] = None   # {file,line,column} for code intelligence

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value, "severity": self.severity,
            "message": self.message, "evidence": list(self.evidence),
            "suggestedActions": [a.value for a in self.suggested_actions],
            "recoverable": self.recoverable, "source": self.source,
            "location": self.location,
        }


@dataclass
class RecoveryAttempt:
    """One bounded recovery attempt, recorded for audit."""

    attempt: int
    strategy: RecoveryStrategy
    diagnosis: RuntimeDiagnosis
    success: bool = False
    detail: str = ""
    at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt, "strategy": self.strategy.value,
            "diagnosis": self.diagnosis.to_dict(), "success": self.success,
            "detail": self.detail, "at": self.at,
        }


__all__ = [
    "ACTIVE_STATES",
    "ApplicationDescriptor",
    "ApplicationState",
    "DiagnosticCategory",
    "HealthCheck",
    "HealthReport",
    "HealthResult",
    "HealthStatus",
    "PortRecord",
    "RecoveryAttempt",
    "RecoveryStrategy",
    "RuntimeDiagnosis",
    "RuntimeHandle",
    "ServiceGraph",
    "ServiceKind",
    "ServiceNode",
    "TERMINAL_STATES",
    "is_active",
    "is_terminal",
    "new_application_id",
    "new_runtime_id",
    "now",
]
