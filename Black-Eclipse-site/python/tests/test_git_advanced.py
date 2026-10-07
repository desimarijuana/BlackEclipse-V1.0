"""Git subsystem — advanced: selective hunk staging, automated interactive rebase,
and patch application. Every test uses an isolated temporary repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.git import diffs, rebase_plan, readers
from harness.git.service import GitService

from git_helpers import commit_all, git, make_repo, write


@pytest.fixture()
def svc(tmp_path):
    return GitService(), make_repo(tmp_path / "repo")


# ── Hunk parsing / reconstruction ────────────────────────────────────────────────

def test_parse_and_summarize_diff():
    patch = (
        "diff --git a/f.txt b/f.txt\n"
        "index 1..2 100644\n"
        "--- a/f.txt\n"
        "+++ b/f.txt\n"
        "@@ -1,3 +1,3 @@\n-line1\n+LINE1\n line2\n line3\n"
        "@@ -10,3 +10,3 @@\n-a\n+b\n c\n d\n"
    )
    files = diffs.parse_unified_diff(patch)
    assert len(files) == 1
    assert files[0].path == "f.txt"
    assert len(files[0].hunks) == 2
    summary = diffs.summarize(files)
    assert summary["hunkCount"] == 2


def test_render_selected_keeps_only_chosen_hunks():
    patch = (
        "diff --git a/f.txt b/f.txt\n"
        "--- a/f.txt\n+++ b/f.txt\n"
        "@@ -1,2 +1,2 @@\n-a\n+A\n b\n"
        "@@ -10,2 +10,2 @@\n-c\n+C\n d\n"
    )
    files = diffs.parse_unified_diff(patch)
    only_first = diffs.render_selected(files, {"f.txt": [0]})
    assert "+A" in only_first and "+C" not in only_first
    both = diffs.render_selected(files, {"f.txt": [-1]})
    assert "+A" in both and "+C" in both


def test_parse_rejects_path_escape():
    patch = "diff --git a/../evil b/../evil\n--- a/../evil\n+++ b/../evil\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(Exception):
        diffs.parse_unified_diff(patch)


def test_parse_rejects_absolute_path():
    patch = "diff --git a/C:/x b/C:/x\n--- a/C:/x\n+++ b/C:/x\n@@ -1 +1 @@\n-a\n+b\n"
    with pytest.raises(Exception):
        diffs.parse_unified_diff(patch)


# ── Selective staging end-to-end ──────────────────────────────────────────────────

def test_stage_only_one_hunk_of_a_file(svc):
    service, repo = svc
    # Two separated edits → two hunks (context is 3 lines, so separate them).
    body = "".join(f"line{i}\n" for i in range(1, 21))
    write(repo.root, "f.txt", body)
    commit_all(repo.root, "seed")
    changed = body.replace("line1\n", "LINE1\n").replace("line20\n", "LINE20\n")
    write(repo.root, "f.txt", changed)

    listed = service.list_hunks(repo)
    assert listed["hunkCount"] == 2
    outcome = service.stage_hunks(repo, {"f.txt": [0]})
    assert outcome.success, outcome.error
    cached = service._staged_paths(repo)
    assert cached == ["f.txt"]
    # Only the first edit is staged; the second is still unstaged.
    from harness.git import readers as r
    staged_patch = r.diff_cached(repo)["patch"]
    assert "+LINE1" in staged_patch and "+LINE20" not in staged_patch


def test_unstage_only_one_hunk(svc):
    service, repo = svc
    body = "".join(f"l{i}\n" for i in range(1, 21))
    write(repo.root, "f.txt", body)
    commit_all(repo.root, "seed")
    write(repo.root, "f.txt", body.replace("l1\n", "L1\n").replace("l20\n", "L20\n"))
    service.stage_hunks(repo, {"f.txt": [-1]})  # stage everything
    from harness.git import readers as r
    staged_all = r.diff_cached(repo)["patch"]
    assert "+L1" in staged_all and "+L20" in staged_all
    outcome = service.unstage_hunks(repo, {"f.txt": [1]})
    assert outcome.success, outcome.error
    staged = r.diff_cached(repo)["patch"]
    assert "+L1" in staged and "+L20" not in staged


def test_apply_patch_to_index(svc):
    service, repo = svc
    write(repo.root, "f.txt", "one\n")
    commit_all(repo.root, "seed")
    write(repo.root, "f.txt", "two\n")
    patch = readers.diff_worktree(repo)["patch"]
    outcome = service.apply_patch(repo, patch, to_index=True)
    assert outcome.success
    assert service._staged_paths(repo) == ["f.txt"]


# ── Automated interactive rebase ────────────────────────────────────────────────────

def _four_commits(repo):
    for i in range(1, 5):
        write(repo.root, f"f{i}.txt", f"{i}\n")
        commit_all(repo.root, f"commit {i}")
    return readers.log(repo, max_count=10)["commits"]  # newest first


def _subjects(repo):
    return [c["subject"] for c in readers.log(repo, max_count=10)["commits"]]


def test_rebase_plan_drops_a_commit(svc):
    service, repo = svc
    commits = _four_commits(repo)
    before = len(commits)
    drop = commits[1]  # "commit 3"
    outcome = service.rebase_plan(repo, "HEAD~4", [{"commit": drop["sha"], "action": "drop"}])
    assert outcome.success, outcome.error
    subjects = _subjects(repo)
    assert drop["subject"] not in subjects
    assert not (repo.root / "f3.txt").exists()
    assert len(subjects) == before - 1


def test_rebase_plan_rewords_a_commit(svc):
    service, repo = svc
    commits = _four_commits(repo)
    target = commits[0]  # newest ("commit 4")
    outcome = service.rebase_plan(
        repo, "HEAD~4",
        [{"commit": target["sha"], "action": "reword", "message": "brand new subject"}],
    )
    assert outcome.success, outcome.error
    subjects = _subjects(repo)
    assert "brand new subject" in subjects
    assert target["subject"] not in subjects


def test_rebase_plan_squashes_commits(svc):
    service, repo = svc
    commits = _four_commits(repo)
    before = len(commits)
    parent = commits[1]
    child = commits[0]
    outcome = service.rebase_plan(repo, "HEAD~4", [
        {"commit": parent["sha"], "action": "pick"},
        {"commit": child["sha"], "action": "fixup"},
    ])
    assert outcome.success, outcome.error
    subjects = _subjects(repo)
    assert len(subjects) == before - 1  # two commits became one


def test_rebase_plan_partial_never_drops_unnamed(svc):
    service, repo = svc
    commits = _four_commits(repo)
    before = len(commits)
    outcome = service.rebase_plan(repo, "HEAD~4", [{"commit": commits[1]["sha"], "action": "pick"}])
    assert outcome.success, outcome.error
    assert len(_subjects(repo)) == before  # nothing dropped


def test_rebase_plan_rejects_unknown_action(svc):
    service, repo = svc
    commits = _four_commits(repo)
    with pytest.raises(Exception):
        rebase_plan.validate_actions([{"commit": commits[0]["sha"], "action": "explode"}])


def test_rebase_plan_validates_input():
    with pytest.raises(Exception):
        rebase_plan.validate_actions([])
    with pytest.raises(Exception):
        rebase_plan.validate_actions([{"action": "drop"}])  # no commit
    ok = rebase_plan.validate_actions([{"commit": "abc", "action": "drop"}])
    assert ok[0]["commit"] == "abc"


# ── Long-tail capabilities ──────────────────────────────────────────────────────────

def test_move_path(svc):
    service, repo = svc
    write(repo.root, "old.txt", "x\n")
    commit_all(repo.root, "add old")
    outcome = service.move_path(repo, "old.txt", "new.txt")
    assert outcome.success, outcome.error
    assert (repo.root / "new.txt").exists() and not (repo.root / "old.txt").exists()


def test_remove_paths_cached_keeps_file(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    commit_all(repo.root, "add f")
    outcome = service.remove_paths(repo, ["f.txt"], cached=True)
    assert outcome.success, outcome.error
    assert (repo.root / "f.txt").exists()  # --cached keeps the working file


def test_stash_clear(svc):
    service, repo = svc
    write(repo.root, "f.txt", "x\n")
    commit_all(repo.root, "seed f")
    write(repo.root, "f.txt", "change\n")
    service.stash_push(repo, message="one")
    write(repo.root, "f.txt", "change2\n")
    service.stash_push(repo, message="two")
    assert service.stash_clear(repo).success
    from harness.git.tools import _stash_list_impl
    assert _stash_list_impl(repo)["count"] == 0


def test_show_tag(svc):
    service, repo = svc
    service.tag_create(repo, "v9", message="nine")
    data = service.show_tag(repo, "v9")
    assert data["available"] is True
    assert "nine" in data["object"] or "v9" in data["object"]


def test_unset_upstream(svc, tmp_path):
    service, repo = svc
    from git_helpers import make_bare_remote
    from git_helpers import git as _git
    bare = make_bare_remote(tmp_path)
    service.remote_add(repo, "origin", str(bare))
    service.push(repo, remote="origin", branch="main", set_upstream=True)
    assert service.unset_upstream(repo).success


def test_move_path_refuses_escape(svc):
    service, repo = svc
    outcome = service.move_path(repo, "a.txt", "../../outside.txt")
    assert outcome.success is False
    assert outcome.error["code"] in ("UNSAFE_COMMAND", "INVALID_ARGUMENT")


def test_extra_tools_register_with_effects():
    from harness.git.register import register_git_subsystem
    from harness.tools import ToolRegistry

    reg = ToolRegistry()
    register_git_subsystem(reg)
    assert reg.get("git_move_path").permission == "write"
    assert reg.get("git_tag_show").permission == "read"
    assert reg.get("git_lfs_pull").effect == "external_action"
    assert reg.get("git_stash_clear").effect_metadata["risk"] in ("destructive", "high")

