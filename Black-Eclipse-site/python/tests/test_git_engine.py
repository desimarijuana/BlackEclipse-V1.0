"""Git engine — repository discovery, the operation catalog, the status/diff/log
parsers, and the executor against ISOLATED temporary repositories.

Nothing here touches the Eclipse source repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.git import executor, parsers, repository
from harness.git.catalog import CATALOG
from harness.git.errors import GitError
from harness.git.operations import is_plain_ref, is_plain_rev, validate_op_args

from git_helpers import commit_all, git, make_repo, write


# ── Discovery ──────────────────────────────────────────────────────────────────

def test_discover_normal_repository(tmp_path):
    repo = make_repo(tmp_path / "repo")
    assert repo.branch == "main"
    assert repo.head is not None
    assert repo.detached_head is False
    assert repo.bare is False
    assert repo.linked_worktree is False
    assert repo.submodule is False
    info = repo.to_dict()
    assert info["is_repository"] is True
    assert Path(info["root"]) == tmp_path / "repo"
    assert info["git_dir"].endswith(".git")


def test_discover_from_nested_directory(tmp_path):
    repo = make_repo(tmp_path / "repo")
    nested = tmp_path / "repo" / "src" / "deep"
    nested.mkdir(parents=True)
    found = repository.discover(nested)
    assert found is not None
    assert found.root == repo.root


def test_discover_non_repository_returns_none(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert repository.discover(plain) is None


def test_discover_unborn_head_is_valid(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    repo = repository.discover(root)
    assert repo is not None
    assert repo.unborn is True
    assert repo.head is None
    assert repo.branch == "main"


def test_discover_bare_repository(tmp_path):
    bare = tmp_path / "bare.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare")
    repo = repository.discover(bare)
    assert repo is not None
    assert repo.bare is True


def test_discover_linked_worktree(tmp_path):
    repo = make_repo(tmp_path / "repo")
    wt = tmp_path / "linked"
    git(repo.root, "worktree", "add", "-q", "--detach", str(wt))
    linked = repository.discover(wt)
    assert linked is not None
    assert linked.linked_worktree is True
    assert linked.git_dir != linked.common_dir


def test_require_repository_raises(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitError) as info:
        repository.require_repository(plain)
    assert info.value.code == "NOT_A_REPOSITORY"


def test_list_repositories_finds_nested(tmp_path):
    from harness.git.service import GitService

    make_repo(tmp_path / "outer")
    nested = tmp_path / "outer" / "vendorpkg"
    nested.mkdir()
    make_repo(nested)
    result = GitService().list_repositories(tmp_path, max_depth=4)
    assert result["count"] >= 2


# ── Operation table / validation ───────────────────────────────────────────────

def test_catalog_is_closed_and_every_op_builds_with_absolute_git(tmp_path):
    repo = make_repo(tmp_path / "repo")
    # No builder may place model text as argv[0]; the git path is absolute.
    for name, op in CATALOG.items():
        argv = op.build({a.name: _sample_for(a) for a in op.args if a.required}, "/abs/git")
        assert argv[0] == "/abs/git", name
        assert "-c" in argv[:3], name


def _sample_for(spec):
    if spec.many:
        return ["HEAD"] if spec.kind in ("rev", "ref") else ["x.txt"]
    if spec.kind == "int":
        return 1
    if spec.kind == "enum":
        return spec.allowed[0]
    if spec.kind == "config_key":
        return "user.name"
    if spec.kind in ("rev", "ref"):
        return "HEAD"
    if spec.kind == "date":
        return "2020-01-01"
    if spec.kind == "message":
        return "a message"
    if spec.kind == "pattern":
        return "pattern"
    return "value"


def test_unknown_argument_is_rejected():
    from harness.git.catalog import CATALOG

    with pytest.raises(GitError):
        validate_op_args(CATALOG["status"], {"nope": "x"})


def test_option_like_ref_is_rejected():
    from harness.git.catalog import CATALOG

    with pytest.raises(GitError) as info:
        validate_op_args(CATALOG["branch_create"], {"name": "--force"})
    assert info.value.code == "UNSAFE_COMMAND"


def test_pathspec_magic_is_rejected():
    from harness.git.catalog import CATALOG

    with pytest.raises(GitError):
        validate_op_args(CATALOG["add"], {"paths": [":(exclude)*.py"]})


def test_ref_validation_rules():
    assert is_plain_ref("feature/auth")
    assert not is_plain_ref("--evil")
    assert not is_plain_ref("a..b")
    assert not is_plain_ref("a b")
    assert not is_plain_ref("bad.lock")
    assert is_plain_rev("HEAD~2")
    assert is_plain_rev("main...feature")
    assert not is_plain_rev("-x")


def test_git_push_subcommands_are_in_catalog_but_validated():
    # Push exists as a tool, but a leading `+` refspec force is NOT expressible.
    from harness.git.catalog import CATALOG

    op = CATALOG["push"]
    argv = op.build({}, "/abs/git")
    assert "push" in argv
    assert "--force" not in argv  # never a default


def test_executor_refuses_when_git_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "resolve_git", lambda: None)
    result = executor.run(tmp_path, "status")
    assert result.ok is False
    assert result.code == "GIT_UNAVAILABLE"


def test_executor_never_uses_a_shell(tmp_path):
    repo = make_repo(tmp_path / "repo")
    # A value that would be a shell injection is inert: it is a validated arg.
    with pytest.raises(GitError):
        executor.build_argv("log", {"rev": "HEAD; rm -rf /"})


# ── Status parser ────────────────────────────────────────────────────────────────

def test_status_clean(tmp_path):
    repo = make_repo(tmp_path / "repo")
    parsed = parsers.parse_status(_status_raw(repo))
    assert parsed["clean"] is True
    assert parsed["branch"] == "main"


def test_status_classifies_modified_staged_untracked(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "tracked.txt", "one\n")
    commit_all(repo.root, "add tracked")
    write(repo.root, "tracked.txt", "one\ntwo\n")
    write(repo.root, "new.txt", "new\n")
    git(repo.root, "add", "tracked.txt")
    parsed = parsers.parse_status(_status_raw(repo))
    assert any(e["path"] == "tracked.txt" for e in parsed["staged"])
    assert "new.txt" in parsed["untracked"]
    assert parsed["clean"] is False


def test_status_reports_conflict(tmp_path):
    repo = _conflict_repo(tmp_path)
    parsed = parsers.parse_status(_status_raw(repo))
    assert parsed["conflicts"]
    assert parsed["conflicts"][0]["path"] == "file.txt"


def test_status_detached_head(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "x.txt", "x\n")
    commit_all(repo.root, "x")
    git(repo.root, "checkout", "-q", "--detach", "HEAD")
    parsed = parsers.parse_status(_status_raw(repo))
    assert parsed["detached_head"] is True
    assert parsed["branch"] is None


def _status_raw(repo):
    result = executor.run(repo.root, "status")
    assert result.ok
    return result.stdout


def _conflict_repo(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "file.txt", "base\n")
    commit_all(repo.root, "base")
    git(repo.root, "checkout", "-q", "-b", "other")
    write(repo.root, "file.txt", "other\n")
    commit_all(repo.root, "other")
    git(repo.root, "checkout", "-q", "main")
    write(repo.root, "file.txt", "main\n")
    commit_all(repo.root, "main")
    git(repo.root, "merge", "other")
    return repo


# ── Diff / numstat parsers ──────────────────────────────────────────────────────

def test_diff_cached_reports_counts(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    write(repo.root, "f.txt", "a\nb\n")
    git(repo.root, "add", "f.txt")
    data = readers.diff_cached(repo)
    assert data["files_changed"] == 1
    assert data["insertions"] == 2
    assert "f.txt" in data["patch"]


def test_numstat_binary_is_flagged(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    (repo.root / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    git(repo.root, "add", "blob.bin")
    data = readers.diff_cached(repo)
    assert data["binary_files"]


def test_name_status_parses_rename(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    write(repo.root, "old.txt", "content\n")
    commit_all(repo.root, "add old")
    git(repo.root, "mv", "old.txt", "new.txt")
    result = executor.run(repo.root, "diff_name_status_cached", {"paths": []})
    entries = parsers.parse_name_status(result.stdout)
    assert any(e["status"] == "renamed" for e in entries)


# ── Log parser ────────────────────────────────────────────────────────────────────

def test_log_parses_commits(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "a.txt", "a\n")
    commit_all(repo.root, "second commit")
    data = parsers.parse_log(executor.run(repo.root, "log", {"maxCount": 10}).stdout)
    assert len(data) == 2
    assert data[0]["subject"] == "second commit"
    assert data[0]["sha"] and data[0]["short_sha"]
    assert data[0]["parents"]


def test_log_merge_has_two_parents(tmp_path):
    repo = _conflict_repo(tmp_path)
    write(repo.root, "file.txt", "resolved\n")
    git(repo.root, "add", "file.txt")
    git(repo.root, "commit", "-qm", "merge")
    data = parsers.parse_log(executor.run(repo.root, "log", {"maxCount": 1}).stdout)
    assert data[0]["is_merge"] is True
    assert len(data[0]["parents"]) == 2


# ── Blame / reflog / branches / worktrees ─────────────────────────────────────────

def test_blame_returns_per_line(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    write(repo.root, "f.txt", "one\ntwo\n")
    commit_all(repo.root, "add")
    data = readers.blame(repo, "f.txt")
    assert data["available"] is True
    assert len(data["lines"]) == 2
    assert data["lines"][0]["line"] == 1


def test_reflog_has_entries(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    data = readers.reflog(repo)
    assert data["available"] is True
    assert data["entries"]


def test_branches_list_current(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    git(repo.root, "branch", "feature")
    data = readers.branches(repo)
    names = {b["name"]: b for b in data["branches"]}
    assert "main" in names and "feature" in names
    assert names["main"]["current"] is True


def test_worktrees_parse(tmp_path):
    from harness.git import readers

    repo = make_repo(tmp_path / "repo")
    git(repo.root, "worktree", "add", "-q", "--detach", str(tmp_path / "linked"))
    data = readers.worktrees(repo)
    assert data["available"] is True
    assert len(data["worktrees"]) == 2


# ── Repository policy ─────────────────────────────────────────────────────────────

def test_load_policy_defaults_and_file(tmp_path):
    from harness.git import safety

    repo = make_repo(tmp_path / "repo")
    default = safety.load_policy(repo)
    assert "main" in default.protected_branches
    (repo.root / ".black-eclipse").mkdir()
    (repo.root / ".black-eclipse" / "git.json").write_text(
        '{"default_branch": "trunk", "commit": {"conventional": true}, "protected_branches": ["trunk"]}',
        encoding="utf-8",
    )
    policy = safety.load_policy(repo)
    assert policy.default_branch == "trunk"
    assert policy.conventional_commits is True
    assert safety.is_protected_branch(repo, "trunk", policy) is True
    assert safety.is_protected_branch(repo, "feature", policy) is False
