"""Git awareness — additive, never a hard dependency.

When the workspace is a git checkout, this reports each path's status:
modified / untracked / staged / deleted / renamed, plus the branch and HEAD.
When git is absent (or the folder is not a checkout), every function returns an
honest `{"available": False, "reason": ...}` — the filesystem subsystem works
identically in a Git repository and a plain directory.

Every child process is ONE fixed, argument-free argv (the same discipline as
`code/workspace.py`); no model-supplied text ever reaches git. This module only
READS — it never stages, commits or checks anything out.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from .. import policy

GIT_TIMEOUT_S = 10
GIT_OUTPUT_CAP = 4 * 1024 * 1024
MAX_GIT_ENTRIES = 5_000

# The closed argv set. `status` reads the working tree; `head`/`branch` name the
# current revision. No argument is model-supplied.
GIT_ARGV: dict[str, tuple[str, ...]] = {
    "status": ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
    "head": ("git", "rev-parse", "HEAD"),
    "branch": ("git", "rev-parse", "--abbrev-ref", "HEAD"),
    "available": ("git", "--version"),
}

# porcelain-v1 status letters → the normalized state.
_STATE_BY_CODE = {
    "M": "modified", "T": "modified", "A": "staged", "D": "deleted",
    "R": "renamed", "C": "copied", "U": "conflicted", "?": "untracked",
}


def _env() -> dict[str, str]:
    return {name: os.environ[name] for name in policy.SECRET_ENV_ALLOWLIST if name in os.environ}


def _run(root: Path, kind: str) -> dict[str, Any]:
    argv = GIT_ARGV.get(kind)
    if argv is None:
        return {"available": False, "reason": f"unknown git read {kind!r}"}
    try:
        completed = subprocess.run(
            list(argv), cwd=str(root), env=_env(), shell=False,
            capture_output=True, timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": f"git is not available ({type(exc).__name__})"}
    if completed.returncode != 0:
        return {"available": False, "reason": "this folder is not a git checkout Eclipse can read"}
    return {"available": True, "stdout": completed.stdout[:GIT_OUTPUT_CAP]}


def git_available(root: Path) -> bool:
    return bool(_run(root, "available").get("available"))


def _classify(record: str) -> Optional[dict[str, Any]]:
    """One porcelain record → `{path, indexState, worktreeState, state}`."""
    if len(record) < 4:
        return None
    index_code, worktree_code = record[0], record[1]
    path = record[3:]
    index_state = None if index_code == " " else _STATE_BY_CODE.get(index_code, "modified")
    worktree_state = None if worktree_code == " " else _STATE_BY_CODE.get(worktree_code, "modified")
    state = worktree_state or index_state or "untracked" if index_code == "?" else (worktree_state or index_state or "modified")
    if index_code == "?" and worktree_code == "?":
        state = "untracked"
    return {
        "path": path.replace("\\", "/"),
        "indexState": index_state,
        "worktreeState": worktree_state,
        "state": state,
    }


def status(root: Path) -> dict[str, Any]:
    """Every dirty path with its normalized state, or an honest unavailability."""
    raw = _run(root, "status")
    if not raw.get("available"):
        return {"available": False, "reason": raw.get("reason", "git is unavailable")}
    entries: list[dict[str, Any]] = []
    parts = raw["stdout"].split(b"\x00")
    index = 0
    while index < len(parts):
        record = parts[index]
        index += 1
        if not record:
            continue
        text = record.decode("utf-8", "replace")
        entry = _classify(text)
        if entry is None:
            continue
        # A rename/copy consumes the NEXT NUL field as the source path.
        if entry["indexState"] in ("renamed", "copied") and index < len(parts):
            source = parts[index].decode("utf-8", "replace")
            index += 1
            if source:
                entry["from"] = source.replace("\\", "/")
        entries.append(entry)
        if len(entries) >= MAX_GIT_ENTRIES:
            break
    return {"available": True, "entries": entries, "count": len(entries)}


def status_for(root: Path, rel_path: str) -> Optional[dict[str, Any]]:
    """The git state of ONE path, or None (clean / not in a checkout)."""
    normalized = rel_path.replace("\\", "/").lstrip("./")
    result = status(root)
    if not result.get("available"):
        return None
    for entry in result["entries"]:
        if entry["path"] == normalized:
            return entry
    return None


def revision(root: Path) -> dict[str, Any]:
    """The current HEAD and branch, or an honest unavailability."""
    head = _run(root, "head")
    branch = _run(root, "branch")
    return {
        "available": bool(head.get("available")),
        "head": head.get("stdout", b"").decode("utf-8", "replace").strip() if head.get("available") else None,
        "branch": branch.get("stdout", b"").decode("utf-8", "replace").strip() if branch.get("available") else None,
        "reason": head.get("reason") if not head.get("available") else None,
    }


def summary(root: Path) -> dict[str, Any]:
    """A bounded overview: availability, revision, and counts per state."""
    result = status(root)
    if not result.get("available"):
        return {"status": "ok", "available": False, "reason": result.get("reason")}
    counts: dict[str, int] = {}
    for entry in result["entries"]:
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1
    rev = revision(root)
    return {
        "status": "ok",
        "available": True,
        "head": rev.get("head"),
        "branch": rev.get("branch"),
        "dirty": len(result["entries"]),
        "counts": counts,
        "entries": result["entries"][:200],
        "truncated": len(result["entries"]) > 200,
    }


__all__ = [
    "GIT_ARGV",
    "MAX_GIT_ENTRIES",
    "git_available",
    "revision",
    "status",
    "status_for",
    "summary",
]
