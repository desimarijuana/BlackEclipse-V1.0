"""Read-only Git operations.

Every function takes a discovered `Repository` and returns a structured dict. No
function here mutates anything: each runs a fixed, argument-free (or
validated-argument) read-only op through the executor and parses the machine
output. Reads never take the repository lock.

A read that fails returns `{"available": False, "error": {...}}` rather than
raising, so one unavailable read cannot crash a tool. Callers that must fail hard
use `require=True`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from . import errors, parsers, safety, state
from .executor import run
from .repository import Repository


def _fail(result: Any) -> dict[str, Any]:
    err = getattr(result, "error", None)
    return {
        "available": False,
        "error": err.to_dict() if err is not None else {"code": result.code, "message": "The read did not complete."},
    }


# ── Status ────────────────────────────────────────────────────────────────────────

def status(repo: Repository, *, full: bool = False) -> dict[str, Any]:
    """The structured repository status (branch tracking, staged/unstaged/untracked)."""
    result = run(repo.root, "status")
    if not result.ok:
        return _fail(result)
    parsed = parsers.parse_status(result.stdout)
    parsed["available"] = True
    parsed["repository"] = str(repo.root)
    if not full:
        # A bounded, model-friendly view: counts + a slice of each list.
        parsed["summary"] = {
            "staged": len(parsed["staged"]),
            "unstaged": len(parsed["unstaged"]),
            "untracked": len(parsed["untracked"]),
            "conflicts": len(parsed["conflicts"]),
        }
    parsed["gitOperation"] = (state.active_operation(repo) or _none_state()).to_dict()
    return parsed


def _none_state() -> state.OperationState:
    return state.OperationState(operation=None, status="NONE")


# ── Diff ────────────────────────────────────────────────────────────────────────────

def _diff(repo: Repository, op: str, args: dict[str, Any], *, numstat_op: str,
          include_untracked: bool = False) -> dict[str, Any]:
    result = run(repo.root, op, args)
    if not result.ok:
        return _fail(result)
    patch = result.stdout
    numstat_args = {k: v for k, v in args.items() if k in ("base", "paths")}
    stats_result = run(repo.root, numstat_op, numstat_args)
    stats = parsers.summarize_numstat(parsers.parse_numstat(stats_result.stdout)) if stats_result.ok else {
        "files_changed": 0, "insertions": 0, "deletions": 0, "binary_files": [], "files": [],
    }
    untracked: list[str] = []
    if include_untracked:
        # `git diff` never shows untracked files. The agent must still see them,
        # so they are listed (status "untracked") and counted, with their content
        # read by the file tools rather than fabricated here.
        others = run(repo.root, "ls_files_others")
        if others.ok:
            untracked = [p for p in others.stdout.split("\x00") if p.strip()]
            untracked = [p.replace("\\", "/") for p in untracked]
            if args.get("paths"):
                wanted = {str(x).replace("\\", "/") for x in args["paths"]}
                untracked = [p for p in untracked if p in wanted]
            for path in untracked:
                stats["files"].append({
                    "path": path, "insertions": None, "deletions": None,
                    "binary": False, "status": "untracked",
                })
            stats["files_changed"] = len(stats["files"])
    return {
        "available": True,
        "patch": patch,
        "truncated": result.truncated,
        "totalChars": result.total_chars,
        "untracked": untracked,
        **stats,
    }


def diff_worktree(repo: Repository, *, base: Optional[str] = None, paths: Optional[list[str]] = None,
                  context: Optional[int] = None) -> dict[str, Any]:
    return _diff(repo, "diff_worktree", {"base": base, "paths": paths or [], "contextLines": context},
                 numstat_op="diff_numstat", include_untracked=base is None)


def diff_cached(repo: Repository, *, base: Optional[str] = None, paths: Optional[list[str]] = None) -> dict[str, Any]:
    return _diff(repo, "diff_cached", {"base": base, "paths": paths or []},
                 numstat_op="diff_numstat_cached")


def diff_range(repo: Repository, frm: str, to: str, *, paths: Optional[list[str]] = None) -> dict[str, Any]:
    return _diff(repo, "diff_range", {"from": frm, "to": to, "paths": paths or []},
                 numstat_op="diff_numstat_range")


# ── History ──────────────────────────────────────────────────────────────────────

def log(repo: Repository, *, rev: Optional[str] = None, max_count: int = 50,
        skip: int = 0, author: Optional[str] = None, since: Optional[str] = None,
        until: Optional[str] = None, grep: Optional[str] = None,
        paths: Optional[list[str]] = None) -> dict[str, Any]:
    result = run(repo.root, "log", {
        "rev": rev, "maxCount": max_count, "skip": skip or None, "author": author,
        "since": since, "until": until, "grep": grep, "paths": paths or [],
    })
    if not result.ok:
        return _fail(result)
    commits = parsers.parse_log(result.stdout)
    return {"available": True, "commits": commits, "count": len(commits)}


def show(repo: Repository, rev: str, *, stat: bool = False, paths: Optional[list[str]] = None) -> dict[str, Any]:
    result = run(repo.root, "show", {"rev": rev, "stat": "true" if stat else None, "paths": paths or []})
    if not result.ok:
        return _fail(result)
    header = parsers.parse_show_header(result.stdout)
    header["available"] = True
    return header


def commit_info(repo: Repository, rev: str) -> dict[str, Any]:
    """A single commit's metadata + file/stat summary (three bounded reads)."""
    show_result = run(repo.root, "show", {"rev": rev, "stat": "true"})
    if not show_result.ok:
        return _fail(show_result)
    log_result = run(repo.root, "log", {"rev": rev, "maxCount": 1})
    commits = parsers.parse_log(log_result.stdout) if log_result.ok else []
    files_result = run(repo.root, "commit_files", {"rev": rev})
    stats_result = run(repo.root, "commit_stats", {"rev": rev})
    files = parsers.parse_name_status(files_result.stdout) if files_result.ok else []
    stats = parsers.summarize_numstat(parsers.parse_numstat(stats_result.stdout)) if stats_result.ok else {}
    commit = commits[0] if commits else parsers.parse_show_header(show_result.stdout)
    return {
        "available": True,
        "commit": commit,
        "files": files,
        "stats": stats,
    }


def commit_files(repo: Repository, rev: str) -> dict[str, Any]:
    result = run(repo.root, "commit_files", {"rev": rev})
    if not result.ok:
        return _fail(result)
    return {"available": True, "files": parsers.parse_name_status(result.stdout)}


def commit_stats(repo: Repository, rev: str) -> dict[str, Any]:
    result = run(repo.root, "commit_stats", {"rev": rev})
    if not result.ok:
        return _fail(result)
    return {"available": True, **parsers.summarize_numstat(parsers.parse_numstat(result.stdout))}


def parents(repo: Repository, rev: str) -> dict[str, Any]:
    result = run(repo.root, "commit_parents", {"rev": rev})
    if not result.ok:
        return _fail(result)
    parts = result.stdout.strip().split()
    return {"available": True, "sha": parts[0] if parts else rev, "parents": parts[1:]}


def reflog(repo: Repository, *, ref: Optional[str] = None, max_count: int = 50) -> dict[str, Any]:
    result = run(repo.root, "reflog", {"ref": ref, "maxCount": max_count})
    if not result.ok:
        return _fail(result)
    return {"available": True, "entries": parsers.parse_reflog(result.stdout)}


def blame(repo: Repository, path: str, *, rev: Optional[str] = None,
          start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict[str, Any]:
    args: dict[str, Any] = {"path": path, "rev": rev}
    if start_line:
        args["startLine"] = start_line
        args["endLine"] = end_line or start_line
    result = run(repo.root, "blame", args)
    if not result.ok:
        return _fail(result)
    return {"available": True, "path": path, "lines": parsers.parse_blame(result.stdout)}


def grep(repo: Repository, pattern: str, *, rev: Optional[str] = None,
         paths: Optional[list[str]] = None) -> dict[str, Any]:
    result = run(repo.root, "grep", {"pattern": pattern, "rev": rev, "paths": paths or []})
    # git grep exits 1 when there are no matches — that is not an error.
    if not result.ok and result.exit_code == 1:
        return {"available": True, "matches": [], "count": 0}
    if not result.ok:
        return _fail(result)
    matches = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 3:
            matches.append({"path": parts[0], "line": int(parts[1]) if parts[1].isdigit() else 0, "text": parts[2]})
    return {"available": True, "matches": matches, "count": len(matches)}


# ── Branches ─────────────────────────────────────────────────────────────────────

def branches(repo: Repository, *, include_remote: bool = True) -> dict[str, Any]:
    local = run(repo.root, "branch_list")
    if not local.ok:
        return _fail(local)
    records = parsers.parse_branches(local.stdout)
    remote: list[dict[str, Any]] = []
    if include_remote:
        remote_result = run(repo.root, "branch_list_remote")
        if remote_result.ok:
            remote = parsers.parse_branches(remote_result.stdout)
    return {"available": True, "branches": records, "remoteBranches": remote}


def merged_branches(repo: Repository, *, base: str = "HEAD") -> dict[str, Any]:
    result = run(repo.root, "branch_merged", {"base": base})
    if not result.ok:
        return _fail(result)
    names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
    return {"available": True, "merged": names}


# ── Remotes / tags / config ─────────────────────────────────────────────────────────

_CRED_URL_RE = __import__("re").compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<user>[^/@\s]*):(?P<secret>[^/@\s]+)@")


def _redact_url(url: str) -> str:
    from .journal import redact_text  # noqa: PLC0415

    return redact_text(url)


def remotes(repo: Repository) -> dict[str, Any]:
    result = run(repo.root, "remote_list")
    if not result.ok:
        return _fail(result)
    entries: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        mode = parts[2].strip("()") if len(parts) > 2 else "fetch"
        record = by_name.setdefault(name, {"name": name, "fetchUrl": None, "pushUrl": None})
        if mode == "push":
            record["pushUrl"] = _redact_url(url)
        else:
            record["fetchUrl"] = _redact_url(url)
    entries = list(by_name.values())
    return {"available": True, "remotes": entries}


def tags(repo: Repository) -> dict[str, Any]:
    result = run(repo.root, "tag_list")
    if not result.ok:
        return _fail(result)
    out: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x00")
        if len(parts) >= 3:
            out.append({"name": parts[0], "type": parts[1], "object": parts[2]})
    return {"available": True, "tags": out}


def config(repo: Repository, *, scope: Optional[list[str]] = None) -> dict[str, Any]:
    result = run(repo.root, "config_list", {"scope": scope or []})
    if not result.ok:
        return _fail(result)
    entries: list[dict[str, str]] = []
    for item in result.stdout.split("\x00"):
        if not item.strip():
            continue
        key, _, value = item.partition("\n") if "\n" in item else item.partition("=")
        safe_value = value
        if key.casefold() in ("user.email", "credential.helper") or "password" in key.casefold() or "token" in key.casefold():
            safe_value = _redact_url(value)
        entries.append({"key": key.strip(), "value": safe_value.strip()[:400]})
    return {"available": True, "entries": entries}


# ── Worktrees / submodules / LFS ────────────────────────────────────────────────────

def worktrees(repo: Repository) -> dict[str, Any]:
    result = run(repo.root, "worktree_list")
    if not result.ok:
        return _fail(result)
    return {"available": True, "worktrees": parsers.parse_worktrees(result.stdout)}


def submodules(repo: Repository) -> dict[str, Any]:
    result = run(repo.root, "submodule_status")
    if not result.ok:
        return _fail(result)
    entries: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # `[ +|-|U]<sha> <path> (<describe>)`
        marker = line[:1]
        rest = line[1:].strip()
        parts = rest.split()
        entries.append({
            "path": parts[1] if len(parts) > 1 else "",
            "sha": parts[0] if parts else "",
            "state": {" ": "clean", "+": "modified", "-": "uninitialized", "U": "conflict"}.get(marker, "unknown"),
        })
    return {"available": True, "submodules": entries}


def lfs_status(repo: Repository) -> dict[str, Any]:
    gitattributes = repo.root / ".gitattributes"
    uses_lfs = False
    if gitattributes.is_file():
        try:
            uses_lfs = "filter=lfs" in gitattributes.read_text(encoding="utf-8", errors="replace")
        except OSError:
            uses_lfs = False
    result = run(repo.root, "lfs_ls_files")
    tracked: list[str] = []
    lfs_available = result.ok
    if result.ok:
        tracked = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return {"available": True, "usesLfs": uses_lfs, "lfsInstalled": lfs_available, "trackedFiles": tracked}


def hooks(repo: Repository) -> dict[str, Any]:
    report = safety.inspect_untrusted(repo)
    return {"available": True, **report.to_dict()}


def ignore_check(repo: Repository, path: str) -> dict[str, Any]:
    result = run(repo.root, "ignore_check", {"path": path})
    ignored = result.ok and bool(result.stdout.strip())
    return {"available": True, "path": path, "ignored": ignored, "detail": result.stdout.strip()[:400]}


# ── Conflicts / operation state ─────────────────────────────────────────────────────

def conflicts(repo: Repository) -> dict[str, Any]:
    active = state.active_operation(repo)
    files = list(active.conflicted_files) if active is not None else []
    blocks: dict[str, list[dict[str, Any]]] = {}
    for rel in files:
        blocks[rel] = state.read_conflicts(repo, rel)
    return {
        "available": True,
        "operation": active.operation if active is not None else None,
        "conflictedFiles": files,
        "blocks": blocks,
        "count": len(files),
    }


def operation_state(repo: Repository) -> dict[str, Any]:
    active = state.active_operation(repo)
    return {"available": True, **(active.to_dict() if active is not None else _none_state().to_dict())}


def repository_state(repo: Repository) -> dict[str, Any]:
    """The agent's first-class GitHub-style context block."""
    status_data = status(repo, full=False)
    return {
        "available": status_data.get("available", False),
        "repository": str(repo.root),
        "branch": repo.branch,
        "head": repo.head,
        "detached": repo.detached_head,
        "upstream": status_data.get("upstream"),
        "ahead": status_data.get("ahead", 0),
        "behind": status_data.get("behind", 0),
        "clean": status_data.get("clean", True),
        "counts": status_data.get("summary", {}),
        "operation": status_data.get("gitOperation"),
    }


__all__ = [
    "blame", "branches", "commit_files", "commit_info", "commit_stats", "config",
    "conflicts", "diff_cached", "diff_range", "diff_worktree", "grep", "hooks",
    "ignore_check", "lfs_status", "log", "merged_branches", "operation_state",
    "parents", "reflog", "remotes", "repository_state", "show", "status",
    "submodules", "tags", "worktrees",
]
