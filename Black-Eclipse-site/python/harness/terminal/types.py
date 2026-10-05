"""Terminal subsystem contracts — the shared vocabulary for every layer.

Nothing here executes anything. These are the enums and dataclasses that the
runtime, the process manager, the session manager, the port manager and the
agent tools all speak. Keeping them in one module is what lets the same backend
serve both the agent tool surface and the UI without a second set of shapes.

Adapted to this repo: the *process* state machine, the structured error contract
and the capability report are new; the runtime names mirror `code/backends.py`'s
existing local/container/remote declaration so the two never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProcessState(str, Enum):
    """The process lifecycle. State is authoritative server-side, never the UI."""

    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    EXITED = "EXITED"
    FAILED = "FAILED"
    CRASHED = "CRASHED"
    TIMEOUT = "TIMEOUT"
    KILLED = "KILLED"
    UNKNOWN = "UNKNOWN"


#: States from which no transition back to RUNNING is possible without a restart.
TERMINAL_STATES: frozenset[ProcessState] = frozenset(
    {
        ProcessState.STOPPED,
        ProcessState.EXITED,
        ProcessState.FAILED,
        ProcessState.CRASHED,
        ProcessState.TIMEOUT,
        ProcessState.KILLED,
    }
)


class StreamName(str, Enum):
    """The three output streams. stdout and stderr are never merged silently."""

    STDOUT = "stdout"
    STDERR = "stderr"
    SYSTEM = "system"  # subsystem notes (start, exit, signal), not process output


class SignalName(str, Enum):
    """A portable signal vocabulary. Windows has no real signals; it is mapped."""

    INT = "SIGINT"
    TERM = "SIGTERM"
    KILL = "SIGKILL"
    STOP = "SIGSTOP"
    CONT = "SIGCONT"


class RuntimeName(str, Enum):
    """Where a command runs. Mirrors the honest-failure rule of `code/backends.py`."""

    LOCAL = "local"
    WSL = "wsl"
    DOCKER = "docker"
    SSH = "ssh"


class ErrorCategory(str, Enum):
    """Structured execution-error classes (never a bare "command failed")."""

    COMMAND_FAILED = "COMMAND_FAILED"
    COMMAND_NOT_FOUND = "COMMAND_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    PORT_CONFLICT = "PORT_CONFLICT"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    PROCESS_CRASH = "PROCESS_CRASH"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    WORKING_DIRECTORY_NOT_FOUND = "WORKING_DIRECTORY_NOT_FOUND"
    SHELL_NOT_FOUND = "SHELL_NOT_FOUND"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class CommandError:
    """A normalized execution failure. Structured, model-facing, secret-free."""

    type: str
    category: str
    message: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "category": self.category,
            "message": self.message,
            "exitCode": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class ShellInfo:
    """One detected shell."""

    name: str
    path: Optional[str]
    argv_prefix: tuple[str, ...]
    kind: str  # "powershell" | "cmd" | "bash" | "sh" | "wsl"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "kind": self.kind}


@dataclass(frozen=True)
class WslInfo:
    """WSL availability and distributions. Never assumed present."""

    available: bool
    distributions: tuple[str, ...] = ()
    default: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "distributions": list(self.distributions),
            "default": self.default,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TerminalCapabilities:
    """What this host can actually do. Honest: never a fabricated True."""

    platform: str
    architecture: str
    default_shell: Optional[str]
    shells: tuple[dict[str, Any], ...]
    wsl: dict[str, Any]
    runtimes: tuple[str, ...]
    pty: bool
    process_management: bool
    port_detection: bool
    docker: bool
    ssh: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "architecture": self.architecture,
            "defaultShell": self.default_shell,
            "shells": list(self.shells),
            "availableShells": [s["name"] for s in self.shells],
            "wsl": self.wsl,
            "runtimes": list(self.runtimes),
            "pty": self.pty,
            "processManagement": self.process_management,
            "portDetection": self.port_detection,
            "docker": self.docker,
            "ssh": self.ssh,
        }


@dataclass
class OutputChunk:
    """One sequenced output event. The cursor the agent polls by."""

    sequence: int
    stream: str
    timestamp: str
    data: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "stream": self.stream,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class CommandResult:
    """The result of a one-shot (foreground) command."""

    execution_id: str
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool
    cwd: str
    runtime: str
    command: str
    error: Optional[CommandError] = None
    stdout_sequence: int = 0
    stderr_sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "executionId": self.execution_id,
            "status": self.status,
            "exitCode": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "durationMs": self.duration_ms,
            "timedOut": self.timed_out,
            "truncated": self.truncated,
            "cwd": self.cwd,
            "runtime": self.runtime,
            "command": self.command,
            "stdoutSequence": self.stdout_sequence,
            "stderrSequence": self.stderr_sequence,
        }
        if self.error is not None:
            data["error"] = self.error.to_dict()
        return data


@dataclass
class ProcessInfo:
    """A tracked background process. The registry row, plus live state."""

    process_id: str
    pid: Optional[int]
    parent_pid: Optional[int]
    command: str
    cwd: str
    runtime: str
    shell: str
    state: str
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    exit_at: Optional[str] = None
    exit_code: Optional[int] = None
    ports: tuple[int, ...] = ()
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    purpose: Optional[str] = None
    health: Optional[dict[str, Any]] = None
    last_error: Optional[CommandError] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "processId": self.process_id,
            "pid": self.pid,
            "parentPid": self.parent_pid,
            "command": self.command,
            "cwd": self.cwd,
            "runtime": self.runtime,
            "shell": self.shell,
            "state": self.state,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "startedAt": self.started_at,
            "exitAt": self.exit_at,
            "exitCode": self.exit_code,
            "ports": list(self.ports),
            "workspaceId": self.workspace_id,
            "agentId": self.agent_id,
            "runId": self.run_id,
            "taskId": self.task_id,
        }
        if self.purpose:
            data["purpose"] = self.purpose
        if self.health is not None:
            data["health"] = self.health
        if self.last_error is not None:
            data["error"] = self.last_error.to_dict()
        return data


@dataclass
class SessionInfo:
    """A persistent shell session. cwd and env survive across commands."""

    session_id: str
    runtime: str
    shell: str
    pid: Optional[int]
    cwd: str
    status: str
    created_at: str
    updated_at: str
    rows: int = 24
    columns: int = 80
    env_profile: dict[str, str] = field(default_factory=dict)
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    owner: Optional[str] = None
    pty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "runtime": self.runtime,
            "shell": self.shell,
            "pid": self.pid,
            "cwd": self.cwd,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "rows": self.rows,
            "columns": self.columns,
            "envKeys": sorted(self.env_profile),
            "workspaceId": self.workspace_id,
            "agentId": self.agent_id,
            "owner": self.owner,
            "pty": self.pty,
        }


@dataclass(frozen=True)
class PortInfo:
    """A listening port, with its owning process when resolvable."""

    port: int
    pid: Optional[int]
    process_id: Optional[str]
    address: Optional[str]
    protocol: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "pid": self.pid,
            "processId": self.process_id,
            "address": self.address,
            "protocol": self.protocol,
            "status": self.status,
        }


__all__ = [
    "TERMINAL_STATES",
    "CommandError",
    "CommandResult",
    "ErrorCategory",
    "OutputChunk",
    "PortInfo",
    "ProcessInfo",
    "ProcessState",
    "RuntimeName",
    "SessionInfo",
    "ShellInfo",
    "SignalName",
    "StreamName",
    "TerminalCapabilities",
    "WslInfo",
]
