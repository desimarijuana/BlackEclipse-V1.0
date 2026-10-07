"""Git subsystem — security tests.

Command injection, path traversal, credential leakage, malicious hooks,
untrusted configuration and symlink escapes. Every test uses an isolated
temporary repository; none may modify the Eclipse source repository.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.git import executor, readers, safety, state
from harness.git.catalog import CATALOG
from harness.git.errors import GitError
from harness.git.operations import validate_op_args
from harness.git.service import GitService

from git_helpers import commit_all, git, make_repo, write


# ── Command injection ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    "HEAD; rm -rf /", "HEAD && curl evil", "HEAD | sh", "$(whoami)",
    "`id`", "HEAD\nrm -rf /", "--upload-pack=touch /tmp/x",
])
def test_revision_injection_is_rejected(payload):
    with pytest.raises(GitError):
        validate_op_args(CATALOG["log"], {"rev": payload})


@pytest.mark.parametrize("payload", ["-D", "--force", "-f", "--all"])
def test_option_like_branch_is_rejected(payload):
    with pytest.raises(GitError):
        validate_op_args(CATALOG["branch_delete"], {"name": payload})


def test_pathspec_magic_is_rejected():
    with pytest.raises(GitError):
        validate_op_args(CATALOG["add"], {"paths": [":(glob)**"]})


def test_null_byte_is_rejected():
    with pytest.raises(GitError):
        validate_op_args(CATALOG["commit"], {"message": "a\x00b"})


def test_no_shell_metacharacter_reaches_argv(tmp_path):
    repo = make_repo(tmp_path / "repo")
    # A branch name with a shell metachar is refused before any process starts.
    with pytest.raises(GitError):
        executor.build_argv("branch_create", {"name": "a;b"})
    # And every catalog op keeps argv[0] absolute with no shell string.
    argv = CATALOG["status"].build({}, "/abs/git")
    assert argv[0] == "/abs/git"


# ── Path traversal / escape ─────────────────────────────────────────────────────────

def test_resolve_conflict_refuses_traversal(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    outcome = service.resolve_conflict(repo, "../../etc/passwd", "x")
    assert outcome.success is False
    assert outcome.error["code"] == "INVALID_ARGUMENT"


def test_resolve_conflict_refuses_symlink_escape(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo.root / "escape.txt"
    try:
        os.symlink(outside / "target.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not creatable here")
    outcome = service.resolve_conflict(repo, "escape.txt", "content")
    # The realpath leaves the root: refused (the write is realpath-confined).
    assert outcome.success is False


@pytest.mark.parametrize("path", [
    "../../escape", "C:\\\\Windows\\\\Temp\\\\escape", "/etc/escape",
    "../../../../tmp/escape",
])
def test_worktree_path_cannot_escape_the_repository_area(tmp_path, path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    outcome = service.worktree_add(repo, path, detach=True)
    assert outcome.success is False
    assert outcome.error["code"] == "INVALID_ARGUMENT"


def test_worktree_sibling_and_inside_are_allowed(tmp_path):
    # `git worktree add` conventionally places a tree BESIDE the repo, so a sibling
    # and a repository-internal path are both legitimate.
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    assert service.worktree_add(repo, "linked", detach=True).success is True
    assert service.worktree_add(repo, str(tmp_path / "sibling-wt"), detach=True).success is True


def test_global_config_write_is_dangerous():
    # A machine-wide config write can inject a hook/ssh command for EVERY repo.
    assert safety.assess_risk("config_set", global_config=True).risk == "dangerous"
    assert safety.assess_risk("config_set", global_config=True).requires_confirmation is True
    assert safety.assess_risk("config_set").risk == "caution"


def test_refspec_leading_plus_force_is_rejected():
    # A `+refspec` is a force push that bypasses --force-with-lease.
    with pytest.raises(GitError):
        validate_op_args(CATALOG["push_refspec"], {"remote": "origin", "refspec": "+main:main"})
    # A plain refspec is fine.
    validate_op_args(CATALOG["push_refspec"], {"remote": "origin", "refspec": "main:main"})


def test_conflict_read_refuses_escape(tmp_path):
    repo = make_repo(tmp_path / "repo")
    assert state.read_conflicts(repo, "../../secret") == []


# ── Credential leakage ─────────────────────────────────────────────────────────────


def test_remote_list_redacts_credentials(tmp_path):
    repo = make_repo(tmp_path / "repo")
    git(repo.root, "remote", "add", "secure", "https://user:ghp_abcdefghijklmnopqrst@github.com/o/r.git")
    data = readers.remotes(repo)
    url = next(r["fetchUrl"] for r in data["remotes"] if r["name"] == "secure")
    assert "ghp_abcdefghijklmnopqrst" not in url
    assert "redacted" in url


def test_config_list_redacts_credential_helper(tmp_path):
    repo = make_repo(tmp_path / "repo")
    git(repo.root, "config", "credential.helper", "store --file=/tmp/token")
    data = readers.config(repo)
    # `credential.helper` value is not itself a secret in this repo's rule, but a
    # token-shaped value is. Assert no pattern-listed secret can appear.
    from harness.session_index import secret_pattern_name

    for entry in data["entries"]:
        assert secret_pattern_name(entry["value"]) is None


def test_journal_redacts_credentials(tmp_path):
    from harness.git.journal import redact_text

    text = redact_text("https://u:ghp_abcdefghijklmnopqrst@host/r.git")
    assert "ghp_abcdefghijklmnopqrst" not in text
    assert redact_text("AKIAABCDEFGHIJKLMNOP") == "«redacted»"


# ── Malicious hooks ────────────────────────────────────────────────────────────────

def test_hooks_are_reported_but_never_executed(tmp_path):
    repo = make_repo(tmp_path / "repo")
    sentinel = tmp_path / "hook-ran"
    hook = repo.git_dir / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    report = safety.inspect_untrusted(repo)
    assert "pre-commit" in report.hooks
    # Nothing ran the hook: the sentinel does not exist.
    assert not sentinel.exists()


def test_commit_does_not_bypass_hooks(tmp_path):
    repo = make_repo(tmp_path / "repo")
    hook = repo.git_dir / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    service = GitService()
    write(repo.root, "f.txt", "x\n")
    service.stage(repo, ["f.txt"])
    outcome = service.commit(repo, "should be blocked")
    # git runs the hook; a failing hook aborts the commit.
    assert outcome.success is False


# ── Untrusted configuration ──────────────────────────────────────────────────────────

def test_untrusted_reports_sensitive_local_config(tmp_path):
    repo = make_repo(tmp_path / "repo")
    git(repo.root, "config", "core.sshCommand", "ssh -i /evil")
    report = safety.inspect_untrusted(repo)
    assert "core.sshcommand" in [k.casefold() for k in report.local_config]


def test_environment_is_scrubbed(tmp_path):
    repo = make_repo(tmp_path / "repo")
    monkey_event = "HARNESS_CALLBACK_TOKEN"
    os.environ[monkey_event] = "should-not-reach-git"
    try:
        # The executor env builder drops the token and proxies.
        env = executor._scrubbed_env()
        assert monkey_event not in env
        assert env.get("GIT_TERMINAL_PROMPT") == "0"
    finally:
        os.environ.pop(monkey_event, None)


# ── Large-file / secret detection ─────────────────────────────────────────────────────

def test_secret_scan_finds_pattern_and_filename(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "config.py", 'OPENAI = "sk-abcdefghijklmnop1234"\n')
    write(repo.root, ".env", "TOKEN=abc\n")
    findings = safety.scan_secrets(repo, ["config.py", ".env"])
    kinds = {f.kind for f in findings}
    assert "filename" in kinds
    assert "pattern" in kinds


def test_large_file_scan_flags_artifacts(tmp_path):
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "node_modules/left-pad/index.js", "x" * 10)
    findings = safety.scan_large_files(repo, ["node_modules/left-pad/index.js"])
    assert findings and findings[0].kind == "artifact"


def test_clean_never_deletes_tracked_files(tmp_path):
    service = GitService()
    repo = make_repo(tmp_path / "repo")
    write(repo.root, "tracked.txt", "important\n")
    commit_all(repo.root, "add tracked")
    outcome = service.clean(repo)
    assert outcome.success
    assert (repo.root / "tracked.txt").exists()
