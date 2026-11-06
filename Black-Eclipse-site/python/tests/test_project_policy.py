"""A project's own write denylist: narrow-only, and enforced before any write."""

from __future__ import annotations

import json

import pytest

from harness.code import project_policy
from harness.code.patch import PatchError, PatchOp, apply
from harness.code.policy import WorkspaceBinding
from harness.code.workspace import ResolvedWorkspace
from harness.skills.permissions import Actor


def _policy(tmp_path, deny_paths):
    folder = tmp_path / ".black-eclipse"
    folder.mkdir(exist_ok=True)
    (folder / "policy.json").write_text(json.dumps({"denyPaths": deny_paths}), encoding="utf-8")
    project_policy.reset_cache()


def _workspace(root):
    binding = WorkspaceBinding(id="ws", root=root, base_revision="HEAD", strategy="worktree")
    return ResolvedWorkspace(
        id="ws", root=root, base_revision="HEAD", strategy="worktree", binding=binding,
    )


def _actor():
    return Actor(id="tester", operator=False, workspace_id="ws", autonomy="edit_verify")


def test_a_directory_prefix_and_a_glob_are_both_honoured(tmp_path):
    _policy(tmp_path, ["db/migrations/", "*.lock"])
    assert project_policy.is_denied(tmp_path, "db/migrations/deep/file.py")
    assert project_policy.is_denied(tmp_path, "db/migrations")
    assert project_policy.is_denied(tmp_path, "package.lock")
    assert not project_policy.is_denied(tmp_path, "src/app.py")


def test_an_absolute_or_traversing_entry_is_ignored_not_honoured(tmp_path):
    _policy(tmp_path, ["/etc/passwd", "../outside", "ok.txt"])
    assert project_policy.load_patterns(tmp_path) == ("ok.txt",)


def test_a_broken_policy_protects_nothing(tmp_path):
    folder = tmp_path / ".black-eclipse"
    folder.mkdir()
    (folder / "policy.json").write_text("{not json", encoding="utf-8")
    project_policy.reset_cache()
    assert project_policy.load_patterns(tmp_path) == ()
    assert not project_policy.is_denied(tmp_path, "src/app.py")


def test_a_patch_cannot_write_a_project_protected_path(tmp_path):
    _policy(tmp_path, ["db/migrations/"])
    (tmp_path / "db" / "migrations").mkdir(parents=True)

    with pytest.raises(PatchError) as exc:
        apply(_workspace(tmp_path), [
            PatchOp(op="create", path="db/migrations/out.py", reason="test", content="x = 1\n"),
        ], actor=_actor())

    assert exc.value.code == "PATCH_PROJECT_DENIED"
    assert not (tmp_path / "db" / "migrations" / "out.py").exists()


def test_a_patch_outside_the_denylist_still_applies(tmp_path):
    _policy(tmp_path, ["db/migrations/"])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("old\n", encoding="utf-8")

    result = apply(_workspace(tmp_path), [
        PatchOp(op="overwrite", path="src/app.py", reason="test", content="new\n"),
    ], actor=_actor())

    assert result["ok"] is True
    assert (tmp_path / "src" / "app.py").read_text(encoding="utf-8") == "new\n"
