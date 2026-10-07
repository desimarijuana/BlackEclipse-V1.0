"""Automated interactive rebase — a plan, not a terminal session.

`git rebase -i` normally opens an editor. This module builds a machine sequence
editor invocation (no TTY) from a structured plan, so an agent can squash, fixup,
drop, reorder, reword or edit commits deterministically.

    plan = [
        {"commit": "abc123", "action": "squash"},
        {"commit": "def456", "action": "reword", "message": "new subject"},
        {"commit": "ghi789", "action": "drop"},
    ]

`reword`/`edit` write the new message through `GIT_EDITOR` (a file the plan
provides), so no editor is ever opened. A partial plan never drops a commit: the
sequence editor appends every unnamed commit as a pick.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from .errors import INVALID_ARGUMENT, GitError

VALID_ACTIONS = ("pick", "reword", "edit", "squash", "fixup", "drop")
MAX_ACTIONS = 500


def build_env(plan: list[dict[str, Any]], queue_dir: str) -> dict[str, str]:
    """The environment for the rebase: the plan + a no-TTY sequence editor.

    The sequence-editor command is quoted for the shell git uses to spawn it, and
    the paths use forward slashes so Windows backslashes survive that shell. The
    sequence editor authors a message queue in `queue_dir`; the message editor
    (`_message_editor.py`) consumes it in the same order, so `reword`/`edit` need
    no terminal.
    """
    python = str(sys.executable).replace("\\", "/")
    editor = str(Path(__file__).with_name("_sequence_editor.py")).replace("\\", "/")
    msg_editor = str(Path(__file__).with_name("_message_editor.py")).replace("\\", "/")
    return {
        "BLACK_ECLIPSE_REBASE_PLAN": json.dumps({"actions": plan}),
        "BLACK_ECLIPSE_REBASE_QUEUE_DIR": str(queue_dir).replace("\\", "/"),
        # git runs each editor through a shell; quote the paths and use forward
        # slashes so a Windows path is not eaten as escapes.
        "GIT_SEQUENCE_EDITOR": f'"{python}" "{editor}"',
        "GIT_EDITOR": f'"{python}" "{msg_editor}"',
    }


def validate_actions(actions: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Validate the plan shape. Raises a structured `GitError` on a bad entry."""
    if not actions:
        raise GitError(INVALID_ARGUMENT, "An automated rebase needs at least one step.")
    if len(actions) > MAX_ACTIONS:
        raise GitError(INVALID_ARGUMENT, "That rebase plan has too many steps.")
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(actions):
        if not isinstance(raw, dict):
            raise GitError(INVALID_ARGUMENT, f"Step {index + 1} is not a valid action.")
        commit = str(raw.get("commit") or "").strip()
        action = str(raw.get("action") or "").strip().casefold()
        if not commit:
            raise GitError(INVALID_ARGUMENT, f"Step {index + 1} does not name a commit.")
        if action not in VALID_ACTIONS:
            raise GitError(INVALID_ARGUMENT, f"'{action}' is not a usable rebase action.")
        entry: dict[str, Any] = {"commit": commit, "action": action}
        message = raw.get("message")
        if message is not None:
            entry["message"] = str(message)[:10_000]
        out.append(entry)
    return out


def messages_by_commit(actions: list[dict[str, Any]]) -> dict[str, str]:
    return {a["commit"]: a["message"] for a in actions if a.get("message")}


__all__ = [
    "MAX_ACTIONS",
    "VALID_ACTIONS",
    "build_env",
    "messages_by_commit",
    "validate_actions",
]