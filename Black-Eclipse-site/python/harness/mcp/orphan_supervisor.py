"""Parent-death orphan reaping for MCP children (Phase 6, Milestone 2).

A hard death of the runtime (SIGKILL, OOM kill, a crashed dev server) must not
leave an MCP `npx`/`python` child running forever. This module guarantees that
without a per-server daemon and without importing anything else in the harness:
it is stdlib-only so it can run after the parent is already gone.

Platform strategy (the ADR records this):

  * **Windows** — the MCP SDK spawns each stdio child inside a Job Object with
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; when the parent dies the OS closes the
    job handle and every member is killed. That is already a hard guarantee, so
    this module is a no-op on Windows (verified: a `taskkill /F` of the parent
    leaves no surviving child).
  * **POSIX** — the SDK spawns each child with `start_new_session=True` (its own
    process-group leader) but there is no `PR_SET_PDEATHSIG`. This module starts
    ONE supervisor per process: the parent holds the only write end of a pipe and
    registers child process groups by line. When the parent dies the write end
    closes, the supervisor's blocking read returns EOF, and it sweeps every
    still-registered group TERM→grace→KILL. A clean shutdown unregisters each
    server, so nothing is signalled.

Design borrowed (not copied) from Hermes's `mcp_death_supervisor.py`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

log = logging.getLogger("harness.mcp.orphan")

_TERM_GRACE_S = 3.0
_REAP_POLL_S = 0.1
_MAX_LINE_CHARS = 256

_SUPERVISOR_MAIN = r'''
import os, signal, sys, time
_GRACE, _POLL, _CAP = 3.0, 0.1, 256
own = os.getpgid(0)
parent = int(os.environ.get("MCP_SUPERVISOR_PARENT_PGID", "0"))

def safe(pgid):
    return pgid > 1 and pgid != own and pgid != parent

def reap(pgids):
    alive = set()
    for pgid in pgids:
        try:
            os.killpg(pgid, signal.SIGTERM); alive.add(pgid)
        except OSError:
            pass
    deadline = time.monotonic() + _GRACE
    while alive and time.monotonic() < deadline:
        time.sleep(_POLL)
        for pgid in list(alive):
            try:
                os.killpg(pgid, 0)
            except OSError:
                alive.discard(pgid)
    for pgid in alive:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass

registered = set()
for line in sys.stdin:
    line = line[:_CAP]
    if not line.endswith("\n"):
        continue
    parts = line.split()
    if len(parts) != 2:
        continue
    verb, raw = parts
    try:
        pgid = int(raw)
    except ValueError:
        continue
    if verb == "register" and safe(pgid):
        registered.add(pgid)
    elif verb == "unregister":
        registered.discard(pgid)
reap(registered)
'''


class OrphanSupervisor:
    """Owns the supervisor child (POSIX) and the register/unregister pipe."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None

    @property
    def available(self) -> bool:
        return os.name == "posix"

    def start(self) -> None:
        """Start the supervisor once; a no-op on Windows or if already running."""
        if not self.available or self._proc is not None:
            return
        try:
            env = {**os.environ, "MCP_SUPERVISOR_PARENT_PGID": str(os.getpgid(0))}
            self._proc = subprocess.Popen(
                [sys.executable, "-c", _SUPERVISOR_MAIN],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
                text=True,
            )
        except OSError:  # pragma: no cover - a spawn failure must not block MCP
            log.warning("could not start the MCP orphan supervisor", exc_info=True)
            self._proc = None

    def register(self, pgid: int) -> None:
        self._send("register", pgid)

    def unregister(self, pgid: int) -> None:
        self._send("unregister", pgid)

    def _send(self, verb: str, pgid: int) -> None:
        if self._proc is None or self._proc.stdin is None or pgid <= 1:
            return
        try:
            self._proc.stdin.write(f"{verb} {int(pgid)}\n")
            self._proc.stdin.flush()
        except (OSError, ValueError):  # pragma: no cover - pipe closed
            pass

    def shutdown(self) -> None:
        """Clean shutdown: close the pipe so the supervisor exits (nothing to reap)."""
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - shutdown must never raise
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


# One supervisor per process.
_supervisor: Optional[OrphanSupervisor] = None


def supervisor() -> OrphanSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = OrphanSupervisor()
    return _supervisor


def child_pgids(parent_pid: Optional[int] = None) -> list[int]:
    """Process groups of this process's direct children (POSIX only).

    A tiny, best-effort enumeration so the manager can register what it spawned;
    empty when the platform cannot enumerate children.
    """
    if os.name != "posix":
        return []
    pid = parent_pid or os.getpid()
    pgids: set[int] = set()
    try:
        import subprocess as _sp

        out = _sp.run(
            ["ps", "-o", "pgid=", "--ppid", str(pid)],
            capture_output=True, text=True, timeout=2, check=False,
        )
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pgids.add(int(line))
    except Exception:  # noqa: BLE001 - enumeration is best-effort
        return []
    return sorted(pg for pg in pgids if pg > 1)


__all__ = ["OrphanSupervisor", "supervisor", "child_pgids"]
