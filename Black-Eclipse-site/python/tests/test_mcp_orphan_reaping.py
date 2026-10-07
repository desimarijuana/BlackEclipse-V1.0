"""Phase 6 Milestone 2 — orphan reaping.

Real process, real kill: spawn a child through the same client and assert that a
hard kill of the parent leaves no surviving child. Platform behavior differs and
is asserted honestly (see ADR-H68):

  * Windows — the MCP SDK spawns the child inside a Job Object with
    KILL_ON_JOB_CLOSE, so the OS reaps it on parent death; the orphan supervisor
    is a no-op there.
  * POSIX — the orphan supervisor detects parent death by pipe EOF and sweeps the
    registered process group TERM→grace→KILL.

The test verifies the guarantee that actually exists on this platform; it never
asserts a fake one.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "mcp_fixtures"
RAW = FIXTURES / "raw_fixture.py"

# A parent that starts a real MCP stdio server and then sleeps forever, writing
# its own pid once the server is up. It starts the supervisor on POSIX.
_PARENT_SOURCE = r'''
import asyncio, os, sys
# The harness package lives in the same directory as this test file. Derive it
# from __file__ (passed as argv[4]) instead of the process cwd: the test is run
# both from the repo root and from `python/`, and the old `os.getcwd()` form
# silently resolved a nonexistent path when pytest ran from `python/`.
sys.path.insert(0, sys.argv[4] if len(sys.argv) > 4 else os.getcwd())
from harness.mcp.client import MCPConnection
from harness.mcp.config import MCPServerConfig
from harness.mcp.orphan_supervisor import child_pgids, supervisor

async def main():
    raw = sys.argv[1]
    out = sys.argv[2]
    child_pidfile = sys.argv[3]
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[raw, "normal"], enabled=True,
        env={"MCP_FIXTURE_PIDFILE": child_pidfile},
    )
    sup = supervisor()
    if sup.available:
        sup.start()
    before = set(child_pgids())
    conn = MCPConnection(cfg)
    task = asyncio.ensure_future(conn.start())
    if sup.available:
        for _ in range(100):
            await asyncio.sleep(0.04)
            new = set(child_pgids()) - before
            if new:
                for pg in new:
                    sup.register(pg)
                break
    await task
    with open(out, "w") as f:
        f.write(str(os.getpid()))
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
'''


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_hard(pid: int) -> None:
    if os.name == "nt":
        # NOT /T: kill only the parent, so a surviving child is left to the OS job.
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
    else:
        import signal

        os.kill(pid, signal.SIGKILL)


def _direct_children(pid: int) -> list[int]:
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["wmic", "process", "where", f"ParentProcessId={pid}", "get", "ProcessId"],
                capture_output=True, text=True, timeout=10,
            )
            found = [int(t) for t in out.stdout.split() if t.isdigit() and int(t) != pid]
            if found:
                return found
        except (OSError, subprocess.SubprocessError):
            pass
        # wmic is deprecated/absent on newer Windows: fall back to CIM via the shell.
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter \"ParentProcessId={pid}\").ProcessId"],
                capture_output=True, text=True, timeout=15,
            )
            return [int(t) for t in out.stdout.split() if t.isdigit() and int(t) != pid]
        except (OSError, subprocess.SubprocessError):
            return []
    out = subprocess.run(["ps", "-o", "pid=", "--ppid", str(pid)], capture_output=True, text=True)
    return [int(x) for x in out.stdout.split() if x.isdigit()]


def test_hard_parent_kill_leaves_no_surviving_child(tmp_path):
    parent_script = tmp_path / "orphan_parent.py"
    parent_script.write_text(_PARENT_SOURCE, encoding="utf-8")
    out = tmp_path / "parent.pid"
    child_pidfile = tmp_path / "child.pid"
    # The interpreter's import root is the `python/` directory that contains this
    # test file's package, independent of pytest's cwd.
    python_root = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.Popen(
        [sys.executable, str(parent_script), str(RAW), str(out), str(child_pidfile), python_root],
        cwd=python_root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (out.exists() and child_pidfile.exists()):
            if proc.poll() is not None:
                pytest.fail("orphan test parent exited before starting its child")
            time.sleep(0.2)
        if not (out.exists() and child_pidfile.exists()):
            pytest.fail("orphan test parent never started its child")
        child_pid = int(child_pidfile.read_text(encoding="utf-8").strip())
        assert _alive(child_pid), "fixture child should be running before the kill"
        _kill_hard(int(out.read_text(encoding="utf-8").strip()))
        time.sleep(5)
        assert not _alive(child_pid), f"child {child_pid} survived a hard parent kill"
    finally:
        if proc.poll() is None:
            proc.kill()
