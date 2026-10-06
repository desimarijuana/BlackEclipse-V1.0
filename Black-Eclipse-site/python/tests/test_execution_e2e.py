"""Execution layer — end-to-end verification loop and tool surface tests.

The e2e test mirrors the spec's acceptance scenario: a project with an intentional
bug is built and tested, fails, is diagnosed, fixed, and only then passes — with
evidence from an ACTUAL execution, and within a bounded number of iterations.
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
    ExecutionVerifier,
    build_runtime_registry,
)
from harness.skills.permissions import Actor


def _binding(root: Path):
    return WorkspaceBinding(id="ws_e", root=root, base_revision="HEAD", strategy="direct")


def _actor():
    return Actor(id="local", operator=False, workspace_id="ws_e", autonomy="edit_verify")


def test_verify_loop_fixes_a_broken_test(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    source = root / "calc.py"
    source.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")  # BUG: subtracts
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8",
    )
    registry = build_runtime_registry()
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    verifier = ExecutionVerifier(orchestrator, max_iterations=3)

    seen_statuses: list[str] = []

    def fix(result, iteration):
        seen_statuses.append(result.status)
        if result.status == "TEST_ERROR":
            source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            return "corrected the addition"
        return None

    outcome = verifier.run(
        ExecutionRequest(language="", workspace=_binding(root), mode=ExecutionMode.BUILD_AND_TEST),
        actor=_actor(), fix=fix,
    )
    assert outcome.status == "passed", outcome.to_dict()
    assert outcome.iterations >= 2  # failed first, then passed
    assert outcome.evidence  # real execution evidence exists
    final = outcome.evidence[-1]
    assert final["status"] == "COMPLETED"


def test_verify_loop_bounded_without_a_fix(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_fail.py").write_text("def test_fail():\n    assert 1 == 2\n", encoding="utf-8")
    registry = build_runtime_registry()
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    verifier = ExecutionVerifier(orchestrator, max_iterations=2)
    outcome = verifier.run(
        ExecutionRequest(language="", workspace=_binding(root), mode=ExecutionMode.BUILD_AND_TEST),
        actor=_actor(),
    )
    # No fix step => it stops honestly and does not claim success.
    assert outcome.status in ("unrepairable", "budget_exhausted")
    assert outcome.iterations <= 2


def test_execution_service_persists_history(tmp_path, monkeypatch):
    from harness.persistence import AgentMemoryStore

    db = tmp_path / "agent-memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", str(db))
    store = AgentMemoryStore(str(db))
    service = ExecutionService(store=store, terminal=None)
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    from dataclasses import replace

    from harness.execution.models import ResourceLimits

    if not service.registry.get("python").available():
        pytest.skip("python runtime not available")
    request = ExecutionRequest(
        language="python", workspace=_binding(root), code="print('persisted')",
        mode=ExecutionMode.RUN, run_id="run-e2e",
        resource_limits=replace(ResourceLimits.from_env(), timeout_ms=20_000),
    )
    result = service.run(request, actor=_actor(), run_id="run-e2e")
    assert result.status == "COMPLETED"
    row = service.store.get_execution(result.execution_id)
    assert row is not None
    assert row["language"] == "python"
    assert "persisted" in row["stdout"]
    listed = service.store.list_executions(run_id="run-e2e")
    assert any(item["id"] == result.execution_id for item in listed)


def test_execution_tools_registered_and_gated(tmp_path):
    from harness.execution.tools import register_execution_tools
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    names = register_execution_tools(registry)
    assert "execute_python" in names
    assert "build_project" in names
    assert registry.get("execute_python").permission == "write"
    assert registry.get("discover_tests").permission == "read"
