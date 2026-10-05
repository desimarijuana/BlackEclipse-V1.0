"""Persistence, recovery and capability discovery."""

from __future__ import annotations

import os

from harness.persistence import AgentMemoryStore
from harness.terminal.manager import TerminalManager
from harness.terminal.recovery import RecoveryManager, pid_alive
from harness.terminal.store import TerminalStore


def _store(tmp_path):
    return AgentMemoryStore(str(tmp_path / "agent-memory.db"))


def test_store_round_trips_process_and_session_rows(tmp_path):
    store = _store(tmp_path)
    ts = TerminalStore(store)
    ts.upsert_process({
        "processId": "proc_x", "pid": 1234, "parentPid": None, "command": "npm run dev",
        "cwd": str(tmp_path), "runtime": "local", "shell": "powershell", "state": "RUNNING",
        "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:01+00:00",
        "ports": [3000], "workspaceId": "ws_1", "agentId": "code-agent", "runId": "run_1",
        "taskId": None, "purpose": "start_development_server",
    })
    row = ts.get_process("proc_x")
    assert row["ports"] == [3000]
    assert row["state"] == "RUNNING"

    ts.save_session({
        "sessionId": "term_x", "runtime": "local", "shell": "powershell", "pid": 42,
        "cwd": str(tmp_path), "status": "running", "rows": 30, "columns": 100,
        "envProfile": {"NODE_ENV": "test"}, "workspaceId": "ws_1", "agentId": "code-agent",
        "owner": None, "pty": False,
        "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00",
    })
    session = ts.get_session("term_x")
    assert session["envProfile"] == {"NODE_ENV": "test"}
    assert session["rows"] == 30

    ts.record_command({
        "id": "exec_x", "sessionId": None, "processId": None, "command": "npm test",
        "cwd": str(tmp_path), "runtime": "local", "shell": None, "exitCode": 0,
        "status": "ok", "durationMs": 100, "createdAt": "2026-01-01T00:00:00+00:00",
    })
    assert ts.list_commands()[0]["command"] == "npm test"
    store.close()


def test_pid_alive_is_true_for_self_and_false_for_a_bogus_pid():
    assert pid_alive(os.getpid()) is True
    assert pid_alive(999_999_999) is False
    assert pid_alive(None) is False


def test_recovery_marks_a_dead_pid_exited(tmp_path):
    store = _store(tmp_path)
    ts = TerminalStore(store)
    ts.upsert_process({
        "processId": "proc_dead", "pid": 999_999_999, "parentPid": None, "command": "gone",
        "cwd": str(tmp_path), "runtime": "local", "shell": "x", "state": "RUNNING",
        "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00",
        "ports": [], "workspaceId": None, "agentId": None, "runId": None, "taskId": None, "purpose": None,
    })
    summary = RecoveryManager(ts).reconcile()
    assert summary["processes"] == 1
    assert ts.get_process("proc_dead")["state"] == "EXITED"
    store.close()


def test_recovery_marks_a_live_pid_unknown_never_running(tmp_path):
    store = _store(tmp_path)
    ts = TerminalStore(store)
    ts.upsert_process({
        "processId": "proc_live", "pid": os.getpid(), "parentPid": None, "command": "still here",
        "cwd": str(tmp_path), "runtime": "local", "shell": "x", "state": "RUNNING",
        "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00",
        "ports": [], "workspaceId": None, "agentId": None, "runId": None, "taskId": None, "purpose": None,
    })
    RecoveryManager(ts).reconcile()
    # We own no handle for it after a restart, so it is UNKNOWN, not RUNNING.
    assert ts.get_process("proc_live")["state"] == "UNKNOWN"
    store.close()


def test_recovery_closes_persisted_sessions(tmp_path):
    store = _store(tmp_path)
    ts = TerminalStore(store)
    ts.save_session({
        "sessionId": "term_old", "runtime": "local", "shell": "powershell", "pid": 999_999_999,
        "cwd": str(tmp_path), "status": "running", "rows": 24, "columns": 80,
        "envProfile": {}, "workspaceId": None, "agentId": None, "owner": None, "pty": False,
        "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00",
    })
    summary = RecoveryManager(ts).reconcile()
    assert summary["sessions"] == 1
    assert ts.get_session("term_old")["status"] == "closed"
    store.close()


def test_capabilities_report_pty_and_runtimes_honestly(tmp_path):
    store = _store(tmp_path)
    mgr = TerminalManager(store=TerminalStore(store))
    caps = mgr.capabilities()
    assert "local" in caps["runtimes"]
    assert isinstance(caps["pty"], bool)
    assert caps["runtimesDetailed"]["docker"]["implemented"] is False
    assert caps["runtimesDetailed"]["ssh"]["implemented"] is False
    assert caps["runtimesDetailed"]["local"]["available"] is True
    store.close()
