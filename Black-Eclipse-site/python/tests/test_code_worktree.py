"""Phase 2 — disposable code workspaces (worktree.py).

The whole point of the phase: the operator's checkout is never touched. These
tests point `BLACK_ECLIPSE_CODE_ROOT` at a git fixture repo, allocate a
workspace, write to it, and prove the checkout is byte-identical after. They
also prove `release` cannot delete outside the scratch root and is idempotent.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from harness.code import worktree
from harness.code.worktree import WorkspaceError, allocate, release, sweep_expired

FIXTURES = Path(__file__).parent / "fixtures" / "code"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _hash_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
    return out


def _git_fixture(tmp_path: Path) -> Path:
    """A real git checkout that IS the code root, with a pre-existing dirty file."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES, repo)
    _write(repo / "src" / "app.py", "print('hello')\n")
    _write(repo / "docs" / "valuation.md", "# Valuation\n\ndividend-discount model\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    _write(repo / ".gitignore", ".black-eclipse/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    # A pre-existing dirty file the agent must not affect.
    _write(repo / "src" / "app.py", "print('dirty pre-existing')\n")
    return repo


@pytest.fixture()
def git_root(tmp_path, monkeypatch):
    repo = _git_fixture(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(repo))
    yield repo
    shutil.rmtree(repo / worktree.SCRATCH_RELPATH, ignore_errors=True)


# ── allocate ────────────────────────────────────────────────────────────────


def test_allocate_creates_a_workspace_under_scratch(git_root):
    ws = allocate()
    try:
        assert ws.strategy == "worktree"
        assert worktree.SCRATCH_RELPATH.replace("/", os.sep) in str(ws.root)
        assert ws.root.is_dir()
        assert ws.id.startswith("cw_")
    finally:
        release(ws.id)


def test_allocate_workspace_is_a_separate_tree_from_the_checkout(git_root):
    ws = allocate()
    try:
        assert os.path.realpath(ws.root) != os.path.realpath(git_root)
        assert (ws.root / "src" / "app.py").exists()
    finally:
        release(ws.id)


# ── operator checkout untouched ─────────────────────────────────────────────


def test_operator_checkout_untouched_by_allocate_and_release(git_root):
    before = _hash_tree(git_root)
    ws = allocate()
    (ws.root / "src" / "app.py").write_text("changed in the copy\n", encoding="utf-8")
    release(ws.id)
    after = _hash_tree(git_root)
    assert before == after


def test_preexisting_dirty_file_is_hash_identical(git_root):
    dirty = git_root / "src" / "app.py"
    before = hashlib.sha256(dirty.read_bytes()).hexdigest()
    ws = allocate()
    release(ws.id)
    after = hashlib.sha256(dirty.read_bytes()).hexdigest()
    assert before == after


# ── release: idempotent, refuses outside scratch ────────────────────────────


def test_release_idempotent(git_root):
    ws = allocate()
    first = release(ws.id)
    assert first["released"] is True and first["alreadyReleased"] is False
    second = release(ws.id)
    assert second == {"released": True, "alreadyReleased": True, "workspaceId": ws.id}


def test_release_outside_scratch_refused(git_root):
    with pytest.raises(WorkspaceError) as exc:
        release("../../../../etc")
    assert exc.value.code == "RELEASE_OUTSIDE_SCRATCH"


def test_release_outside_scratch_absolute_path_refused(git_root):
    outside = git_root / "src"
    with pytest.raises(WorkspaceError) as exc:
        release(str(outside))
    assert exc.value.code == "RELEASE_OUTSIDE_SCRATCH"
    assert outside.exists()


# ── cancellation / orphan cleanup ───────────────────────────────────────────


def test_cancelled_run_sweep_leaves_no_orphan(git_root):
    ws = allocate()
    old = 10**9
    os.utime(ws.root, (ws.root.stat().st_atime - old, ws.root.stat().st_mtime - old))
    released = sweep_expired()
    assert ws.id in released
    assert not ws.root.exists()


def test_orphan_workspace_is_removed_by_release(git_root):
    ws = allocate()
    assert ws.root.exists()
    release(ws.id)
    assert not ws.root.exists()


# ── diff ────────────────────────────────────────────────────────────────────


def test_diff_reports_added_and_modified(git_root):
    ws = allocate()
    try:
        (ws.root / "src" / "app.py").write_text("print('new')\n", encoding="utf-8")
        _write(ws.root / "src" / "extra.py", "x = 1\n")
        result = worktree.diff(ws.id, strategy=ws.strategy)
        assert result["filesChanged"] >= 1
        changed = set(result["added"]) | set(result["modified"]) | set(result["deleted"])
        assert changed
        assert result["digest"]
    finally:
        release(ws.id)


def test_diff_of_unknown_workspace_is_refused(git_root):
    with pytest.raises(WorkspaceError) as exc:
        worktree.diff("cw_does_not_exist")
    assert exc.value.code == "UNKNOWN_WORKSPACE"


def test_snapshot_fallback_reports_snapshot_strategy(tmp_path, monkeypatch):
    # A non-git tree: `git worktree` is unavailable, so a snapshot copy is used
    # and the strategy says so honestly.
    plain = tmp_path / "plain"
    shutil.copytree(FIXTURES, plain)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(plain))
    ws = allocate()
    try:
        assert ws.strategy == "snapshot"
        result = worktree.diff(ws.id, strategy="snapshot")
        assert result["strategy"] == "snapshot"
    finally:
        release(ws.id)


# ── Windows long-path regression ─────────────────────────────────────────────
#
# An unconfigured git on Windows aborts `worktree add` with "Filename too long"
# when the tree contains deep paths (the scaffold-kit templates do), which
# silently demoted every task to the snapshot fallback and then refused with
# SNAPSHOT_TOO_LARGE. The git argv must therefore always carry
# `-c core.longpaths=true`, so the worktree strategy stays usable.


def test_git_argv_enables_long_paths():
    for key in ("add", "remove", "rev_parse"):
        argv = worktree.GIT_WORKTREE_ARGV[key]
        assert argv[0] == "git"
        assert "-c" in argv and "core.longpaths=true" in argv, key


def test_allocate_uses_the_worktree_strategy_when_git_is_present(git_root):
    ws = allocate()
    try:
        # If `-c core.longpaths=true` were dropped, this would be "snapshot" on a
        # deep-tree checkout. The fixture is shallow, so this asserts the argv is
        # wired correctly rather than relying on hitting MAX_PATH.
        assert ws.strategy == "worktree"
    finally:
        release(ws.id)


# ── direct mode (the user's real folder, opt-in) ─────────────────────────────


def test_direct_workspace_is_the_real_root(git_root):
    ws = allocate(direct=True)
    assert ws.strategy == "direct"
    assert ws.root == git_root
    assert ws.id.startswith("cw_direct_")


def test_release_never_deletes_a_direct_workspace(git_root):
    ws = allocate(direct=True)
    marker = git_root / "keep-me.txt"
    marker.write_text("real file", encoding="utf-8")
    result = release(ws.id)
    assert result.get("direct") is True
    # The user's real folder is untouched.
    assert marker.exists()


def test_direct_workspace_diff_is_honest_without_git(tmp_path, monkeypatch):
    plain = tmp_path / "plain-direct"
    plain.mkdir()
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(plain))
    ws = allocate(direct=True)
    assert ws.strategy == "direct"
    result = worktree.diff(ws.id, strategy="direct")
    # Not a git checkout: no invented diff, just an honest empty result.
    assert result["strategy"] == "direct"
    assert result["filesChanged"] == 0


def test_direct_auto_resolves_from_a_selected_trusted_root(store, tmp_path, monkeypatch):
    """A run with no explicit `direct` edits the real folder iff one is selected."""
    from harness.code import roots, workspace  # noqa: PLC0415
    from harness.graph import _resolve_direct  # noqa: PLC0415

    class _Req:
        direct = None

    class _Explicit:
        direct = True

    class _ExplicitFalse:
        direct = False

    try:
        # No selected root → isolated.
        monkeypatch.delenv("BLACK_ECLIPSE_CODE_ROOT", raising=False)
        workspace.set_trusted_root_provider(None)
        assert _resolve_direct(_Req()) is False
        # A selected trusted root → direct.
        target = tmp_path / "chosen"
        target.mkdir()
        rstore = roots.TrustedRootStore(store)
        root = rstore.approve(str(target))
        rstore.select(root.id)
        workspace.set_trusted_root_provider(lambda: rstore.selected().path if rstore.selected() else None)
        assert _resolve_direct(_Req()) is True
        # An explicit value always wins.
        assert _resolve_direct(_Explicit()) is True
        assert _resolve_direct(_ExplicitFalse()) is False
    finally:
        workspace.set_trusted_root_provider(None)


@pytest.fixture()
def store(tmp_path):
    from harness.persistence import AgentMemoryStore  # noqa: PLC0415

    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()
