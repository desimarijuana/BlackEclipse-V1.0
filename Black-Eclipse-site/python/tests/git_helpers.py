"""Shared fixtures for the Git subsystem tests.

Every test uses an ISOLATED temporary repository — never the Eclipse source
repository. `make_repo` creates a fresh git checkout with one commit; `commit_all`
stages and commits; `write` edits a file.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from harness.git import repository as repo_mod
from harness.git.repository import Repository

_ENV = {
    **{k: os.environ[k] for k in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT")
       if k in os.environ},
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, shell=False, env=_ENV,
    )


def make_repo(root: Path, *, branch: str = "main") -> Repository:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", branch)
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial commit")
    repo = repo_mod.discover(root)
    assert repo is not None
    return repo


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(root: Path, message: str = "change") -> subprocess.CompletedProcess:
    git(root, "add", "-A")
    return git(root, "commit", "-qm", message)


def make_bare_remote(root: Path, name: str = "origin.git", *, branch: str = "main") -> Path:
    bare = root / name
    bare.mkdir(parents=True, exist_ok=True)
    git(bare, "init", "-q", "--bare", "-b", branch)
    return bare


__all__ = ["commit_all", "git", "make_bare_remote", "make_repo", "write"]
