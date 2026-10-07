"""The Git operation state machine.

A merge/rebase/cherry-pick/revert/bisect can remain ACTIVE after a failure: git
leaves sentinel files in the git dir (MERGE_HEAD, rebase-merge/, CHERRY_PICK_HEAD,
REVERT_HEAD, BISECT_LOG). This module detects that state from the repository
itself on every call — it never trusts a cached flag — so the agent always knows
whether a multi-step operation is open and what the next legal action is.

It also contains the conflict-block parser: it reads Git's `<<<<<<<`/`=======`/
`>>>>>>>` markers into structured `{start_line, end_line, ours, theirs}` blocks so
the model can reason about ONE conflict at a time instead of a whole file.

Nothing here decides policy or runs git; it reads files under the git dir and the
worktree.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .executor import run
from .repository import Repository

# Sentinel files (path relative to the git dir) → operation name.
_MERGE_SENTINELS = ("MERGE_HEAD",)
_REBASE_DIRS = ("rebase-merge", "rebase-apply")
_CHERRY_SENTINEL = "CHERRY_PICK_HEAD"
_REVERT_SENTINEL = "REVERT_HEAD"
_BISECT_SENTINEL = "BISECT_LOG"

# Operations and the next action a caller should take.
_IN_PROGRESS = "IN_PROGRESS"
_CONFLICTED = "CONFLICTED"
_COMPLETED = "COMPLETED"
_ABORTED = "ABORTED"

_ABORT: dict[str, str] = {
    "merge": "merge_abort",
    "rebase": "rebase_abort",
    "cherry_pick": "cherry_pick_abort",
    "revert": "revert_abort",
    "bisect": "git_bisect_reset",
}
_CONTINUE: dict[str, str] = {
    "merge": "merge_continue",
    "rebase": "rebase_continue",
    "cherry_pick": "cherry_pick_continue",
    "revert": "revert_continue",
    "bisect": "git_bisect_good",
}


@dataclass(frozen=True)
class OperationState:
    """The active (or absent) multi-step operation."""

    operation: Optional[str]      # merge|rebase|cherry_pick|revert|bisect|None
    status: str                   # IN_PROGRESS|CONFLICTED|COMPLETED|ABORTED|NONE
    conflicts: bool = False
    conflicted_files: tuple[str, ...] = ()
    can_continue: bool = False
    can_abort: bool = False
    can_skip: bool = False
    head_name: Optional[str] = None
    onto: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.operation is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "conflicts": self.conflicts,
            "conflictedFiles": list(self.conflicted_files),
            "canContinue": self.can_continue,
            "canAbort": self.can_abort,
            "canSkip": self.can_skip,
            "headName": self.head_name,
            "onto": self.onto,
        }


def _git_dir_path(repo: Repository) -> Path:
    """The git dir that holds per-operation state (linked worktree aware)."""
    return repo.git_dir


def _read_first(path: Path, limit: int = 200) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()[:limit]
    except OSError:
        return ""


def _conflicted_files(repo: Repository) -> tuple[str, ...]:
    """Unmerged paths from `git diff --name-only --diff-filter=U -z`."""
    result = run(repo.root, "unmerged")
    if not result.ok:
        return ()
    files = [f.replace("\\", "/") for f in result.stdout.split("\x00") if f.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return tuple(out)


def active_operation(repo: Repository) -> Optional[OperationState]:
    """Detect the active multi-step operation, or None when the tree is idle."""
    git_dir = _git_dir_path(repo)
    conflicted = _conflicted_files(repo)
    has_conflicts = bool(conflicted)

    operation: Optional[str] = None
    head_name: Optional[str] = None
    onto: Optional[str] = None
    can_skip = False

    if (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir():
        operation = "rebase"
        head_file = git_dir / "rebase-merge" / "head-name"
        if head_file.exists():
            head_name = _read_first(head_file).replace("refs/heads/", "")
        onto_file = git_dir / "rebase-merge" / "onto"
        if onto_file.exists():
            onto = _read_first(onto_file)
        can_skip = True
    elif (git_dir / "rebase-apply").is_dir():
        operation = "rebase"
        can_skip = True
    elif (git_dir / "MERGE_HEAD").exists():
        operation = "merge"
        head_name = _read_first(git_dir / "MERGE_MSG") or None
    elif (git_dir / "CHERRY_PICK_HEAD").exists():
        operation = "cherry_pick"
    elif (git_dir / "REVERT_HEAD").exists():
        operation = "revert"
    elif (git_dir / "BISECT_LOG").exists():
        operation = "bisect"
    elif (git_dir / "sequencer").is_dir():
        # A multi-commit cherry-pick/revert in progress without a *_HEAD yet.
        operation = "cherry_pick"

    if operation is None:
        return None

    status = _CONFLICTED if has_conflicts else _IN_PROGRESS
    return OperationState(
        operation=operation,
        status=status,
        conflicts=has_conflicts,
        conflicted_files=conflicted,
        can_continue=not has_conflicts,
        can_abort=True,
        can_skip=can_skip,
        head_name=head_name,
        onto=onto,
    )


def abort_hint(repo: Repository) -> Optional[str]:
    """The `git_*_abort` tool name for the active operation, or None."""
    state = active_operation(repo)
    if state is None or state.operation is None:
        return None
    return _ABORT.get(state.operation)


def continue_hint(repo: Repository) -> Optional[str]:
    state = active_operation(repo)
    if state is None or state.operation is None:
        return None
    return _CONTINUE.get(state.operation)


# ── Conflict markers ───────────────────────────────────────────────────────────

_CONFLICT_START = re.compile(r"^<{7}(?: (.*))?$")
_CONFLICT_BASE = re.compile(r"^\|{7}(?: (.*))?$")
_CONFLICT_SEP = re.compile(r"^={7}$")
_CONFLICT_END = re.compile(r"^>{7}(?: (.*))?$")

MAX_CONFLICT_BLOCKS = 500
MAX_CONFLICT_BYTES = 2_000_000


@dataclass
class ConflictBlock:
    start_line: int
    end_line: int
    ours_label: str
    theirs_label: str
    ours: str
    theirs: str
    base: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "ours": self.ours,
            "theirs": self.theirs,
            "ours_label": self.ours_label,
            "theirs_label": self.theirs_label,
        }
        if self.base is not None:
            out["base"] = self.base
        return out


def parse_conflict_markers(text: str) -> list[ConflictBlock]:
    """Parse conflict blocks from a file's text. Pure; bounded by the caller."""
    lines = text.split("\n")
    blocks: list[ConflictBlock] = []
    i = 0
    n = len(lines)
    while i < n and len(blocks) < MAX_CONFLICT_BLOCKS:
        m = _CONFLICT_START.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        ours_label = (m.group(1) or "").strip()
        ours: list[str] = []
        base: Optional[list[str]] = None
        theirs: list[str] = []
        i += 1
        mode = "ours"
        closed = False
        while i < n:
            line = lines[i]
            if _CONFLICT_BASE.match(line):
                mode = "base"
                if base is None:
                    base = []
                i += 1
                continue
            if _CONFLICT_SEP.match(line):
                mode = "theirs"
                i += 1
                continue
            end = _CONFLICT_END.match(line)
            if end:
                blocks.append(ConflictBlock(
                    start_line=start + 1,
                    end_line=i + 1,
                    ours_label=ours_label,
                    theirs_label=(end.group(1) or "").strip(),
                    ours="\n".join(ours),
                    theirs="\n".join(theirs),
                    base="\n".join(base) if base is not None else None,
                ))
                closed = True
                i += 1
                break
            if mode == "ours":
                ours.append(line)
            elif mode == "base" and base is not None:
                base.append(line)
            else:
                theirs.append(line)
            i += 1
        if not closed:
            # An unterminated block: report what we have so it is never hidden.
            blocks.append(ConflictBlock(
                start_line=start + 1, end_line=n,
                ours_label=ours_label, theirs_label="",
                ours="\n".join(ours), theirs="\n".join(theirs),
                base="\n".join(base) if base is not None else None,
            ))
    return blocks


def read_conflicts(repo: Repository, rel_path: str) -> list[dict[str, Any]]:
    """Parse conflict blocks from `rel_path` (a worktree-relative path)."""
    target = (repo.root / rel_path).resolve()
    try:
        target.relative_to(repo.root.resolve())
    except ValueError:
        return []
    if not target.is_file():
        return []
    try:
        size = target.stat().st_size
    except OSError:
        return []
    if size > MAX_CONFLICT_BYTES:
        return []
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [b.to_dict() for b in parse_conflict_markers(text)]


__all__ = [
   	"ConflictBlock",
    "MAX_CONFLICT_BLOCKS",
    "OperationState",
    "abort_hint",
    "active_operation",
    "continue_hint",
    "parse_conflict_markers",
    "read_conflicts",
]
