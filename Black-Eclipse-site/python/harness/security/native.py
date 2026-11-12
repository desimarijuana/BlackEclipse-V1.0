"""Native OS isolation backends (C6): bubblewrap and macOS seatbelt.

The point of this module is honesty. A profile promise is only kept when the
platform has a primitive that can keep it:

  * Linux  — `bubblewrap` (`bwrap`): mount namespace, read-only or writable
             bind mounts, `--unshare-net` when no network, PID/dev/tmp isolation;
  * macOS  — `sandbox-exec` (Seatbelt): a deny-by-default write/network policy
             with explicit workspace exceptions;
  * Windows — no native filesystem/network primitive is wired here. The Job
             Object backend remains `LocalSandbox` (process + resource limits),
             and this backend reports itself unavailable rather than pretending.

`bwrap_argv()` and `seatbelt_policy()` are pure so the guarantee can be tested
on any host; `NativeSandbox.capabilities()` tells the profile resolver the truth.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

from .models import new_id
from .sandbox import (
    ExecutionSandbox,
    SandboxHandle,
    SandboxResult,
    SandboxSpec,
)

_BWRAP = "bwrap"
_SEATBELT = "sandbox-exec"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_macos() -> bool:
    return sys.platform == "darwin"


def bwrap_argv(spec: SandboxSpec, *, tool: str = _BWRAP) -> list[str]:
    """The bubblewrap argv for a spec. Pure — unit-testable on any host."""
    argv = [
        tool, "--die-with-parent", "--new-session", "--unshare-pid",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
    ]
    if not spec.allow_network:
        argv += ["--unshare-net"]
    # A read-only root, then the explicit mounts. Nothing else is writable.
    argv += ["--ro-bind", "/", "/"]
    for host, container, read_only in spec.mounts:
        argv += ["--ro-bind" if read_only else "--bind", str(host), str(container)]
    if spec.cwd and os.path.isdir(str(spec.cwd)):
        argv += ["--chdir", str(spec.cwd)]
    argv += ["--clearenv"]
    for key, value in {**dict(spec.env or {}), **dict(spec.secret_env or {})}.items():
        argv += ["--setenv", str(key), str(value)]
    argv += ["--", *list(spec.argv)]
    return argv


def seatbelt_policy(spec: SandboxSpec) -> str:
    """The macOS Seatbelt profile for a spec. Pure — unit-testable anywhere."""
    lines = ["(version 1)", "(allow default)"]
    if not spec.allow_network:
        lines.append("(deny network*)")
    lines.append("(deny file-write*)")
    for host, _container, read_only in spec.mounts:
        if not read_only:
            lines.append(f'(allow file-write* (subpath "{host}"))')
    lines.append('(allow file-write* (subpath "/tmp"))')
    return "\n".join(lines)


def seatbelt_argv(spec: SandboxSpec, *, tool: str = _SEATBELT) -> list[str]:
    return [tool, "-p", seatbelt_policy(spec), "--", *list(spec.argv)]


class NativeSandbox(ExecutionSandbox):
    """bubblewrap (Linux) / sandbox-exec (macOS); unavailable on Windows."""

    name = "native"

    def _tool(self) -> Optional[str]:
        if _is_linux():
            return shutil.which(_BWRAP)
        if _is_macos():
            return shutil.which(_SEATBELT)
        return None

    def available(self) -> bool:
        return self._tool() is not None

    def capabilities(self) -> dict[str, Any]:
        tool = self._tool()
        return {
            "backend": self.name,
            "platform": sys.platform,
            "tool": os.path.basename(tool) if tool else None,
            "processIsolation": True,
            "filesystemIsolation": bool(tool),
            "networkIsolation": bool(tool),
            "secretIsolation": True,
            "egressProxy": False,
            "note": (
                "bubblewrap mount/network namespaces" if _is_linux() else
                "macOS Seatbelt write/network policy" if _is_macos() else
                "no native filesystem/network primitive on Windows; use Docker"
            ),
        }

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        return SandboxHandle(id=new_id("sbx"), backend=self.name)

    def execute(self, handle: SandboxHandle, spec: SandboxSpec) -> SandboxResult:
        tool = self._tool()
        if not tool:
            return SandboxResult(
                None, "", self.capabilities()["note"], self.name, 0.0,
                refused=True, reason="sandbox unavailable",
            )
        if not spec.argv:
            return SandboxResult(None, "", "empty command", self.name, 0.0,
                                 refused=True, reason="empty command")
        argv = (
            bwrap_argv(spec, tool=tool) if _is_linux()
            else seatbelt_argv(spec, tool=tool)
        )
        # seatbelt has no `--clearenv`; the launcher environment must already be
        # the scrubbed allowlist. bwrap clears it again, so this is safe on both.
        from ..code.sandbox import build_env  # noqa: PLC0415

        run_env = build_env({**dict(spec.env or {}), **dict(spec.secret_env or {})})
        started = time.time()
        try:
            proc = subprocess.run(
                argv, env=run_env, capture_output=True, text=True,
                timeout=max(1, int(spec.timeout_s)), check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(None, exc.stdout or "", "timeout", self.name,
                                 time.time() - started, limited=True, reason="timeout")
        except Exception as exc:  # noqa: BLE001 - a launch error is a refusal
            return SandboxResult(None, "", str(exc), self.name, time.time() - started,
                                 refused=True, reason="launch failed")
        return SandboxResult(proc.returncode, proc.stdout or "", proc.stderr or "",
                             self.name, time.time() - started)


__all__ = [
    "NativeSandbox",
    "bwrap_argv",
    "seatbelt_argv",
    "seatbelt_policy",
]
