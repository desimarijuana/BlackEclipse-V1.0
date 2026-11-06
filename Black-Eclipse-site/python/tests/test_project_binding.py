"""A build belongs to ONE project (Phase 23 / P0).

The failure this pins: worktrees were always cut from the globally SELECTED root,
and promotion resolved its target the same way at promote time. Bind a chat to
project B, switch the selection to A, and a reviewed diff could land in A.

Now the run's own resolved root is what `allocate` cuts from, the workspace row
records it, promotion reads it back, and a missing project is refused rather than
silently redirected.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from harness.code import promotion, worktree
from harness.code.promotion import PromotionError
from harness.code.store import CodeWorkspaceStore
from harness.persistence import AgentMemoryStore
from test_code_promotion import _git_fixture


def _repo(tmp_path: Path, name: str, text: str) -> Path:
    root = _git_fixture(tmp_path / name)
    (root / "src" / "app.py").write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "project text"], cwd=root, check=False)
    return root


@pytest.fixture()
def two_projects(tmp_path, monkeypatch):
    a = _repo(tmp_path, "a", "print('hello')\n")
    b = _repo(tmp_path, "b", "print('from b')\n")
    # The SELECTION points at A throughout; only the run's root names B.
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(a))
    yield a, b
    for root in (a, b):
        shutil.rmtree(root / worktree.SCRATCH_RELPATH, ignore_errors=True)


def _code_store(directory: Path) -> tuple[AgentMemoryStore, CodeWorkspaceStore]:
    directory.mkdir(parents=True, exist_ok=True)
    store = AgentMemoryStore(str(directory / "agent-memory.db"))
    return store, CodeWorkspaceStore(store)


def test_allocate_cuts_from_the_runs_root_not_the_selection(two_projects):
    a, b = two_projects
    cw = worktree.allocate(root=b)
    assert cw.checkout_root == b
    assert b in cw.root.parents
    assert a not in cw.root.parents
    # The disposable copy contains the OTHER project's file, not the selected one.
    assert (cw.root / "src" / "app.py").read_text(encoding="utf-8") == "print('from b')\n"


def test_promotion_lands_in_the_recorded_project_after_the_selection_moves(two_projects, tmp_path):
    a, b = two_projects
    store, code_store = _code_store(tmp_path / "mem")
    try:
        cw = worktree.allocate(root=b)
        (cw.root / "src" / "app.py").write_text("print('landed in b')\n", encoding="utf-8")
        code_store.save_workspace(
            cw.id, str(cw.root), cw.base_revision, cw.strategy,
            run_id="run_b", file_count=1,
            checkout_root=str(cw.checkout_root) if cw.checkout_root else None,
        )

        preview = promotion.build_preview("run_b", code_store=code_store)
        assert Path(preview["checkoutRoot"]) == b

        promotion.apply_promotion(preview)
        assert (b / "src" / "app.py").read_text(encoding="utf-8") == "print('landed in b')\n"
        # The selected project is untouched: this is the whole point.
        assert (a / "src" / "app.py").read_text(encoding="utf-8") == "print('hello')\n"
    finally:
        store.close()


def test_a_legacy_row_without_a_project_keeps_the_selection(two_projects, tmp_path):
    a, b = two_projects
    store, code_store = _code_store(tmp_path / "mem-legacy")
    try:
        cw = worktree.allocate(root=b)
        (cw.root / "src" / "app.py").write_text("print('legacy')\n", encoding="utf-8")
        # A row written before the column existed: no checkoutRoot. The scratch
        # path still names the project it was cut from, which beats the selection.
        code_store.save_workspace(
            cw.id, str(cw.root), cw.base_revision, cw.strategy, run_id="run_old",
        )
        preview = promotion.build_preview("run_old", code_store=code_store)
        assert Path(preview["checkoutRoot"]) == b
        assert Path(preview["checkoutRoot"]) != a
    finally:
        store.close()


def test_a_vanished_project_is_refused_not_redirected(two_projects, tmp_path):
    _a, b = two_projects
    store, code_store = _code_store(tmp_path / "mem-gone")
    try:
        cw = worktree.allocate(root=b)
        (cw.root / "src" / "app.py").write_text("print('gone')\n", encoding="utf-8")
        gone = tmp_path / "project-that-moved"
        code_store.save_workspace(
            cw.id, str(cw.root), cw.base_revision, cw.strategy,
            run_id="run_gone", checkout_root=str(gone),
        )
        with pytest.raises(PromotionError) as exc:
            promotion.build_preview("run_gone", code_store=code_store)
        assert exc.value.code == "PROMOTION_UNAVAILABLE"
    finally:
        store.close()


def test_a_prepared_change_folder_cannot_be_a_project_root(two_projects):
    _a, b = two_projects
    scratch = b / worktree.SCRATCH_RELPATH
    scratch.mkdir(parents=True, exist_ok=True)
    with pytest.raises(worktree.WorkspaceError) as exc:
        worktree.allocate(root=scratch)
    assert exc.value.code == "WORKSPACE_ROOT_UNAVAILABLE"
