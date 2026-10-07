"""File System subsystem — verification (syntax / change / edit) and git awareness.

Verification is part of the editing lifecycle: every write carries a post-write
syntax + integrity verdict. Git awareness is additive and never required.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

import pytest

from harness.code.fs import verify as V

from fs_helpers import make_service, make_ws, tree


# ── syntax validation ────────────────────────────────────────────────────────


def test_python_syntax_valid_and_invalid():
    assert V.validate_syntax("def f():\n    return 1\n", path="x.py").valid is True
    bad = V.validate_syntax("def f(:\n    pass\n", path="x.py")
    assert bad.valid is False
    assert bad.line == 1 and bad.checker == "ast"


def test_json_and_toml_syntax():
    assert V.validate_syntax('{"a": 1}', path="x.json").valid is True
    assert V.validate_syntax('{"a": }', path="x.json").valid is False
    assert V.validate_syntax('a = 1\n', path="x.toml").valid is True
    assert V.validate_syntax('a = \n', path="x.toml").valid is False


def test_bracket_balance_for_js_ts():
    assert V.validate_syntax("function f() { return 1; }\n", path="x.ts").valid is True
    assert V.validate_syntax("function f() { return 1;\n", path="x.ts").valid is False
    # A bracket inside a string or a comment must not count.
    assert V.validate_syntax('const s = "}";\n', path="x.js").valid is True
    assert V.validate_syntax("// }\nconst x = 1;\n", path="x.js").valid is True


def test_unknown_language_passes_through():
    result = V.validate_syntax("anything at all", path="x.txt")
    assert result.valid is True and result.checker == "none"


# ── change validation (no writes) ────────────────────────────────────────────


def test_validate_changes_reports_ambiguous(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "dup.txt").write_text("same\nsame\n", encoding="utf-8")
    svc = make_service(root)
    result = svc.validate_changes([
        {"path": "src/dup.txt", "operation": "replace", "oldText": "same", "newText": "x"},
    ])
    assert result["valid"] is False
    assert result["checks"][0]["code"] == "AMBIGUOUS_PATCH"
    # Nothing changed.
    assert (root / "src" / "dup.txt").read_text(encoding="utf-8") == "same\nsame\n"


def test_validate_changes_reports_missing_target(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.validate_changes([
        {"path": "src/app.py", "operation": "replace", "oldText": "nope", "newText": "x"},
    ])
    assert result["valid"] is False
    assert result["checks"][0]["code"] == "PATCH_CONTEXT_MISMATCH"


def test_validate_changes_all_valid(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.validate_changes([
        {"path": "src/app.py", "operation": "replace", "oldText": "alpha", "newText": "ALPHA"},
        {"path": "src/other.py", "operation": "replace", "oldText": "UNTOUCHED", "newText": "X"},
    ])
    assert result["valid"] is True and all(c["ok"] for c in result["checks"])


# ── post-write verification ──────────────────────────────────────────────────


def test_write_file_returns_a_verification_verdict(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.write_file("src/app.py", "def f():\n    return 1\n")
    assert result["verification"]["verified"] is True
    assert result["verification"]["syntax"]["valid"] is True


def test_write_file_flags_broken_syntax(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.write_file("src/broken.py", "def f(:\n    pass\n", create_if_missing=True)
    assert result["verification"]["verified"] is False
    assert result["verification"]["syntax"]["valid"] is False


def test_edit_returns_a_verification_verdict(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.replace_text("src/app.py", "beta", "BETA", expected_occurrences=1)
    assert result["verification"]["verified"] is True


def test_verify_file_tool_path(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    assert svc.verify_file("src/app.py")["verified"] is True
    (root / "src" / "broken.py").write_text("def g(:\n    pass\n", encoding="utf-8")
    assert svc.verify_file("src/broken.py")["verified"] is False


def test_verify_file_binary_is_not_syntax_checked(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "blob.bin").write_bytes(b"\x00\x01\x02")
    svc = make_service(root)
    result = svc.verify_file("src/blob.bin")
    assert result["binary"] is True and result["verified"] is True


# ── git awareness ─────────────────────────────────────────────────────────────


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)


def _init_git(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not installed")
def test_git_status_reports_states(tmp_path):
    root = tree(tmp_path)
    _init_git(root)
    (root / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    (root / "new.txt").write_text("new\n", encoding="utf-8")
    svc = make_service(root)
    result = svc.git_status()
    assert result["available"] is True
    states = {e["state"] for e in result["entries"]}
    assert "modified" in states and "untracked" in states
    assert result["branch"]


@pytest.mark.skipif(not __import__("shutil").which("git"), reason="git not installed")
def test_file_metadata_includes_git_state(tmp_path):
    root = tree(tmp_path)
    _init_git(root)
    (root / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    svc = make_service(root)
    meta = svc.file_metadata("src/app.py")
    assert meta["git"]["state"] == "modified"


def test_git_status_is_honest_outside_a_checkout(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.git_status()
    # Either git is absent (available False) or the temp folder is not a checkout.
    assert result["status"] == "ok"
    assert result["available"] is False


# ── tools through the registry + events ───────────────────────────────────────


class _FakeEmitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))
        return {}

    def emit_sync(self, event_type, data=None):
        self.events.append((event_type, data or {}))


def _ctx(root, emitter=None):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.git.register import register_git_subsystem
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    register_git_subsystem(registry)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=make_ws(root), autonomy="edit_verify",
        authorize_effect=make_code_authorizer(), direct=True, emitter=emitter,
    )
    return registry, ctx


def _call(registry, name, args, ctx):
    return asyncio.run(registry.execute(name, f"c_{name}", args, ctx))


def test_registry_registers_verify_and_git_tools(tmp_path):
    root = tree(tmp_path)
    registry, _ = _ctx(root)
    for name in ("verify_file", "validate_changes"):
        tool = registry.get(name)
        assert tool is not None and tool.permission == "read"
    # `git_status` is the ONE Git-engine tool (registered by `register_git_tools`),
    # still read-only.
    git_tool = registry.get("git_status")
    assert git_tool is not None and git_tool.permission == "read"


def test_verify_file_tool_through_registry(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "verify_file", {"path": "src/app.py"}, ctx)
    assert result.ok and result.data["verified"] is True


def test_multi_file_patch_emits_transaction_events(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    emitter = _FakeEmitter()
    registry, ctx = _ctx(root, emitter)
    _call(registry, "multi_file_patch", {"patches": [
        {"path": "src/app.py", "operation": "replace", "oldText": "alpha", "newText": "ALPHA"},
    ]}, ctx)
    kinds = [e[0] for e in emitter.events]
    assert "fs.transaction.started" in kinds
    assert "fs.transaction.committed" in kinds


def test_multi_file_patch_refusal_emits_rolled_back(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    emitter = _FakeEmitter()
    registry, ctx = _ctx(root, emitter)
    _call(registry, "multi_file_patch", {"patches": [
        {"path": "src/app.py", "operation": "replace", "oldText": "MISSING", "newText": "X"},
    ]}, ctx)
    kinds = [e[0] for e in emitter.events]
    assert "fs.transaction.rolled_back" in kinds


def test_index_workspace_emits_updated_event(tmp_path):
    root = tree(tmp_path)
    emitter = _FakeEmitter()
    registry, ctx = _ctx(root, emitter)
    _call(registry, "index_workspace", {}, ctx)
    assert any(e[0] == "fs.index.updated" for e in emitter.events)
