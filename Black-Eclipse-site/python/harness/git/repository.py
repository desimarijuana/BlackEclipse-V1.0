"""Repository discovery.

First-class discovery, not a guess: it supports a normal `.git` directory, a
`.git` FILE (linked worktrees and submodules), a bare repository, a nested
repository, and a submodule (whose git dir lives under the parent's
`.git/modules/`). State is read from git on every call — never a cached value.

`discover(start)` walks up from `start` to the nearest enclosing directory that
git recognizes, and reports every fact the subsystem needs:

    {
      "is_repository": true,
      "root": "...",             # worktree toplevel, or the bare dir
      "git_dir": "...",           # absolute
      "common_dir": "...",        # shared by linked worktrees
      "branch": "main",           # or None when detached / unborn
      "head": "abc123...",        # or None when unborn
      "detached_head": false,
      "bare": false,
      "linked_worktree": false,
      "submodule": false,
      "unborn": false,
      "has_changes": true,
    }

A worktree with no commits yet (an unborn HEAD) is a valid repository: `head`
is None, `unborn` is true, and no sha is invented.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import errors
from .executor import run
from .errors import GitError

MAX_WALK_UP = 64


@dataclass(frozen=True)
class Repository:
    """A discovered repository. Facts only; no cached mutable state."""

    root: Path
    git_dir: Path
    common_dir: Path
    branch: Optional[str]
    head: Optional[str]
    detached_head: bool
    bare: bool
    linked_worktree: bool
    submodule: bool
    unborn: bool
    has_changes: bool
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_repository": True,
            "root": str(self.root),
            "git_dir": str(self.git_dir),
            "common_dir": str(self.common_dir),
            "branch": self.branch,
            "head": self.head,
            "detached_head": self.detached_head,
            "bare": self.bare,
            "linked_worktree": self.linked_worktree,
            "submodule": self.submodule,
            "unborn": self.unborn,
            "has_changes": self.has_changes,
        }


def _has_git_marker(directory: Path) -> bool:
    marker = directory / ".git"
    return marker.is_dir() or marker.is_file()


def find_git_root(start: Path, *, max_up: int = MAX_WALK_UP) -> Optional[Path]:
    """Walk up from `start` to the nearest directory containing a `.git` marker.

    A `.git` may be a directory (normal / bare-with-worktree) or a FILE
    (linked worktree / submodule). A bare repository has no `.git` marker at its
    top level; it is detected separately by `is_bare_git_dir`.
    """
    current = Path(os.path.realpath(start))
    if current.is_file():
        current = current.parent
    for _ in range(max_up):
        if _has_git_marker(current):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def is_bare_git_dir(path: Path) -> bool:
    """Whether `path` is itself a bare git directory (HEAD + objects + refs)."""
    candidate = Path(os.path.realpath(path))
    if not candidate.is_dir():
        return False
    return (
        (candidate / "HEAD").is_file()
        and (candidate / "objects").is_dir()
        and (candidate / "refs").is_dir()
    )


def _one_line(result: Any) -> Optional[str]:
    if not getattr(result, "ok", False):
        return None
    text = result.stdout.strip().splitlines()
    return text[0] if text else None


def _bool_line(result: Any) -> Optional[bool]:
    line = _one_line(result)
    if line is None:
        return None
    return line.strip().casefold() == "true"


def _probe(cwd: Path) -> dict[str, Optional[str]]:
    """The five discovery facts, with a bare-repo fallback for the combined probe."""
    combined = run(cwd, "discover")
    if combined.ok:
        lines = combined.stdout.strip().splitlines()
        if len(lines) >= 5:
            return {
                "toplevel": lines[0].strip(),
                "git_dir": lines[1].strip(),
                "bare": lines[2].strip().casefold(),
                "inside_git_dir": lines[3].strip().casefold(),
                "inside_work_tree": lines[4].strip().casefold(),
            }
    # The combined probe aborts inside a bare repo ("must be run in a work tree").
    bare = _bool_line(run(cwd, "is_bare"))
    git_dir = _one_line(run(cwd, "git_dir"))
    if bare is None and git_dir is None:
        return {}
    return {
        "toplevel": None,
        "git_dir": git_dir,
        "bare": "true" if bare else "false",
        "inside_git_dir": None,
        "inside_work_tree": "false" if bare else None,
    }


def _detect_submodule(git_dir: Path, top: Path) -> bool:
    """A submodule's git dir lives under the parent's `.git/modules/`."""
    lowered = str(git_dir).replace("\\", "/").casefold()
    if "/.git/modules/" in lowered:
        return True
    # A `.git` FILE whose target path contains `/modules/` is a submodule too.
    marker = top / ".git"
    if marker.is_file():
        try:
            content = marker.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return False
        if "modules" in content.replace("\\", "/").casefold():
            return True
    return False


def _is_linked_worktree(git_dir: Path, common_dir: Path) -> bool:
    try:
        return os.path.realpath(git_dir) != os.path.realpath(common_dir)
    except OSError:
        return False


def discover(start: Path | str = ".") -> Optional[Repository]:
    """Discover the repository enclosing `start`, or None when there is none.

    Never raises for a non-repository: returns None so the caller reports
    `NOT_A_REPOSITORY` with its own structured failure.
    """
    path = Path(start)
    root = find_git_root(path)
    if root is None:
        # A bare repository given directly as the start path.
        candidate = Path(os.path.realpath(path))
        if is_bare_git_dir(candidate):
            root = candidate
        else:
            return None

    facts = _probe(root)
    if not facts:
        return None

    bare = facts.get("bare") == "true"
    git_dir_raw = facts.get("git_dir")
    if not git_dir_raw:
        return None
    git_dir = Path(os.path.realpath(git_dir_raw))

    if bare:
        top = git_dir
    else:
        top_raw = facts.get("toplevel") or str(root)
        top = Path(os.path.realpath(top_raw))

    # common dir (shared by linked worktrees); fall back to git_dir.
    common_dir = git_dir
    common = run(root, "common_dir")
    if common.ok:
        line = _one_line(common)
        if line:
            common_dir = Path(os.path.realpath(line))

    branch_result = run(root, "head_ref")
    branch = _one_line(branch_result) if branch_result.ok else None
    detached = branch == "HEAD"
    # On an UNBORN branch `rev-parse --abbrev-ref HEAD` fails; the symbolic ref
    # still names the branch the first commit will land on.
    if branch is None and not bare:
        symbolic = run(root, "symbolic_ref_head")
        if symbolic.ok:
            named = _one_line(symbolic)
            if named and named != "HEAD":
                branch = named.replace("refs/heads/", "")
                detached = False

    head_result = run(root, "head_sha")
    head = _one_line(head_result) if head_result.ok else None
    unborn = head is None and not bare

    status = run(root, "status")
    has_changes = False
    if status.ok:
        # Any porcelain-v2 line that is not a `# branch.*` header means dirty.
        for line in status.stdout.splitlines():
            if line and not line.startswith("#"):
                has_changes = True
                break

    return Repository(
        root=top,
        git_dir=git_dir,
        common_dir=common_dir,
        branch=None if detached else branch,
        head=head,
        detached_head=detached,
        bare=bare,
        linked_worktree=_is_linked_worktree(git_dir, common_dir),
        submodule=_detect_submodule(git_dir, top),
        unborn=unborn,
        has_changes=has_changes,
        id="git_" + _digest(str(top)),
    )


def _digest(text: str) -> str:
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def require_repository(start: Path | str = ".") -> Repository:
    """Like `discover`, but raises a structured `GitError` when absent."""
    repo = discover(start)
    if repo is None:
        raise GitError(
            errors.NOT_A_REPOSITORY,
            "This folder is not set up to track versions yet.",
        )
    return repo


def repository_info(repo: Repository) -> dict[str, Any]:
    """The discovery record plus the active multi-step operation, if any."""
    from .state import active_operation  # noqa: PLC0415

    info = repo.to_dict()
    op = active_operation(repo)
    info["operation"] = op.to_dict() if op is not None else None
    return info


__all__ = [
    "MAX_WALK_UP",
    "Repository",
    "discover",
    "find_git_root",
    "is_bare_git_dir",
    "repository_info",
    "require_repository",
]
