"""Recovery after a runtime restart.

The process registry is persisted, but the OS handles are not: after Eclipse (or
the Python runtime) restarts, we own no live `Popen` and no Job Object. So we do
NOT trust a persisted state. On boot `RecoveryManager`:

  * reads every non-terminal process row;
  * checks whether its pid still exists;
  * marks a process EXITED when the pid is gone;
  * marks a process UNKNOWN (still alive, but no longer under management) when the
    pid exists — never RUNNING, because we cannot control it;
  * closes every persisted session, since its shell died with the runtime.

No fabricated "still running" and no silent adoption of a stranger process.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..persistence import now_iso


def pid_alive(pid: Optional[int]) -> bool:
    """Whether a pid currently exists. Best-effort, never raises."""
    if not pid or int(pid) <= 0:
        return False
    pid = int(pid)
    if os.name == "nt":  # pragma: no cover - Windows
        import ctypes

        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong(0)
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            # STILL_ACTIVE == 259
            return bool(ok) and code.value == 259
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class RecoveryManager:
    """Reconcile persisted process/session state at startup."""

    def __init__(self, store: Optional[Any], *, on_event: Optional[Any] = None) -> None:
        self._store = store
        self._on_event = on_event

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001
                pass

    def reconcile(self) -> dict[str, Any]:
        """Reconcile every persisted record. Returns a summary. Never raises."""
        if self._store is None:
            return {"processes": 0, "sessions": 0, "reconciled": [], "unavailable": True}
        reconciled: list[dict[str, Any]] = []
        processes = 0
        sessions = 0
        try:
            alive_rows = self._store.list_alive_processes()
        except Exception:  # noqa: BLE001
            alive_rows = []
        for row in alive_rows:
            processes += 1
            pid = row.get("pid")
            if pid_alive(pid):
                state = "UNKNOWN"
                note = "still running on the computer, but no longer managed by Eclipse"
            else:
                state = "EXITED"
                note = "no longer running; it ended while Eclipse was closed"
            try:
                self._store.mark_process_reconciled(row["id"], state, exit_code=row.get("exitCode"))
            except Exception:  # noqa: BLE001
                pass
            reconciled.append({"processId": row["id"], "state": state, "note": note})
            self._emit("process.reconciled", {"processId": row["id"], "state": state})
        # Sessions: their shell process died with the runtime.
        try:
            persisted_sessions = self._store.list_sessions(limit=500)
        except Exception:  # noqa: BLE001
            persisted_sessions = []
        for row in persisted_sessions:
            if row.get("status") in ("closed",):
                continue
            sessions += 1
            try:
                if row.get("pid") and pid_alive(row.get("pid")):
                    self._store.update_session(row["id"], status="orphaned", updatedAt=now_iso())
                else:
                    self._store.mark_session_closed(row["id"])
            except Exception:  # noqa: BLE001
                pass
            self._emit("session.reconciled", {"sessionId": row["id"]})
        return {"processes": processes, "sessions": sessions, "reconciled": reconciled}


__all__ = ["RecoveryManager", "pid_alive"]
