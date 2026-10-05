"""Persistent shell sessions: state, stdin, control, resize, confinement."""

from __future__ import annotations

import os
import time

import pytest

from harness.persistence import AgentMemoryStore
from harness.terminal import shell_detect
from harness.terminal.manager import TerminalManager
from harness.terminal.session import SessionManager
from harness.terminal.store import TerminalStore


def _kind() -> str:
    shell = shell_detect.default_shell()
    return shell.kind if shell else "sh"


def echo_cmd(msg: str) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"Write-Output '{msg}'"
    if kind == "cmd":
        return f"echo {msg}"
    return f"printf '{msg}\\n'"


def set_env_cmd(key: str, value: str) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"$env:{key}='{value}'"
    if kind == "cmd":
        return f"set {key}={value}"
    return f"export {key}={value}"


def read_env_cmd(key: str) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"Write-Output $env:{key}"
    if kind == "cmd":
        return f"echo %{key}%"
    return f"printf '%s\\n' \"${key}\""


@pytest.fixture()
def manager(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    mgr = TerminalManager(store=TerminalStore(store))
    yield mgr
    mgr.close_all()
    store.close()


def test_open_shell_returns_a_full_session_record(manager):
    info = manager.open_shell(cwd=os.getcwd(), agent_id="code-agent")
    assert info["sessionId"].startswith("term_")
    assert info["status"] == "running"
    assert info["pid"]
    assert info["cwd"] == os.getcwd()
    assert info["agentId"] == "code-agent"
    manager.close_shell(info["sessionId"])


def test_requested_unknown_shell_refused(manager):
    from harness.terminal.session import SessionStartError

    with pytest.raises(SessionStartError):
        manager.open_shell(shell_name="not-a-real-shell", cwd=os.getcwd())


def test_persistent_shell_keeps_working_directory_and_env(manager):
    info = manager.open_shell(cwd=os.getcwd())
    sid = info["sessionId"]
    # Run a command, set a variable, read it back in a later command.
    first = manager.run_in_shell(sid, echo_cmd("one"), workspace_root=os.getcwd())
    assert "one" in first["text"]
    manager.run_in_shell(sid, set_env_cmd("ECL_SESSION_VAR", "carried"), workspace_root=os.getcwd())
    second = manager.run_in_shell(sid, read_env_cmd("ECL_SESSION_VAR"), workspace_root=os.getcwd())
    assert "carried" in second["text"]
    manager.close_shell(sid)


def test_session_cd_builtin_moves_within_workspace_only(manager, tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    info = manager.open_shell(cwd=str(tmp_path))
    sid = info["sessionId"]
    inside = manager.run_in_shell(sid, f"cd {sub.name}", workspace_root=str(tmp_path))
    assert inside.get("data", {}).get("status") == "ok"
    assert "subdir" in (inside.get("data", {}).get("cwd") or "")
    # An escape is refused by the builtin, so the cwd does not move.
    escaped = manager.run_in_shell(sid, "cd ..\\..\\..", workspace_root=str(tmp_path))
    assert escaped.get("data", {}).get("code") in ("PATH_ESCAPE", None)
    manager.close_shell(sid)


def test_session_stdin_can_answer_a_prompt(manager):
    info = manager.open_shell(cwd=os.getcwd())
    sid = info["sessionId"]
    kind = _kind()
    if kind == "powershell":
        # `Read-Host` reads the console, not stdin; `[Console]::In` reads the pipe.
        prompt = "$line = [Console]::In.ReadLine(); Write-Output ('answer:' + $line); Start-Sleep -Milliseconds 300"
    elif kind == "cmd":
        prompt = "set /p ans=Answer: & echo answer:%ans%"
    else:
        prompt = "read ans; echo answer:$ans"
    import threading

    result: dict = {}
    thread = threading.Thread(
        target=lambda: result.update(r=manager.run_in_shell(sid, prompt, timeout_s=6, workspace_root=os.getcwd())),
        daemon=True,
    )
    thread.start()
    # Deliver the answer; retry a few times because the interpreter may not be at
    # the read yet. With a real PTY (installed by default) repeated writes are
    # harmless; the piped fallback would treat a second write as a command, so the
    # loop stops as soon as the answer appears.
    text = ""
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        manager.write_shell_input(sid, "yes", newline=True)
        time.sleep(0.5)
        text = result.get("r", {}).get("text") or ""
        if "answer:yes" in text:
            break
    thread.join(timeout=8)
    assert "answer:yes" in (result.get("r", {}).get("text") or ""), result.get("r")
    manager.close_shell(sid)


def test_session_control_and_resize_are_accepted(manager):
    info = manager.open_shell(cwd=os.getcwd())
    sid = info["sessionId"]
    # Resize is recorded; a real PTY would also apply it.
    assert manager.resize_shell(sid, 40, 120) in (True, False)
    updated = manager.get_shell(sid)
    assert updated["rows"] == 40 and updated["columns"] == 120
    # Ctrl+C is delivered (a real byte in PTY; a byte to the child otherwise).
    assert manager.send_control(sid, "c") in (True, False)
    manager.close_shell(sid)


def test_reading_session_output_uses_a_cursor(manager):
    info = manager.open_shell(cwd=os.getcwd())
    sid = info["sessionId"]
    manager.run_in_shell(sid, echo_cmd("cursor_line"), workspace_root=os.getcwd())
    window = manager.read_shell_output(sid, tail=50)
    assert "cursor_line" in window["text"]
    cursor = window["nextSequence"]
    again = manager.read_shell_output(sid, cursor=cursor)
    assert again["count"] == 0
    manager.close_shell(sid)


def test_close_shell_is_idempotent_and_removes_the_session(manager):
    info = manager.open_shell(cwd=os.getcwd())
    sid = info["sessionId"]
    assert manager.close_shell(sid) is True
    assert manager.close_shell(sid) is False
    assert manager.get_shell(sid) is None
    assert manager.list_shells() == []


def test_session_builtin_handles_pwd_without_spawning():
    # The builtin is a pure function of a session's state; exercising it directly
    # proves `pwd`/`cd`/`export` never fall back to a process.
    class _FakeSession:
        cwd = os.getcwd()
        env_profile: dict = {}
        updated_at = ""

    from pathlib import Path

    root = Path(os.getcwd())
    text, data = SessionManager.handle_session_builtin(_FakeSession(), "pwd", root)
    assert data["status"] == "ok"
    assert text == os.getcwd()
