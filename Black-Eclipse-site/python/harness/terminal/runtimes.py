"""Execution runtimes — where a session or process actually runs.

This is the terminal subsystem's counterpart to `code/backends.py`, but at the
*command* level rather than the file level. A runtime answers three questions:

  1. is it available on this host? (probed, never assumed)
  2. how is a command string mapped to an argv for it? (shell wrapping)
  3. how is a Windows path mapped into its filesystem? (WSL `/mnt/c/...`)

`LocalRuntime` and `WSLruntime` are FULLY implemented. `DockerRuntime` and
`SSHRuntime` exist so the interface is honest and a future phase can fill them in,
but they REFUSE with a structured `NOT_IMPLEMENTED`/`RUNTIME_UNAVAILABLE` — never a
silent fallback to local. That matches §76 (do not fake capabilities) exactly.
"""

from __future__ import annotations

import os
import re
import shutil
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


@dataclass
class DockerRuntime:
    """Declared for the future; NOT implemented. Refuses honestly."""

    container: Optional[str] = None
    name: str = "docker"

    @property
    def available(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name, "available": False, "implemented": False,
            "reason": "running inside containers is not implemented yet",
        }

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running inside containers is not implemented yet")

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running inside containers is not implemented yet")

    def map_path(self, path: str) -> str:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running inside containers is not implemented yet")


@dataclass
class SSHRuntime:
    """Declared for the future; NOT implemented. Refuses honestly.

    Remote credentials are deliberately NOT part of the local environment model;
    a future phase owns them behind this runtime only.
    """

    host: Optional[str] = None
    name: str = "ssh"

    @property
    def available(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name, "available": False, "implemented": False,
            "reason": "running commands on another computer is not implemented yet",
        }

    def shell_for(self, name: Optional[str]) -> ShellInfo:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running commands on another computer is not implemented yet")

    def build_argv(self, command: str, *, shell: Optional[str], cwd: str) -> list[str]:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running commands on another computer is not implemented yet")

    def map_path(self, path: str) -> str:
        raise RuntimeUnavailable("NOT_IMPLEMENTED", "running commands on another computer is not implemented yet")


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
        return DockerRuntime()
    if lowered == "ssh":
        return SSHRuntime()
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
