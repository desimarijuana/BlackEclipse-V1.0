"""Phase 2 — the structured patch engine (patch.py).

Proves the hard rules: atomic (a refusal applies nothing), a unique span or
nothing, a hash on both sides, and a distinct code per rejection vector. The
fixture is an explicit temp tree passed as the workspace root (the code root is
never an argument to worktree.py; here we build a ResolvedWorkspace directly).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from harness.code import patch as patch_mod
from harness.code.patch import PatchError, parse_patch
from harness.code.policy import WorkspaceBinding
from harness.code.workspace import ResolvedWorkspace
from harness.skills.permissions import Actor


def _ws(root: Path) -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id="ws_t", root=real, base_revision="abc1234", strategy="checkout")
    return ResolvedWorkspace(id="ws_t", root=real, base_revision="abc1234", strategy="checkout", binding=binding)


def _actor(autonomy: str = "edit_verify") -> Actor:
    return Actor(id="coder", operator=False, workspace_id="ws_t", autonomy=autonomy)


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (root / "src" / "other.py").write_text("UNTOUCHED = True\n", encoding="utf-8")
    (root / "doc.md").write_text("one\ntwo\n", encoding="utf-8")
    return root


def _apply(root, ops, *, scope=(), actor=None):
    return patch_mod.apply(_ws(root), parse_patch({"operations": ops}), scope=scope, actor=actor or _actor())


# ── happy path: the intended file, only that file ───────────────────────────


def test_intended_file_edited_and_only_that_file(tmp_path):
    root = _tree(tmp_path)
    other_before = (root / "src" / "other.py").read_bytes()
    result = _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "fix", "old": "beta", "new": "BETA"}])
    assert result["ok"] is True
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    assert (root / "src" / "other.py").read_bytes() == other_before


def test_unrelated_files_untouched(tmp_path):
    root = _tree(tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    _apply(root, [{"op": "create", "path": "src/new_file.py", "reason": "x", "content": "x = 1\n"}])
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    # Only the new file appeared; every pre-existing file is byte-identical.
    assert set(after) - set(before) == {"src/new_file.py"}
    for rel in before:
        assert before[rel] == after[rel], rel


def test_applied_op_records_hashes_both_sides(tmp_path):
    root = _tree(tmp_path)
    result = _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "r", "old": "alpha", "new": "ALPHA"}])
    op = result["applied"][0]
    assert op["contentHashBefore"] and op["contentHashAfter"]
    assert op["contentHashBefore"] != op["contentHashAfter"]


# ── atomicity ───────────────────────────────────────────────────────────────


def test_refusal_at_op_n_applies_nothing(tmp_path):
    root = _tree(tmp_path)
    app_before = (root / "src" / "app.py").read_bytes()
    ops = [
        {"op": "replace", "path": "src/app.py", "reason": "ok", "old": "beta", "new": "BETA"},
        {"op": "create", "path": "jdds.db", "reason": "bad", "content": "x"},
    ]
    with pytest.raises(PatchError):
        _apply(root, ops)
    # Op 1 must NOT have been written.
    assert (root / "src" / "app.py").read_bytes() == app_before
    assert not (root / "jdds.db").exists()


# ── rejection vectors, distinct codes ───────────────────────────────────────


def test_traversal_refused(tmp_path):
    with pytest.raises(PatchError) as exc:
        parse_patch({"operations": [{"op": "create", "path": "../escape", "reason": "x", "content": "y"}]})
    assert exc.value.code == "PATCH_PATH_TRAVERSAL"


def test_absolute_refused(tmp_path):
    with pytest.raises(PatchError) as exc:
        parse_patch({"operations": [{"op": "create", "path": "/etc/passwd", "reason": "x", "content": "y"}]})
    assert exc.value.code == "PATCH_PATH_ABSOLUTE"


def test_windows_absolute_refused():
    with pytest.raises(PatchError) as exc:
        parse_patch({"operations": [{"op": "create", "path": r"C:\Windows\x", "reason": "x", "content": "y"}]})
    assert exc.value.code == "PATCH_PATH_ABSOLUTE"


def test_symlink_escape_refused(tmp_path):
    root = _tree(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s", encoding="utf-8")
    link = root / "link"
    made = False
    try:
        os.symlink(outside, link, target_is_directory=True)
        made = True
    except (OSError, NotImplementedError):
        import subprocess
        import sys

        if sys.platform == "win32":
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                  capture_output=True, text=True).returncode == 0
    if not made:
        pytest.skip("this host allows neither symlinks nor junctions")
    with pytest.raises(PatchError) as exc:
        patch_mod.apply(_ws(root), parse_patch({"operations": [
            {"op": "create", "path": "link/new.txt", "reason": "x", "content": "y"}]}), actor=_actor())
    assert exc.value.code == "PATCH_PATH_SYMLINK"


def test_protected_path_refused(tmp_path):
    root = _tree(tmp_path)
    for rel in ("jdds.db", "agent-memory.db", "mcp-servers.json", ".env", "python/harness/code/policy.py"):
        with pytest.raises(PatchError) as exc:
            patch_mod.apply(_ws(root), parse_patch({"operations": [
                {"op": "create", "path": rel, "reason": "x", "content": "y"}]}), actor=_actor())
        assert exc.value.code in ("PATCH_PROTECTED_PATH", "PATCH_PATH_TRAVERSAL")


def test_oversize_refused(tmp_path):
    with pytest.raises(PatchError) as exc:
        parse_patch({"operations": [
            {"op": "create", "path": "src/big.py", "reason": "x", "content": "a" * (patch_mod.MAX_FILE_BYTES + 1)}]})
    assert exc.value.code == "PATCH_TOO_LARGE"


def test_outside_scope_refused(tmp_path):
    root = _tree(tmp_path)
    app_before = (root / "src" / "app.py").read_bytes()
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "beta", "new": "B"}],
               scope=("doc.md",))
    assert exc.value.code == "PATCH_OUTSIDE_SCOPE"
    assert (root / "src" / "app.py").read_bytes() == app_before


def test_ambiguous_span_refused(tmp_path):
    root = _tree(tmp_path)
    (root / "dup.txt").write_text("same\nsame\n", encoding="utf-8")
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "replace", "path": "dup.txt", "reason": "x", "old": "same", "new": "done"}])
    assert exc.value.code == "PATCH_SPAN_AMBIGUOUS"


def test_span_not_found_refused(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "nope", "new": "y"}])
    assert exc.value.code == "PATCH_SPAN_NOT_FOUND"


def test_base_mismatch_refused(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "beta",
                       "new": "B", "expectHash": "0" * 64}])
    assert exc.value.code == "PATCH_BASE_MISMATCH"


def test_file_exists_refused(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "create", "path": "src/app.py", "reason": "x", "content": "y"}])
    assert exc.value.code == "PATCH_FILE_EXISTS"


# ── plan_only denied ────────────────────────────────────────────────────────


def test_plan_only_profile_denied(tmp_path):
    root = _tree(tmp_path)
    app_before = (root / "src" / "app.py").read_bytes()
    with pytest.raises(PatchError) as exc:
        _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "beta", "new": "B"}],
               actor=_actor("plan_only"))
    assert exc.value.code == "PROFILE_DENIED"
    assert (root / "src" / "app.py").read_bytes() == app_before


# ── move + revert ───────────────────────────────────────────────────────────


def test_move_then_revert_restores_exactly(tmp_path):
    root = _tree(tmp_path)
    before = (root / "doc.md").read_bytes()
    result = _apply(root, [{"op": "move", "path": "moved.md", "reason": "x", "fromPath": "doc.md"}])
    assert result["ok"] and not (root / "doc.md").exists() and (root / "moved.md").exists()
    patch_mod.revert(_ws(root), result["applied"], actor=_actor())
    assert (root / "doc.md").read_bytes() == before
    assert not (root / "moved.md").exists()


def test_revert_refuses_over_a_changed_base(tmp_path):
    root = _tree(tmp_path)
    result = _apply(root, [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "beta", "new": "BETA"}])
    # A concurrent edit after the apply.
    (root / "src" / "app.py").write_text("completely different\n", encoding="utf-8")
    with pytest.raises(PatchError) as exc:
        patch_mod.revert(_ws(root), result["applied"], actor=_actor())
    assert exc.value.code == "PATCH_BASE_MISMATCH"


def test_revert_of_create_deletes_the_file(tmp_path):
    root = _tree(tmp_path)
    result = _apply(root, [{"op": "create", "path": "new.txt", "reason": "x", "content": "hello"}])
    assert (root / "new.txt").exists()
    patch_mod.revert(_ws(root), result["applied"], actor=_actor())
    assert not (root / "new.txt").exists()


# ── the tool path: profile / unbound refusals with a precise code ────────────


def _registry_ctx(root, autonomy):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="run_t", log=lambda *_: None, workspace=_ws(root),
        autonomy=autonomy, authorize_effect=make_code_authorizer(),
    )
    return registry, ctx


def test_tool_plan_only_is_profile_denied(tmp_path):
    import asyncio

    root = _tree(tmp_path)
    app_before = (root / "src" / "app.py").read_bytes()
    registry, ctx = _registry_ctx(root, "plan_only")
    result = asyncio.run(registry.execute(
        "workspace_patch_apply", "c1",
        {"operations": [{"op": "replace", "path": "src/app.py", "reason": "x", "old": "beta", "new": "B"}]},
        ctx, allowed={"workspace_patch_apply"},
    ))
    assert result.ok and result.data["code"] == "PROFILE_DENIED"
    assert (root / "src" / "app.py").read_bytes() == app_before


def test_tool_without_a_workspace_is_unbound(tmp_path):
    import asyncio

    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="run_t", log=lambda *_: None, workspace=None, autonomy="edit_verify",
        authorize_effect=make_code_authorizer(),
    )
    result = asyncio.run(registry.execute(
        "workspace_patch_apply", "c1",
        {"operations": [{"op": "create", "path": "x.txt", "reason": "x", "content": "y"}]},
        ctx, allowed={"workspace_patch_apply"},
    ))
    assert result.data["code"] == "WORKSPACE_UNBOUND"
