"""Execution layer — integration tests: real subprocess runs through the sandbox.

These exercise the actual runtime adapters and the orchestrator against a real
temporary project. They are honest about the environment: a runtime that is not
installed must report UNAVAILABLE, never fail the test with a fake pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.code.policy import WorkspaceBinding
from harness.execution import (
    ExecutionMode,
    ExecutionOrchestrator,
    ExecutionRequest,
    build_runtime_registry,
)
from harness.skills.permissions import Actor


def _actor(workspace_id="ws_i", autonomy="edit_verify"):
    return Actor(id="local", operator=False, workspace_id=workspace_id, autonomy=autonomy)


def _binding(root: Path):
    return WorkspaceBinding(id="ws_i", root=root, base_revision="HEAD", strategy="direct")


def _orchestrator(tmp_path, scratch):
    registry = build_runtime_registry()
    return registry, ExecutionOrchestrator(registry, scratch_root=scratch)


def test_execute_python_inline(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    root = tmp_path / "proj"
    root.mkdir()
    registry, orch = _orchestrator(tmp_path, scratch)
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code="print(6*7)", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "COMPLETED"
    assert result.exit_code == 0
    assert "42" in result.stdout


def test_execute_javascript_inline(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("javascript").available():
        pytest.skip("node not available")
    result = orch.run(
        ExecutionRequest(language="javascript", workspace=_binding(root), code="console.log('hi')", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "COMPLETED"
    assert "hi" in result.stdout


def test_run_missing_entrypoint_is_a_structured_failure(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), entrypoint="nope.py", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status != "COMPLETED"
    assert result.exit_code not in (0,)


def test_failing_python_yields_runtime_diagnostic(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    code = "def f():\n    raise ValueError('boom')\nf()"
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code=code, mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "FAILED"
    assert result.error_class == "USER_CODE_ERROR"
    assert any("boom" in d.message for d in result.diagnostics)


def test_build_and_test_python_project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    result = orch.run(
        ExecutionRequest(language="", workspace=_binding(root), mode=ExecutionMode.BUILD_AND_TEST),
        actor=_actor(),
    )
    assert result.status == "COMPLETED", result.to_dict()
    summary = (result.metadata or {}).get("testSummary") or {}
    assert summary.get("passed", 0) >= 1
    assert summary.get("failed", 0) == 0


def test_failing_test_reports_normalized_failure(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text("from calc import add\n\ndef test_bad():\n    assert add(2, 3) == 6\n", encoding="utf-8")
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    result = orch.run(
        ExecutionRequest(language="", workspace=_binding(root), mode=ExecutionMode.TEST),
        actor=_actor(),
    )
    assert result.status == "TEST_ERROR"
    assert result.error_class == "TEST_ERROR"
    summary = (result.metadata or {}).get("testSummary") or {}
    assert summary.get("failed", 0) >= 1


def test_discover_tests_python(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    registry = build_runtime_registry()
    adapter = registry.get("python")
    found = adapter.discover_tests(root, None)
    assert any("test_x.py" in f for f in found)


def test_sql_sqlite_select(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    result = orch.run(
        ExecutionRequest(
            language="sql", workspace=_binding(root), code="SELECT 1+1 AS n",
            mode=ExecutionMode.RUN, metadata={"dialect": "sqlite", "read_only": True, "row_limit": 10},
        ),
        actor=_actor(),
    )
    assert result.status == "COMPLETED"
    assert "[2]" in result.stdout.replace(" ", "")


def test_sql_destructive_blocked_when_read_only(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    result = orch.run(
        ExecutionRequest(
            language="sql", workspace=_binding(root), code="DROP TABLE users",
            mode=ExecutionMode.RUN, metadata={"dialect": "sqlite", "read_only": True},
        ),
        actor=_actor(),
    )
    assert "SQL_DESTRUCTIVE_BLOCKED" in result.stdout


def test_shell_command_runs_and_reports_exit(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry, orch = _orchestrator(tmp_path, tmp_path / "scratch")
    if not registry.get("shell").available():
        pytest.skip("shell runtime not available")
    result = orch.run(
        ExecutionRequest(language="shell", workspace=_binding(root), code="echo hello-shell", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "COMPLETED"
    assert "hello-shell" in result.stdout


def test_scratched_workdir_is_removed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    registry, orch = _orchestrator(tmp_path, scratch)
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code="print('x')", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    # The per-execution staged directory is always cleaned up.
    leftovers = list(scratch.glob("exec_*"))
    assert leftovers == []
