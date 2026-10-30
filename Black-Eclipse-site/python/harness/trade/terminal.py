"""Bring the attached MetaTrader terminal to the front after an Eclipse order.

In attach mode the terminal runs on the same host as the harness, so revealing it
is a local desktop affordance, not remote control. A failure here must never
change the order result: the helper returns a status and the caller ignores it.
On non-Windows hosts (a container or a bridge to a remote EA) it is an explicit
no-op rather than a fake success.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

_DEFAULT_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

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


def reveal_terminal(connection: Any) -> dict[str, Any]:
    """Focus or launch the connection's MetaTrader terminal (best effort)."""
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


__all__ = ["reveal_terminal"]
