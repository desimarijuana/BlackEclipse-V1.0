"""Unified-diff generation — one place the agent's diff preview is produced.

Deterministic, content-exact, and bounded. Used by:
  * a dry-run to show what WOULD change without writing;
  * `multi_file_patch` / `apply_diff` to report the change that landed;
  * the UI event stream (`code.fs.*`) to show a diff.

Only the text is produced here; nothing is written.
"""

from __future__ import annotations

import difflib
from typing import Optional

MAX_DIFF_CHARS = 200_000


def unified_diff(
    old: str,
    new: str,
    *,
    path: str = "file",
    context: int = 3,
    max_chars: int = MAX_DIFF_CHARS,
) -> dict[str, object]:
    """A unified diff between `old` and `new`, with honest truncation.

    Returns `{diff, additions, deletions, truncated, hasChanges}`. An identical
    pair yields an empty diff and `hasChanges=False`.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    if old == new:
        return {"diff": "", "additions": 0, "deletions": 0, "truncated": False, "hasChanges": False}
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}", n=max(0, int(context)),
    ))
    text = "".join(diff_lines)
    additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n[DIFF TRUNCATED: the change is larger than the preview]\n"
    return {
        "diff": text,
        "additions": additions,
        "deletions": deletions,
        "truncated": truncated,
        "hasChanges": True,
    }


def preview_for(path: str, before: Optional[str], after: Optional[str]) -> dict[str, object]:
    """A dry-run preview record for one file (create/modify/delete)."""
    if before is None and after is not None:
        result = unified_diff("", after, path=path)
        return {"path": path, "operation": "create", **result}
    if before is not None and after is None:
        result = unified_diff(before, "", path=path)
        return {"path": path, "operation": "delete", **result}
    result = unified_diff(before or "", after or "", path=path)
    return {"path": path, "operation": "modify", **result}


__all__ = ["MAX_DIFF_CHARS", "preview_for", "unified_diff"]
