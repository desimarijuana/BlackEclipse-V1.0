"""Shell and environment detection — never assume a shell exists.

`code/shell.py::detect_shell()` already resolves the *host* shell for one-shot
commands. This module is the richer detector the terminal subsystem needs: it
enumerates every usable shell (PowerShell / pwsh / CMD / bash / sh / zsh / fish),
names the default, probes WSL availability and its distributions, and reports a
capability record. It does NO hard-coded paths: every shell is found by
`shutil.which` or an environment variable that the OS itself set.

The WSL probe runs `wsl.exe -l -q` with a short timeout. On a machine without WSL
this returns honestly (`available: False`, with a reason) — never a fabricated
distribution list.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache
from typing import Optional

from .types import ShellInfo, TerminalCapabilities, WslInfo

_PROBE_TIMEOUT_S = 4


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _powershell_args(path: str) -> tuple[str, ...]:
    return (path, "-NoLogo", "-NoProfile", "-Command")


@lru_cache(maxsize=1)
def detect_shells() -> tuple[ShellInfo, ...]:
    """Every usable shell on this host, in preference order."""
    shells: list[ShellInfo] = []
    if os.name == "nt":
        for name in ("pwsh", "powershell"):
            path = _which(name)
            if path:
                shells.append(ShellInfo(name=name, path=path, argv_prefix=_powershell_args(path), kind="powershell"))
        comspec = os.environ.get("COMSPEC") or _which("cmd")
        if comspec:
            shells.append(ShellInfo(name="cmd", path=comspec, argv_prefix=(comspec, "/d", "/s", "/c"), kind="cmd"))
        wsl = _which("wsl")
        if wsl:
            shells.append(ShellInfo(name="wsl", path=wsl, argv_prefix=(wsl, "--", "bash", "-lc"), kind="wsl"))
        # Git-for-Windows / MSYS bash, when present.
        for name in ("bash", "sh"):
            path = _which(name)
            if path:
                shells.append(ShellInfo(name=name, path=path, argv_prefix=(path, "-c"), kind="bash"))
    else:
        for name in ("bash", "zsh", "fish", "sh"):
            path = _which(name)
            if path:
                kind = "bash" if name in ("bash", "sh") else name
                shells.append(ShellInfo(name=name, path=path, argv_prefix=(path, "-c"), kind=kind))
    return tuple(shells)


def default_shell() -> Optional[ShellInfo]:
    """The preferred shell, or None when none was detected (an honest refusal)."""
    shells = detect_shells()
    return shells[0] if shells else None


def _decode(raw: bytes) -> str:
    # `wsl -l -q` writes UTF-16LE on Windows; fall back to utf-8 for other hosts.
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = raw.decode(encoding)
            if text.strip():
                return text
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("utf-8", "replace")


@lru_cache(maxsize=1)
def detect_wsl() -> WslInfo:
    """Probe WSL honestly. A missing WSL is reported, never assumed."""
    if os.name != "nt":
        return WslInfo(available=False, reason="WSL only exists on Windows.")
    wsl = _which("wsl")
    if not wsl:
        return WslInfo(available=False, reason="The Windows Subsystem for Linux is not installed.")
    try:
        completed = subprocess.run(
            [wsl, "-l", "-q"], capture_output=True, timeout=_PROBE_TIMEOUT_S, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return WslInfo(available=False, reason=f"WSL could not be reached: {exc}")
    if completed.returncode != 0:
        reason = _decode(completed.stderr or b"").strip() or "WSL is not ready on this computer."
        return WslInfo(available=False, reason=reason)
    names = [n.strip() for n in _decode(completed.stdout or b"").splitlines() if n.strip()]
    if not names:
        return WslInfo(available=False, reason="WSL is installed but has no distributions.")
    return WslInfo(available=True, distributions=tuple(names), default=names[0])


def _docker_available() -> bool:
    """Docker is DETECTED, never installed or fabricated.

    The interface exists (`terminal/runtimes.py::DockerRuntime`) but is not
    implemented; detection only decides whether the capability report claims it.
    """
    return _which("docker") is not None


def capabilities() -> TerminalCapabilities:
    """The honest capability report for this host."""
    shells = detect_shells()
    wsl = detect_wsl()
    from .pty_backend import pty_available

    runtimes: list[str] = ["local"]
    if wsl.available:
        runtimes.append("wsl")
    # Docker/SSH interfaces exist but are NOT implemented in Phase 1.
    return TerminalCapabilities(
        platform=("windows" if os.name == "nt" else platform.system().lower()),
        architecture=platform.machine() or "unknown",
        default_shell=shells[0].name if shells else None,
        shells=tuple(s.to_dict() for s in shells),
        wsl=wsl.to_dict(),
        runtimes=tuple(runtimes),
        pty=pty_available(),
        process_management=True,
        port_detection=True,
        docker=_docker_available(),
        ssh=_which("ssh") is not None,
    )


def resolve_shell(name: Optional[str]) -> Optional[ShellInfo]:
    """Resolve a requested shell name/path to a detected shell. None if unknown.

    A caller may ask for a shell by name ("powershell", "cmd", "wsl", "bash") or
    pass an absolute path that matches one of the detected shells. An unknown
    name returns None so the caller reports SHELL_NOT_FOUND rather than guessing.
    """
    shells = detect_shells()
    if not name:
        return shells[0] if shells else None
    wanted = str(name).strip().casefold()
    for shell in shells:
        if shell.name.casefold() == wanted:
            return shell
    for shell in shells:
        if shell.path and shell.path.casefold() == wanted:
            return shell
    return None


__all__ = [
    "capabilities",
    "default_shell",
    "detect_shells",
    "detect_wsl",
    "resolve_shell",
]
