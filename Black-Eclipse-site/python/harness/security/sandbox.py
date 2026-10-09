"""Execution sandbox — the physical execution boundary.

The Permission Engine decides *whether* an action is authorized; the sandbox
enforces *where and how* code actually runs. They are deliberately separate: an
authorized command still runs inside an isolation boundary, and an unavailable
boundary fails closed (never an unbounded fallback).

Backends:
  * `LocalSandbox`  — process isolation via the existing `code/sandbox.py`
    primitive (Windows Job Object / POSIX process groups), with an allowlist-only
    environment and no secret leakage. It does NOT enforce filesystem or network
    isolation (documented honestly via `capabilities()`).
  * `DockerSandbox` — a real container boundary: `--network none|bridge`,
    read-only rootfs, non-root user, dropped capabilities, no-new-privileges,
    memory/pids/cpu limits, explicit mounts and secret env. Reports unavailable
    when the `docker` CLI is absent.
  * `UnavailableSandbox` — fails every operation closed.
"""

from __future__ import annotations

import abc
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import new_id


@dataclass
class SandboxSpec:
    """What to run and the boundary to run it in."""

    argv: list[str]
    cwd: Optional[str] = None
    env: dict[str, str] = field(default_factory=dict)
    allow_network: bool = False
    mounts: list[tuple[str, str, bool]] = field(default_factory=list)  # (host, container, ro)
    secret_env: dict[str, str] = field(default_factory=dict)
    timeout_s: int = 120
    memory_mb: Optional[int] = None
    pids: Optional[int] = None
    cpus: Optional[float] = None
    image: str = "eclipse-sandbox:latest"


@dataclass
class SandboxResult:
    exit_code: Optional[int]
    stdout: str
    stderr: str
    backend: str
    duration_s: float
    limited: bool = False
    refused: bool = False
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.refused


@dataclass
class SandboxHandle:
    id: str
    backend: str
    created_at: float = field(default_factory=time.time)


class SandboxError(RuntimeError):
    pass


class SandboxUnavailable(SandboxError):
    """No isolation primitive is available — every operation must fail closed."""


class ExecutionSandbox(abc.ABC):
    """The interface every backend implements."""

    name: str = "base"

    @abc.abstractmethod
    def available(self) -> bool: ...

    @abc.abstractmethod
    def capabilities(self) -> dict[str, Any]: ...

    @abc.abstractmethod
    def create(self, spec: SandboxSpec) -> SandboxHandle: ...

    @abc.abstractmethod
    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult: ...

    def start(self, handle: SandboxHandle) -> None:  # pragma: no cover - default no-op
        return None

    def mount(self, handle: SandboxHandle, host: str, container: str, *, read_only: bool = True) -> None:
        return None

    def network_policy(self, handle: SandboxHandle, *, allow: bool) -> None:
        return None

    def inject_secret(self, handle: SandboxHandle, name: str, value: str) -> None:
        return None

    def collect_output(self, result: SandboxResult) -> SandboxResult:
        return result

    def terminate(self, handle: SandboxHandle) -> None:
        return None

    def destroy(self, handle: SandboxHandle) -> None:
        return None


class LocalSandbox(ExecutionSandbox):
    """Process isolation over the existing `code/sandbox.py` primitive."""

    name = "local"

    def available(self) -> bool:
        try:
            from ..code.sandbox import backend_name  # noqa: PLC0415

            return backend_name() != "unavailable"
        except Exception:  # noqa: BLE001
            return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "processIsolation": self.available(),
            "filesystemIsolation": False,
            "networkIsolation": False,
            "secretIsolation": True,
        }

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        return SandboxHandle(id=new_id("sbx"), backend=self.name)

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:
        from pathlib import Path  # noqa: PLC0415

        from ..code.sandbox import RunSpec, SandboxUnavailable as _Unavailable, build_env, run  # noqa: PLC0415

        if not spec.argv:
            return SandboxResult(None, "", "empty command", self.name, 0.0, refused=True,
                                 reason="empty command")
        env = build_env(spec.secret_env)
        run_spec = RunSpec(
            argv=list(spec.argv),
            cwd=Path(spec.cwd or os.getcwd()),
            env=env,
            timeout_s=spec.timeout_s,
            output_cap_bytes=200_000,
            network=spec.allow_network,
            memory_mb=int(spec.memory_mb or 0),
            process_limit=int(spec.pids or 0),
        )
        started = time.time()
        try:
            raw = run(run_spec)
        except _Unavailable as exc:
            return SandboxResult(None, "", str(exc), self.name, time.time() - started,
                                 refused=True, reason="sandbox unavailable")
        except Exception as exc:  # noqa: BLE001 - a launch error is a refusal, never unbounded
            return SandboxResult(None, "", str(exc), self.name, time.time() - started,
                                 refused=True, reason="launch failed")
        launch_error = getattr(raw, "launch_error", None)
        timed_out = bool(getattr(raw, "timed_out", False))
        return SandboxResult(
            exit_code=getattr(raw, "exit_code", None),
            stdout=getattr(raw, "output", "") or "",
            stderr="",
            backend=self.name,
            duration_s=float(getattr(raw, "duration_ms", 0) or 0) / 1000.0 or (time.time() - started),
            limited=bool(timed_out or getattr(raw, "killed", False) or getattr(raw, "resource_limit", None)),
            refused=bool(launch_error),
            reason=str(launch_error or ("timeout" if timed_out else "")),
        )


def docker_available() -> bool:
    return bool(shutil.which("docker"))


def docker_argv(spec: SandboxSpec, container_name: str) -> list[str]:
    """Build the hardened `docker run` argv. Pure — no side effects (unit-testable)."""
    argv = ["docker", "run", "--rm", "--name", container_name,
            "--workdir", "/work"]
    argv += ["--network", "bridge" if spec.allow_network else "none"]
    argv += ["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m"]
    argv += ["--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
    argv += ["--user", "1000:1000"]
    if spec.memory_mb:
        argv += ["--memory", f"{int(spec.memory_mb)}m", "--memory-swap", f"{int(spec.memory_mb)}m"]
    if spec.pids:
        argv += ["--pids-limit", str(int(spec.pids))]
    if spec.cpus:
        argv += ["--cpus", str(float(spec.cpus))]
    for host, container, read_only in spec.mounts:
        argv += ["-v", f"{host}:{container}{':ro' if read_only else ''}"]
    for key, value in spec.secret_env.items():
        argv += ["-e", f"{key}={value}"]
    for key, value in spec.env.items():
        argv += ["-e", f"{key}={value}"]
    argv += [spec.image, *spec.argv]
    return argv


class DockerSandbox(ExecutionSandbox):
    """A real container boundary via the `docker` CLI."""

    name = "docker"

    def available(self) -> bool:
        return docker_available()

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "processIsolation": True,
            "filesystemIsolation": True,
            "networkIsolation": True,
            "secretIsolation": True,
        }

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        return SandboxHandle(id=new_id("sbx"), backend=self.name)

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:
        if not self.available():
            return SandboxResult(None, "", "docker is not installed", self.name, 0.0,
                                 refused=True, reason="sandbox unavailable")
        if not spec.argv:
            return SandboxResult(None, "", "empty command", self.name, 0.0,
                                 refused=True, reason="empty command")
        argv = docker_argv(spec, container_name=f"eclipse_{handle.id}")
        started = time.time()
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=spec.timeout_s, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(None, exc.stdout or "", "timeout", self.name,
                                 time.time() - started, limited=True, reason="timeout")
        except Exception as exc:  # noqa: BLE001
            return SandboxResult(None, "", str(exc), self.name, time.time() - started,
                                 refused=True, reason="launch failed")
        return SandboxResult(proc.returncode, proc.stdout or "", proc.stderr or "",
                             self.name, time.time() - started)

    def terminate(self, handle: SandboxHandle) -> None:
        try:
            subprocess.run(["docker", "kill", f"eclipse_{handle.id}"], capture_output=True, check=False)
        except Exception:  # noqa: BLE001
            pass

    def destroy(self, handle: SandboxHandle) -> None:
        self.terminate(handle)


class UnavailableSandbox(ExecutionSandbox):
    """No isolation primitive — every operation refuses, fail-closed."""

    name = "unavailable"

    def available(self) -> bool:
        return False

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name, "processIsolation": False,
            "filesystemIsolation": False, "networkIsolation": False, "secretIsolation": False,
        }

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        raise SandboxUnavailable("no execution sandbox is available")

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:
        return SandboxResult(None, "", "no execution sandbox is available", self.name, 0.0,
                             refused=True, reason="sandbox unavailable")


_DEFAULT: Optional[ExecutionSandbox] = None
_LOCK = threading.RLock()


def select_sandbox(prefer: Optional[str] = None) -> ExecutionSandbox:
    """Pick the best available backend; never return an unbounded one.

    Preference: an explicit `prefer`, then Docker (strongest), then Local, then
    Unavailable.
    """
    global _DEFAULT
    with _LOCK:
        if prefer:
            candidate = {"docker": DockerSandbox(), "local": LocalSandbox()}.get(prefer)
            if candidate is not None and candidate.available():
                return candidate
            return UnavailableSandbox()
        if _DEFAULT is not None and _DEFAULT.available():
            return _DEFAULT
        for backend in (DockerSandbox(), LocalSandbox()):
            if backend.available():
                _DEFAULT = backend
                return backend
        _DEFAULT = UnavailableSandbox()
        return _DEFAULT


def get_sandbox() -> ExecutionSandbox:
    return select_sandbox(os.environ.get("BLACK_ECLIPSE_SANDBOX_BACKEND"))


def set_sandbox(sandbox: Optional[ExecutionSandbox]) -> None:
    """Test seam: force a sandbox (or None to re-detect)."""
    global _DEFAULT
    with _LOCK:
        _DEFAULT = sandbox


__all__ = [
    "DockerSandbox",
    "ExecutionSandbox",
    "LocalSandbox",
    "SandboxError",
    "SandboxHandle",
    "SandboxResult",
    "SandboxSpec",
    "SandboxUnavailable",
    "UnavailableSandbox",
    "docker_argv",
    "docker_available",
    "get_sandbox",
    "select_sandbox",
    "set_sandbox",
]
