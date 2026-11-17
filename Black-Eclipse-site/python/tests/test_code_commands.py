"""Phase 3 — the command broker (commands.py + the command_run tool).

Every probe asserts BOTH the behaviour and the recorded row/event: a block that
leaves no record is a failure, not a pass.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from harness.code import commands, policy, sandbox
from harness.code.commands import CommandUnavailable, build_argv, resolve_class, validate_args
from harness.code.policy import WorkspaceBinding
from harness.code.tools import make_code_authorizer, register_code_tools
from harness.code.workspace import ResolvedWorkspace
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "code"
try:
    VENDORED = commands.executable_path(commands.COMMAND_CLASSES["python_test"])
except commands.CommandUnavailable:  # pragma: no cover - environment dependent
    # Same contract as test_code_sandbox.py: the vendored interpreter exists in a
    # packaged app and locally after `npm run setup:python`, not on a bare runner.
    pytest.skip(
        "the vendored python_test toolchain is not provisioned in this "
        "environment (run `npm run setup:python`)",
        allow_module_level=True,
    )


class _Recorder:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))
        return {"type": event_type, "data": data or {}}

    def emit_sync(self, event_type, data=None):
        self.events.append((event_type, data or {}))


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


def _git_root(tmp_path: Path) -> Path:
    """A real git checkout that IS the code root (so a worktree can allocate)."""
    import shutil
    import subprocess

    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / ".gitignore").write_text(".black-eclipse/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


@pytest.fixture()
def code_root(tmp_path, monkeypatch):
    repo = _git_root(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(repo))
    yield repo
    import shutil

    from harness.code import worktree

    shutil.rmtree(repo / worktree.SCRATCH_RELPATH, ignore_errors=True)


def _ws(root: Path) -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id="ws_c", root=real, base_revision="abc1234", strategy="checkout")
    return ResolvedWorkspace(id="ws_c", root=real, base_revision="abc1234", strategy="checkout", binding=binding)


def _registry():
    reg = ToolRegistry()
    register_code_tools(reg)
    return reg


def _call(store, root, *, autonomy="edit_verify", args, flags=None, ws=True):
    from harness.code.store import CodeWorkspaceStore

    code_store = CodeWorkspaceStore(store)
    recorder = _Recorder()
    ctx = ToolContext(
        run_id="run_cmd", log=lambda *_: None, emitter=recorder,
        workspace=_ws(root) if ws else None, autonomy=autonomy,
        code_store=code_store, command_flags=flags or {},
        authorize_effect=make_code_authorizer(),
    )
    result = asyncio.run(_registry().execute(
        "command_run", "c1", args, ctx, allowed={"command_run"},
    ))
    return result, code_store, recorder


def _rows(store):
    from harness.code.store import CodeWorkspaceStore

    return CodeWorkspaceStore(store).list_command_executions("run_cmd")


# ── the table ───────────────────────────────────────────────────────────────


def test_git_read_subcommand_is_closed():
    cls = commands.COMMAND_CLASSES["git_read"]
    spec = next(s for s in cls.args if s.name == "subcommand")
    for mutating in ("push", "reset", "clean", "checkout", "commit", "config", "remote", "stash"):
        assert mutating not in spec.allowed


def test_git_read_rejects_push():
    cls = commands.COMMAND_CLASSES["git_read"]
    with pytest.raises(CommandUnavailable):
        build_argv(cls, {"subcommand": "push"})


def test_only_dependency_install_has_network():
    for name, cls in commands.COMMAND_CLASSES.items():
        assert cls.network is (name == "dependency_install")


def test_closed_executable_set():
    assert set(commands.EXECUTABLES) == {"node", "npm", "npx", "python", "pytest", "git"}
    # The vendored interpreter is named once; python/pytest both point at it.
    assert commands.EXECUTABLES["python"] == commands.EXECUTABLES["pytest"]


def test_arg_traversal_rejected():
    cls = commands.COMMAND_CLASSES["python_test"]
    with pytest.raises(CommandUnavailable):
        build_argv(cls, {"paths": ["../../etc/passwd"]})


def test_dependency_install_off_by_default():
    with pytest.raises(CommandUnavailable) as exc:
        resolve_class("dependency_install")
    assert exc.value.code == "COMMAND_NOT_ENABLED"
    # With the operator flag it resolves.
    cls = resolve_class("dependency_install", operator_flags={"dependency_install": True})
    assert cls.network is True
    assert "--ignore-scripts" in cls.argv_template({"packages": ["left-pad"]}, "npm")


def test_unknown_class_rejected():
    with pytest.raises(CommandUnavailable) as exc:
        resolve_class("nope")
    assert exc.value.code == "COMMAND_NOT_ALLOWLISTED"


def test_network_default_denied():
    # No class except dependency_install has network=True, and that one is off by
    # default — so a network fetch cannot be requested through any reachable class.
    assert commands.COMMAND_CLASSES["dependency_install"].network is True
    for name, cls in commands.COMMAND_CLASSES.items():
        if name != "dependency_install":
            assert cls.network is False
    with pytest.raises(CommandUnavailable):
        resolve_class("dependency_install")


def test_write_outside_worktree_is_contained():
    # The class cwd is the worktree root and no argument may traverse above it, so
    # a path argument cannot point the command at the operator's checkout.
    for cls_name, arg_name in (("python_test", "paths"), ("unit_test", "files"),
                               ("format_check", "files")):
        cls = commands.COMMAND_CLASSES[cls_name]
        with pytest.raises(CommandUnavailable):
            build_argv(cls, {arg_name: ["../../outside/x.py"]})


# ── benign probe ────────────────────────────────────────────────────────────


def test_benign_python_test_exits_zero(store, code_root):
    # Run the fixture by absolute path via python_test's args (paths).
    result, code_store, recorder = _call(
        store, code_root, autonomy="edit_verify",
        args={"command_class": "python_test", "args": {"paths": ["benign_check.py"]}},
    )
    assert result.ok
    assert result.data["exitCode"] == 0
    rows = code_store.list_command_executions("run_cmd")
    assert len(rows) == 1
    assert rows[0]["commandClass"] == "python_test"
    assert rows[0]["exitCode"] == 0
    assert any(e[0] == "command.started" for e in recorder.events)
    assert any(e[0] == "command.completed" for e in recorder.events)


def test_failing_check_records_real_code(store, code_root):
    result, code_store, _ = _call(
        store, code_root,
        args={"command_class": "python_test", "args": {"paths": ["failing_check.py"]}},
    )
    # pytest exits 1 for a failing test; the row records the REAL code.
    assert result.data["exitCode"] != 0
    rows = code_store.list_command_executions("run_cmd")
    assert rows and rows[0]["exitCode"] == result.data["exitCode"]


# ── infinite loop: killed + recorded ────────────────────────────────────────


def test_infinite_loop_killed_and_recorded(store, code_root, monkeypatch):
    # Run the fixture as a SCRIPT (a test seam): patch the class argv template so
    # the infinite loop is the executed program, and shrink the timeout.
    import dataclasses

    cls = commands.COMMAND_CLASSES["python_test"]
    vendor = commands.executable_path(cls)
    patched = dataclasses.replace(
        cls, timeout_s=2,
        argv_template=lambda a, exe: [vendor, "infinite_check.py"],
    )
    monkeypatch.setitem(commands.COMMAND_CLASSES, "python_test", patched)
    result, code_store, recorder = _call(
        store, code_root,
        args={"command_class": "python_test", "args": {}},
    )
    assert result.data["timedOut"] is True
    assert any(e[0] == "command.killed" for e in recorder.events)
    rows = code_store.list_command_executions("run_cmd")
    assert rows and rows[0]["timedOut"] == 1


# ── flood: truncated + recorded ─────────────────────────────────────────────


def test_flood_truncated_and_recorded(store, code_root, monkeypatch):
    import dataclasses

    cls = commands.COMMAND_CLASSES["python_test"]
    vendor = commands.executable_path(cls)
    patched = dataclasses.replace(
        cls, output_cap_bytes=50_000,
        argv_template=lambda a, exe: [vendor, "flood_check.py"],
    )
    monkeypatch.setitem(commands.COMMAND_CLASSES, "python_test", patched)
    result, code_store, recorder = _call(
        store, code_root,
        args={"command_class": "python_test", "args": {}},
    )
    assert result.data["truncated"] is True
    assert result.data["totalChars"] > 50_000
    assert any(e[0] == "command.truncated" for e in recorder.events)
    rows = code_store.list_command_executions("run_cmd")
    assert rows and rows[0]["truncated"] == 1


# ── refusals: rm/curl/powershell/bash ───────────────────────────────────────


@pytest.mark.parametrize("bad", [
    {"command_class": "rm_rf", "args": {}},
    {"command_class": "curl", "args": {}},
    {"command_class": "powershell", "args": {}},
    {"command_class": "bash", "args": {}},
])
def test_unknown_command_classes_refused_and_recorded(store, code_root, bad):
    result, code_store, recorder = _call(store, code_root, args=bad)
    assert result.data["status"] == "refused"
    assert result.data["code"] == "COMMAND_NOT_ALLOWLISTED"
    assert any(e[0] == "command.refused" for e in recorder.events)
    rows = code_store.list_command_executions("run_cmd")
    assert rows and json.loads(rows[0]["policyDecision"])["code"] == "COMMAND_NOT_ALLOWLISTED"


def test_git_push_refused_and_recorded(store, code_root):
    result, code_store, recorder = _call(
        store, code_root, args={"command_class": "git_read", "args": {"subcommand": "push"}},
    )
    assert result.data["status"] == "refused"
    assert any(e[0] == "command.refused" for e in recorder.events)
    assert code_store.list_command_executions("run_cmd")


def test_dependency_install_refused_without_flag(store, code_root):
    result, code_store, recorder = _call(
        store, code_root,
        args={"command_class": "dependency_install", "args": {"packages": ["left-pad"]}},
    )
    assert result.data["code"] == "COMMAND_NOT_ENABLED"
    assert any(e[0] == "command.refused" for e in recorder.events)


# ── plan_only ───────────────────────────────────────────────────────────────


def test_plan_only_refused_and_recorded(store, code_root):
    result, code_store, recorder = _call(
        store, code_root, autonomy="plan_only",
        args={"command_class": "python_test", "args": {"paths": ["benign_check.py"]}},
    )
    assert result.data["code"] == "PROFILE_DENIED"
    assert any(e[0] == "command.refused" for e in recorder.events)
    rows = code_store.list_command_executions("run_cmd")
    assert rows and json.loads(rows[0]["policyDecision"])["code"] == "PROFILE_DENIED"


def test_unbound_workspace_refused(store, code_root):
    result, code_store, recorder = _call(
        store, code_root, ws=False,
        args={"command_class": "python_test", "args": {}},
    )
    assert result.data["code"] == "WORKSPACE_UNBOUND"
    assert any(e[0] == "command.refused" for e in recorder.events)


# ── SANDBOX_UNAVAILABLE refuses rather than executing ───────────────────────


def test_sandbox_unavailable_refuses_and_records(store, code_root, monkeypatch):
    from harness.code.sandbox import SandboxUnavailable

    def _boom():
        raise SandboxUnavailable("no primitive")

    monkeypatch.setattr(sandbox, "select_backend", _boom)
    result, code_store, recorder = _call(
        store, code_root,
        args={"command_class": "python_test", "args": {"paths": ["benign_check.py"]}},
    )
    assert result.data["code"] == "SANDBOX_UNAVAILABLE"
    assert any(e[0] == "command.refused" for e in recorder.events)
    rows = code_store.list_command_executions("run_cmd")
    assert rows and json.loads(rows[0]["policyDecision"])["code"] == "SANDBOX_UNAVAILABLE"


# ── policy authority is consulted ───────────────────────────────────────────


def test_decide_command_grants_git_read_under_edit_verify():
    from harness.skills.permissions import Actor

    actor = Actor(id="coder", operator=False, workspace_id="ws_c", autonomy="edit_verify")
    binding = WorkspaceBinding(id="ws_c", root=Path("/tmp"), base_revision="x", strategy="checkout")
    decision = policy.decide_command(actor, binding, "git_read", ["git", "status"])
    assert decision.allowed
