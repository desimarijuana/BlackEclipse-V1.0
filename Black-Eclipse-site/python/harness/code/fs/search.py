"""Search engine — ripgrep when available, a bounded Python scan otherwise.

The engine is a platform abstraction: `search_text` prefers `ripgrep` (fast,
respects `.gitignore`) and falls back to a bounded Python line scan. Both paths
honor the workspace's ignore rules and return the SAME structured result shape
(path, line, column, matched text, context).

`search_files` / `find_files` are glob-based file discovery over the workspace,
ignore-aware and bounded.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from .. import policy
from . import errors as err
from . import metadata as meta
from . import resolver as res
from .context import FsContext

MAX_PATTERN_CHARS = 500
MAX_MATCHES = 500
MAX_FILES_SCANNED = 10_000
MAX_SCAN_BYTES = 32 * 1024 * 1024
MAX_SEARCH_MS = 8_000
RG_TIMEOUT_S = 15
RG_OUTPUT_CAP = 8 * 1024 * 1024
MAX_RESULT_LINE_CHARS = 500

# Default path globs excluded unless the caller asks otherwise. Mirrors
# `policy.IGNORED_DIRS` plus the common bulky/generated trees.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git", "node_modules", "__pycache__", ".next", ".next-dev", "_backups",
    ".black-eclipse", ".venv", "venv", "dist", "build", "vendor",
)


def ripgrep_path() -> Optional[str]:
    """The ripgrep executable, or None. Never fabricates an engine."""
    return shutil.which("rg")


def engine_name() -> str:
    return "ripgrep" if ripgrep_path() else "python-scan"


@dataclass
class SearchMatch:
    path: str
    line: int
    column: int
    text: str
    context: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "text": self.text,
            "context": self.context,
        }


def _is_ignored(rel: str, *, include_ignored: bool) -> bool:
    if include_ignored:
        return False
    return policy.is_protected(rel) or policy.is_ignored(rel)


def _iter_files(ctx: FsContext, base: str, *, include_ignored: bool, include_hidden: bool) -> Iterator[tuple[str, Path]]:
    start = res.require_directory(ctx.ws, base or ".")
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        current = Path(dirpath)
        keep: list[str] = []
        for d in dirnames:
            rel = res.relative(ctx.ws, current / d)
            if not include_hidden and d.startswith("."):
                continue
            if _is_ignored(rel, include_ignored=include_ignored):
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            rel = res.relative(ctx.ws, current / name)
            if not include_hidden and name.startswith("."):
                continue
            if _is_ignored(rel, include_ignored=include_ignored):
                continue
            yield rel, current / name


def _resolve_search_root(ctx: FsContext, base: str) -> tuple[Path, Optional[str]]:
    """Resolve a search root: a folder, or a SINGLE regular file.

    Returns `(start_dir, only_file_rel)`. A model often points `path` at the one
    file it cares about; requiring a directory there raised `NOT_A_DIRECTORY`
    (observed, twice) even though the intent was unambiguous. When a file is
    named, the search runs over exactly that file and `only_file_rel` carries its
    workspace-relative path for display.
    """
    target = res.resolve(ctx.ws, base or ".")
    if not target.exists():
        raise err.FsError(err.PATH_NOT_FOUND, "That path isn't there.", path=base)
    if target.is_dir():
        return target, None
    if not target.is_file():
        raise err.FsError(err.NOT_A_FILE, "That isn't a regular file.", path=base)
    return target.parent, res.relative(ctx.ws, target)


def _file_is_searchable(rel_file: str, *, include_ignored: bool, include_hidden: bool) -> bool:
    """The same ignore/hidden rule a folder scan would apply to this file."""
    if not include_hidden and Path(rel_file).name.startswith("."):
        return False
    return not _is_ignored(rel_file, include_ignored=include_ignored)


def search_text(
    ctx: FsContext,
    pattern: str,
    *,
    path: str = ".",
    regex: bool = False,
    case_sensitive: bool = False,
    whole_word: bool = False,
    glob: Optional[str] = None,
    max_results: int = 100,
    context_lines: int = 0,
    literal: Optional[bool] = None,
    include_ignored: bool = False,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Search file contents. Returns structured matches + the engine used."""
    ctx.require("search", "")
    text = str(pattern or "")
    if not text:
        raise err.FsError(err.INVALID_PATH, "There was no search pattern.")
    if len(text) > MAX_PATTERN_CHARS:
        raise err.FsError(err.TOO_LARGE, "That search pattern is too long.")
    literal = (not regex) if literal is None else bool(literal)
    # An explicit `literal` wins; otherwise literal is the inverse of `regex`.
    is_literal = literal if literal is not None else (not regex)
    # Validate a regex pattern in-process BEFORE any engine runs, so an invalid
    # pattern is refused deterministically (ripgrep would only emit an error).
    if not is_literal:
        try:
            re.compile(text)
        except re.error as exc:
            raise err.FsError(err.SEARCH_FAILED, f"That search pattern isn't valid: {exc}") from None
    bound = max(1, min(int(max_results), MAX_MATCHES))
    started = time.monotonic()
    rg = ripgrep_path()
    if rg is not None:
        try:
            return _search_ripgrep(
                ctx, rg, text, path=path, literal=is_literal, case_sensitive=case_sensitive,
                whole_word=whole_word, glob=glob, max_results=bound, context_lines=context_lines,
                include_ignored=include_ignored, include_hidden=include_hidden, started=started,
            )
        except err.FsError:
            raise
        except (OSError, subprocess.SubprocessError):
            pass  # fall through to the scan
    return _search_scan(
        ctx, text, path=path, regex=not is_literal, case_sensitive=case_sensitive,
        whole_word=whole_word, glob=glob, max_results=bound, context_lines=context_lines,
        include_ignored=include_ignored, include_hidden=include_hidden, started=started,
    )


def _search_ripgrep(
    ctx: FsContext, rg: str, pattern: str, *, path: str, literal: bool,
    case_sensitive: bool, whole_word: bool, glob: Optional[str], max_results: int,
    context_lines: int, include_ignored: bool, include_hidden: bool, started: float,
) -> dict[str, Any]:
    single = _resolve_search_root(ctx, path)
    start, only_file = single
    if only_file is not None and not _file_is_searchable(
        only_file, include_ignored=include_ignored, include_hidden=include_hidden
    ):
        return {
            "status": "ok", "engine": "ripgrep", "pattern": pattern, "matches": [],
            "count": 0, "truncated": False, "ms": int((time.monotonic() - started) * 1000),
        }
    argv = [rg, "--json", "--line-number", "--with-filename", "--color", "never"]
    argv.append(f"-C{max(0, int(context_lines))}")
    if not case_sensitive:
        argv.append("--ignore-case")
    if whole_word:
        argv.append("--word-regexp")
    if literal:
        argv.append("--fixed-strings")
    if include_hidden:
        argv.append("--hidden")
    if include_ignored:
        argv.append("--no-ignore")
    else:
        for excluded in DEFAULT_EXCLUDES:
            argv.extend(["--glob", f"!**/{excluded}/**"])
    if glob:
        argv.extend(["--glob", glob])
    argv.extend(["--", pattern, Path(only_file).name if only_file else "."])
    proc = subprocess.run(
        argv, cwd=str(start), shell=False, capture_output=True, timeout=RG_TIMEOUT_S,
        env={k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "PATHEXT") if k in os.environ},
    )
    out = proc.stdout[:RG_OUTPUT_CAP]
    matches: list[SearchMatch] = []
    truncated = False
    for raw in out.splitlines():
        try:
            import json

            record = json.loads(raw)
        except ValueError:
            continue
        if record.get("type") != "match":
            continue
        data = record.get("data") or {}
        rel = data.get("path", {}).get("text", "")
        rel = rel.replace("\\", "/")
        if rel.startswith("./"):
            rel = rel[2:]
        if only_file is not None:
            rel = only_file  # rg ran inside the file's own folder
        line_no = int(data.get("line_number") or 0)
        line_text = (data.get("lines") or {}).get("text", "").rstrip("\n").rstrip("\r")
        column = 1
        sub = data.get("submatches") or []
        if sub:
            column = int(sub[0].get("start", 0)) + 1
        matches.append(SearchMatch(
            path=rel, line=line_no, column=column,
            text=line_text[:MAX_RESULT_LINE_CHARS], context=[],
        ))
        if len(matches) >= max_results:
            truncated = True
            break
    if (time.monotonic() - started) * 1000 > MAX_SEARCH_MS:
        truncated = True
    return {
        "status": "ok",
        "engine": "ripgrep",
        "pattern": pattern,
        "matches": [m.to_dict() for m in matches],
        "count": len(matches),
        "truncated": truncated,
        "ms": int((time.monotonic() - started) * 1000),
    }


def _build_regex(pattern: str, *, regex: bool, case_sensitive: bool, whole_word: bool) -> "re.Pattern[str]":
    source = pattern if regex else re.escape(pattern)
    if whole_word:
        source = rf"\b(?:{source})\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(source, flags)
    except re.error as exc:
        raise err.FsError(err.SEARCH_FAILED, f"That search pattern isn't valid: {exc}") from None


def _search_scan(
    ctx: FsContext, pattern: str, *, path: str, regex: bool, case_sensitive: bool,
    whole_word: bool, glob: Optional[str], max_results: int, context_lines: int,
    include_ignored: bool, include_hidden: bool, started: float,
) -> dict[str, Any]:
    compiled = _build_regex(pattern, regex=regex, case_sensitive=case_sensitive, whole_word=whole_word)
    matches: list[SearchMatch] = []
    files_scanned = 0
    total_bytes = 0
    truncated = False
    start, only_file = _resolve_search_root(ctx, path)
    if only_file is not None:
        if _file_is_searchable(only_file, include_ignored=include_ignored, include_hidden=include_hidden):
            file_iter: Iterator[tuple[str, Path]] = iter([(only_file, start / Path(only_file).name)])
        else:
            file_iter = iter([])
    else:
        file_iter = _iter_files(ctx, path, include_ignored=include_ignored, include_hidden=include_hidden)
    for rel, full in file_iter:
        if glob and not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(Path(rel).name, glob):
            continue
        try:
            size = full.stat().st_size
        except OSError:
            continue
        if size > meta.MAX_TEXT_BYTES:
            continue
        if total_bytes + size > MAX_SCAN_BYTES or files_scanned >= MAX_FILES_SCANNED:
            truncated = True
            break
        if res.is_binary_file(full):
            continue
        files_scanned += 1
        total_bytes += size
        try:
            from . import encoding as enc

            lines = enc.read_text(full).text.splitlines()
        except err.FsError:
            continue
        for index, line in enumerate(lines):
            if (time.monotonic() - started) * 1000 > MAX_SEARCH_MS:
                truncated = True
                break
            match = compiled.search(line)
            if not match:
                continue
            if context_lines:
                low = max(0, index - context_lines)
                high = min(len(lines), index + context_lines + 1)
                context = [{"line": n + 1, "text": lines[n]} for n in range(low, high)]
            else:
                context = []
            matches.append(SearchMatch(
                path=rel, line=index + 1, column=match.start() + 1,
                text=line[:MAX_RESULT_LINE_CHARS], context=context,
            ))
            if len(matches) >= max_results:
                truncated = True
                break
        if truncated:
            break
    return {
        "status": "ok",
        "engine": "python-scan",
        "pattern": pattern,
        "matches": [m.to_dict() for m in matches],
        "count": len(matches),
        "filesScanned": files_scanned,
        "truncated": truncated,
        "ms": int((time.monotonic() - started) * 1000),
    }


# ── file discovery ──────────────────────────────────────────────────────────


def _match_any(rel: str, patterns: list[str]) -> bool:
    name = Path(rel).name
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)


def find_files(
    ctx: FsContext,
    *,
    include: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
    extensions: Optional[list[str]] = None,
    path: str = ".",
    directories_only: bool = False,
    files_only: bool = False,
    include_hidden: bool = False,
    include_ignored: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    """Glob-based file discovery: include/exclude/extensions, ignore-aware."""
    ctx.require("search", "")
    bound = max(1, min(int(limit), MAX_MATCHES))
    include_patterns = list(include or [])
    exclude_patterns = list(exclude or [])
    exts = [e if e.startswith(".") else "." + e for e in (extensions or [])]
    results: list[dict[str, Any]] = []
    truncated = False
    if directories_only and not files_only:
        # Directory discovery walks directories, not the file list.
        for dirpath, dirnames, _files in os.walk(res.require_directory(ctx.ws, path or "."), followlinks=False):
            current = Path(dirpath)
            keep: list[str] = []
            for d in dirnames:
                rel = res.relative(ctx.ws, current / d)
                if _is_ignored(rel, include_ignored=include_ignored):
                    continue
                if not include_hidden and d.startswith("."):
                    continue
                keep.append(d)
                if include_patterns and not _match_any(rel, include_patterns):
                    continue
                if exclude_patterns and _match_any(rel, exclude_patterns):
                    continue
                results.append({"path": rel, "type": "dir"})
                if len(results) >= bound:
                    truncated = True
                    break
            dirnames[:] = keep
            if truncated:
                break
        return {"status": "ok", "path": path, "files": results, "count": len(results), "truncated": truncated}
    for rel, full in _iter_files(ctx, path, include_ignored=include_ignored, include_hidden=include_hidden):
        if include_patterns and not _match_any(rel, include_patterns):
            continue
        if exclude_patterns and _match_any(rel, exclude_patterns):
            continue
        if exts and full.suffix.lower() not in exts:
            continue
        entry = {"path": rel, "type": "file", "extension": full.suffix}
        try:
            entry["size"] = full.stat().st_size
        except OSError:
            pass
        results.append(entry)
        if len(results) >= bound:
            truncated = True
            break
    return {
        "status": "ok",
        "path": path,
        "files": results,
        "count": len(results),
        "truncated": truncated,
    }


def search_files(ctx: FsContext, pattern: str, *, path: str = ".", **kwargs: Any) -> dict[str, Any]:
    """File-name search: a glob pattern plus the `find_files` filters."""
    result = find_files(ctx, include=[pattern], path=path, **kwargs)
    result["pattern"] = pattern
    return result


__all__ = [
    "DEFAULT_EXCLUDES",
    "MAX_MATCHES",
    "MAX_PATTERN_CHARS",
    "SearchMatch",
    "engine_name",
    "find_files",
    "ripgrep_path",
    "search_files",
    "search_text",
]
