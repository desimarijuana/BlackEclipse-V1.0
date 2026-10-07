"""Application Runtime layer — security & failure tests.

Security: command-injection resistance (argv, never a shell string), path
confinement for env files, secret masking in every output/event, and
operator-authorization for destructive operations.

Failure: missing runtime, missing package manager, port conflict, invalid compose,
engine unavailable, and process-crash diagnosis — each must fail gracefully with a
structured diagnosis, never a crash and never a fake success.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.execution.application.compose import DockerComposeAdapter
from harness.execution.application.container import DockerAdapter
from harness.execution.application.diagnostics import RuntimeDiagnosticsEngine
from harness.execution.application.environment import EnvironmentManager, is_secret_name
from harness.execution.application.manager import ApplicationRuntimeManager, RuntimePolicy, build_runtime_registry
from harness.execution.application.models import DiagnosticCategory
from harness.execution.application.store import ApplicationRuntimeStore
from harness.persistence import AgentMemoryStore


def _manager(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "m.db"))
    return ApplicationRuntimeManager(registry=build_runtime_registry(), terminal=None, store=ApplicationRuntimeStore(store))


# ── command injection ───────────────────────────────────────────────────────────


def test_container_name_injection_is_refused(tmp_path):
    adapter = DockerAdapter()
    # A shell metacharacter in a name/arg must be a structured INVALID_NAME/ARG,
    # never concatenated into a command line.
    result = adapter.remove("web; rm -rf /", force=True)
    assert result.ok is False
    assert result.code == "INVALID_NAME"


def test_container_exec_injection_is_refused(tmp_path):
    adapter = DockerAdapter()
    result = adapter.exec("web; whoami", ["sh", "-c", "echo pwned"])
    assert result.ok is False
    assert result.code == "INVALID_NAME"


def test_container_build_bad_arg_key_refused():
    adapter = DockerAdapter()
    result = adapter.build(context=Path("."), tag="img:1", args={"BAD KEY": "x"})
    assert result.ok is False
    assert result.code in ("INVALID_ARG", "ENGINE_UNAVAILABLE", "SANDBOX_UNAVAILABLE", "FAILED")


def test_container_port_map_validation():
    adapter = DockerAdapter()
    result = adapter.run(image="nginx", ports=["3000; rm -rf /"])
    # The port map is rejected structurally (or the engine is simply unavailable).
    assert result.ok is False
    assert result.code in ("INVALID_ARG", "ENGINE_UNAVAILABLE", "SANDBOX_UNAVAILABLE")


def test_compose_service_name_injection_refused():
    adapter = DockerComposeAdapter()
    result = adapter.up(cwd=Path("."), services=["web; whoami"])
    assert result.ok is False
    assert result.code == "INVALID_NAME"


# ── secret safety ────────────────────────────────────────────────────────────────


def test_secret_values_never_reach_a_report(tmp_path):
    (tmp_path / ".env").write_text("DATABASE_URL=postgres://u:hunter2@h/db\nPORT=3000\n", encoding="utf-8")
    manager = EnvironmentManager()
    report = manager.load(tmp_path)
    serialized = str(report.to_dict())
    assert "hunter2" not in serialized
    assert "postgres://" not in serialized
    # The non-secret value is still visible (it is configuration, not a secret).
    assert "3000" in serialized


def test_secret_names_are_conservative():
    for name in ("DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "SIGNING_KEY", "MONGODB_URI"):
        assert is_secret_name(name), name
    for name in ("PORT", "NODE_ENV", "LOG_LEVEL"):
        assert not is_secret_name(name), name


def test_env_metadata_exposes_no_values(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=sk-secret\nPORT=3000\n", encoding="utf-8")
    manager = _manager(tmp_path)
    meta = manager.environment.metadata(tmp_path)
    for item in meta["variables"]:
        assert "value" not in item


def test_secret_never_appears_in_events(tmp_path):
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=hunter2\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"x","scripts":{"dev":"node x.js"}}', encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    manager = _manager(tmp_path)
    handle = manager.start(tmp_path, install=False, build=False, wait_ready=False)
    events_text = str(manager.events(handle.runtime_id))
    assert "hunter2" not in events_text


# ── path confinement ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_environment_set_outside_workspace_refused(tmp_path):
    from harness.code.workspace import ResolvedWorkspace
    from harness.execution.application.runtime import set_application_runtime
    from harness.execution.application.tools import environment_set
    from harness.tools import ToolContext

    manager = _manager(tmp_path)
    set_application_runtime(manager)
    binding = __import__("harness.code.policy", fromlist=["WorkspaceBinding"]).WorkspaceBinding(
        id="ws", root=tmp_path, base_revision="HEAD", strategy="direct",
    )
    resolved = ResolvedWorkspace(id="ws", root=tmp_path, base_revision="HEAD", strategy="direct", binding=binding)
    ctx = ToolContext(run_id="r", log=lambda *_: None, workspace=resolved, autonomy="approve_external", direct=True)
    text, data = await environment_set({"file": "../escape.env", "name": "X", "value": "1"}, ctx)
    assert data.get("status") == "refused"


# ── destructive authorization ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_environment_set_requires_operator(tmp_path):
    from harness.code.workspace import ResolvedWorkspace
    from harness.execution.application.runtime import set_application_runtime
    from harness.execution.application.tools import environment_set
    from harness.tools import ToolContext

    manager = _manager(tmp_path)
    set_application_runtime(manager)
    binding = __import__("harness.code.policy", fromlist=["WorkspaceBinding"]).WorkspaceBinding(
        id="ws", root=tmp_path, base_revision="HEAD", strategy="direct",
    )
    resolved = ResolvedWorkspace(id="ws", root=tmp_path, base_revision="HEAD", strategy="direct", binding=binding)
    # Not an operator: the write must be refused.
    ctx = ToolContext(run_id="r", log=lambda *_: None, workspace=resolved, autonomy="edit_verify")
    text, data = await environment_set({"name": "X", "value": "1"}, ctx)
    assert data.get("status") == "refused"
    assert data.get("code") == "OPERATOR_REQUIRED"


def test_policy_asks_for_destructive():
    policy = RuntimePolicy(level="ask")
    for op in ("compose.down", "container.remove", "container.volume.remove"):
        assert policy.decide(op)[0] is False
        assert policy.decide(op, authorized=True)[0] is True


# ── graceful failures ─────────────────────────────────────────────────────────────


def test_missing_package_manager_fails_structurally(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"x","scripts":{"dev":"node x.js"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    # No node_modules → an install is needed → pnpm is required.
    manager = _manager(tmp_path)
    handle = manager.start(tmp_path, install=True)
    # Either pnpm IS installed (then it proceeds) or the failure is the honest
    # PACKAGE_MANAGER_UNAVAILABLE / RUNTIME_MISSING diagnosis — never a silent npm.
    if handle.state.value == "FAILED":
        assert handle.last_error is not None
        assert handle.last_error["category"] in ("runtime_missing", "dependency_failure")


def test_invalid_compose_file_is_diagnosed():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(
        output="yaml: line 3: mapping values are not allowed in this context",
        step="compose", reason="compose validation failed",
    )
    assert diag.category is not DiagnosticCategory.PORT_CONFLICT
    assert diag.message


def test_docker_unavailable_is_honest(monkeypatch):
    # With no docker on PATH, the adapter must report unavailable and every op a
    # structured ENGINE_UNAVAILABLE.
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    adapter = DockerAdapter()
    assert adapter.available() is False
    result = adapter.ps()
    assert result.ok is False
    assert result.code == "ENGINE_UNAVAILABLE"


def test_process_crash_diagnosis_has_location():
    engine = RuntimeDiagnosticsEngine()
    diag = engine.classify(
        output="node:internal/modules/cjs/loader:1234\nError: Cannot find module 'express'\n    at Module._resolveFilename (src/app.js:5:9)",
        exit_code=1, step="run", language="javascript",
    )
    assert diag.category in (DiagnosticCategory.DEPENDENCY_FAILURE, DiagnosticCategory.PROCESS_CRASH, DiagnosticCategory.BUILD_FAILURE)
    assert diag.recoverable


def test_diagnosis_from_exception_never_crashes():
    engine = RuntimeDiagnosticsEngine()
    for exc in (FileNotFoundError("no such file"), TimeoutError("timed out"), PermissionError("denied"), ValueError("x")):
        diag = engine.from_exception(exc, step="start")
        assert diag.message


def test_unknown_language_directory_is_handled(tmp_path):
    # A directory with no manifests must not raise.
    manager = _manager(tmp_path)
    data = manager.inspect(tmp_path)
    assert data["descriptor"]["language"] == ""
