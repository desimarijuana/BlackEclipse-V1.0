"""Trusted workspace roots + the folder picker (folder-selection foundation).

Approving a folder is the ONE way a new root becomes justifiable. These tests
prove: approval is idempotent and realpath-based; the selected root is what
`workspace.default_root()` resolves to (after the env override); revocation
removes it; and browse is bounded and never invents a value.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.code import roots, workspace
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _reset_provider():
    yield
    workspace.set_trusted_root_provider(None)


def test_approve_creates_a_root(store, tmp_path):
    target = tmp_path / "myproj"
    target.mkdir()
    roots_store = roots.TrustedRootStore(store)
    root = roots_store.approve(str(target), label="My Project")
    assert root.label == "My Project"
    assert Path(root.path) == Path(os.path.realpath(str(target)))
    assert roots_store.is_trusted(str(target))


def test_approve_is_idempotent_by_realpath(store, tmp_path):
    target = tmp_path / "myproj"
    target.mkdir()
    roots_store = roots.TrustedRootStore(store)
    a = roots_store.approve(str(target))
    # A trailing separator / relative form resolves to the same root.
    b = roots_store.approve(str(target) + os.sep)
    assert a.id == b.id
    assert len(roots_store.list()) == 1


def test_approve_refuses_a_non_directory(store, tmp_path):
    roots_store = roots.TrustedRootStore(store)
    missing = tmp_path / "nope"
    with pytest.raises(ValueError):
        roots_store.approve(str(missing))


def test_select_and_clear(store, tmp_path):
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    roots_store = roots.TrustedRootStore(store)
    ra = roots_store.approve(str(a))
    rb = roots_store.approve(str(b))
    roots_store.select(ra.id)
    assert roots_store.selected().id == ra.id
    roots_store.select(rb.id)
    assert roots_store.selected().id == rb.id  # exactly one selected
    roots_store.clear_selection()
    assert roots_store.selected() is None


def test_revoke_removes_the_root(store, tmp_path):
    target = tmp_path / "p"; target.mkdir()
    roots_store = roots.TrustedRootStore(store)
    root = roots_store.approve(str(target))
    assert roots_store.revoke(root.id) is True
    assert roots_store.is_trusted(str(target)) is False
    assert roots_store.revoke(root.id) is False


def test_selected_root_drives_default_root(store, tmp_path, monkeypatch):
    monkeypatch.delenv("BLACK_ECLIPSE_CODE_ROOT", raising=False)
    target = tmp_path / "chosen"; target.mkdir()
    roots_store = roots.TrustedRootStore(store)
    root = roots_store.approve(str(target))
    roots_store.select(root.id)
    workspace.set_trusted_root_provider(lambda: roots_store.selected().path if roots_store.selected() else None)
    assert workspace.default_root() == Path(os.path.realpath(str(target)))


def test_env_override_wins_over_selected_root(store, tmp_path, monkeypatch):
    target = tmp_path / "chosen"; target.mkdir()
    env_root = tmp_path / "env"; env_root.mkdir()
    roots_store = roots.TrustedRootStore(store)
    root = roots_store.approve(str(target))
    roots_store.select(root.id)
    workspace.set_trusted_root_provider(lambda: roots_store.selected().path if roots_store.selected() else None)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(env_root))
    assert workspace.default_root() == Path(os.path.realpath(str(env_root)))


def test_browse_lists_children(tmp_path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    result = roots.browse(str(tmp_path))
    names = {e["name"] for e in result["entries"]}
    assert "folder" in names and "file.txt" in names
    folder = next(e for e in result["entries"] if e["name"] == "folder")
    assert folder["isDir"] is True


def test_browse_root_lists_drives_or_slash():
    result = roots.browse(None)
    assert result["path"] is None
    assert result["entries"]  # drives on Windows, "/" on POSIX


def test_browse_missing_path_is_honest(tmp_path):
    result = roots.browse(str(tmp_path / "nope"))
    assert result["entries"] == []
    assert result["reason"]


def test_browse_never_recurses(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "deep").mkdir()
    result = roots.browse(str(tmp_path))
    names = {e["name"] for e in result["entries"]}
    assert "a" in names
    assert "deep" not in names  # children only, never grandchildren


def test_create_folder_makes_one_leaf(tmp_path):
    result = roots.create_folder(str(tmp_path), "my project")
    assert (tmp_path / "my project").is_dir()
    assert Path(result["path"]) == Path(os.path.realpath(str(tmp_path / "my project")))
    assert result["name"] == "my project"
    assert Path(result["parent"]) == Path(os.path.realpath(str(tmp_path)))


def test_create_folder_refuses_a_path_or_a_missing_parent(tmp_path):
    for name in ("a/b", "a\\b", ".", "..", ""):
        with pytest.raises(ValueError):
            roots.create_folder(str(tmp_path), name)
    with pytest.raises(ValueError):
        roots.create_folder(None, "x")  # the drive list has no writable location
    with pytest.raises(ValueError):
        roots.create_folder(str(tmp_path / "missing"), "x")


def test_create_folder_is_idempotent_for_an_existing_folder(tmp_path):
    (tmp_path / "exists").mkdir()
    assert roots.create_folder(str(tmp_path), "exists")["name"] == "exists"
