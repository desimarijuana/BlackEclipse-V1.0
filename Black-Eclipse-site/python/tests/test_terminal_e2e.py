"""End-to-end: start a real dev server, detect its port, verify it, restart it.

This is the §61 acceptance path in miniature, using the process management the
rest of the subsystem provides. It uses `sys.executable` (the interpreter running
the suite — the vendored one in CI) so it is never skipped for a missing Python.
"""

from __future__ import annotations

import os
import socket
import time
import urllib.request

import pytest

from harness.persistence import AgentMemoryStore
from harness.terminal.manager import TerminalManager
from harness.terminal.store import TerminalStore

_SERVER = """
import sys, os, http.server, socketserver
value_path = "value.txt"
VALUE = open(value_path).read().strip() if os.path.exists(value_path) else "v1"

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = VALUE.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

print("ready on port", sys.argv[1], flush=True)
with socketserver.TCPServer(("127.0.0.1", int(sys.argv[1])), Handler) as httpd:
    httpd.serve_forever()
""".lstrip()


def _launch(exe: str, script: str, port: int) -> str:
    """A command line that runs ``exe script port`` in the host shell.

    PowerShell needs the call operator before a quoted path; cmd and POSIX bash
    take the quoted path directly.
    """
    if os.name == "nt":
        from harness.terminal.shell_detect import default_shell

        kind = default_shell().kind if default_shell() else "cmd"
        if kind == "powershell":
            return f'& "{exe}" {script} {port}'
    return f'"{exe}" {script} {port}'


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str, timeout: float = 3.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.read().decode("utf-8", "replace")


def _wait_http(url: str, timeout_s: float = 15.0) -> str:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _get(url)
        except Exception as exc:  # noqa: BLE001 - not ready yet
            last = exc
            time.sleep(0.2)
    raise AssertionError(f"server never answered {url}: {last}")


@pytest.fixture()
def manager(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    mgr = TerminalManager(store=TerminalStore(store))
    yield mgr
    mgr.close_all()
    store.close()


def test_create_run_serve_detect_restart_and_stop(manager, tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "server.py").write_text(_SERVER, encoding="utf-8")
    (project / "value.txt").write_text("v1", encoding="utf-8")
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    # 1-3. Create + start the development server in the background.
    proc = manager.start_process(
        command=_launch(os.sys.executable, "server.py", port),
        cwd=str(project),
        purpose="start_development_server",
    )
    assert proc["state"] in ("RUNNING", "STARTING")
    assert proc["pid"]

    # 4. Detect the process and stream its logs.
    info = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        info = manager.get_process(proc["processId"])
        if info and "ready on port" in (manager.read_process_output(proc["processId"], tail=50)["text"] or ""):
            break
        time.sleep(0.2)
    assert "ready on port" in manager.read_process_output(proc["processId"], tail=50)["text"]

    # 5. Detect the port via the OS listening table.
    conflict = None
    for _ in range(50):
        conflict = manager.find_port_conflict(port)
        if conflict is not None:
            break
        time.sleep(0.1)
    assert conflict is not None and conflict["port"] == port
    # The listening process is the server, which the shell wrapper launched as a
    # child, so it is attributed to the managed process's tree rather than to the
    # wrapper's own pid.
    info = manager.get_process(proc["processId"])
    assert conflict["pid"] in (
        {info["pid"]} | {c["pid"] for c in manager.process_tree(proc["processId"])["children"]}
    )

    # 6 + 7. Health check: the server answers.
    assert _wait_http(url) == "v1"

    # 8. Modify the source value the server reads at startup.
    (project / "value.txt").write_text("v2", encoding="utf-8")
    # The running server still serves the old value (it cached it at startup).
    assert _get(url) == "v1"

    # 9. Restart with the same configuration; 10. verify the NEW version.
    restarted = manager.restart_process(proc["processId"])
    assert restarted is not None
    assert restarted["processId"] != proc["processId"]
    restarted_port = None
    for _ in range(80):
        conflict = manager.find_port_conflict(port)
        if conflict is not None and port in (manager.get_process(restarted["processId"]) or {}).get("ports", []):
            restarted_port = conflict
            break
        time.sleep(0.1)
    assert restarted_port is not None
    assert _wait_http(url) == "v2"

    # 11. Stop the server; 12. confirm the process terminated and the port is free.
    assert manager.stop_process(restarted["processId"]) is True
    deadline = time.monotonic() + 10
    state = None
    while time.monotonic() < deadline:
        state = manager.get_process(restarted["processId"])["state"]
        if state in ("STOPPED", "KILLED", "EXITED"):
            break
        time.sleep(0.1)
    assert state in ("STOPPED", "KILLED", "EXITED")
    # The port is released shortly after.
    released = False
    for _ in range(60):
        if manager.find_port_conflict(port) is None:
            released = True
            break
        time.sleep(0.1)
    assert released, "the port was not released after the server stopped"
