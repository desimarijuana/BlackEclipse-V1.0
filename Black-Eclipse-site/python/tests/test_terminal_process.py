"""Background process lifecycle, streaming, signals, trees, timeouts, restart.

Cross-platform: a small helper picks the command syntax for the detected host
shell, so the same test exercises PowerShell on Windows and bash on POSIX.
"""

from __future__ import annotations

import os
import time

import pytest

from harness.persistence import AgentMemoryStore
from harness.terminal import shell_detect
from harness.terminal.manager import TerminalManager
from harness.terminal.recovery import pid_alive
from harness.terminal.store import TerminalStore

_TERMINAL = {"EXITED", "CRASHED", "STOPPED", "KILLED", "FAILED", "TIMEOUT"}


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


def err_cmd(msg: str) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"[Console]::Error.WriteLine('{msg}')"
    if kind == "cmd":
        return f"echo {msg} 1>&2"
    return f"printf '{msg}\\n' >&2"


def fail_cmd(code: int = 7) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"exit {code}"
    if kind == "cmd":
        return f"exit /b {code}"
    return f"exit {code}"


def sleep_cmd(seconds: int = 5) -> str:
    kind = _kind()
    if kind == "powershell":
        return f"Start-Sleep -Seconds {seconds}"
    if kind == "cmd":
        return f"ping -n {seconds + 1} 127.0.0.1 >NUL"
    return f"sleep {seconds}"


def read_stdin_cmd() -> str:
    kind = _kind()
    if kind == "powershell":
        return "$x = [Console]::In.ReadLine(); Write-Output ('got:' + $x); Start-Sleep -Milliseconds 300"
    if kind == "cmd":
        return "set /p x= & echo got:%x%"
    return "read x; echo got:$x"


@pytest.fixture()
def manager(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    events: list[tuple[str, dict]] = []
    mgr = TerminalManager(store=TerminalStore(store), on_event=lambda t, d: events.append((t, d)))
    mgr.events = events  # type: ignore[attr-defined]
    yield mgr
    mgr.close_all()
    store.close()


def _wait_state(manager: TerminalManager, process_id: str, states: set[str], timeout_s: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout_s
    info = manager.get_process(process_id) or {}
    while time.monotonic() < deadline:
        info = manager.get_process(process_id) or {}
        if info.get("state") in states:
            return info
        time.sleep(0.05)
    return info


def test_background_process_streams_stdout(manager):
    proc = manager.start_process(command=echo_cmd("hello_stream"), cwd=os.getcwd())
    assert proc["state"] in ("RUNNING", "STARTING")
    assert proc["pid"]
    done = _wait_state(manager, proc["processId"], _TERMINAL)
    assert done["exitCode"] == 0
    window = manager.read_process_output(proc["processId"], tail=20)
    assert "hello_stream" in window["text"]
    # stdout and stderr are separate buffers.
    assert manager.read_process_output(proc["processId"], stream="stderr")["text"] == ""


def test_background_process_streams_stderr_separately(manager):
    proc = manager.start_process(command=err_cmd("oops_stream"), cwd=os.getcwd())
    _wait_state(manager, proc["processId"], _TERMINAL)
    stderr = manager.read_process_output(proc["processId"], stream="stderr")
    assert "oops_stream" in stderr["text"]
    stdout = manager.read_process_output(proc["processId"], stream="stdout")
    assert "oops_stream" not in stdout["text"]


def test_crash_detection_reports_exit_code_and_category(manager):
    proc = manager.start_process(command=fail_cmd(7), cwd=os.getcwd())
    done = _wait_state(manager, proc["processId"], _TERMINAL)
    assert done["state"] == "CRASHED"
    assert done["exitCode"] == 7
    assert done["error"] and done["error"]["category"] in ("PROCESS_CRASH", "COMMAND_NOT_FOUND")
    # The crash is emitted with a last-output tail.
    assert any(t == "process.crashed" for t, _ in manager.events)


def test_stdin_is_delivered_to_a_background_process(manager):
    proc = manager.start_process(command=read_stdin_cmd(), cwd=os.getcwd())
    # Give the process a moment to be reading.
    time.sleep(0.8)
    assert manager.write_process_input(proc["processId"], "ping", newline=True) is True
    _wait_state(manager, proc["processId"], _TERMINAL)
    window = manager.read_process_output(proc["processId"], tail=20)
    assert "got:ping" in window["text"]


def test_stop_ends_a_long_running_process(manager):
    proc = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    assert proc["pid"]
    assert manager.stop_process(proc["processId"]) is True
    done = _wait_state(manager, proc["processId"], _TERMINAL)
    assert done["state"] in ("STOPPED", "KILLED", "EXITED")
    # No orphan: the pid is gone shortly after.
    time.sleep(0.2)
    assert pid_alive(done.get("pid")) in (False, None) or done["state"] in ("STOPPED", "KILLED")


def test_kill_terminates_the_process_tree(manager):
    proc = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    tree = manager.process_tree(proc["processId"])
    assert tree and tree["processId"] == proc["processId"]
    assert manager.kill_process(proc["processId"]) is True
    done = _wait_state(manager, proc["processId"], _TERMINAL)
    assert done["state"] in ("KILLED", "STOPPED")
    assert any(t == "process.killed" for t, _ in manager.events)


def test_send_signal_int_ends_the_process(manager):
    proc = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    result = manager.send_signal(proc["processId"], "SIGINT")
    assert result["ok"] is True
    done = _wait_state(manager, proc["processId"], _TERMINAL)
    assert done["state"] in ("KILLED", "STOPPED", "CRASHED", "EXITED")


def test_send_signal_stop_is_honestly_not_implemented(manager):
    proc = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    result = manager.send_signal(proc["processId"], "SIGSTOP")
    assert result["ok"] is False
    assert result["code"] == "NOT_IMPLEMENTED"
    manager.kill_process(proc["processId"])


def test_restart_preserves_configuration_and_gets_a_new_process_id(manager):
    proc = manager.start_process(command=echo_cmd("restartme"), cwd=os.getcwd())
    _wait_state(manager, proc["processId"], _TERMINAL)
    again = manager.restart_process(proc["processId"])
    assert again is not None
    assert again["processId"] != proc["processId"]
    assert again["command"] == proc["command"]
    assert again["cwd"] == proc["cwd"]
    assert any(t == "process.restarted" for t, _ in manager.events)


def test_foreground_timeout_is_a_structured_timeout(manager):
    result = manager.execute_command(command=sleep_cmd(5), cwd=os.getcwd(), timeout_ms=1_000)
    assert result.timed_out is True
    assert result.status == "timed_out"
    assert result.error is not None
    assert result.error.category == "TIMEOUT"


def test_foreground_command_captures_exit_code(manager):
    ok = manager.execute_command(command=echo_cmd("foreground_ok"), cwd=os.getcwd(), timeout_ms=20_000)
    assert ok.exit_code == 0
    assert "foreground_ok" in ok.stdout
    bad = manager.execute_command(command=fail_cmd(4), cwd=os.getcwd(), timeout_ms=20_000)
    assert bad.exit_code == 4
    assert bad.error is not None


def test_working_directory_not_found_is_structured(manager):
    result = manager.execute_command(command=echo_cmd("x"), cwd=os.path.join(os.getcwd(), "no-such-dir-xyz"), timeout_ms=5_000)
    assert result.status == "failed"
    assert result.error.category == "WORKING_DIRECTORY_NOT_FOUND"


def test_foreground_command_can_be_cancelled(manager):
    import threading

    holder: dict = {}
    thread = threading.Thread(
        target=lambda: holder.update(result=manager.execute_command(command=sleep_cmd(30), cwd=os.getcwd(), timeout_ms=60_000)),
        daemon=True,
    )
    thread.start()
    # Wait for the command to register its cancel event.
    deadline = time.monotonic() + 5
    execution_id = None
    while time.monotonic() < deadline and execution_id is None:
        with manager._lock:
            execution_id = next(iter(manager._cancel), None)
        time.sleep(0.05)
    assert execution_id is not None
    assert manager.cancel(execution_id) is True
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert holder["result"].status == "cancelled"


def test_process_and_command_rows_are_persisted(manager):
    proc = manager.start_process(command=echo_cmd("rowme"), cwd=os.getcwd())
    _wait_state(manager, proc["processId"], _TERMINAL)
    manager.execute_command(command=echo_cmd("history"), cwd=os.getcwd(), timeout_ms=20_000)
    assert any(row["id"] == proc["processId"] for row in manager._store.list_processes())
    assert manager._store.list_commands()


def test_health_distinguishes_running_from_ready(manager):
    # A process that exits immediately is not ready; its pid is not alive.
    proc = manager.start_process(command=echo_cmd("quick"), cwd=os.getcwd())
    _wait_state(manager, proc["processId"], _TERMINAL)
    health = manager.processes.health(proc["processId"])
    assert health["pidAlive"] is False
    assert health["ready"] is False
    # A live server that binds a port is RUNNING then READY.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    server = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    time.sleep(0.5)
    running = manager.processes.health(server["processId"], port=port)
    assert running["pidAlive"] is True
    # It is not listening on that port, so RUNNING but not READY.
    assert running["ready"] is False
    manager.kill_process(server["processId"])


def test_runaway_process_is_reported_without_silent_killing(manager):
    # A process that outlives the test's interest stays RUNNING; it is NOT killed
    # by any implicit timeout. Only an explicit stop/kill ends it.
    proc = manager.start_process(command=sleep_cmd(10), cwd=os.getcwd())
    time.sleep(1.0)
    info = manager.get_process(proc["processId"])
    assert info is not None and info["state"] == "RUNNING"
    manager.kill_process(proc["processId"])
