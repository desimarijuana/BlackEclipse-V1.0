"""Unified-diff parsing and selective-hunk reconstruction.

An agent that changes several things in one file must be able to stage only the
hunks it intends. This module parses a unified diff into files and hunks and
re-renders a patch containing a chosen subset, so `git_apply_cached` can stage
partial changes without a TTY (git's `add -p`.

It also enforces the ONE path-safety rule for an applied patch: every file header
must be a repository-relative path with no `..` component and no absolute or
drive-letter target. `git apply` refuses to write outside the tree on its own;
this is the defense-in-depth check so a malformed/hostile patch is rejected
before git sees it.

Pure functions only. Nothing here runs a process.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .errors import INVALID_ARGUMENT, UNSAFE_COMMAND, GitError

MAX_PATCH_CHARS = 2_000_000
MAX_HUNKS = 2_000

# `diff --git a/<old> b/<new>`; the paths are quoted when they contain specials.
_DIFF_HEADER = re.compile(r"^diff --git (?P<a>.+) (?P<b>.+)$")
_HUNK_HEADER = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<context>.*)$")
_MINUS = re.compile(r"^--- (?P<path>.+)$")
_PLUS = re.compile(r"^\+\+\+ (?P<path>.+)$")
_DRIVE = re.compile(r"^[A-Za-z]:")


def _unquote(path: str) -> str:
    text = path.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    # git quotes a tab/newline as \t/\n; those never appear in a real path here.
    return text


def _is_safe_path(path: str) -> bool:
    text = _unquote(path).replace("\\", "/")
    if not text or text == "/dev/null":
        return True
    if "\x00" in text:
        return False
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    if text.startswith("/") or _DRIVE.match(text):
        return False
    if ".." in text.split("/"):
        return False
    return bool(text)


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    context: str
    lines: list[str] = field(default_factory=list)

    def header(self) -> str:
        old = f"-{self.old_start}" + (f",{self.old_count}" if self.old_count != 1 else "")
        new = f"+{self.new_start}" + (f",{self.new_count}" if self.new_count != 1 else "")
        return f"@@ {old} {new} @@{self.context}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "oldStart": self.old_start, "oldCount": self.old_count,
            "newStart": self.new_start, "newCount": self.new_count,
            "header": self.header(), "preview": "\n".join(self.lines[:40]),
        }


@dataclass
class FileDiff:
    old_path: str
    new_path: str
    header_lines: list[str] = field(default_factory=list)
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The post-change path (from the `b/` side), which is what a caller selects by."""
        return _clean_path(self.new_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "oldPath": _clean_path(self.old_path),
            "hunks": [h.to_dict() for h in self.hunks],
        }


def _clean_path(path: str) -> str:
    text = _unquote(path).replace("\\", "/")
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    return text


def parse_unified_diff(patch: str) -> list[FileDiff]:
    """Split a unified diff into files and hunks. Raises on an unsafe path."""
    if not isinstance(patch, str) or not patch.strip():
        raise GitError(INVALID_ARGUMENT, "There was no change to apply.")
    if len(patch) > MAX_PATCH_CHARS:
        raise GitError(INVALID_ARGUMENT, "That change is too large to apply at once.")
    files: list[FileDiff] = []
    current: Optional[FileDiff] = None
    current_hunk: Optional[Hunk] = None
    total_hunks = 0

    for line in patch.split("\n"):
        header = _DIFF_HEADER.match(line)
        if header:
            if current is not None:
                files.append(current)
            a_path, b_path = header.group("a"), header.group("b")
            if not (_is_safe_path(a_path) and _is_safe_path(b_path)):
                raise GitError(UNSAFE_COMMAND, "That change names a file outside the project.")
            current = FileDiff(old_path=_unquote(a_path), new_path=_unquote(b_path), header_lines=[line])
            current_hunk = None
            continue
        if current is None:
            # Leading noise before the first `diff --git` is dropped.
            continue
        hunk_header = _HUNK_HEADER.match(line)
        if hunk_header:
            if current_hunk is not None:
                current.hunks.append(current_hunk)
                total_hunks += 1
            if total_hunks >= MAX_HUNKS:
                raise GitError(INVALID_ARGUMENT, "That change has too many parts.")
            current_hunk = Hunk(
                old_start=int(hunk_header.group("old_start")),
                old_count=int(hunk_header.group("old_count") or 1),
                new_start=int(hunk_header.group("new_start")),
                new_count=int(hunk_header.group("new_count") or 1),
                context=hunk_header.group("context") or "",
            )
            continue
        if current_hunk is not None:
            # A hunk body runs until the next `diff --git`/`@@`/EOF. A blank line
            # inside a hunk is a context line (git emits a leading space); a truly
            # empty line only appears in `\ No newline at end of file` handling.
            current_hunk.lines.append(line)
        else:
            minus = _MINUS.match(line)
            plus = _PLUS.match(line)
            if minus or plus:
                target = (minus or plus).group("path")
                if not _is_safe_path(target):
                    raise GitError(UNSAFE_COMMAND, "That change names a file outside the project.")
            current.header_lines.append(line)
    if current_hunk is not None and current is not None:
        current.hunks.append(current_hunk)
        total_hunks += 1
    if current is not None:
        files.append(current)
    if not files:
        raise GitError(INVALID_ARGUMENT, "There was no readable change to apply.")
    return files


def render_selected(files: list[FileDiff], selection: dict[str, list[int]]) -> str:
    """Render a patch containing only the selected hunks.

    `selection` maps a file path to a list of 0-based hunk indexes. A path with
    `-1` selects every hunk in that file. Files not named are omitted.
    """
    chunks: list[str] = []
    for file in files:
        wanted = selection.get(file.path)
        if wanted is None:
            continue
        chosen = file.hunks if -1 in wanted else [file.hunks[i] for i in wanted if 0 <= i < len(file.hunks)]
        if not chosen:
            continue
        # Only new-file headers (`--- a/x`/`+++ b/x`/`new file mode`) are needed;
        # `diff --git` + `---`/`+++` + the selected hunks is a valid patch.
        body = [file.header_lines[0]] if file.header_lines else []
        head = [ln for ln in file.header_lines if ln.startswith(("--- ", "+++ ", "new file", "deleted file", "old mode", "new mode", "similarity", "rename", "copy"))]
        body.extend(head)
        for hunk in chosen:
            body.append(hunk.header())
            body.extend(hunk.lines)
        chunks.append("\n".join(body))
    if not chunks:
        raise GitError(INVALID_ARGUMENT, "No hunks were selected to apply.")
    return "\n".join(chunks) + "\n"


def summarize(files: list[FileDiff]) -> dict[str, Any]:
    return {
        "files": [
            {"path": f.path, "hunks": len(f.hunks), "hunkIndexes": list(range(len(f.hunks)))}
            for f in files
        ],
        "fileCount": len(files),
        "hunkCount": sum(len(f.hunks) for f in files),
    }


__all__ = [
    "FileDiff",
    "Hunk",
    "MAX_HUNKS",
    "MAX_PATCH_CHARS",
    "parse_unified_diff",
    "render_selected",
    "summarize",
]
