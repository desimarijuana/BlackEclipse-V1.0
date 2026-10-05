"""Execution runtimes — where a session or process actually runs.

This is the terminal subsystem's counterpart to `code/backends.py`, but at the
*command* level rather than the file level. A runtime answers three questions:

  1. is it available on this host? (probed, never assumed)
  2. how is a command string mapped to an argv for it? (shell wrapping)
  3. how is a Windows path mapped into its filesystem? (WSL `/mnt/c/...`)

`LocalRuntime`, `WSLruntime`, `DockerRuntime` and `SSHRuntime` are all
implemented for command execution and background processes. Interactive
persistent sessions are the local/WSL path only; a Docker/SSH session request
refuses honestly. Every runtime probes availability and NEVER falls back to
local — that matches §76 (do not fake capabilities) exactly.

SSH credentials are deliberately NOT part of the local environment model: the
runtime uses the host's own OpenSSH configuration and agent (`~/.ssh/config`),
never a secret the terminal subsystem reads or stores.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from .shell_detect import detect_wsl, resolve_shell
from .types import ShellInfo


class RuntimeUnavailable(RuntimeError):
    """A runtime cannot serve this request. Carries a structured code."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class ExecutionRuntime(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def describe(self) -> dict[str, object]: ...

    def shell_for(self, name: Optional[str]) -> ShellInfo: ...

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]: ...

    def map_path(self, path: str) -> str: ...

    def extra_env(self) -> dict[str, str]: ...


def _windows_to_wsl(path: str) -> str:
    """`C:\\Users\\me` -> `/mnt/c/Users/me`. A non-Windows path is returned as-is."""
    text = str(path).replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/?(.*)$", text)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).lstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return text


@dataclass
class LocalRuntime:
    """The zero-config default: the host shell (PowerShell/CMD/bash)."""

    name: str = "local"

    @property
    def available(self) -> bool:
        return resolve_shell(None) is not None

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "available": self.available}

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        shell = resolve_shell(name)
        if shell is None:
            raise RuntimeUnavailable("SHELL_NOT_FOUND", "the requested shell is not available on this computer")
        return shell

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        info = self.shell_for(shell)
        return list(info.argv_prefix) + [command]

    def map_path(self, path: str) -> str:
        return str(path)

    def extra_env(self) -> dict[str, str]:
        return {}


@dataclass
class WSLruntime:
    """A persistent command run inside a WSL distribution.

    Windows paths are mapped to `/mnt/<drive>/...`; cwd is passed through
    `wsl.exe --cd`. WSL pids are NOT Windows pids — callers must treat a WSL
    process's pid as opaque and always address it by its harness process id.
    """

    distro: Optional[str] = None
    name: str = "wsl"

    @property
    def available(self) -> bool:
        return detect_wsl().available

    def _distro(self) -> str:
        info = detect_wsl()
        if not info.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", info.reason or "the Linux subsystem is not available")
        if self.distro:
            if self.distro not in info.distributions:
                raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", f"the distribution {self.distro!r} is not installed")
            return self.distro
        if info.default:
            return info.default
        raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "no Linux distribution is configured")

    def describe(self) -> dict[str, object]:
        info = detect_wsl()
        return {"name": self.name, "available": info.available, "distributions": list(info.distributions), "default": info.default}

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "shell selection is owned by the Linux subsystem")

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        wsl = shutil.which("wsl")
        if wsl is None:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "the Linux subsystem is not installed")
        distro = self._distro()
        linux_cwd = self.map_path(cwd)
        return [wsl, "-d", distro, "--cd", linux_cwd, "--", "bash", "-lc", command]

    def map_path(self, path: str) -> str:
        return _windows_to_wsl(path)

    def extra_env(self) -> dict[str, str]:
        return {}


# Docker is DETECTED, never installed. `docker` alone is not enough: the daemon
# must answer. A container to exec into must be configured by the operator — we
# never guess or spawn one.
CONTAINER_ENV = "HARNESS_TERMINAL_DOCKER_CONTAINER"
CONTAINER_WORKDIR_ENV = "HARNESS_TERMINAL_DOCKER_WORKDIR"


def _docker_status() -> tuple[bool, str]:
    exe = shutil.which("docker")
    if exe is None:
        return False, "Docker is not installed on this computer."
    try:
        completed = subprocess.run(
            [exe, "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=6, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Docker is installed but its service could not be reached: {exc}"
    if completed.returncode != 0:
        return False, "Docker is installed but its service is not running."
    return True, ""


@dataclass
class DockerRuntime:
    """Run commands inside a configured, already-running container.

    Configuration (operator-supplied, never guessed):
      * `HARNESS_TERMINAL_DOCKER_CONTAINER` — a running container name/id to exec into.
      * `HARNESS_TERMINAL_DOCKER_WORKDIR` — the folder inside it (default `/workspace`).

    Command execution and background processes are fully supported (each is
    `docker exec -i`). Interactive persistent sessions are NOT: a session needs a
    shell we drive directly, and that is the local/WSL path. A session request for
    Docker refuses honestly rather than pretending.
    """

    container: Optional[str] = None
    workdir: Optional[str] = None
    name: str = "docker"

    def __post_init__(self) -> None:
        self.container = self.container or os.environ.get(CONTAINER_ENV) or None
        self.workdir = self.workdir or os.environ.get(CONTAINER_WORKDIR_ENV) or "/workspace"

    @property
    def daemon_available(self) -> bool:
        return _docker_status()[0]

    @property
    def available(self) -> bool:
        return bool(self.container) and self.daemon_available

    def describe(self) -> dict[str, object]:
        daemon, reason = _docker_status()
        configured = bool(self.container)
        available = daemon and configured
        why = ""
        if not daemon:
            why = reason
        elif not configured:
            why = f"no container is configured (set {CONTAINER_ENV})"
        return {
            "name": self.name, "available": available, "implemented": True,
            "daemonAvailable": daemon, "container": self.container,
            "workdir": self.workdir, "reason": why,
        }

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        if not self.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", self.describe().get("reason") or "Docker is not available")
        raise RuntimeUnavailable(
            "NOT_IMPLEMENTED",
            "interactive sessions inside containers are not implemented; use a command or a background process",
        )

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        if not self.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", str(self.describe().get("reason") or "Docker is not available"))
        exe = shutil.which("docker")
        if exe is None:  # pragma: no cover - raced with the probe
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "Docker is not installed on this computer.")
        workdir = cwd if (cwd and cwd.startswith("/")) else (self.workdir or "/workspace")
        inner = f"cd {shlex.quote(workdir)} && {command}"
        return [exe, "exec", "-i", str(self.container), "sh", "-lc", inner]

    def map_path(self, path: str) -> str:
        # A container path is POSIX and independent of the host; an absolute POSIX
        # path is passed through, anything else resolves under the container workdir.
        text = str(path).replace("\\", "/")
        if text.startswith("/"):
            return text
        base = (self.workdir or "/workspace").rstrip("/")
        return f"{base}/{text}" if text and text != "." else base

    def extra_env(self) -> dict[str, str]:
        # The Docker client honours DOCKER_HOST / DOCKER_CONTEXT; pass them through
        # so a non-default daemon or context still works. Neither is a secret.
        out: dict[str, str] = {}
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            if key in os.environ:
                out[key] = os.environ[key]
        return out


SSH_HOST_ENV = "HARNESS_TERMINAL_SSH_HOST"


@dataclass
class SSHRuntime:
    """Run commands on a host the operator has configured in OpenSSH.

    The host is named by `HARNESS_TERMINAL_SSH_HOST` and MUST exist as an alias in
    the user's `~/.ssh/config` (or a `user@host` the ssh client accepts). The
    runtime NEVER reads, stores or forwards a password or key: keys, the agent and
    `known_hosts` are OpenSSH's, exactly as the user set them up. `BatchMode=yes`
    makes a missing key fail fast instead of prompting, so a command never hangs
    an agent run.

    Command execution and background processes are supported (`ssh <host> <cmd>`).
    Interactive persistent sessions are not.
    """

    host: Optional[str] = None
    name: str = "ssh"

    def __post_init__(self) -> None:
        self.host = self.host or os.environ.get(SSH_HOST_ENV) or None

    @property
    def available(self) -> bool:
        return bool(self.host) and shutil.which("ssh") is not None

    def describe(self) -> dict[str, object]:
        exe = shutil.which("ssh")
        configured = bool(self.host)
        available = configured and exe is not None
        why = ""
        if exe is None:
            why = "the ssh client is not installed on this computer"
        elif not configured:
            why = f"no remote host is configured (set {SSH_HOST_ENV})"
        return {
            "name": self.name, "available": available, "implemented": True,
            "client": exe, "host": self.host, "reason": why,
            "auth": "the host's own OpenSSH configuration and agent; no secret is read or stored",
        }

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        if not self.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", str(self.describe().get("reason") or "SSH is not available"))
        raise RuntimeUnavailable(
            "NOT_IMPLEMENTED",
            "interactive sessions on another computer are not implemented; use a command or a background process",
        )

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        if not self.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", str(self.describe().get("reason") or "SSH is not available"))
        exe = shutil.which("ssh")
        if exe is None:  # pragma: no cover - raced with the probe
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "the ssh client is not installed on this computer")
        # `cd <cwd> && command`; cwd is remote and optional (empty = the login dir).
        inner = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
        return [
            exe, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            str(self.host), inner,
        ]

    def map_path(self, path: str) -> str:
        # A remote path is used verbatim; the terminal subsystem never rewrites it
        # to a local path, because they are different computers.
        return str(path)

    def extra_env(self) -> dict[str, str]:
        # OpenSSH authenticates via the host's own config/agent. Only the agent
        # socket (and, when the agent is absent, its Windows named-pipe equivalent)
        # is forwarded so key-based auth works from the scrubbed environment. No
        # key material or passphrase is ever read.
        out: dict[str, str] = {}
        for key in ("SSH_AUTH_SOCK", "SSH_AGENT_PID"):
            if key in os.environ:
                out[key] = os.environ[key]
        if os.name == "nt" and "SSH_AUTH_SOCK" not in out:
            # The Windows OpenSSH agent exposes a named pipe instead of a socket.
            candidate = os.environ.get("SSH_AUTH_SOCK_NAMED_PIPE")
            if candidate:
                out["SSH_AUTH_SOCK"] = candidate
        return out


def select_runtime(name: str, *, distro: Optional[str] = None) -> ExecutionRuntime:
    """Resolve a runtime by name. An unknown or unavailable one REFUSES."""
    lowered = (name or "local").strip().casefold()
    if lowered in ("", "local"):
        return LocalRuntime()
    if lowered == "wsl":
        runtime = WSLruntime(distro=distro)
        if not runtime.available:
            info = detect_wsl()
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", info.reason or "the Linux subsystem is not available")
        return runtime
    if lowered == "docker":
        runtime = DockerRuntime()
        if not runtime.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", str(runtime.describe().get("reason") or "Docker is not available"))
        return runtime
    if lowered == "ssh":
        runtime = SSHRuntime()
        if not runtime.available:
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", str(runtime.describe().get("reason") or "SSH is not available"))
        return runtime
    raise RuntimeUnavailable("INVALID_ARGUMENT", f"unknown runtime {name!r}")


def describe_runtimes() -> dict[str, object]:
    """Honest state of every runtime, for capabilities/system-info."""
    return {
        "local": LocalRuntime().describe(),
        "wsl": WSLruntime().describe(),
        "docker": DockerRuntime().describe(),
        "ssh": SSHRuntime().describe(),
    }


__all__ = [
    "DockerRuntime",
    "ExecutionRuntime",
    "LocalRuntime",
    "RuntimeUnavailable",
    "SSHRuntime",
    "WSLruntime",
    "describe_runtimes",
    "select_runtime",
]
