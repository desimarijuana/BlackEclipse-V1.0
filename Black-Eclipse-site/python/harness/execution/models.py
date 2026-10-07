"""Execution domain models — the strongly-typed requests, contexts and results.

These dataclasses are the vocabulary of the whole execution layer. They are
deliberately free of pydantic so the core stays import-light and usable from
`service.py` boot; the agent tool surface validates its inputs with pydantic
separately (the established pattern for `command_run`, `analysis_run`, …).

Reused types: the code workspace binding (`code.policy.WorkspaceBinding`) and the
sandbox run spec (`code.sandbox.RunSpec`) are NOT duplicated here — an
`ExecutionContext` carries a `WorkspaceBinding` and the orchestrator builds a
`RunSpec` from it. This keeps the ONE execution primitive authoritative.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..code.policy import WorkspaceBinding


class ExecutionMode(str, Enum):
    """What an execution is for. Drives which engine (build/test) runs."""

    RUN = "RUN"
    BUILD = "BUILD"
    TEST = "TEST"
    BUILD_AND_TEST = "BUILD_AND_TEST"
    WORKFLOW = "WORKFLOW"


class NetworkPolicy(str, Enum):
    """How much network a child may reach. Default is NONE, fail-closed."""

    NONE = "NONE"
    LOCAL_ONLY = "LOCAL_ONLY"
    ALLOWLIST = "ALLOWLIST"
    FULL = "FULL"


class FilesystemPolicy(str, Enum):
    """How much of the filesystem a child may touch."""

    READ_ONLY = "READ_ONLY"
    WORKSPACE_READ_WRITE = "WORKSPACE_READ_WRITE"
    ISOLATED = "ISOLATED"


class RiskLevel(str, Enum):
    """The risk band of an execution, used by the policy engine."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ErrorClass(str, Enum):
    """Infrastructure vs user-code failure — the distinction an agent needs.

    A user-code error means the project is at fault; an infrastructure error means
    Eclipse could not run the check. They must never be conflated.
    """

    USER_CODE_ERROR = "USER_CODE_ERROR"
    BUILD_ERROR = "BUILD_ERROR"
    TEST_ERROR = "TEST_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    SECURITY_ERROR = "SECURITY_ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    # A declared memory/CPU/process limit was exceeded; the tree was killed.
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    NONE = "NONE"


@dataclass(frozen=True)
class ResourceLimits:
    """The bounds every execution carries. All configurable via environment."""

    cpu_limit: float = 1.0                # fractional cores (advisory; monitored)
    memory_limit_mb: int = 1024
    process_limit: int = 64
    timeout_ms: int = 60_000
    startup_timeout_ms: int = 30_000
    idle_timeout_ms: int = 0             # 0 = disabled
    # Cumulative CPU-time ceiling in seconds (0 = derive a generous ceiling from
    # the wall-clock timeout). Enforced by the parent monitor on real CPU time.
    cpu_seconds: int = 0
    max_stdout_bytes: int = 1_048_576
    max_stderr_bytes: int = 1_048_576
    max_log_lines: int = 10_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpuLimit": self.cpu_limit,
            "memoryLimitMb": self.memory_limit_mb,
            "processLimit": self.process_limit,
            "timeoutMs": self.timeout_ms,
            "startupTimeoutMs": self.startup_timeout_ms,
            "idleTimeoutMs": self.idle_timeout_ms,
            "cpuSeconds": self.cpu_seconds,
            "maxStdoutBytes": self.max_stdout_bytes,
            "maxStderrBytes": self.max_stderr_bytes,
            "maxLogLines": self.max_log_lines,
        }

    @classmethod
    def from_env(cls) -> "ResourceLimits":
        """Read limits from the `HARNESS_EXEC_*` environment, with safe defaults."""
        import os

        def _int(name: str, default: int) -> int:
            try:
                return max(1, int(os.environ.get(name, default)))
            except (TypeError, ValueError):
                return default

        def _int0(name: str, default: int = 0) -> int:
            """An integer where 0 is a legitimate value (meaning 'unset')."""
            try:
                return max(0, int(os.environ.get(name, default)))
            except (TypeError, ValueError):
                return default

        def _float(name: str, default: float) -> float:
            try:
                return max(0.1, float(os.environ.get(name, default)))
            except (TypeError, ValueError):
                return default

        return cls(
            cpu_limit=_float("HARNESS_EXEC_CPU_LIMIT", 1.0),
            memory_limit_mb=_int("HARNESS_EXEC_MAX_MEMORY_MB", 1024),
            process_limit=_int("HARNESS_EXEC_MAX_PROCESSES", 64),
            timeout_ms=_int("HARNESS_EXEC_DEFAULT_TIMEOUT_MS", 60_000),
            startup_timeout_ms=_int("HARNESS_EXEC_STARTUP_TIMEOUT_MS", 30_000),
            idle_timeout_ms=_int0("HARNESS_EXEC_IDLE_TIMEOUT_MS", 0),
            cpu_seconds=_int0("HARNESS_EXEC_CPU_SECONDS", 0),
            max_stdout_bytes=_int("HARNESS_EXEC_MAX_OUTPUT_BYTES", 1_048_576),
            max_stderr_bytes=_int("HARNESS_EXEC_MAX_OUTPUT_BYTES", 1_048_576),
            max_log_lines=_int("HARNESS_EXEC_MAX_LOG_LINES", 10_000),
        )


@dataclass
class ExecutionRequest:
    """One request to run code, build, or test.

    The model-facing tools construct this from validated arguments; the
    orchestrator consumes it. `workspace` is the run's binding — an execution is
    always bound to a workspace, and the binding is what the policy engine
    checks. There is no "default to host" path.
    """

    language: str
    workspace: WorkspaceBinding
    code: str = ""
    entrypoint: str = ""
    cwd: str = ""                        # relative to the workspace root
    args: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    runtime: str = ""                    # explicit runtime name, or "" to auto-detect
    mode: ExecutionMode = ExecutionMode.RUN
    network_policy: NetworkPolicy = NetworkPolicy.NONE
    filesystem_policy: FilesystemPolicy = FilesystemPolicy.WORKSPACE_READ_WRITE
    resource_limits: Optional[ResourceLimits] = None
    test_policy: Optional[dict[str, Any]] = None   # e.g. {"framework": "...", "files": [...]}
    build_policy: Optional[dict[str, Any]] = None
    artifact_policy: Optional[dict[str, Any]] = None
    interactive: bool = False
    stdin: str = ""
    # Identity (never model-supplied): set by the tool/graph from the run.
    run_id: str = ""
    agent_id: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def limits(self) -> ResourceLimits:
        return self.resource_limits or ResourceLimits.from_env()


@dataclass(frozen=True)
class ExecutionContext:
    """Everything needed to REPRODUCE an execution. Immutable once created."""

    execution_id: str
    language: str
    runtime: str
    binding: WorkspaceBinding
    cwd: str
    mode: ExecutionMode
    environment: dict[str, str]
    network_policy: NetworkPolicy
    filesystem_policy: FilesystemPolicy
    limits: ResourceLimits
    created_at: float
    run_id: str = ""
    agent_id: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    parent_execution: Optional[str] = None
    secrets_policy: str = "none"          # "none" when no secret was injected
    reproducible: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "language": self.language,
            "runtime": self.runtime,
            "cwd": self.cwd,
            "mode": self.mode.value,
            "networkPolicy": self.network_policy.value,
            "filesystemPolicy": self.filesystem_policy.value,
            "resourceLimits": self.limits.to_dict(),
            "workspaceId": self.workspace_id,
            "runId": self.run_id,
            "agentId": self.agent_id,
            "projectId": self.project_id,
            "parentExecution": self.parent_execution,
            "secretsPolicy": self.secrets_policy,
            "reproducible": self.reproducible,
            "createdAt": self.created_at,
        }


@dataclass
class Diagnostic:
    """A normalized, agent-consumable diagnostic (compiler/runtime/test)."""

    file: str = ""
    line: int = 0
    column: int = 0
    severity: str = "error"              # "error" | "warning" | "info"
    category: str = "runtime"            # runtime|compile|test|lint|dependency|permission|sandbox|port
    message: str = ""
    stack: list[str] = field(default_factory=list)
    source: str = ""                     # which engine produced it
    code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "line": self.line, "column": self.column,
            "severity": self.severity, "category": self.category,
            "message": self.message, "stack": self.stack,
            "source": self.source, "code": self.code,
        }


@dataclass
class TestResult:
    """One normalized test outcome."""

    suite: str = ""
    test: str = ""
    status: str = "PASSED"               # PASSED|FAILED|SKIPPED|TODO|TIMEOUT|ERROR
    duration_ms: int = 0
    error: str = ""
    stack: list[str] = field(default_factory=list)
    file: str = ""
    line: int = 0
    column: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite, "test": self.test, "status": self.status,
            "durationMs": self.duration_ms, "error": self.error, "stack": self.stack,
            "file": self.file, "line": self.line, "column": self.column,
        }


@dataclass
class Artifact:
    """A file produced by an execution, with an honest identity."""

    path: str
    type: str = "file"
    size: int = 0
    hash: str = ""
    execution_id: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "type": self.type, "size": self.size,
            "hash": self.hash, "executionId": self.execution_id,
            "createdAt": self.created_at,
        }


@dataclass
class ResourceUsage:
    """Measured resource usage. Unknown values stay None — never invented."""

    cpu_ms: Optional[int] = None
    memory_peak_mb: Optional[float] = None
    process_count: Optional[int] = None
    stdout_bytes: Optional[int] = None
    stderr_bytes: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpuMs": self.cpu_ms, "memoryPeakMb": self.memory_peak_mb,
            "processCount": self.process_count,
            "stdoutBytes": self.stdout_bytes, "stderrBytes": self.stderr_bytes,
        }


@dataclass
class ExecutionResult:
    """The structured result every execution returns. Never only raw stdout."""

    execution_id: str
    status: str
    exit_code: Optional[int]
    language: str
    runtime: str
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    files_changed: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    resource_usage: ResourceUsage = field(default_factory=ResourceUsage)
    truncated: bool = False
    error_class: str = ErrorClass.NONE.value
    error: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    build: Optional[dict[str, Any]] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "COMPLETED" and (self.exit_code in (0, None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "status": self.status,
            "exitCode": self.exit_code,
            "language": self.language,
            "runtime": self.runtime,
            "durationMs": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "filesChanged": self.files_changed,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "tests": [t.to_dict() for t in self.tests],
            "resourceUsage": self.resource_usage.to_dict(),
            "truncated": self.truncated,
            "errorClass": self.error_class,
            "error": self.error,
            "context": self.context,
            "build": self.build,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "metadata": self.metadata,
        }


def new_execution_id() -> str:
    """A unique execution id (`exec_<hex>`), used everywhere an execution is named."""
    import uuid

    return "exec_" + uuid.uuid4().hex[:16]


def resource_run_kwargs(limits: "ResourceLimits") -> dict[str, int]:
    """The OS-limit fields a `RunSpec` accepts, derived from `ResourceLimits`.

    `cpu_seconds` is the cumulative CPU-time ceiling: an explicit value when set,
    otherwise the wall-clock budget rounded up (floor 1). Memory and process
    limits pass through. A zero means "unset" and the platform default applies.
    """
    cpu_seconds = int(limits.cpu_seconds or 0)
    if not cpu_seconds and limits.timeout_ms:
        cpu_seconds = max(1, int(limits.timeout_ms // 1000) + 5)
    return {
        "cpu_seconds": cpu_seconds,
        "memory_mb": int(limits.memory_limit_mb or 0),
        "process_limit": int(limits.process_limit or 0),
    }


def now() -> float:
    return time.time()


__all__ = [
    "Artifact",
    "Diagnostic",
    "ErrorClass",
    "ExecutionContext",
    "ExecutionMode",
    "ExecutionRequest",
    "ExecutionResult",
    "FilesystemPolicy",
    "NetworkPolicy",
    "ResourceLimits",
    "ResourceUsage",
    "RiskLevel",
    "TestResult",
    "new_execution_id",
    "now",
    "resource_run_kwargs",
]
