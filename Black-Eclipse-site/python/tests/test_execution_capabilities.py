"""Execution layer — capabilities added after the first cut:
resource telemetry, extra language runtimes, SQL multi-driver, model autofix.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from harness.code.policy import WorkspaceBinding
from harness.execution import (
    ExecutionMode,
    ExecutionOrchestrator,
    ExecutionRequest,
    build_runtime_registry,
)
from harness.execution import telemetry
from harness.skills.permissions import Actor


def _binding(root: Path):
    return WorkspaceBinding(id="ws_x", root=root, base_revision="HEAD", strategy="direct")


def _actor():
    return Actor(id="local", operator=False, workspace_id="ws_x", autonomy="edit_verify")


# ── resource telemetry ──────────────────────────────────────────────────────────


def test_telemetry_samples_this_process():
    if not telemetry.available():
        pytest.skip("resource sampling not available on this platform")
    sample = telemetry.sample_pid(os.getpid())
    assert sample is not None
    if sys.platform != "darwin":  # /proc present on Linux; Windows via ctypes
        assert sample.cpu_ms is not None and sample.cpu_ms >= 0
        assert sample.memory_mb is not None and sample.memory_mb > 0


def test_telemetry_missing_pid_is_none():
    assert telemetry.sample_pid(0) is None
    assert telemetry.sample_pid(-1) is None
    # A pid that certainly does not exist reads as unmeasurable, never zero.
    assert telemetry.sample_pid(999_999_999) is None


def test_run_reports_real_resource_usage(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "scratch").mkdir()
    registry = build_runtime_registry()
    if not registry.get("python").available() or not telemetry.available():
        pytest.skip("python or telemetry not available")
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    code = "total = 0\nfor i in range(1_500_000):\n    total += i\nprint(total)\n"
    result = orchestrator.run(
        ExecutionRequest(language="python", workspace=_binding(root), code=code, mode=ExecutionMode.RUN),
        actor=_actor(),
    )
    assert result.status == "COMPLETED"
    # Real CPU time was measured (a compute loop uses measurable CPU).
    usage = result.resource_usage
    if sys.platform != "darwin":
        assert usage.cpu_ms is not None and usage.cpu_ms >= 0
        assert usage.memory_peak_mb is not None and usage.memory_peak_mb > 0


def test_metrics_persist_to_the_store(tmp_path, monkeypatch):
    from harness.persistence import AgentMemoryStore
    from harness.execution.service import ExecutionService

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = ExecutionService(store=store, terminal=None)
    root = tmp_path / "proj"
    root.mkdir()
    if not service.registry.get("python").available() or not telemetry.available():
        store.close()
        pytest.skip("python or telemetry not available")
    result = service.run(
        ExecutionRequest(
            language="python", workspace=_binding(root),
            code="print(sum(range(500000)))", mode=ExecutionMode.RUN, run_id="run-metrics",
        ),
        actor=_actor(), run_id="run-metrics",
    )
    row = service.store.get_execution(result.execution_id)
    names = {m["name"] for m in row["metrics"]}
    if sys.platform != "darwin":
        assert "cpuMs" in names
        assert "memoryPeakMb" in names
    store.close()


# ── extra language runtimes ──────────────────────────────────────────────────────


def test_all_declared_languages_have_a_registered_adapter():
    registry = build_runtime_registry()
    for language in ("python", "javascript", "typescript", "sql", "shell",
                     "rust", "go", "java", "csharp", "c", "cpp", "php", "ruby"):
        assert registry.get(language) is not None, language


def test_missing_toolchain_runtimes_report_unavailable_honestly():
    registry = build_runtime_registry()
    # On this dev machine no Go/Rust/Java/etc toolchain is installed. The adapter
    # must exist and report UNAVAILABLE — never run the source through something else.
    for language in ("go", "rust", "java", "csharp", "php", "ruby"):
        adapter = registry.get(language)
        assert adapter is not None
        assert adapter.available() is False


def test_go_inline_refused_honestly_when_go_absent(tmp_path):
    registry = build_runtime_registry()
    adapter = registry.get("go")
    if adapter.available():
        pytest.skip("Go is installed on this machine")
    with pytest.raises(Exception) as excinfo:
        adapter.prepare_run(
            ExecutionRequest(language="go", workspace=_binding(tmp_path), code="package main\nfunc main(){}"),
            tmp_path, tmp_path,
        )
    assert "Go" in str(excinfo.value)


def test_rust_inline_is_refused_with_a_plan(tmp_path):
    registry = build_runtime_registry()
    adapter = registry.get("rust")
    # Rust has no single-file run mode: inline must be refused even if cargo exists.
    request = ExecutionRequest(language="rust", workspace=_binding(tmp_path), code="fn main() {}")
    with pytest.raises(Exception):
        adapter.prepare_run(request, tmp_path, tmp_path)


# ── SQL multi-driver ──────────────────────────────────────────────────────────────


def test_postgres_without_a_driver_refuses_honestly(tmp_path):
    registry = build_runtime_registry()
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    (tmp_path / "scratch").mkdir()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    root = tmp_path / "proj"
    root.mkdir()
    result = orchestrator.run(
        ExecutionRequest(
            language="sql", workspace=_binding(root), code="SELECT 1",
            mode=ExecutionMode.RUN,
            metadata={"dialect": "postgres", "database": "host=127.0.0.1 port=1 dbname=x"},
        ),
        actor=_actor(),
    )
    # No PostgreSQL driver is installed in CI: the runner refuses with a stable code
    # rather than pretending to connect.
    assert "SQL_DRIVER_MISSING" in result.stdout or "SQL_CONNECT_FAILED" in result.stdout


def test_sqlite_database_confined_to_workspace(tmp_path):
    registry = build_runtime_registry()
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    (tmp_path / "scratch").mkdir()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.db"
    outside.write_text("x", encoding="utf-8")
    result = orchestrator.run(
        ExecutionRequest(
            language="sql", workspace=_binding(root), code="SELECT 1",
            mode=ExecutionMode.RUN,
            metadata={"dialect": "sqlite", "database": str(outside)},
        ),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED" or "OUTSIDE_WORKSPACE" in (result.error or {}).get("code", "")


# ── model autofix (gating + JSON parse + confined apply) ─────────────────────────


def test_autofix_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_EXEC_AUTOFIX", raising=False)
    from harness.execution.autofix import autofix_enabled

    assert autofix_enabled() is False


def test_autofix_parses_and_applies_a_confined_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_EXEC_AUTOFIX", "1")
    root = tmp_path / "proj"
    root.mkdir()
    source = root / "calc.py"
    source.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    binding = _binding(root)
    actor = _actor()

    import harness.execution.autofix as autofix

    async def _fake_model(ctx, prompt):
        return '{"file": "calc.py", "old": "return a - b", "new": "return a + b"}'

    monkeypatch.setattr(autofix, "_ask_model", _fake_model)
    fix = autofix.make_model_fix(
        _ctx_with_model(), root, binding, actor,
    )

    class _Result:
        diagnostics = [type("D", (), {"file": "calc.py", "line": 2, "message": "assert failed", "category": "test", "severity": "error"})()]

    summary = asyncio.new_event_loop().run_until_complete(fix(_Result(), 1))
    assert summary is not None and "calc.py" in summary
    assert "a + b" in source.read_text(encoding="utf-8")


def test_autofix_refuses_a_path_outside_the_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_EXEC_AUTOFIX", "1")
    root = tmp_path / "proj"
    root.mkdir()
    binding = _binding(root)
    actor = _actor()

    import harness.execution.autofix as autofix

    async def _fake_model(ctx, prompt):
        return '{"file": "../escape.py", "content": "evil"}'

    monkeypatch.setattr(autofix, "_ask_model", _fake_model)
    # A diagnostic naming a file outside the workspace is not actionable (read is denied).
    fix = autofix.make_model_fix(_ctx_with_model(), root, binding, actor)

    class _Result:
        diagnostics = [type("D", (), {"file": "../escape.py", "line": 1, "message": "x", "category": "runtime", "severity": "error"})()]

    summary = asyncio.new_event_loop().run_until_complete(fix(_Result(), 1))
    assert summary is None
    assert not (tmp_path / "escape.py").exists()


# ── regression: the three bugs found in the code-execution verification pass ─────


def test_typescript_runner_never_drops_the_program(tmp_path):
    """Regression: `['npx', '<file>']` (missing `tsx`) failed with WinError 2.

    The runner prefix must always END in an invocable program and the file must
    come AFTER it, never in the program slot.
    """
    from harness.execution import build_runtime_registry

    adapter = build_runtime_registry().get("typescript")
    if not adapter.available():
        pytest.skip("node not available")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.ts").write_text('console.log("x")', encoding="utf-8")

    class _Req:
        code = ""
        entrypoint = "main.ts"
        args = []
        metadata = {}

    prepared = adapter.prepare_run(_Req(), root, tmp_path / "work")
    argv = prepared.argv
    # The program (npx/tsx/ts-node/local bin) is first; the `.ts` file is an argument.
    assert argv[0] not in ("", "npx") or (len(argv) > 1 and argv[1] in ("tsx", "ts-node"))
    assert any(tok.endswith("main.ts") for tok in argv)
    assert not argv[0].endswith("main.ts")
    # An `npx` runner always names the package it runs.
    if argv[0] in ("npx", "npx.cmd"):
        assert argv[1] in ("tsx", "ts-node")


def test_sql_multi_statement_script_commits_and_returns_rows(tmp_path):
    """Regression: a 4-statement script must run and its writes must PERSIST.

    The old runner rejected multi-statement scripts and never committed DML, so a
    follow-up SELECT returned zero rows.
    """
    registry = build_runtime_registry()
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    (tmp_path / "scratch").mkdir()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    root = tmp_path / "proj"
    root.mkdir()
    binding = WorkspaceBinding(id="ws_x", root=root, base_revision="HEAD", strategy="direct")

    script = (
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
        "INSERT INTO users (name) VALUES ('Alice');"
        "INSERT INTO users (name) VALUES ('Bob');"
        "SELECT * FROM users;"
    )
    # A `.sqlite` name must be accepted (regression: `*.sqlite` was IGNORED_PATH).
    first = orchestrator.run(
        ExecutionRequest(language="sql", workspace=binding, code=script, mode=ExecutionMode.RUN,
                         metadata={"database": "verify.sqlite", "dialect": "sqlite", "read_only": False, "row_limit": 100}),
        actor=_actor(),
    )
    assert first.status == "COMPLETED", first.to_dict()
    assert "Alice" in first.stdout and "Bob" in first.stdout

    # A SEPARATE execution must see the committed rows.
    second = orchestrator.run(
        ExecutionRequest(language="sql", workspace=binding, code="SELECT * FROM users", mode=ExecutionMode.RUN,
                         metadata={"database": "verify.sqlite", "dialect": "sqlite", "read_only": True, "row_limit": 100}),
        actor=_actor(),
    )
    assert second.status == "COMPLETED"
    assert "Alice" in second.stdout and "Bob" in second.stdout


def test_sql_read_only_still_blocks_destructive_statements(tmp_path):
    registry = build_runtime_registry()
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    (tmp_path / "scratch").mkdir()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    root = tmp_path / "proj"
    root.mkdir()
    binding = WorkspaceBinding(id="ws_x", root=root, base_revision="HEAD", strategy="direct")
    result = orchestrator.run(
        ExecutionRequest(language="sql", workspace=binding, code="DROP TABLE users", mode=ExecutionMode.RUN,
                         metadata={"database": "v.sqlite", "dialect": "sqlite", "read_only": True}),
        actor=_actor(),
    )
    assert "SQL_DESTRUCTIVE_BLOCKED" in result.stdout


def test_sql_database_outside_workspace_is_still_refused(tmp_path):
    """`allow_ignored` relaxes ONLY the ignore-globs — escapes remain refused."""
    registry = build_runtime_registry()
    if not registry.get("sql").available():
        pytest.skip("sql runtime not available")
    (tmp_path / "scratch").mkdir()
    orchestrator = ExecutionOrchestrator(registry, scratch_root=tmp_path / "scratch")
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.sqlite"
    outside.write_text("x", encoding="utf-8")
    binding = WorkspaceBinding(id="ws_x", root=root, base_revision="HEAD", strategy="direct")
    result = orchestrator.run(
        ExecutionRequest(language="sql", workspace=binding, code="SELECT 1", mode=ExecutionMode.RUN,
                         metadata={"database": str(outside), "dialect": "sqlite", "read_only": True}),
        actor=_actor(),
    )
    assert result.status == "SECURITY_BLOCKED" or "OUTSIDE_WORKSPACE" in (result.error or {}).get("code", "")


def test_policy_resolve_within_allow_ignored_keeps_other_guards(tmp_path):
    from harness.code.policy import PolicyDenial, resolve_within

    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.db").write_text("x", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    # Ignored by default, allowed when explicitly opted in...
    with pytest.raises(PolicyDenial):
        resolve_within(root, "app.db")
    assert resolve_within(root, "app.db", allow_ignored=True).name == "app.db"
    # ...but PROTECTED and traversal are unchanged.
    with pytest.raises(PolicyDenial) as protected:
        resolve_within(root, ".env", allow_ignored=True)
    assert protected.value.code == "PROTECTED_PATH"
    with pytest.raises(PolicyDenial) as traversal:
        resolve_within(root, "../escape.db", allow_ignored=True)
    assert traversal.value.code in ("PATH_TRAVERSAL", "PATH_OUTSIDE_WORKSPACE")


# ── regression: bare program names, BOM manifests, ANSI summaries ───────────────


def test_json_adapters_resolve_absolute_executables(tmp_path, monkeypatch):
    """Regression: bare `npm`/`npx`/`tsc` cannot be spawned on Windows.

    Every build/test argv the JS/TS adapters produce must begin with an absolute
    path (the resolved `.CMD` shim), never a bare program name.
    """
    from harness.execution import build_runtime_registry

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text('{"scripts":{"build":"tsc --noEmit","test":"vitest run"}}', encoding="utf-8")
    ts = build_runtime_registry().get("typescript")

    build = ts.build(root, None, tmp_path / "w")
    assert build is not None
    assert build.argv[0] not in ("npm", "npx", "tsc"), build.argv
    import os
    assert os.path.isabs(build.argv[0]) or "/" in build.argv[0] or "\\" in build.argv[0], build.argv

    test = ts.test(root, None, {}, tmp_path / "w")
    assert test is not None
    assert test.argv[0] not in ("npm", "npx"), test.argv


def test_manifest_read_tolerates_utf8_bom(tmp_path):
    """Regression: a BOM'd `package.json` (Windows editors) failed to parse, so the
    test framework and scripts were missed and the engine fell back to `node --test`."""
    from harness.execution.projects import ProjectDetector, read_json

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_bytes(
        b"\xef\xbb\xbf" + b'{"scripts":{"test":"vitest run"},"devDependencies":{"vitest":"^4","typescript":"^5"}}'
    )
    assert read_json(root / "package.json").get("scripts", {}).get("test") == "vitest run"
    info = ProjectDetector().detect(root)
    assert info.test_framework == "vitest"
    assert info.scripts.get("build") is None  # only the declared script is present


def test_test_summary_parses_through_ansi_codes():
    """Regression: vitest color codes wrapped the counts, so a PASSING run reported
    `parsed:false` / 0 tests."""
    from harness.execution.testing import _parse_summary

    colored_pass = "\x1b[2m Test Files \x1b[22m \x1b[1m\x1b[32m1 passed\x1b[39m\x1b[22m (1)\n\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m2 passed\x1b[39m\x1b[22m (2)\n"
    passed, failed, skipped, parsed = _parse_summary(colored_pass, "vitest")
    assert parsed is True and passed == 2 and failed == 0

    colored_fail = "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[31m1 failed\x1b[39m\x1b[22m\x1b[2m | \x1b[22m\x1b[1m\x1b[32m1 passed\x1b[39m\x1b[22m (2)"
    passed, failed, skipped, parsed = _parse_summary(colored_fail, "vitest")
    assert parsed is True and passed == 1 and failed == 1


def test_ansi_colored_stack_is_still_parsed():
    """Regression: colored output broke the diagnostic parsers."""
    from harness.execution.diagnostics import normalize

    colored = "\x1b[31msrc/user.ts:91:14 - error TS2339: Property 'x' does not exist\x1b[39m"
    diags = normalize(colored, language="typescript")
    assert diags and diags[0].file == "src/user.ts" and diags[0].line == 91


def _ctx_with_model():
    from harness.tools import ToolContext

    class _Settings:
        provider = "ollama"
        model = "test"

    return ToolContext(run_id="r", log=lambda *_: None, model_settings=_Settings())
