"""Eclipse's own state inside a project — invisible to that project's git.

Every build writes into `<project>/.black-eclipse/` (worktrees, capability drafts,
rollbacks). In Eclipse's own repo that directory is already ignored, but a user's
repo has no such rule, so the first build would leave untracked files in their
`git status`.

The fix is a self-ignoring directory: `.black-eclipse/.gitignore` containing `*`.
Git applies it to everything inside, including itself, without touching the
project's root `.gitignore`. Nothing outside the directory is modified.
"""

from __future__ import annotations

from pathlib import Path

STATE_RELPATH = ".black-eclipse"
_IGNORE_TEXT = "*\n"


def ensure_state_dir(root: Path | str | None) -> Path | None:
    """Create `<root>/.black-eclipse/` and make git ignore it. Best-effort."""
    if root is None:
        return None
    base = Path(root) / STATE_RELPATH
    try:
        base.mkdir(parents=True, exist_ok=True)
        ignore = base / ".gitignore"
        if not ignore.exists():
            ignore.write_text(_IGNORE_TEXT, encoding="utf-8")
    except OSError:
        return base if base.is_dir() else None
    return base


__all__ = ["STATE_RELPATH", "ensure_state_dir"]
