"""Machine-readable Git output parsers.

Every parser consumes the fixed, machine format the catalog requests — never
human-readable porcelain that could change between Git versions. The parsers
are pure functions of bytes/str and are unit-tested without a repository.

Formats handled:

  * status      — `git status --porcelain=v2 -z --branch`  → structured state
  * log         — `--format=%H%x00…%x01`                   → commit records
  * name-status — `git diff --name-status -z`             → path/status pairs
  * numstat     — `git diff --numstat -z`                 → per-file counts
  * blame       — `git blame --line-porcelain`            → per-line attribution
  * worktree    — `git worktree list --porcelain`         → worktree records
  * branch list — `--format=…%00…`                        → branch records
  * reflog      — `--format=%H%x00…`                      → reflog entries
"""

from __future__ import annotations

from typing import Any, Optional

# ── Status ────────────────────────────────────────────────────────────────────

# porcelain v2 XY letter → normalized state. `.` means "no change".
_X_MEANING = {
    "M": "modified", "T": "modified", "A": "added", "D": "deleted",
    "R": "renamed", "C": "copied", "U": "conflicted", "?": "untracked",
    "!": "ignored",
}


def _state(letter: str) -> Optional[str]:
    if not letter or letter == ".":
        return None
    return _X_MEANING.get(letter, "modified")


def _is_conflict(xy: str) -> bool:
    # v2 unmerged codes: DD AU UD UA DU AA UU.
    return xy in ("DD", "AU", "UD", "UA", "DU", "AA", "UU")


def parse_status(raw: str) -> dict[str, Any]:
    """Parse `status --porcelain=v2 -z --branch` into structured state.

    Handles modified/added/deleted/renamed/copied/untracked/ignored, staged vs
    unstaged, conflicts, branch tracking, ahead/behind, and detached HEAD.
    """
    branch: Optional[str] = None
    oid: Optional[str] = None
    upstream: Optional[str] = None
    ahead = 0
    behind = 0
    detached = False

    staged: list[dict[str, Any]] = []
    unstaged: list[dict[str, Any]] = []
    untracked: list[str] = []
    ignored: list[str] = []
    conflicts: list[dict[str, Any]] = []
    renamed: list[dict[str, Any]] = []
    deleted: list[str] = []

    fields = raw.split("\x00")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        # Header lines may be newline-joined when several arrive in one field.
        for line in record.split("\n"):
            line = line.rstrip("\r")
            if not line:
                continue
            if line.startswith("# branch.oid "):
                value = line[len("# branch.oid "):].strip()
                oid = None if value == "(initial)" else value
                if value == "(initial)":
                    oid = None
                continue
            if line.startswith("# branch.head "):
                value = line[len("# branch.head "):].strip()
                if value == "(detached)":
                    detached = True
                    branch = None
                else:
                    branch = value
                continue
            if line.startswith("# branch.upstream "):
                upstream = line[len("# branch.upstream "):].strip()
                continue
            if line.startswith("# branch.ab "):
                # `# branch.ab +N -M`
                parts = line[len("# branch.ab "):].split()
                for part in parts:
                    try:
                        if part.startswith("+"):
                            ahead = int(part[1:])
                        elif part.startswith("-"):
                            behind = int(part[1:])
                    except ValueError:
                        pass
                continue
            if line.startswith("#"):
                continue

            kind = line[0]
            if kind == "?":
                path = line[2:] if len(line) > 2 else ""
                if path:
                    untracked.append(_norm(path))
                continue
            if kind == "!":
                path = line[2:] if len(line) > 2 else ""
                if path:
                    ignored.append(_norm(path))
                continue
            if kind == "1" or kind == "2":
                parts = line.split(" ", 8)
                if len(parts) < 9:
                    continue
                xy = parts[1]
                path_raw = parts[8]
                entry: dict[str, Any] = {"path": _norm(path_raw)}
                if _is_conflict(xy):
                    conflicts.append({**entry, "status": xy})
                    continue
                x_state = _state(xy[0] if xy else ".")
                y_state = _state(xy[1] if len(xy) > 1 else ".")
                if x_state is not None:
                    staged.append({"path": entry["path"], "status": x_state})
                    if x_state == "deleted":
                        deleted.append(entry["path"])
                if y_state is not None:
                    unstaged.append({"path": entry["path"], "status": y_state})
                    if y_state == "deleted" and entry["path"] not in deleted:
                        deleted.append(entry["path"])
                if kind == "2":
                    # A rename/copy consumes the NEXT NUL field as the source.
                    source = fields[index] if index < len(fields) else ""
                    index += 1
                    if source:
                        renamed.append({"path": entry["path"], "from": _norm(source)})
                continue
            if kind == "u":
                parts = line.split(" ", 10)
                if len(parts) >= 11:
                    conflicts.append({"path": _norm(parts[10]), "status": parts[1]})
                continue

    clean = not (staged or unstaged or untracked or conflicts)
    return {
        "branch": branch,
        "head": oid,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "detached_head": detached,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "ignored": ignored,
        "conflicts": conflicts,
        "renamed": renamed,
        "deleted": sorted(set(deleted)),
        "clean": clean,
    }


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip()


# ── Log ────────────────────────────────────────────────────────────────────────

_LOG_FIELDS = ("sha", "short_sha", "author", "email", "date", "parents", "subject", "body")


def parse_log(raw: str) -> list[dict[str, Any]]:
    """Parse the NUL/0x01-delimited log format into structured commits."""
    out: list[dict[str, Any]] = []
    for record in raw.split("\x01"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x00")
        if len(parts) < len(_LOG_FIELDS):
            # Pad short records defensively.
            parts += [""] * (len(_LOG_FIELDS) - len(parts))
        entry = dict(zip(_LOG_FIELDS, parts[: len(_LOG_FIELDS)]))
        parents = [p for p in entry["parents"].split() if p]
        out.append({
            "sha": entry["sha"],
            "short_sha": entry["short_sha"],
            "author": entry["author"],
            "email": entry["email"],
            "date": entry["date"],
            "subject": entry["subject"],
            "body": entry["body"].strip("\n"),
            "parents": parents,
            "is_merge": len(parents) > 1,
        })
    return out


def parse_show_header(raw: str) -> dict[str, Any]:
    """Parse the leading header of `git show` into commit metadata + patch."""
    header: dict[str, Any] = {}
    lines = raw.splitlines()
    patch_start = 0
    for i, line in enumerate(lines):
        if line.startswith("commit "):
            header["sha"] = line[len("commit "):].strip().split()[0]
        elif line.startswith("Author:"):
            header["author"] = line[len("Author:"):].strip()
        elif line.startswith("AuthorDate:"):
            header["date"] = line[len("AuthorDate:"):].strip()
        elif line.startswith("Commit:"):
            header["committer"] = line[len("Commit:"):].strip()
        elif line.startswith("CommitDate:"):
            header["commit_date"] = line[len("CommitDate:"):].strip()
        elif line.startswith("    "):
            pass
        elif line.startswith("diff --git") or line.startswith("--- "):
            patch_start = i
            break
        elif line.startswith("Merge:"):
            header["merge"] = line[len("Merge:"):].strip()
    header["patch"] = "\n".join(lines[patch_start:]) if patch_start else ""
    return header


# ── name-status / numstat ────────────────────────────────────────────────────────

def parse_name_status(raw: str) -> list[dict[str, Any]]:
    """Parse `diff --name-status -z` into path/status records (rename-aware)."""
    out: list[dict[str, Any]] = []
    fields = raw.split("\x00")
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        code = status[0]
        if code in ("R", "C"):
            src = fields[index] if index < len(fields) else ""
            index += 1
            dst = fields[index] if index < len(fields) else ""
            index += 1
            out.append({"status": _status_word(code), "from": _norm(src), "path": _norm(dst)})
        else:
            path = fields[index] if index < len(fields) else ""
            index += 1
            out.append({"status": _status_word(code), "path": _norm(path)})
    return out


def _status_word(code: str) -> str:
    return {
        "A": "added", "D": "deleted", "M": "modified", "R": "renamed",
        "C": "copied", "T": "typechanged", "U": "unmerged", "X": "unknown",
    }.get(code, "modified")


def parse_numstat(raw: str) -> list[dict[str, Any]]:
    """Parse `diff --numstat -z` into per-file insertions/deletions (binary = None)."""
    out: list[dict[str, Any]] = []
    fields = raw.split("\x00")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        parts = record.split("\t")
        if len(parts) < 3:
            continue
        adds, dels, path = parts[0], parts[1], parts[2]
        entry: dict[str, Any] = {
            "insertions": None if adds == "-" else int(adds or 0),
            "deletions": None if dels == "-" else int(dels or 0),
            "binary": adds == "-" or dels == "-",
            "path": _norm(path),
        }
        # A rename's third field is empty and the two paths follow as NUL fields.
        if not path:
            src = fields[index] if index < len(fields) else ""
            index += 1
            dst = fields[index] if index < len(fields) else ""
            index += 1
            entry["from"] = _norm(src)
            entry["path"] = _norm(dst)
        out.append(entry)
    return out


def summarize_numstat(entries: list[dict[str, Any]]) -> dict[str, Any]:
    insertions = sum(e["insertions"] or 0 for e in entries)
    deletions = sum(e["deletions"] or 0 for e in entries)
    return {
        "files_changed": len(entries),
        "insertions": insertions,
        "deletions": deletions,
        "binary_files": [e["path"] for e in entries if e.get("binary")],
        "files": entries,
    }


# ── Blame ─────────────────────────────────────────────────────────────────────────

def parse_blame(raw: str) -> list[dict[str, Any]]:
    """Parse `blame --line-porcelain` into per-line attribution records."""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.split("\n"):
        if line.startswith("\t"):
            current["content"] = line[1:]
            out.append({
                "line": current.get("final_line"),
                "commit": current.get("sha"),
                "author": current.get("author", ""),
                "date": current.get("author_time", ""),
                "content": current.get("content", ""),
            })
            current = {}
            continue
        parts = line.split(" ", 3)
        if len(parts) == 4 and len(parts[0]) >= 7 and all(c in "0123456789abcdef" for c in parts[0][:7]):
            current["sha"] = parts[0]
            try:
                current["final_line"] = int(parts[2])
            except ValueError:
                pass
            continue
        if line.startswith("author "):
            current["author"] = line[len("author "):]
        elif line.startswith("author-mail "):
            current["email"] = line[len("author-mail "):].strip("<>")
        elif line.startswith("author-time "):
            current["author_time"] = line[len("author-time "):]
    return out


# ── Worktree ────────────────────────────────────────────────────────────────────

def parse_worktrees(raw: str) -> list[dict[str, Any]]:
    """Parse `worktree list --porcelain` into records."""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                out.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            if current:
                out.append(current)
            current = {"path": _norm(line[len("worktree "):]), "detached": False, "bare": False,
                       "locked": False, "prunable": False}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].replace("refs/heads/", "")
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        elif line.startswith("locked"):
            current["locked"] = True
            extra = line[len("locked"):].strip()
            if extra:
                current["lockReason"] = extra
        elif line.startswith("prunable"):
            current["prunable"] = True
        elif line.startswith("bare"):
            current["bare"] = True
    if current:
        out.append(current)
    return out


# ── Branch list ──────────────────────────────────────────────────────────────────

def parse_branches(raw: str) -> list[dict[str, Any]]:
    """Parse the branch `--format=…%00…` output into branch records."""
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x00")
        if len(parts) < 4:
            continue
        name, sha, head_marker, upstream = parts[0], parts[1], parts[2], parts[3]
        track = parts[4] if len(parts) > 4 else ""
        record: dict[str, Any] = {
            "name": name,
            "sha": sha,
            "current": head_marker.strip() == "*",
            "upstream": upstream or None,
            "ahead": 0,
            "behind": 0,
        }
        # `[ahead 2, behind 1]` or `[gone]`.
        if "ahead" in track:
            record["ahead"] = _int_between(track, "ahead ")
        if "behind" in track:
            record["behind"] = _int_between(track, "behind ")
        if "gone" in track:
            record["gone"] = True
        out.append(record)
    return out


def _int_between(text: str, marker: str) -> int:
    try:
        rest = text.split(marker, 1)[1]
        digits = ""
        for ch in rest:
            if ch.isdigit():
                digits += ch
            else:
                break
        return int(digits) if digits else 0
    except (IndexError, ValueError):
        return 0


# ── Reflog ────────────────────────────────────────────────────────────────────────

def parse_reflog(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x00")
        if len(parts) < 5:
            continue
        out.append({
            "sha": parts[0], "selector": parts[1], "subject": parts[2],
            "date": parts[3], "author": parts[4],
        })
    return out


# ── Refs / show-ref ─────────────────────────────────────────────────────────────────

def parse_show_ref(raw: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            out.append({"sha": parts[0], "ref": parts[1]})
    return out


__all__ = [
    "parse_blame",
    "parse_branches",
    "parse_log",
    "parse_name_status",
    "parse_numstat",
    "parse_reflog",
    "parse_show_header",
    "parse_show_ref",
    "parse_status",
    "parse_worktrees",
    "summarize_numstat",
]
