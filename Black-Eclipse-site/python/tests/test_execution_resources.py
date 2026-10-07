"""Execution layer — resource-limit enforcement + toolchain resolution.

These cover the fixes found by the toolchain/DB/resource verification rounds:
absolute executables, toolchain cache env, BOM manifests, ANSI parsing, and
parent-side OS resource-limit enforcement (memory / processes / CPU).
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from harness.code.policy import WorkspaceBinding
from harness.execution import (
    ExecutionMode,
    ExecutionOrchestrator,
    ExecutionRequest,
    ResourceLimits,
    build_runtime_registry,
)
from harness.skills.permissions import Actor


def _binding(root: Path):
    return WorkspaceBinding(id="ws_r", root=root, base_revision="HEAD", strategy="direct")


def _actor():
    return Actor(id="r", operator=False, workspace_id="ws_r", autonomy="edit_verify")


def _orch(tmp_path):
    (tmp_path / "scratch").mkdir(exist_ok=True)
    return ExecutionOrchestrator(build_runtime_registry(), scratch_root=tmp_path / "scratch")


def _run(orch, root, code, limits=None):
    return orch.run(
        ExecutionRequest(language="python", workspace=_binding(root), code=code,
                         mode=ExecutionMode.RUN, resource_limits=limits),
        actor=_actor(),
    )


# ── resource limits ─────────────────────────────────────────────────────────────


def test_cpu_seconds_defaults_to_unset_not_one(monkeypatch):
    """Regression: `_int` clamped a 0 default to 1, imposing a 1s CPU ceiling on
    every execution and mis-flagging ordinary runs as RESOURCE_LIMIT."""
    monkeypatch.delenv("HARNESS_EXEC_CPU_SECONDS", raising=False)
    limits = ResourceLimits.from_env()
    assert limits.cpu_seconds == 0
    from harness.execution.models import resource_run_kwargs

    # A 0 cpu_seconds derives a generous ceiling from the wall-clock timeout.
    assert resource_run_kwargs(limits)["cpu_seconds"] >= 5


def test_memory_limit_is_enforced(tmp_path):
    orch = _orch(tmp_path)
    if not build_runtime_registry().get("python").available():
        pytest.skip("python runtime not available")
    root = tmp_path / "proj"
    root.mkdir()
    code = ("import time\nb=[]\n"
            "for _ in range(8):\n    b.append(bytearray(64*1024*1024))\n"
            "time.sleep(5)\n")
    limits = replace(ResourceLimits.from_env(), memory_limit_mb=128, timeout_ms=30_000)
    result = _run(orch, root, code, limits)
    assert result.status == "RESOURCE_LIMIT"
    assert result.error_class == "RESOURCE_LIMIT"
    assert (result.error or {}).get("limit") in ("memory", "cpu", "processes")


def test_process_limit_is_enforced(tmp_path):
    orch = _orch(tmp_path)
    if not build_runtime_registry().get("python").available():
        pytest.skip("python runtime not available")
    root = tmp_path / "proj"
    root.mkdir()
    code = ("import subprocess, sys, time\nkids=[]\n"
            "for _ in range(30):\n"
            "    kids.append(subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)']))\n"
            "time.sleep(5)\n")
    limits = replace(ResourceLimits.from_env(), process_limit=5, timeout_ms=30_000)
    result = _run(orch, root, code, limits)
    assert result.status == "RESOURCE_LIMIT"


def test_cpu_limit_is_enforced(tmp_path):
    orch = _orch(tmp_path)
    if not build_runtime_registry().get("python").available():
        pytest.skip("python runtime not available")
    root = tmp_path / "proj"
    root.mkdir()
    code = "x=0\nfor i in range(200_000_000):\n    x=(x+i*i)%1000003\nprint(x)\n"
    limits = replace(ResourceLimits.from_env(), cpu_seconds=1, timeout_ms=30_000)
    result = _run(orch, root, code, limits)
    assert result.status == "RESOURCE_LIMIT"
    assert (result.error or {}).get("limit") == "cpu"


def test_ordinary_failure_is_not_a_resource_limit(tmp_path):
    """A normal crash must never be misclassified as a limit breach."""
    orch = _orch(tmp_path)
    if not build_runtime_registry().get("python").available():
        pytest.skip("python runtime not available")
    root = tmp_path / "proj"
    root.mkdir()
    result = _run(orch, root, "raise ValueError('boom')\n")
    assert result.status == "FAILED"
    assert result.error_class == "USER_CODE_ERROR"


def test_limit_signatures_do_not_match_incidental_text():
    from harness.code.sandbox import RunSpec, _signature_limit

    spec = RunSpec(argv=["x"], cwd=Path("."), env={}, timeout_s=1,
                   output_cap_bytes=100, network=False, memory_mb=128, cpu_seconds=1)
    # A temp path or line number containing "137" must NOT be a cpu breach.
    assert _signature_limit("File C:/tmp/pytest-137/x.py line 5", spec) is None
    assert _signature_limit("MemoryError", spec) == "memory"


# ── toolchain resolution ─────────────────────────────────────────────────────────


def test_manifest_read_tolerates_utf8_bom(tmp_path):
    from harness.execution.projects import ProjectDetector, read_json

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_bytes(
        b"\xef\xbb\xbf" + b'{"scripts":{"test":"vitest run"},"devDependencies":{"vitest":"^4"}}'
    )
    assert read_json(root / "package.json").get("scripts", {}).get("test") == "vitest run"
    assert ProjectDetector().detect(root).test_framework == "vitest"


def test_all_language_adapters_are_registered():
    registry = build_runtime_registry()
    for language in ("python", "javascript", "typescript", "sql", "shell",
                     "go", "rust", "java", "csharp", "c", "cpp", "php", "ruby"):
        assert registry.get(language) is not None, language


def test_csharp_env_provides_cli_cache_and_platform_vars(tmp_path):
    from harness.execution.runtimes.extra import CSharpRuntime

    env = CSharpRuntime()._env(tmp_path)
    assert env["DOTNET_CLI_HOME"]
    assert env["NUGET_PACKAGES"]
    assert env["DOTNET_CLI_TELEMETRY_OPTOUT"] == "1"
    if os.name == "nt":
        # The curated non-secret platform vars must be forwarded for NuGet/MSBuild.
        assert "APPDATA" in env and "USERPROFILE" in env and "PROGRAMFILES" in env


def test_go_env_defines_a_real_cache_and_tmpdir(tmp_path):
    from harness.execution.runtimes.extra import GoRuntime

    env = GoRuntime()._env(tmp_path)
    assert env["GOCACHE"] and env["GOTMPDIR"] and env["GOMODCACHE"]
    assert Path(env["GOTMPDIR"]).is_dir()


def test_rust_env_forwards_toolchain_home_when_present(monkeypatch, tmp_path):
    """Regression: rustup's `cargo` proxy fails without RUSTUP_HOME/CARGO_HOME,
    which the sandbox scrubs."""
    from harness.execution.runtimes.extra import RustRuntime

    monkeypatch.setenv("CARGO_HOME", str(tmp_path / "cargo"))
    monkeypatch.setenv("RUSTUP_HOME", str(tmp_path / "rustup"))
    env = RustRuntime()._env(tmp_path)
    assert env["CARGO_HOME"] == str(tmp_path / "cargo")
    assert env["RUSTUP_HOME"] == str(tmp_path / "rustup")
    # A target cache is always set so cargo never writes into the repo.
    assert env["CARGO_TARGET_DIR"]


def test_c_compiler_build_compiles_primary_source(tmp_path):
    from harness.execution.runtimes.extra import CRuntime

    runtime = CRuntime()
    compiler = runtime.resolve(None)
    if not compiler:
        pytest.skip("no C compiler installed")
    root = tmp_path / "c"
    root.mkdir()
    (root / "main.c").write_text('#include <stdio.h>\nint main(void){ return 0; }\n', encoding="utf-8")
    prepared = runtime.build(root, None, tmp_path / "work")
    assert prepared is not None
    assert prepared.argv[0] == compiler
    assert any(tok.endswith("main.c") for tok in prepared.argv)


def test_typescript_build_uses_absolute_program(tmp_path):
    from harness.execution.runtimes.typescript import TypeScriptRuntime

    runtime = TypeScriptRuntime()
    if not runtime.available():
        pytest.skip("node not available")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text('{"scripts":{"build":"tsc --noEmit"}}', encoding="utf-8")
    prepared = runtime.build(root, None, tmp_path / "work")
    assert prepared is not None
    assert prepared.argv[0] not in ("npm", "npx", "tsc"), prepared.argv
