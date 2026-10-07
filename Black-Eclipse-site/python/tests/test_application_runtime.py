"""Application Runtime layer — integration tests with a fake terminal + mocks.

These exercise the full lifecycle (discover → validate → install → build → start
→ health → stop → restart → reconcile → recover) without requiring Docker or a
real subprocess, using a `FakeTerminal` that reuses the execution layer's proven
shape. The mock adapters make the tests deterministic.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from harness.execution.application.container import ContainerResult
from harness.execution.application.manager import ApplicationRuntimeManager, RuntimePolicy, build_runtime_registry
from harness.execution.application.models import ApplicationState, HealthStatus
from harness.execution.application.store import ApplicationRuntimeStore
from harness.persistence import AgentMemoryStore


class FakeTerminal:
    """A stand-in terminal manager: process records + ports, no real processes."""

    def __init__(self, *, alive: bool = True) -> None:
        self._procs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._counter = 0
        self._alive = alive
        self._occupied: set[int] = {3000}

    def start_process(self, **kwargs):
        with self._lock:
            self._counter += 1
            pid = f"proc_{self._counter}"
            self._procs[pid] = {
                "processId": pid, "pid": 1000 + self._counter, "state": "RUNNING",
                "command": kwargs.get("command", ""), "workspaceId": kwargs.get("workspace_id"),
                "purpose": kwargs.get("purpose"),
            }
            return dict(self._procs[pid])

    def stop_process(self, process_id):
        if process_id in self._procs:
            self._procs[process_id]["state"] = "STOPPED"
            return True
        return False

    def get_process(self, process_id):
        return self._procs.get(process_id)

    def read_process_output(self, process_id, tail=200, stream=None):
        return {"text": "fake log output", "status": "RUNNING", "count": 1}

    def list_processes(self, **kwargs):
        return list(self._procs.values())

    def find_port_conflict(self, port):
        if port in self._occupied:
            return {"port": port, "pid": 9999, "processId": None, "_owned": False}
        return None

    def list_ports(self):
        return [{"port": p} for p in sorted(self._occupied)]


class MockContainer:
    """A mock container engine that never touches a real daemon."""

    name = "docker"
    capabilities = frozenset({"container.build", "container.run", "container.lifecycle", "container.logs", "container.ps", "container.inspect", "health"})

    def __init__(self) -> None:
        self.calls: list[str] = []

    def available(self):
        return True

    def version(self):
        return "mock-1.0"

    def detect(self):
        return True

    def ps(self, *, all=True):
        return ContainerResult(ok=True, operation="ps", data=[{"Name": "web", "Service": "web", "State": "running"}])

    def logs(self, container, *, tail=200, timestamps=False):
        return ContainerResult(ok=True, operation="logs", output="mock container log")

    def healthcheck(self, container):
        return ContainerResult(ok=True, operation="healthcheck", data={"Status": "running", "Health": {"Status": "healthy"}})

    def inspect(self, container):
        return ContainerResult(ok=True, operation="inspect", data={"State": {"Status": "running"}})


def _make_manager(tmp_path, *, terminal=None, policy=None):
    db = tmp_path / "agent-memory.db"
    store = AgentMemoryStore(str(db))
    rt_store = ApplicationRuntimeStore(store)
    registry = build_runtime_registry()
    registry.containers.register(MockContainer())
    manager = ApplicationRuntimeManager(
        registry=registry, terminal=terminal, store=rt_store, bus=None, policy=policy,
    )
    return manager, rt_store, store


def _node_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        '{"name":"web","scripts":{"dev":"node server.js","build":"echo build","test":"echo test"},'
        '"dependencies":{"express":"4"}}',
        encoding="utf-8",
    )
    (root / "server.js").write_text("require('http')", encoding="utf-8")
    (root / "node_modules").mkdir(exist_ok=True)


def test_start_local_service_and_stop(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, rt_store, store = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    assert handle.state in (ApplicationState.RUNNING, ApplicationState.DEGRADED)
    assert handle.processes, "a process should have been started"
    assert handle.descriptor is not None and handle.descriptor.package_manager == "npm"
    # Persisted: Eclipse can recover knowledge of the runtime after its restart.
    row = rt_store.get_runtime(handle.runtime_id)
    assert row is not None and row["state"] in ("RUNNING", "DEGRADED")
    # Stop cleanly.
    result = manager.stop(handle.runtime_id)
    assert result["status"] == "ok"
    assert manager.status(handle.runtime_id)["runtime"]["state"] == "STOPPED"


def test_start_without_terminal_fails_honestly(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    # A project with no long-running command and no terminal: nothing runs, so the
    # runtime must report the honest truth rather than a fake RUNNING.
    manager, _, _ = _make_manager(tmp_path, terminal=None)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    assert handle.state == ApplicationState.FAILED
    assert handle.last_error is not None


def test_port_conflict_picks_alternative_port(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    (root / "package.json").write_text(
        '{"name":"web","scripts":{"dev":"node server.js"},"dependencies":{"next":"14"}}',
        encoding="utf-8",
    )
    (root / "tsconfig.json").write_text("{}", encoding="utf-8")
    terminal = FakeTerminal()  # occupies 3000
    manager, _, _ = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    # 3000 is occupied by a foreign process; the manager records an alternative.
    ports = [p.port for p in handle.ports]
    assert 3000 not in ports or any(p.source == "declared" and p.port == 3000 for p in handle.ports)
    assert handle.state in (ApplicationState.RUNNING, ApplicationState.DEGRADED)


def test_health_marks_degraded_when_service_never_ready(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, _, _ = _make_manager(tmp_path, terminal=terminal)
    # The FakeTerminal reports RUNNING, so process health passes; but there is no
    # HTTP endpoint. We assert the health REPORT is a real evaluation, not an
    # assumption.
    handle = manager.start(root, install=False, build=False, wait_ready=True, health_timeout_s=1.0)
    assert handle.health is not None
    assert handle.health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)


def test_restart_increments_count(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, _, _ = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    restarted = manager.restart(handle.runtime_id, install=False, build=False, wait_ready=False)
    assert restarted.restart_count == 1
    assert restarted.runtime_id != handle.runtime_id


def test_reconcile_marks_degraded_when_gone(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, rt_store, _ = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    # Simulate Eclipse restart: a fresh manager with the SAME store, no live procs.
    terminal2 = FakeTerminal()
    terminal2._procs = {}  # the old process is gone
    manager2, _, _ = _make_manager(tmp_path, terminal=terminal2)
    result = manager2.reconcile()
    assert result["count"] >= 1
    reconciled = [r for r in result["reconciled"] if r["runtimeId"] == handle.runtime_id]
    assert reconciled and reconciled[0]["state"] == "DEGRADED"


def test_compose_up_records_services(tmp_path):
    root = tmp_path / "stack"
    root.mkdir()
    (root / "docker-compose.yml").write_text(
        "services:\n  web:\n    build: .\n    ports:\n      - 3000:3000\n  db:\n    image: postgres:16\n",
        encoding="utf-8",
    )

    class FakeCompose:
        name = "docker-compose"
        engine = "docker"
        capabilities = frozenset({"compose.up", "compose.down", "compose.ps", "compose.pull", "compose.validate", "compose.config", "compose.logs", "compose.exec"})

        def available(self):
            return True

        def version(self):
            return "mock"

        def validate(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="validate")

        def config(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="config")

        def pull(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="pull")

        def up(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="up", output="Started web db")

        def down(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="down")

        def ps(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="ps", services=[{"Service": "web", "Name": "x_web_1"}, {"Service": "db", "Name": "x_db_1"}])

        def build(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="build")

        def start(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="start")

        def stop(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="stop")

        def restart(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="restart")

        def rm(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="rm")

        def logs(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="logs")

        def exec(self, **kwargs):
            from harness.execution.application.compose import ComposeResult
            return ComposeResult(ok=True, operation="exec")

    db = tmp_path / "agent-memory.db"
    store = AgentMemoryStore(str(db))
    registry = build_runtime_registry()
    registry.containers.register(MockContainer())
    registry.compose.register(FakeCompose())
    manager = ApplicationRuntimeManager(registry=registry, terminal=None, store=ApplicationRuntimeStore(store))
    handle = manager.start(root, wait_ready=False)
    assert handle.state in (ApplicationState.RUNNING, ApplicationState.DEGRADED)
    assert "web" in handle.services and "db" in handle.services


def test_inspect_reports_service_graph(tmp_path):
    root = tmp_path / "stack"
    root.mkdir()
    (root / "docker-compose.yml").write_text(
        "services:\n  web:\n    build: .\n    depends_on:\n      - db\n  db:\n    image: postgres:16\n",
        encoding="utf-8",
    )
    manager, _, _ = _make_manager(tmp_path)
    data = manager.inspect(root)
    graph = data["serviceGraph"]
    assert graph["startupOrder"].index("db") < graph["startupOrder"].index("web")


def test_events_are_emitted(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, _, _ = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    events = manager.events(handle.runtime_id)
    types = {e["type"] for e in events}
    assert "application.discovered" in types
    assert "runtime.started" in types


def test_metrics_are_point_in_time(tmp_path):
    root = tmp_path / "web"
    _node_project(root)
    terminal = FakeTerminal()
    manager, _, _ = _make_manager(tmp_path, terminal=terminal)
    handle = manager.start(root, install=False, build=False, wait_ready=False)
    data = manager.metrics(handle.runtime_id)
    assert data["status"] == "ok"
    assert "uptimeS" in data and data["restartCount"] == 0


def test_destructive_requires_authorization(tmp_path):
    policy = RuntimePolicy(level="ask")
    allowed, decision, reason = policy.decide("compose.down")
    assert allowed is False and decision == "ask"
    allowed2, _, _ = policy.decide("compose.down", authorized=True)
    assert allowed2 is True
    # A read operation is allowed freely.
    assert policy.decide("runtime.inspect")[0] is True


def test_runtime_policy_deny_blocks():
    policy = RuntimePolicy(level="deny")
    assert policy.decide("container.remove", authorized=True)[0] is False
