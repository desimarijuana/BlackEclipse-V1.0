"""Execution layer — tool handlers, scheduler, workflow and service manager.

The terminal is faked so the service-manager and scheduler paths run without a
real shell; the runtime execution tests live in `test_execution_runtime.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.code.policy import WorkspaceBinding
from harness.execution import (
    ExecutionMode,
    ExecutionOrchestrator,
    ExecutionRequest,
    ExecutionService,
    build_runtime_registry,
)
from harness.execution.runtime import set_execution_service
from harness.execution.services import HealthChecker, PortManager, ServiceManager
from harness.execution.workflow import (
    ExecutionPlan,
    ExecutionStep,
    ExecutionWorkflow,
    RetryPolicy,
)
from harness.skills.permissions import Actor
from harness.tools import ToolContext


def _binding(root: Path, ws="ws_t"):
    return WorkspaceBinding(id=ws, root=root, base_revision="HEAD", strategy="direct")


def _actor(ws="ws_t"):
    return Actor(id="local", operator=False, workspace_id=ws, autonomy="edit_verify")


class FakeTerminal:
    """A minimal stand-in for the terminal manager (no real processes)."""

    def __init__(self):
        self._procs: dict[str, dict] = {}
        self._counter = 0

    def start_process(self, **kwargs):
        self._counter += 1
        pid = f"proc_{self._counter}"
        self._procs[pid] = {"processId": pid, "state": "RUNNING", "command": kwargs.get("command", "")}
        return dict(self._procs[pid])

    def stop_process(self, process_id):
        if process_id in self._procs:
            self._procs[process_id]["state"] = "STOPPED"
            return True
        return False

    def get_process(self, process_id):
        return self._procs.get(process_id)

    def read_process_output(self, process_id, tail=200):
        return {"text": "fake log output", "count": 1}

    def find_port_conflict(self, port):
        return None


# ── tool handlers ──────────────────────────────────────────────────────────────


def _tool_ctx(root, ws="ws_t", autonomy="edit_verify"):
    from harness.code.workspace import ResolvedWorkspace

    binding = _binding(root, ws)
    resolved = ResolvedWorkspace(id=ws, root=root, base_revision="HEAD", strategy="direct", binding=binding)
    ctx = ToolContext(run_id="run-t", log=lambda *_: None, workspace=resolved, autonomy=autonomy, agent_id="code-agent")
    return ctx


@pytest.mark.asyncio
async def test_execute_python_tool_runs(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    service = ExecutionService(store=None, terminal=None)
    if not service.registry.get("python").available():
        pytest.skip("python runtime not available")
    set_execution_service(service)
    try:
        from harness.execution.tools import execute_python

        text, data = await execute_python({"code": "print('tool-ok')"}, _tool_ctx(root))
        assert data["status"] == "COMPLETED"
        assert "tool-ok" in data["stdout"]
    finally:
        set_execution_service(None)


@pytest.mark.asyncio
async def test_execute_code_dispatches_and_refuses_unknown(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    service = ExecutionService(store=None, terminal=None)
    set_execution_service(service)
    try:
        from harness.execution.tools import execute_code

        if service.registry.get("python").available():
            _text, data = await execute_code({"language": "python", "code": "print(1)"}, _tool_ctx(root))
            assert data["status"] == "COMPLETED"
        text, data = await execute_code({"language": "brainfuck", "code": "+"}, _tool_ctx(root))
        assert data["status"] == "refused"
        assert data["code"] == "UNKNOWN_LANGUAGE"
    finally:
        set_execution_service(None)


@pytest.mark.asyncio
async def test_execute_denied_without_grant(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    service = ExecutionService(store=None, terminal=None)
    set_execution_service(service)
    try:
        from harness.execution.tools import execute_python

        text, data = await execute_python({"code": "print(1)"}, _tool_ctx(root, autonomy="plan_only"))
        assert data["status"] == "refused"
        assert data["code"] == "PROFILE_DENIED"
    finally:
        set_execution_service(None)


# ── scheduler ─────────────────────────────────────────────────────────────────────


def test_scheduler_runs_and_reports(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry = build_runtime_registry()
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    from harness.execution.scheduler import ExecutionScheduler

    scheduler = ExecutionScheduler(orchestrator, max_concurrent=2)
    try:
        submission = scheduler.submit(
            ExecutionRequest(language="python", workspace=_binding(root), code="print('sched')", mode=ExecutionMode.RUN),
            actor=_actor(),
        )
        result = scheduler.wait(submission, timeout=30)
        assert result is not None and result.status == "COMPLETED"
    finally:
        scheduler.shutdown(wait=True)


def test_scheduler_cancel_unknown_is_false(tmp_path):
    registry = build_runtime_registry()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path)
    from harness.execution.scheduler import ExecutionScheduler

    scheduler = ExecutionScheduler(orchestrator, max_concurrent=1)
    try:
        assert scheduler.cancel("nope") is False
    finally:
        scheduler.shutdown(wait=True)


# ── workflow ─────────────────────────────────────────────────────────────────────


def test_workflow_sequential_and_conditional(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry = build_runtime_registry()
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    workflow = ExecutionWorkflow(orchestrator)
    plan = ExecutionPlan(name="demo", steps=[
        ExecutionStep(name="first", request=ExecutionRequest(
            language="python", workspace=_binding(root), code="print('one')", mode=ExecutionMode.RUN)),
        ExecutionStep(name="second", request=ExecutionRequest(
            language="python", workspace=_binding(root), code="print('two')", mode=ExecutionMode.RUN),
            run_if="first"),
    ])
    outcome = workflow.run(plan, actor=_actor())
    assert outcome.status == "COMPLETED"
    assert [s["name"] for s in outcome.steps] == ["first", "second"]


def test_workflow_skips_when_gate_fails(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry = build_runtime_registry()
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    workflow = ExecutionWorkflow(orchestrator)
    plan = ExecutionPlan(name="demo", steps=[
        ExecutionStep(name="bad", request=ExecutionRequest(
            language="python", workspace=_binding(root), code="raise SystemExit(3)", mode=ExecutionMode.RUN)),
        ExecutionStep(name="after", request=ExecutionRequest(
            language="python", workspace=_binding(root), code="print('never')", mode=ExecutionMode.RUN),
            run_if="bad"),
    ])
    outcome = workflow.run(plan, actor=_actor())
    assert outcome.status == "FAILED"
    assert outcome.steps[0]["status"] != "COMPLETED"


def test_retry_policy_is_category_driven():
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry("TIMEOUT", 1) is True
    assert policy.should_retry("BUILD_ERROR", 1) is False
    assert policy.should_retry("SECURITY_ERROR", 1) is False
    assert policy.should_retry("TIMEOUT", 3) is False


# ── service manager ────────────────────────────────────────────────────────────


def test_service_manager_uses_terminal_and_health():
    terminal = FakeTerminal()
    manager = ServiceManager(terminal)
    data = manager.start_service(command="python server.py", cwd=".", port=0, protocol="process", wait_ready=False)
    assert data["status"] == "ok"
    service_id = data["service"]["serviceId"]
    status = manager.get_service_status(service_id)
    assert status["running"] is True
    logs = manager.get_service_logs(service_id)
    assert "fake log output" in logs["logs"]
    stopped = manager.stop_service(service_id)
    assert stopped["status"] == "ok"


def test_service_manager_unavailable_without_terminal():
    manager = ServiceManager(None)
    data = manager.start_service(command="x", cwd=".")
    assert data["status"] == "unavailable"


def test_port_manager_allocates_and_releases():
    ports = PortManager(None)
    port = ports.allocate(preferred=0, owner="t")
    assert port > 0
    ports.release(port)


def test_health_checker_process_and_tcp():
    checker = HealthChecker()
    assert checker.process(True)["ok"] is True
    # A TCP check to a closed port is a structured negative, never an exception.
    result = checker.tcp("127.0.0.1", 1, timeout_s=0.2)
    assert result["ok"] is False


def test_workspace_binding_prefers_the_code_workspace(tmp_path):
    """Verification must act on the tree the agent edited (the worktree)."""
    from types import SimpleNamespace

    from harness.execution.service import make_actor, workspace_binding

    ctx = _tool_ctx(tmp_path, ws="server")
    # No code workspace yet -> the request's resolved binding (server root).
    assert workspace_binding(ctx).id == "server"
    # Once a code workspace is allocated, execution/verification binds to it.
    cw_binding = _binding(tmp_path / "wt", ws="cw1")
    ctx._code_workspace = (SimpleNamespace(id="cw1"), cw_binding, None, None)
    assert workspace_binding(ctx).id == "cw1"
    assert make_actor(ctx).workspace_id == "cw1"
