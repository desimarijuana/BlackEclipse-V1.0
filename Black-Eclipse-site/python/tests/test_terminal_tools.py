"""The terminal tools through the ONE registry (validation + authorizer + handler)."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import pytest

from harness.code.policy import WorkspaceBinding
from harness.code.worktree import CodeWorkspace
from harness.code.workspace import ResolvedWorkspace
from harness.persistence import AgentMemoryStore, now_iso
from harness.terminal import runtime as runtime_mod
from harness.terminal.manager import TerminalManager
from harness.terminal.store import TerminalStore
from harness.terminal.tools import make_terminal_tool_authorizer, register_terminal_tools
from harness.tools import ToolContext, ToolRegistry

READY = {"EXITED", "CRASHED", "STOPPED", "KILLED", "FAILED", "TIMEOUT"}


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data: dict | None = None) -> dict:
        self.events.append((event_type, data or {}))
        return {"type": event_type}

    def emit_sync(self, event_type: str, data: dict | None = None) -> None:
        self.events.append((event_type, data or {}))


class _ApprovingStore:
    """A stand-in operator that approves every `ask` request, so the tests can
    drive the execution path without a live UI. The `deny` path is still enforced
    by the handler, and the registry-level gate is tested elsewhere."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def consume_kind(self, *, kind: str, request_key: str, digest: str, workspace_id=None):
        return {"kind": kind, "digest": digest}

    def find_active_kind(self, *, kind: str, request_key: str, digest: str):
        return {"kind": kind, "digest": digest}

    def request_kind(self, **kwargs) -> dict:
        self.requests.append(kwargs)
        return kwargs


@pytest.fixture()
def project(tmp_path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "hello.txt").write_text("hi\n", encoding="utf-8")
    return Path(os.path.realpath(root))


@pytest.fixture()
def manager(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    mgr = TerminalManager(store=TerminalStore(store))
    runtime_mod.set_terminal_manager(mgr)
    yield mgr
    mgr.close_all()
    runtime_mod.set_terminal_manager(None)
    store.close()


def _context(project: Path, *, autonomy: str = "edit_verify", approvals=_ApprovingStore()) -> ToolContext:
    ws_id = "cw_" + project.name[:20]
    binding = WorkspaceBinding(id=ws_id, root=project, base_revision="abc", strategy="direct")
    resolved = ResolvedWorkspace(id=ws_id, root=project, base_revision="abc", strategy="direct", binding=binding)
    cw = CodeWorkspace(id=ws_id, root=project, strategy="direct", base_revision="abc", created_at=now_iso())
    ctx = ToolContext(
        run_id="run_term", log=lambda *_: None, workspace=resolved, autonomy=autonomy,
        agent_id="code-agent", approvals=approvals,
        authorize_effect=make_terminal_tool_authorizer(),
    )
    ctx._code_workspace = (cw, binding, resolved, None)
    return ctx


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_terminal_tools(reg)
    return reg


def _call(registry, name, args, ctx):
    return asyncio.run(registry.execute(name, f"call_{name}", args, ctx))


def _echo(msg: str) -> str:
    return f"Write-Output '{msg}'" if os.name == "nt" else f"printf '{msg}\\n'"


def _sleep(seconds: int = 5) -> str:
    return f"Start-Sleep -Seconds {seconds}" if os.name == "nt" else f"sleep {seconds}"


def _wait(process_id: str, timeout_s: float = 8.0) -> dict:
    mgr = runtime_mod.get_terminal_manager()
    deadline = time.monotonic() + timeout_s
    info = mgr.get_process(process_id) or {}
    while time.monotonic() < deadline and info.get("state") not in READY:
        time.sleep(0.05)
        info = mgr.get_process(process_id) or {}
    return info


def test_all_terminal_tools_are_registered(manager):
    registry = _registry()
    names = set(registry.names())
    expected = {
        "execute_command", "open_shell", "close_shell", "list_terminal_sessions",
        "terminal_session_status", "run_shell_command", "write_shell_input",
        "read_shell_output", "resize_shell", "send_shell_control", "start_process",
        "stop_process", "kill_process", "restart_process", "list_processes",
        "process_status", "read_process_output", "write_process_input",
        "send_signal", "process_tree", "process_health",
        "list_ports", "terminal_capabilities", "system_info", "resource_report",
    }
    assert expected <= names


def test_execute_command_through_the_registry(manager, project):
    registry = _registry()
    ctx = _context(project)
    result = _call(registry, "execute_command", {"command": _echo("registry_ok"), "timeoutMs": 30_000}, ctx)
    assert result.ok, result.text
    assert result.data["status"] == "ok"
    assert "registry_ok" in result.data["stdout"]
    # The execution is recorded.
    assert manager._store.list_commands()


def test_execute_command_refuses_a_destructive_shape(manager, project):
    registry = _registry()
    ctx = _context(project)
    # A destructive command never reaches the handler: the authorizer refuses it,
    # so the registry reports TOOL_FORBIDDEN and no process runs.
    result = _call(registry, "execute_command", {"command": "rm -rf /", "timeoutMs": 5_000}, ctx)
    assert not result.ok
    assert "TOOL_FORBIDDEN" in result.text
    assert manager.list_processes() == []


def test_execute_command_refuses_without_the_execute_grant(manager, project):
    registry = _registry()
    ctx = _context(project, autonomy="plan_only")
    result = _call(registry, "execute_command", {"command": _echo("x"), "timeoutMs": 5_000}, ctx)
    assert result.data.get("code") == "PROFILE_DENIED"


def test_execute_command_refuses_a_cwd_outside_the_workspace(manager, project):
    registry = _registry()
    ctx = _context(project)
    result = _call(registry, "execute_command", {"command": _echo("x"), "cwd": "../../..", "timeoutMs": 5_000}, ctx)
    assert result.data.get("status") == "refused"
    assert result.data.get("code") == "WORKSPACE_ESCAPE"


def test_terminal_run_uses_the_same_terminal_manager(manager, project):
    """V2 terminal merge: the code profile's `terminal_run` must execute through
    the shared TerminalManager, not a second sandbox primitive."""
    import sys

    from harness.code.terminal_tools import terminal_run

    ctx = _context(project)
    command = f'"{sys.executable}" -c "print(\'manager_ok\')"'
    text, data = asyncio.run(terminal_run({"command": command, "timeoutS": 30}, ctx))
    assert data["status"] == "ok", text
    assert "manager_ok" in text
    assert str(data.get("executionId", "")).startswith("exec_")
    assert any(row.get("id") == data["executionId"] for row in manager._store.list_commands())


def test_start_read_stop_a_background_process_through_the_registry(manager, project):
    registry = _registry()
    ctx = _context(project)
    started = _call(registry, "start_process", {"command": _echo("bg_via_tool"), "purpose": "run_script"}, ctx)
    assert started.ok
    pid = started.data["processId"]
    _wait(pid)
    output = _call(registry, "read_process_output", {"processId": pid, "tail": 20}, ctx)
    assert "bg_via_tool" in output.data["text"]
    listed = _call(registry, "list_processes", {}, ctx)
    assert any(p["processId"] == pid for p in listed.data["processes"])
    # A long-running one can be stopped.
    long_running = _call(registry, "start_process", {"command": _sleep(10)}, ctx)
    lp = long_running.data["processId"]
    time.sleep(0.3)
    stopped = _call(registry, "stop_process", {"processId": lp}, ctx)
    assert stopped.ok


def test_open_run_and_close_a_persistent_shell_through_the_registry(manager, project):
    registry = _registry()
    ctx = _context(project)
    opened = _call(registry, "open_shell", {}, ctx)
    assert opened.ok
    sid = opened.data["sessionId"]
    ran = _call(registry, "run_shell_command", {"sessionId": sid, "command": _echo("shell_via_tool")}, ctx)
    assert ran.ok
    assert "shell_via_tool" in ran.data.get("text", "") or "shell_via_tool" in ran.text
    closed = _call(registry, "close_shell", {"sessionId": sid}, ctx)
    assert closed.ok


def test_read_only_tools_need_no_authorizer(manager, project):
    registry = _registry()
    ctx = _context(project)
    ctx.authorize_effect = None  # no authorizer at all
    caps = _call(registry, "terminal_capabilities", {}, ctx)
    assert caps.ok and caps.data["platform"] in ("windows", "linux", "darwin")
    ports = _call(registry, "list_ports", {}, ctx)
    assert ports.ok
    system = _call(registry, "system_info", {}, ctx)
    assert system.ok


def test_process_health_reports_not_ready_for_a_finished_process(manager, project):
    registry = _registry()
    ctx = _context(project)
    started = _call(registry, "start_process", {"command": _echo("health"), "purpose": "run_script"}, ctx)
    pid = started.data["processId"]
    _wait(pid)
    health = _call(registry, "process_health", {"processId": pid}, ctx)
    assert health.ok
    assert health.data["ready"] is False


def test_one_workspace_cannot_touch_anothers_process(manager, project, tmp_path):
    registry = _registry()
    # Start a process under one workspace.
    owner_ctx = _context(project)
    started = _call(registry, "start_process", {"command": _echo("mine")}, owner_ctx)
    assert started.ok
    pid = started.data["processId"]
    _wait(pid)
    # A DIFFERENT workspace id may not read or stop it.
    other = tmp_path / "other"
    other.mkdir()
    other_ctx = _context(Path(os.path.realpath(other)))
    other_ctx._code_workspace = (None, None, other_ctx.workspace, None)
    assert _call(registry, "process_status", {"processId": pid}, other_ctx).data.get("code") == "NOT_FOUND"
    assert _call(registry, "read_process_output", {"processId": pid}, other_ctx).data.get("code") == "NOT_FOUND"
    assert _call(registry, "stop_process", {"processId": pid}, other_ctx).data.get("code") == "NOT_FOUND"


def test_effectful_tool_is_refused_without_an_authorizer(manager, project):
    registry = _registry()
    ctx = _context(project)
    ctx.authorize_effect = None
    result = _call(registry, "start_process", {"command": _echo("x")}, ctx)
    assert not result.ok
    assert "TOOL_FORBIDDEN" in result.text
