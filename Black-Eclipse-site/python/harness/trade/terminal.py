"""The desktop side of MetaTrader 5: is it running, and bring it to the front.

In attach mode the terminal runs on the same host as the harness, so revealing it
is a local desktop affordance, not remote control. Eclipse never starts the
terminal on its own: `mt5.initialize(path=...)` silently LAUNCHES terminal64.exe
when it is closed, which turned every background broker read into a pop-up. A
connection may opt in with `autoLaunchTerminal: true`; otherwise a read against a
closed terminal fails honestly with TERMINAL_NOT_RUNNING.

A failure here must never change an order result: `reveal_terminal` returns a
status and the caller ignores it. On non-Windows hosts (a container or a bridge
to a remote EA) both helpers are an explicit no-op rather than a fake success.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Optional

_DEFAULT_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# The names a MetaTrader terminal can run under. MT5 ships terminal64.exe; the
# 32-bit build and MT4 use terminal.exe.
_TERMINAL_IMAGES = frozenset({"terminal64.exe", "terminal.exe"})

# Focus the already-running terminal by PID; if none exists, start the configured
# executable. The path travels in an env var so it can never be interpreted as
# PowerShell source.
_SCRIPT = r"""
$p = Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($p) {
  try {
    $w = New-Object -ComObject WScript.Shell
    if ($w.AppActivate($p.Id)) { exit 0 }
  } catch {}
}
if (Test-Path -LiteralPath $env:BE_MT5_PATH) {
  Start-Process -FilePath $env:BE_MT5_PATH
  exit 0
}
exit 3
"""


def _windows_image_names() -> Optional[set[str]]:
    """Every running image name, from the OS; ``None`` when it cannot be read.

    This is the same dependency-free Toolhelp snapshot `terminal/proctree.py`
    uses. It is duplicated here (a few lines) on purpose: broker adapters must
    not import the terminal subsystem, which pulls in the sandbox and process
    managers, just to ask "is terminal64.exe running?".
    """
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            return None
        names: set[str] = set()
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if kernel32.Process32First(snapshot, ctypes.byref(entry)):
                while True:
                    names.add(entry.szExeFile.decode("utf-8", "replace").strip().lower())
                    if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)
        return names
    except Exception:  # noqa: BLE001 - an unreadable snapshot is "unknown", not "closed"
        return None


def terminal_running(path: Optional[str] = None) -> bool:
    """Whether a MetaTrader terminal is already running. NEVER launches it.

    ``path`` narrows the match to that executable's own image name so a stray
    terminal.exe from another install does not masquerade as this connection's
    terminal. On an unreadable process list we answer True: the IPC call then
    decides, rather than falsely refusing a terminal that is actually running.
    """
    if sys.platform != "win32":
        return False
    names = _windows_image_names()
    if names is None:
        return True
    wanted = set(_TERMINAL_IMAGES)
    if path:
        base = os.path.basename(str(path)).strip().lower()
        if base:
            wanted.add(base)
    return bool(names & wanted)


def reveal_terminal(connection: Any) -> dict[str, Any]:
    """Focus (or, when explicitly enabled, launch) the MetaTrader terminal."""
    if sys.platform != "win32":
        return {"opened": False, "reason": "PLATFORM_UNSUPPORTED"}

    config = getattr(connection, "config", None) or {}
    if config.get("openTerminalOnTrade") is False:
        return {"opened": False, "reason": "DISABLED"}

    path = str(
        config.get("terminalPath")
        or os.environ.get("BE_MT5_PATH")
        or _DEFAULT_PATH
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
            env={**os.environ, "BE_MT5_PATH": path},
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:  # noqa: BLE001 - an affordance must not fail an order
        return {"opened": False, "reason": f"{type(exc).__name__}: {exc}"}

    if proc.returncode == 0:
        return {"opened": True, "path": path}
    detail = (proc.stderr or "").strip()
    return {
        "opened": False,
        "path": path,
        "reason": detail or f"exit {proc.returncode}",
    }


__all__ = ["reveal_terminal", "terminal_running"]
