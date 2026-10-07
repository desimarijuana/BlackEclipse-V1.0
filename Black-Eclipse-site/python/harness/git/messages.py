"""Deterministic commit-message and pull-request drafting.

This is NOT a model call. The agent owns the prose; this module provides a
deterministic, testable fallback that names the change honestly from the staged
diff. It is used when the model does not supply a message, and by the PR
generator to assemble the structured sections the provider layer sends.

Conventional-commit inference is heuristic and deliberately conservative: it
picks a type from the changed paths and a subject from the most significant path.
It never claims a change it did not observe.
"""

from __future__ import annotations

from typing import Any, Optional

from .executor import run
from .parsers import parse_name_status, parse_numstat, summarize_numstat
from .repository import Repository

# Path fragments → conventional type. First match wins; ordered by specificity.
_TYPE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("/test/", "test_", "_test.", ".test.", ".spec.", "/tests/", "spec/"), "test"),
    (("/docs/", ".md", "readme", "changelog", "documentation"), "docs"),
    (("/ci/", ".github/workflows", ".gitlab-ci", "bitbucket-pipelines", "jenkinsfile", "azure-pipelines"), "ci"),
    (("dockerfile", "docker-compose", "package.json", "requirements.txt", "cargo.toml", "go.mod", "pyproject.toml", "makefile"), "build"),
    (("/perf/", "benchmark", "profiler"), "perf"),
    (("lock", ".lock"), "chore"),
)


def _infer_type(entries: list[dict[str, Any]], *, conventional: bool) -> str:
    if not conventional:
        return ""
    all_new = bool(entries) and all(e.get("status") == "added" for e in entries)
    all_deleted = bool(entries) and all(e.get("status") == "deleted" for e in entries)
    paths = " ".join((e.get("path") or "").casefold() for e in entries)
    for needles, kind in _TYPE_RULES:
        if any(n in paths for n in needles):
            return "test" if kind == "test" else ("docs" if kind == "docs" else kind)
    if all_new:
        return "feat"
    if all_deleted:
        return "chore"
    return "fix"


def _subject(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "update project files"
    # Name the highest-churn path's basename, else the first path.
    primary = entries[0].get("path") or ""
    base = primary.replace("\\", "/").split("/")[-1]
    count = len(entries)
    if count == 1:
        return f"update {base}"
    top_dir = primary.replace("\\", "/").split("/")[0] if "/" in primary else base
    return f"update {top_dir} ({count} files)"


def generate_commit_message(repo: Repository, *, conventional: bool = False) -> dict[str, Any]:
    """A deterministic conventional-or-plain message from the STAGED diff."""
    names_result = run(repo.root, "diff_name_status_cached", {"paths": []})
    numstat = run(repo.root, "diff_numstat_cached", {"paths": []})
    staged_entries = parse_name_status(names_result.stdout) if names_result.ok else []
    changes = parse_numstat(numstat.stdout) if numstat.ok else []
    stats = summarize_numstat(changes) if numstat.ok else {
        "files_changed": len(staged_entries), "insertions": 0, "deletions": 0,
    }
    staged_names = [e["path"] for e in staged_entries]
    change_entries = staged_entries

    kind = _infer_type(change_entries, conventional=conventional)
    subject = _subject(change_entries)
    header = f"{kind}: {subject}" if kind else subject.capitalize()
    body_lines = [
        f"{stats.get('files_changed', len(change_entries))} file(s) changed, "
        f"+{stats.get('insertions', 0)}/-{stats.get('deletions', 0)}."
    ]
    if staged_names:
        preview = ", ".join(staged_names[:5])
        body_lines.append(f"Touched: {preview}{'…' if len(staged_names) > 5 else ''}")
    message = header + "\n\n" + "\n".join(body_lines)
    return {
        "available": True,
        "message": message,
        "header": header,
        "type": kind or None,
        "conventional": bool(kind),
        "files": staged_names,
        "stats": {k: stats.get(k) for k in ("files_changed", "insertions", "deletions")},
    }


def _names_from_patch(patch: str) -> list[str]:
    names: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/"):].strip()
            if path and path != "/dev/null":
                names.append(path)
    # Deduplicate preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def generate_pull_request(
    repo: Repository, *, base: str = "main", head: Optional[str] = None,
    issue: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble a structured PR description from the branch diff vs `base`."""
    from .readers import log as read_log  # noqa: PLC0415

    head_ref = head or repo.branch
    range_spec = f"{base}...{head_ref}" if head_ref else base
    show = run(repo.root, "diff_range", {"from": base, "to": head_ref or "HEAD", "paths": []})
    numstat = run(repo.root, "diff_range" if False else "diff_numstat", {"base": base, "paths": []})
    commits_result = read_log(repo, rev=range_spec, max_count=50)
    commits = commits_result.get("commits", []) if commits_result.get("available") else []
    stats = summarize_numstat(parse_numstat(numstat.stdout)) if numstat.ok else {}
    files = _names_from_patch(show.stdout) if show.ok else []

    title = commits[0]["subject"] if commits else "Update project"
    summary = "\n".join(f"- {c['subject']}" for c in commits[:20]) or "- (no commits)"
    body_lines = [
        "## Summary",
        summary,
        "",
        "## Changes",
        f"{stats.get('files_changed', len(files))} file(s), +{stats.get('insertions', 0)}/-{stats.get('deletions', 0)}.",
    ]
    if issue:
        body_lines += ["", "## Context", f"Addresses: {issue}"]
    body_lines += [
        "", "## Testing", "Checks were run by the task before this request.",
        "", "## Risk", "Medium",
    ]
    return {
        "available": True,
        "provider": "git",
        "title": title,
        "body": "\n".join(body_lines),
        "source_branch": head_ref,
        "target_branch": base,
        "files": files,
        "stats": {k: stats.get(k) for k in ("files_changed", "insertions", "deletions")},
        "commits": [c["sha"] for c in commits[:50]],
    }


__all__ = ["generate_commit_message", "generate_pull_request"]
