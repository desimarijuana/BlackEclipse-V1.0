"""Resource telemetry and runaway-process protection."""

from __future__ import annotations

import os
import time

from harness.persistence import AgentMemoryStore
from harness.terminal import resources
from harness.terminal.manager import TerminalManager
from harness.terminal.process_manager import ProcessManager
from harness.terminal.store import TerminalStore


def test_system_resources_are_structured_and_honest():
    report = resources.system_resources()
    assert isinstance(report["cpuCount"], int) and report["cpuCount"] >= 1
    # Memory is either a real number or honestly unknown — never fabricated.
    if report["memoryTotalBytes"] is not None:
        assert report["memoryTotalBytes"] > 0
        assert 0 <= report["memoryUsedPct"] <= 100


def test_resource_limits_read_from_env(monkeypatch):
    monkeypatch.setenv("HARNESS_TERMINAL_MAX_PROCESSES", "7")
    monkeypatch.setenv("HARNESS_TERMINAL_RUNAWAY_SECONDS", "123")
    limits = resources.ResourceLimits.from_env()
    assert limits.max_processes == 7
    assert limits.runaway_seconds == 123
    assert limits.to_dict()["maxProcesses"] == 7


def _script(tmp_path, name: str, body: str) -> str:
    """A command that runs a helper script under whatever shell the host uses."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    from harness.terminal.shell_detect import default_shell

    shell = default_shell()
    if shell and shell.kind == "powershell":
        return f'& "{os.sys.executable}" "{path}"'
    return f'"{os.sys.executable}" "{path}"'


def test_process_limit_refuses_a_new_start(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_TERMINAL_MAX_PROCESSES", "1")
    sleeper = _script(tmp_path, "sleep.py", "import time\ntime.sleep(5)\n")
    mgr = TerminalManager(store=TerminalStore(AgentMemoryStore(str(tmp_path / "am.db"))))
    try:
        first = mgr.start_process(command=sleeper, cwd=str(tmp_path))
        assert first["state"] in ("RUNNING", "STARTING")
        second = mgr.start_process(command=sleeper, cwd=str(tmp_path))
        assert second["state"] == "FAILED"
        assert second["error"]["type"] == "PROCESS_LIMIT"
    finally:
        mgr.close_all()


def test_runaway_flags_output_without_killing(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_TERMINAL_MAX_OUTPUT_BYTES", "10")
    loud = _script(tmp_path, "loud.py", "import sys, time\nsys.stdout.write('x' * 500)\nsys.stdout.flush()\ntime.sleep(5)\n")
    mgr = TerminalManager(store=TerminalStore(AgentMemoryStore(str(tmp_path / "am.db"))))
    try:
        proc = mgr.start_process(command=loud, cwd=str(tmp_path))
        time.sleep(1.2)
        report = mgr.processes.resource_report()
        flags = [p for p in report["processes"] if p["processId"] == proc["processId"]]
        assert flags and flags[0]["runaway"] and "output" in flags[0]["runaway"]["reasons"]
        # It is FLAGGED, not killed: the process is still running.
        assert mgr.get_process(proc["processId"])["state"] == "RUNNING"
    finally:
        mgr.close_all()


def test_resource_report_has_limits_and_active_count(tmp_path):
    mgr = TerminalManager(store=TerminalStore(AgentMemoryStore(str(tmp_path / "am.db"))))
    try:
        report = mgr.processes.resource_report()
        assert "limits" in report and "maxProcesses" in report["limits"]
        assert report["activeProcesses"] == 0
        assert report["system"]["cpuCount"] >= 1
    finally:
        mgr.close_all()


def test_proctree_descendant_matching_is_precise():
    from harness.terminal import proctree

    mapping = proctree.process_map()
    if not mapping:
        import pytest

        pytest.skip("process enumeration unavailable on this host")
    # This test process is always in the map, and it has no python descendants.
    assert os.getpid() in mapping
    assert proctree.descendant_pids_matching(os.getpid(), "definitely-not-a-process") == []
    assert proctree.descendant_pids_matching(None, "python") == []


def test_health_reports_runaway_field(tmp_path):
    mgr = TerminalManager(store=TerminalStore(AgentMemoryStore(str(tmp_path / "am.db"))))
    try:
        proc = mgr.start_process(command=f'"{os.sys.executable}" -c "print(1)"', cwd=str(tmp_path))
        for _ in range(60):
            if mgr.get_process(proc["processId"])["state"] not in ("RUNNING", "STARTING"):
                break
            time.sleep(0.05)
        health = mgr.processes.health(proc["processId"])
        assert "ready" in health and health["ready"] is False
    finally:
        mgr.close_all()
