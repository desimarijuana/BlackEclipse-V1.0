"""The machine sequence editor for `git rebase -i` (driven, never interactive).

Git invokes this with the todo file path as `argv[1]`. The edit plan is JSON in
`BLACK_ECLIPSE_REBASE_PLAN`; this script rewrites the todo so the rebase performs
exactly the planned picks/reorders/drops/squashes/fixups/rewords with NO terminal.

Safety: a commit not named in the plan is APPENDED as `pick`, so a partial plan
never silently drops a commit. An unknown commit id is ignored the same way.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _split(line: str) -> tuple[str, str, str]:
    """`pick <sha> <subject>` → (action, sha, rest)."""
    parts = line.split(" ", 2)
    if len(parts) < 2:
        return ("", "", "")
    return (parts[0], parts[1], parts[2] if len(parts) > 2 else "")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 1
    todo_path = argv[1]
    try:
        plan = json.loads(os.environ.get("BLACK_ECLIPSE_REBASE_PLAN", "{}"))
    except ValueError:
        plan = {}
    actions = plan.get("actions") or []

    with open(todo_path, encoding="utf-8") as handle:
        original = handle.readlines()

    # Index the todo's real commits by sha.
    by_sha: dict[str, str] = {}
    ordered: list[str] = []
    for line in original:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        action, sha, rest = _split(line.rstrip("\n"))
        if action in ("pick", "p", "reword", "r", "edit", "e", "squash", "s", "fixup", "f", "drop", "d") and sha:
            by_sha[sha] = line if line.endswith("\n") else line + "\n"
            ordered.append(sha)

    used: set[str] = set()
    queue_dir = os.environ.get("BLACK_ECLIPSE_REBASE_QUEUE_DIR")
    queue: list[str] = []

    # Resolve each plan entry to a real sha once.
    resolved: list[tuple[str, str, str]] = []  # (sha, verb, message)
    for entry in actions:
        target = _match_sha(by_sha, str(entry.get("commit") or ""))
        if target is None or target in used:
            continue
        used.add(target)
        verb = _verb(str(entry.get("action") or "pick"))
        resolved.append((target, verb, str(entry.get("message") or "")))

    plan_by_sha = {sha: (verb, message) for sha, verb, message in resolved}
    names_all = len(used) == len(ordered)

    # Emit. If the plan names EVERY commit it may define the final ORDER
    # (reorder); a PARTIAL plan never reorders — unnamed commits stay in their
    # original relative position and only take an action where named.
    if names_all and resolved:
        emission_order = [sha for sha, _, _ in resolved]
    else:
        emission_order = ordered

    out: list[str] = []
    for sha in emission_order:
        verb, message = plan_by_sha.get(sha, ("pick", ""))
        _, _, rest = _split(by_sha[sha].rstrip("\n"))
        out.append(f"{verb} {sha}{(' ' + rest) if rest else ''}\n")
        if queue_dir and verb in ("reword", "edit"):
            queue.append(message)
    if not out and ordered:
        out = [by_sha[sha] for sha in ordered]

    if queue_dir:
        _write_queue(queue_dir, queue)

    with open(todo_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(out if out else original)
    return 0


def _write_queue(queue_dir: str, queue: list[str]) -> None:
    try:
        base = Path(queue_dir)
        base.mkdir(parents=True, exist_ok=True)
        for index, message in enumerate(queue):
            (base / f"msg_{index}.txt").write_text(message, encoding="utf-8", newline="\n")
        (base / "counter").write_text("0", encoding="utf-8")
    except OSError:
        pass


def _match_sha(by_sha: dict[str, str], commit: str) -> str | None:
    text = str(commit).strip()
    if not text:
        return None
    if text in by_sha:
        return text
    # The plan may pass a FULL 40-char sha while git's todo lists a short one (or
    # vice versa), so match when EITHER is a prefix of the other.
    for sha in by_sha:
        if sha.startswith(text) or text.startswith(sha):
            return sha
    return None


def _verb(action: str) -> str:
    return {
        "pick": "pick", "p": "pick",
        "reword": "reword", "r": "reword",
        "edit": "edit", "e": "edit",
        "squash": "squash", "s": "squash",
        "fixup": "fixup", "f": "fixup",
        "drop": "drop", "d": "drop",
    }.get(action, "pick")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
