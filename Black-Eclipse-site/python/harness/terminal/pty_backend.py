"""Optional real-PTY support, with an honest fallback.

A true interactive terminal (ANSI, TUI apps, cursor control, window size) needs a
pseudo-terminal. Python's stdlib has none. Two maintained options exist:

  * ``pywinpty`` (Windows) — a bundled real ConPTY.
  * ``ptyprocess`` (POSIX) — a forkpty wrapper.

Neither is in `python/requirements.txt`, and the zero-config rule says we must not
add one automatically. So this module PROBES for them and reports availability
truthfully. When a real PTY is unavailable the session layer uses a piped
persistent shell instead — which still preserves cwd and environment, accepts
stdin, and streams output — and the capability report says ``pty: false``.

This module never fakes a PTY. It never raises on import of an optional dep.
"""

from __future__ import annotations

import shutil
from typing import Any, Optional

# Result codes returned by `open_pty` when no backend is present.
BACKEND_NONE = "none"


def _try_pywinpty() -> Optional[Any]:
    try:  # pragma: no cover - depends on optional install
        import winpty  # type: ignore

        return winpty
    except Exception:  # noqa: BLE001
        return None


def _try_ptyprocess() -> Optional[Any]:
    try:  # pragma: no cover - depends on optional install
        import ptyprocess  # type: ignore

        return ptyprocess
    except Exception:  # noqa: BLE001
        return None


def pty_backend_name() -> str:
    """The name of the available PTY backend, or 'none' — never guessed."""
    import os

    if os.name == "nt":
        return "pywinpty" if _try_pywinpty() is not None else BACKEND_NONE
    return "ptyprocess" if _try_ptyprocess() is not None else BACKEND_NONE


def pty_available() -> bool:
    return pty_backend_name() != BACKEND_NONE


class PseudoTerminal:
    """A thin, uniform wrapper over a real PTY, or an explicit no-op.

    ``available`` is False when no backend exists; every method then either
    returns False or raises ``PtyUnavailable`` so the caller falls back cleanly.
    """

    def __init__(self) -> None:
        self.backend = pty_backend_name()
        self.available = self.backend != BACKEND_NONE
        self._impl: Any = None

    def spawn(self, argv: list[str], *, cwd: str, env: dict[str, str], rows: int, columns: int) -> bool:
        """Start a PTY-backed process. Returns False when no backend exists."""
        if not self.available:
            return False
        import os

        try:
            if os.name == "nt":
                winpty = _try_pywinpty()
                if winpty is None:  # pragma: no cover - race
                    self.available = False
                    return False
                self._impl = winpty.PtyProcess.spawn(
                    argv, cwd=cwd, env=env, dimensions=(int(rows), int(columns)),
                )
                return True
            ptyprocess = _try_ptyprocess()
            if ptyprocess is None:  # pragma: no cover - race
                self.available = False
                return False
            self._impl = ptyprocess.PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(int(rows), int(columns)))
            return True
        except Exception:  # noqa: BLE001 - a failed PTY spawn must not crash a session
            self.available = False
            self._impl = None
            return False

    def write(self, data: str) -> bool:
        if not self.available or self._impl is None:
            return False
        try:
            self._impl.write(data)
            return True
        except Exception:  # noqa: BLE001
            return False

    def read(self, size: int = 4096) -> str:
        if not self.available or self._impl is None:
            return ""
        try:
            chunk = self._impl.read(size)
        except EOFError:
            return ""
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8", "replace")
        return chunk or ""

    def resize(self, rows: int, columns: int) -> bool:
        if not self.available or self._impl is None:
            return False
        try:
            self._impl.setwinsize(int(rows), int(columns))
            return True
        except Exception:  # noqa: BLE001
            return False

    def isalive(self) -> bool:
        if not self.available or self._impl is None:
            return False
        try:
            return bool(self._impl.isalive())
        except Exception:  # noqa: BLE001
            return False

    def terminate(self, *, force: bool = False) -> None:
        if self._impl is None:
            return
        try:
            self._impl.terminate(force=force)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["BACKEND_NONE", "PseudoTerminal", "pty_available", "pty_backend_name"]
