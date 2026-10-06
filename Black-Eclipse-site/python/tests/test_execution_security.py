"""Execution layer — security and resource-attack tests.

Each case is an adversarial input that must end in a structured refusal, a
timeout, or a cancelled execution with the whole process tree cleaned — never a
successful run, never a leaked process, never a sandbox bypass.
"""

from __future__ import annotations

import threading
import time

import pytest

from harness.code.policy import WorkspaceBinding
from harness.execution import (
    ExecutionMode,
    ExecutionOrchestrator,
    ExecutionRequest,
    build_runtime_registry,
)
from harness.execution.artifacts import ArtifactManager
from harness.skills.permissions import Actor


def _setup(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    registry = build_runtime_registry()
    return registry, ExecutionOrchestrator(registry, scratch_root=scratch), root


def _actor(autonomy="edit_verify"):
    return Actor(id="local", operator=False, workspace_id="ws_s", autonomy=autonomy)


def _binding(root):
    return WorkspaceBinding(id="ws_s", root=root, base_revision="HEAD", strategy="direct")


# ── filesystem isolation ───────────────────────────────────────────────────────


def test_entrypoint_traversal_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), entrypoint="../../etc/passwd", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED"
    assert (result.error or {}).get("code") in ("PATH_TRAVERSAL", "PATH_OUTSIDE_WORKSPACE", "PROTECTED_PATH")


def test_entrypoint_absolute_path_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    other = tmp_path / "outside.py"
    other.write_text("print('escaped')\n", encoding="utf-8")
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), entrypoint=str(other), mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED"


def test_entrypoint_protected_file_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    (root / "jdds.db").write_text("secret", encoding="utf-8")
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), entrypoint="jdds.db", mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED"


def test_sql_database_outside_workspace_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    secret = tmp_path / "secret.db"
    secret.write_text("x", encoding="utf-8")
    result = orch.run(
        ExecutionRequest(
            language="sql", workspace=_binding(root), code="SELECT 1",
            mode=ExecutionMode.RUN, metadata={"dialect": "sqlite", "database": str(secret)},
        ),
        actor=_actor(),
    )
    assert "OUTSIDE_WORKSPACE" in (result.error or {}).get("code", "") or result.status == "SECURITY_BLOCKED"


# ── permissions / autonomy ──────────────────────────────────────────────────────


def test_plan_only_cannot_execute(tmp_path):
    registry, orch, root = _setup(tmp_path)
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code="print('no')", mode=ExecutionMode.RUN),
        actor=_actor(autonomy="plan_only"),
    )
    assert result.status == "SECURITY_BLOCKED"
    assert (result.error or {}).get("code") == "PROFILE_DENIED"


def test_workspace_mismatch_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    actor = Actor(id="eve", operator=False, workspace_id="someone_else", autonomy="edit_verify")
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code="print('no')", mode=ExecutionMode.RUN),
        actor=actor,
    )
    assert result.status == "SECURITY_BLOCKED"


def test_forbidden_secret_is_refused(tmp_path):
    registry, orch, root = _setup(tmp_path)
    result = orch.run(
        ExecutionRequest(
            language="python", workspace=_binding(root), code="print('x')",
            mode=ExecutionMode.RUN, secrets={"GITHUB_TOKEN": "leak"},
        ),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED"
    assert (result.error or {}).get("code") == "SECRET_FORBIDDEN"


# ── resource attacks ─────────────────────────────────────────────────────────────


def test_infinite_loop_is_timed_out(tmp_path):
    registry, orch, root = _setup(tmp_path)
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    from dataclasses import replace

    from harness.execution.models import ResourceLimits

    request = ExecutionRequest(
        language="python", workspace=_binding(root),
        code="while True:\n    pass\n", mode=ExecutionMode.RUN,
        resource_limits=replace(ResourceLimits.from_env(), timeout_ms=2000),
    )
    started = time.monotonic()
    result = orch.run(request, actor=_actor())
    elapsed = time.monotonic() - started
    assert result.status in ("TIMED_OUT", "FAILED")
    assert result.error_class == "TIMEOUT"
    assert elapsed < 30  # the timeout actually fired


def test_huge_output_is_bounded(tmp_path):
    registry, orch, root = _setup(tmp_path)
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    from dataclasses import replace

    from harness.execution.models import ResourceLimits

    request = ExecutionRequest(
        language="python", workspace=_binding(root),
        code="import sys\nfor _ in range(200000):\n    sys.stdout.write('x'*100 + '\\n')\n",
        mode=ExecutionMode.RUN,
        resource_limits=replace(ResourceLimits.from_env(), max_stdout_bytes=10_000),
    )
    result = orch.run(request, actor=_actor())
    # The output is capped; the result records truncation rather than exhausting memory.
    assert result.truncated is True
    assert len(result.stdout) <= 20_000


def test_cancellation_stops_the_run(tmp_path):
    registry, orch, root = _setup(tmp_path)
    if not registry.get("python").available():
        pytest.skip("python runtime not available")
    cancel = threading.Event()

    def _cancel_soon():
        time.sleep(1.0)
        cancel.set()

    threading.Thread(target=_cancel_soon, daemon=True).start()
    started = time.monotonic()
    result = orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code="\nwhile True:\n    pass\n", mode=ExecutionMode.RUN),
        actor=_actor(), cancel_event=cancel,
    )
    assert result.status in ("CANCELLED", "FAILED", "TIMED_OUT")
    if result.status == "CANCELLED":
        assert result.error_class == "CANCELLED"
    assert time.monotonic() - started < 30


# ── artifact confinement ────────────────────────────────────────────────────────


def test_artifact_manager_refuses_outside_paths(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    manager = ArtifactManager(root=root, execution_id="exec_x")
    artifacts = manager.collect_paths(["../secret.txt", str(secret)])
    assert artifacts == []
