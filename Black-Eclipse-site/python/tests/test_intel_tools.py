"""End-to-end tests for the CIUE agent tools (through the ONE registry).

These exercise the tools exactly as the model calls them: register into the SAME
`ToolRegistry`, run with a real workspace + a real code-index, and assert the
structured `data` payload. They also prove the resilience contract: a language
server that is missing or fails is a fallback, never a crash.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from harness.code.intel.lsp.manager import LSPManager
from harness.code.intel.runtime import CodeIntelRuntime, set_code_intel_runtime
from harness.code.policy import WorkspaceBinding
from harness.code.tools import make_code_authorizer, register_code_tools
from harness.code.workspace import ResolvedWorkspace
from harness.tools import ToolContext, ToolRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "intel"


def _workspace(root: Path) -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id="ws_tools", root=real, base_revision="abc1234", strategy="checkout")
    return ResolvedWorkspace(
        id="ws_tools", root=real, base_revision="abc1234", strategy="checkout", binding=binding,
    )


@pytest.fixture
def runtime(tmp_path):
    rt = CodeIntelRuntime()
    rt.set_enabled(False)  # no background watcher thread in tests; manager still works
    set_code_intel_runtime(rt)
    try:
        yield rt
    finally:
        rt.stop()
        set_code_intel_runtime(None)


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_code_tools(registry)
    return registry


def _ctx(ws: ResolvedWorkspace, runtime: CodeIntelRuntime) -> ToolContext:
    return ToolContext(
        run_id="run_intel", log=lambda *_: None, workspace=ws,
        autonomy="edit_verify", code_intel_runtime=runtime,
        authorize_effect=make_code_authorizer(),
    )


def _run(coro):
    return asyncio.run(coro)


async def _call(registry, name, args, ctx):
    return await registry.execute(name, f"call_{name}", args, ctx, allowed=None)


def _setup(tmp_path, name: str, runtime):
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    ws = _workspace(root)
    registry = _registry()
    ctx = _ctx(ws, runtime)
    # Index first so the tools answer from the index (no language server).
    _run(_call(registry, "code_index_workspace", {"force": True}, ctx))
    return ws, registry, ctx


# ── tool registration ─────────────────────────────────────────────────────────


def test_ciue_tools_are_registered():
    registry = _registry()
    names = set(registry.names())
    for tool in (
        "code_get_definition", "code_find_references", "code_find_symbol",
        "code_search_symbols", "code_get_diagnostics", "code_get_call_hierarchy",
        "code_get_project_structure", "code_get_relevant_context",
        "code_rename_symbol", "code_intel_status",
    ):
        assert tool in names
    assert registry.get("code_rename_symbol").permission == "write"
    assert registry.get("code_get_definition").permission == "read"


# ── happy path (index fallback) ────────────────────────────────────────────────


def test_definition_tool_returns_a_location(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_definition", {"name": "UserService"}, ctx))
    assert result.ok
    assert result.data["count"] >= 1
    assert result.data["definitions"][0]["location"]["file"].endswith("user.ts")


def test_references_tool_marks_definition(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_find_references", {"name": "UserService"}, ctx))
    assert result.ok
    assert result.data["count"] >= 1
    assert any(r["definition"] for r in result.data["references"])


def test_find_symbol_tool(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_find_symbol", {"name": "formatUser"}, ctx))
    assert result.ok
    assert result.data["symbols"][0]["name"] == "formatUser"


def test_project_structure_tool(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_project_structure", {}, ctx))
    assert result.ok
    assert "typescript" in result.data["project"]["languages"]


def test_analyze_file_tool(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_analyze_file", {"path": "src/services/user.ts"}, ctx))
    assert result.ok
    assert result.data["language"] == "typescript"
    assert any(s["name"] == "UserService" for s in result.data["symbols"])


def test_diagnostics_tool_reports_syntax_error(tmp_path, runtime):
    ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    (ws.root / "src" / "broken.py").write_text("def bad(\n    pass\n", encoding="utf-8")
    result = _run(_call(registry, "code_get_diagnostics", {"file": "src/broken.py"}, ctx))
    assert result.ok
    assert result.data["summary"]["error"] >= 1


def test_relevant_context_tool(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_relevant_context", {"query": "fix UserService"}, ctx))
    assert result.ok
    assert result.data["fileCount"] >= 1


def test_intel_status_tool(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_intel_status", {}, ctx))
    assert result.ok
    assert result.data["workspace"]["fileCount"] >= 1


def test_read_tool_does_not_force_a_synchronous_index(tmp_path, runtime, monkeypatch):
    """A read query must never trigger a blocking full index.

    With the runtime ENABLED, its per-workspace background indexer owns freshness.
    A read path that called `manager._ensure_fresh()` ran a whole-workspace index
    on the event loop, which cannot be cancelled by the tool timeout and froze
    /health. Make a forced refresh raise, so any regression is caught here.
    """
    from harness.code.intel.manager import CodeIntelligenceManager

    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    runtime.set_enabled(True)  # background indexer owns freshness (production)

    def _boom(*_args, **_kwargs):
        raise AssertionError("the read path forced a synchronous full index")

    monkeypatch.setattr(CodeIntelligenceManager, "_ensure_fresh", _boom)
    result = _run(_call(registry, "code_get_definition", {"name": "UserService"}, ctx))
    assert result.ok
    assert result.data["count"] >= 1


# ── semantic rename (preview + apply into a worktree) ────────────────────────────


def test_rename_tool_previews_by_default(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_rename_symbol", {"name": "formatUser", "newName": "renderUser"}, ctx))
    assert result.ok
    assert result.data["applied"] is False
    assert result.data["preview"]["fileCount"] >= 1


def test_rename_tool_refuses_without_write_grant(tmp_path, runtime):
    ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    ctx.autonomy = "plan_only"
    result = _run(_call(
        registry, "code_rename_symbol",
        {"name": "formatUser", "newName": "renderUser", "dryRun": False}, ctx,
    ))
    assert result.ok
    assert result.data["status"] == "refused"


# ── resilience: no workspace / unknown symbol ─────────────────────────────────


def test_all_tools_refuse_without_a_workspace(runtime):
    registry = _registry()
    ctx = ToolContext(run_id="r", log=lambda *_: None, workspace=None, code_intel_runtime=runtime)
    for name, args in (
        ("code_get_definition", {"name": "X"}),
        ("code_find_symbol", {"name": "X"}),
        ("code_get_diagnostics", {}),
        ("code_get_project_structure", {}),
    ):
        result = _run(_call(registry, name, args, ctx))
        assert result.ok
        assert result.data["code"] == "WORKSPACE_UNAVAILABLE"


def test_unknown_symbol_is_an_honest_refusal(tmp_path, runtime):
    _ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_definition", {"name": "NoSuchSymbolAnywhere"}, ctx))
    assert result.ok
    assert result.data["status"] == "refused"
    assert result.data["code"] == "NOT_FOUND"


# ── resilience: a missing language server never crashes a call ──────────────────


def test_missing_language_server_falls_back_to_index(tmp_path, runtime, monkeypatch):
    # Force every provider to be "not installed" so the LSP path is genuinely absent.
    from harness.code.intel.lsp import manager as manager_mod

    monkeypatch.setattr(manager_mod, "resolve_launch_argv", lambda spec, root: None)
    ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_definition", {"name": "UserService"}, ctx))
    assert result.ok
    assert result.data["count"] >= 1
    assert result.data["engine"] == "index"


def test_failed_language_server_is_reported_not_fatal(tmp_path, runtime, monkeypatch):
    """A provider whose client raises on start is a diagnostic, never a crash."""
    from harness.code.intel.lsp import manager as manager_mod
    from harness.code.intel.lsp.client import LSPClient

    def _explode(self, *args, **kwargs):
        raise RuntimeError("simulated language server crash")

    monkeypatch.setattr(LSPClient, "start", _explode)
    # Make a server appear installed so the manager actually attempts to start it.
    monkeypatch.setattr(manager_mod, "resolve_launch_argv", lambda spec, root: ["definitely-not-real"])

    ws, registry, ctx = _setup(tmp_path, "typescript-project", runtime)
    result = _run(_call(registry, "code_get_definition", {"name": "UserService"}, ctx))
    assert result.ok  # the tool never crashes
    assert result.data["count"] >= 1  # the structural fallback answered
    statuses = runtime.lsp.statuses()
    assert any(s["state"] == "failed" for s in statuses)


def test_lsp_manager_reports_missing_without_crashing(tmp_path):
    manager = LSPManager()
    client, reason = manager.ensure_client(tmp_path, "typescript")
    # Either a real server happened to be installed, or the reason is honest.
    if client is None:
        assert reason in ("LANGUAGE_SERVER_MISSING", "LANGUAGE_SERVER_FAILED")
    manager.stop_all()
