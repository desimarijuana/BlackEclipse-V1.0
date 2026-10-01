"""The five read-only repository tools (Phase 1).

`register_code_tools(registry)` exposes the read half of the code capability:
list, search, read with line numbers, find things in the docs, and report the
checkout status. Every tool declares `permission="read"`, so the registry's
non-read gate never fires: a read tool is callable by an allowlisted run and
needs no approval. There is NO write tool, NO patch tool and NO command runner —
the only child process is the fixed, argument-free `git` probe in `workspace.py`.

Every handler returns `(text, data)`: `text` is the bounded, model-facing prose
(bounded again at the registry seam, ADR-H91); `data` is the structured record
the front door reads. Nothing here fabricates: a missing workspace, a missing
file or an absent git all produce an explicit refusal, never an invented value.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import policy
from .workspace import (
    MAX_LIST_ENTRIES,
    MAX_MATCHES,
    MAX_PATTERN_CHARS,
    MAX_READ_LINES,
    MAX_SCAN_BYTES,
    MAX_SCAN_FILES,
    MAX_SEARCH_MS,
    ResolvedWorkspace,
    WorkspaceDenial,
    confine,
    git_probe,
    is_binary,
    walk,
)
from ..session_index import redact_span, secret_pattern_name

REDACT_MARKER = "«redacted»"
_DOCS_WINDOW_LINES = 6
_SEARCH_DEADLINE_CHECK_LINES = 200


# ── Input models (pydantic, extra="forbid") ─────────────────────────────────


class WorkspaceStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "."
    depth: int = Field(2, ge=1, le=4)
    includeSizes: bool = False  # noqa: N815
    maxEntries: int = Field(200, ge=1, le=MAX_LIST_ENTRIES)  # noqa: N815


class WorkspaceSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(..., min_length=1, max_length=MAX_PATTERN_CHARS)
    path: str = "."
    maxMatches: int = Field(50, ge=1, le=MAX_MATCHES)  # noqa: N815
    contextLines: int = Field(2, ge=0, le=5)  # noqa: N815
    caseSensitive: bool = False  # noqa: N815


class WorkspaceReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1, max_length=1024)
    startLine: int = Field(1, ge=1)  # noqa: N815
    maxLines: int = Field(400, ge=1, le=MAX_READ_LINES)  # noqa: N815


class WorkspaceDocsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=200)
    path: str = "docs"
    maxResults: int = Field(5, ge=1, le=20)  # noqa: N815
    maxChars: int = Field(4_000, ge=200, le=8_000)  # noqa: N815


_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace_status": {"type": "object", "properties": {}, "additionalProperties": False},
    "workspace_list": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Folder to list, relative to the project root (default '.')."},
            "depth": {"type": "integer", "description": "How deep to descend (1-4, default 2)."},
            "includeSizes": {"type": "boolean", "description": "Include each file's size in bytes."},
            "maxEntries": {"type": "integer", "description": "Maximum entries to return (default 200)."},
        },
        "additionalProperties": False,
    },
    "workspace_search": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to find in file contents."},
            "path": {"type": "string", "description": "Folder to search, relative to the project root (default '.')."},
            "maxMatches": {"type": "integer", "description": "Maximum matches to return (default 50)."},
            "contextLines": {"type": "integer", "description": "Lines of context around each match (0-5, default 2)."},
            "caseSensitive": {"type": "boolean", "description": "Match case-sensitively (default false)."},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
    "workspace_read": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to read, relative to the project root."},
            "startLine": {"type": "integer", "description": "First line to return (1-based; use the previous nextStartLine to continue)."},
            "maxLines": {"type": "integer", "description": "Maximum lines to return (default 400)."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "workspace_docs": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for in the project's notes and documentation."},
            "path": {"type": "string", "description": "Folder to search for notes/documentation (default 'docs')."},
            "maxResults": {"type": "integer", "description": "Maximum excerpts to return (default 5)."},
            "maxChars": {"type": "integer", "description": "Total character budget for excerpts (default 4000)."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


# ── Events ──────────────────────────────────────────────────────────────────


async def emit_code_event(ctx: ToolContext, event_type: str, data: dict[str, Any]) -> None:
    """Emit a `code.*` event on the run's emitter, or degrade to `ctx.log`.

    Payloads are content-free (counts, paths, names) — never file contents and
    never a secret value. graph.py is not touched for events; this is the single
    seam.
    """
    emitter = getattr(ctx, "emitter", None)
    if emitter is not None:
        try:
            await emitter.emit(event_type, data)
            return
        except Exception:  # noqa: BLE001 - an event must never break a tool call
            pass
    try:
        if ctx.log is not None:
            ctx.log(event_type, data)
    except Exception:  # noqa: BLE001
        pass


def _present(args: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None.

    The registry builds its generic arg model with `Optional[...] = None` for
    every non-required field, so an omitted optional arrives here as an explicit
    None. Our stricter pydantic models need the field to be ABSENT so their own
    defaults apply.
    """
    return {k: v for k, v in args.items() if v is not None}


def _refusal(tool: str, denial: WorkspaceDenial) -> tuple[str, Any]:
    return (
        f"REFUSED ({denial.code}): {denial.reason}",
        {"status": "refused", "code": denial.code, "path": denial.path, "tool": tool},
    )


def _no_workspace(tool: str) -> tuple[str, Any]:
    return (
        "REFUSED (WORKSPACE_UNAVAILABLE): There is no project folder available to look through.",
        {"status": "refused", "code": "WORKSPACE_UNAVAILABLE", "tool": tool},
    )


# ── workspace_status ────────────────────────────────────────────────────────


async def _status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    ws: Optional[ResolvedWorkspace] = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_status", "code": "WORKSPACE_UNAVAILABLE"})
        return _no_workspace("workspace_status")
    head = git_probe(ws, "head")
    branch = git_probe(ws, "branch")
    status = git_probe(ws, "status")
    await emit_code_event(
        ctx, "code.workspace.bound",
        {"workspaceId": ws.id, "strategy": ws.strategy, "baseRevision": ws.base_revision},
    )
    if not status.get("available"):
        text = (
            "I can't tell the version of this project: "
            f"{status.get('reason', 'git is unavailable')}. Nothing was changed by this task."
        )
        return text, {"status": "unavailable", "workspaceId": ws.id, "strategy": ws.strategy}
    dirty = status.get("dirty") or []
    lines = [
        f"Project root: {ws.root}",
        f"Revision: {head.get('head', 'unknown') if head.get('available') else 'unknown'}",
        f"Current line of work: {branch.get('branch', 'unknown') if branch.get('available') else 'unknown'}",
    ]
    if dirty:
        lines.append(f"{len(dirty)} file(s) already differ from the last saved version (none changed by this task):")
        for entry in dirty[:50]:
            lines.append(f"  {entry['status']} {entry['path']} (pre-existing)")
    else:
        lines.append("No files differ from the last saved version.")
    text = "\n".join(lines)
    data = {
        "status": "ok",
        "workspaceId": ws.id,
        "strategy": ws.strategy,
        "baseRevision": ws.base_revision,
        "head": head.get("head") if head.get("available") else None,
        "branch": branch.get("branch") if branch.get("available") else None,
        "dirty": dirty,
    }
    return text, data


# ── workspace_list ──────────────────────────────────────────────────────────


async def _list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    ws: Optional[ResolvedWorkspace] = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_list", "code": "WORKSPACE_UNAVAILABLE"})
        return _no_workspace("workspace_list")
    model = WorkspaceListInput(**_present(args))
    try:
        entries, truncated = walk(
            ws, model.path, depth=model.depth, max_entries=model.maxEntries,
        )
    except WorkspaceDenial as denial:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_list", "code": denial.code, "path": denial.path})
        return _refusal("workspace_list", denial)
    lines = [f"Contents of {model.path} (depth {model.depth}):"]
    for entry in entries:
        suffix = ""
        if model.includeSizes and entry.get("type") == "file" and "size" in entry:
            suffix = f"  ({entry['size']} bytes)"
        lines.append(f"  {entry['path']}{suffix}")
    if truncated:
        lines.append(f"[showing the first {len(entries)} entries; the list continues]")
    await emit_code_event(ctx, "code.listed", {"path": model.path, "entries": len(entries), "truncated": truncated})
    return "\n".join(lines), {
        "status": "ok",
        "path": model.path,
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
    }


# ── workspace_search ────────────────────────────────────────────────────────


def _iter_scan_files(ws: ResolvedWorkspace, base: str) -> Iterator[Tuple[str, Path]]:
    """Yield `(rel, Path)` for text files under `base`, ignore-aware and bounded."""
    start = confine(ws, base or ".")
    if not start.is_dir():
        raise WorkspaceDenial("NOT_FOUND", "That isn't a folder Eclipse can search.", path=base)
    scanned = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
        for name in filenames:
            full = current / name
            rel = full.relative_to(ws.root).as_posix()
            if policy.is_ignored(rel):
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if total_bytes + size > MAX_SCAN_BYTES:
                return
            if is_binary(full):
                continue
            total_bytes += size
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                return
            yield rel, full


async def _search(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    ws: Optional[ResolvedWorkspace] = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_search", "code": "WORKSPACE_UNAVAILABLE"})
        return _no_workspace("workspace_search")
    model = WorkspaceSearchInput(**_present(args))
    flags = re.MULTILINE if model.caseSensitive else re.MULTILINE | re.IGNORECASE
    try:
        regex = re.compile(model.pattern, flags)
    except re.error as exc:
        return f"That search pattern isn't valid: {exc}", {"status": "refused", "code": "INVALID_PATTERN"}
    started = time.monotonic()
    deadline_ms = MAX_SEARCH_MS
    matches: list[dict[str, Any]] = []
    files_scanned = 0
    truncated = False
    try:
        files = _iter_scan_files(ws, model.path)
    except WorkspaceDenial as denial:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_search", "code": denial.code, "path": denial.path})
        return _refusal("workspace_search", denial)
    for rel, full in files:
        files_scanned += 1
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_lines = text.splitlines()
        for index, line in enumerate(all_lines):
            if index % _SEARCH_DEADLINE_CHECK_LINES == 0 and (time.monotonic() - started) * 1000 > deadline_ms:
                truncated = True
                break
            if not regex.search(line):
                continue
            low = max(0, index - model.contextLines)
            high = min(len(all_lines), index + model.contextLines + 1)
            context = [{"line": n + 1, "text": all_lines[n]} for n in range(low, high)]
            matches.append({"path": rel, "line": index + 1, "text": line, "context": context})
            if len(matches) >= model.maxMatches:
                truncated = True
                break
        if truncated:
            break
    elapsed = int((time.monotonic() - started) * 1000)
    lines = [f"{len(matches)} match(es) for /{model.pattern}/:"]
    for match in matches:
        lines.append(f"{match['path']}:{match['line']}: {match['text'].strip()}")
    if truncated:
        lines.append(f"[results truncated after {len(matches)} matches across {files_scanned} files]")
    await emit_code_event(ctx, "code.searched", {
        "pattern": model.pattern, "matches": len(matches),
        "filesScanned": files_scanned, "truncated": truncated, "ms": elapsed,
    })
    return "\n".join(lines), {
        "status": "ok",
        "pattern": model.pattern,
        "matches": matches,
        "count": len(matches),
        "filesScanned": files_scanned,
        "truncated": truncated,
        "ms": elapsed,
    }


# ── workspace_read ──────────────────────────────────────────────────────────


async def _read(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    ws: Optional[ResolvedWorkspace] = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_read", "code": "WORKSPACE_UNAVAILABLE"})
        return _no_workspace("workspace_read")
    model = WorkspaceReadInput(**_present(args))
    try:
        target = confine(ws, model.path)
    except WorkspaceDenial as denial:
        # Protected/ignored/escape all fire BEFORE a byte is read, so `jdds.db`
        # reports PROTECTED_PATH and never BINARY_FILE.
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_read", "code": denial.code, "path": denial.path})
        return _refusal("workspace_read", denial)
    if is_binary(target):
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_read", "code": "BINARY_FILE", "path": model.path})
        return (
            "REFUSED (BINARY_FILE): That file isn't readable text, so Eclipse left it alone.",
            {"status": "refused", "code": "BINARY_FILE", "path": model.path},
        )
    try:
        raw_lines = target.read_text(encoding="utf-8", errors="strict").splitlines()
    except (UnicodeDecodeError, OSError):
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_read", "code": "BINARY_FILE", "path": model.path})
        return (
            "REFUSED (BINARY_FILE): That file isn't readable text, so Eclipse left it alone.",
            {"status": "refused", "code": "BINARY_FILE", "path": model.path},
        )
    start = model.startLine - 1
    window = raw_lines[start:start + model.maxLines]
    redacted_lines: list[int] = []
    pattern_names: set[str] = set()
    numbered: list[str] = []
    for offset, line in enumerate(window):
        line_no = start + offset + 1
        cleaned = redact_span(line, REDACT_MARKER)
        if cleaned != line.strip() and REDACT_MARKER in cleaned:
            redacted_lines.append(line_no)
            name = secret_pattern_name(line)
            if name:
                pattern_names.add(name)
        numbered.append(f"{line_no:>6}\t{cleaned}")
    continues = start + len(window) < len(raw_lines)
    next_start = (start + len(window) + 1) if continues else None
    rel = target.relative_to(ws.root).as_posix()
    header = f"{rel} (lines {start + 1}-{start + len(window)} of {len(raw_lines)})"
    body = [header, *numbered]
    if continues:
        body.append(f"[continues — call workspace_read again with startLine={next_start}]")
    if redacted_lines:
        body.append(f"[{len(redacted_lines)} line(s) redacted for privacy]")
    await emit_code_event(ctx, "code.read", {
        "path": rel, "startLine": model.startLine, "lines": len(window),
        "nextStartLine": next_start, "redactedLines": redacted_lines,
    })
    if redacted_lines:
        await emit_code_event(ctx, "code.redacted", {
            "path": rel, "lines": redacted_lines,
            "patternName": sorted(pattern_names)[0] if pattern_names else "secret",
            "patternNames": sorted(pattern_names),
        })
    return "\n".join(body), {
        "status": "ok",
        "path": rel,
        "startLine": model.startLine,
        "lines": len(window),
        "totalLines": len(raw_lines),
        "nextStartLine": next_start,
        "redactedLines": redacted_lines,
        "content": numbered,
    }


# ── workspace_docs ──────────────────────────────────────────────────────────


def _tokenize(query: str) -> list[str]:
    """Tokenize EXACTLY as `persistence.search_session_messages` does."""
    return re.findall(r"[A-Za-z0-9]+", query)[:12]


def _rank_docs(ws: ResolvedWorkspace, model: WorkspaceDocsInput) -> tuple[list[dict[str, Any]], bool]:
    tokens = _tokenize(model.query)
    if not tokens:
        return [], False
    phrase = " ".join(tokens).lower()
    lowered = [t.lower() for t in tokens]
    excerpts: list[dict[str, Any]] = []
    total_chars = 0
    truncated = False
    for rel, full in _iter_scan_files(ws, model.path):
        try:
            lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        step = max(1, _DOCS_WINDOW_LINES)
        for window_start in range(0, len(lines), step):
            window = lines[window_start:window_start + _DOCS_WINDOW_LINES]
            if not window:
                continue
            block = "\n".join(window)
            low = block.lower()
            frequency = sum(low.count(token) for token in lowered)
            if frequency == 0 and phrase not in low:
                continue
            phrase_bonus = 100 if phrase and phrase in low else 0
            score = phrase_bonus + frequency
            excerpt = {
                "path": rel,
                "startLine": window_start + 1,
                "endLine": window_start + len(window),
                "text": block,
                "score": score,
            }
            excerpts.append(excerpt)
    # Deterministic ranking: score desc, then path, then start line.
    excerpts.sort(key=lambda e: (-e["score"], e["path"], e["startLine"]))
    selected: list[dict[str, Any]] = []
    for excerpt in excerpts:
        if len(selected) >= model.maxResults:
            truncated = True
            break
        if total_chars + len(excerpt["text"]) > model.maxChars:
            truncated = True
            break
        total_chars += len(excerpt["text"])
        selected.append(excerpt)
    return selected, truncated


async def _docs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    ws: Optional[ResolvedWorkspace] = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_docs", "code": "WORKSPACE_UNAVAILABLE"})
        return _no_workspace("workspace_docs")
    model = WorkspaceDocsInput(**_present(args))
    try:
        selected, truncated = _rank_docs(ws, model)
    except WorkspaceDenial as denial:
        await emit_code_event(ctx, "code.refused", {"tool": "workspace_docs", "code": denial.code, "path": denial.path})
        return _refusal("workspace_docs", denial)
    lines = [f"{len(selected)} passage(s) for {model.query!r} (engine: scan):"]
    for excerpt in selected:
        lines.append(f"--- {excerpt['path']}:{excerpt['startLine']}-{excerpt['endLine']} ---")
        lines.append(excerpt["text"])
    if truncated:
        lines.append("[more passages exist — narrow the question or raise the limit]")
    await emit_code_event(ctx, "code.docs", {
        "query": model.query, "results": len(selected), "engine": "scan",
    })
    return "\n".join(lines), {
        "status": "ok",
        "query": model.query,
        "engine": "scan",
        "results": selected,
        "count": len(selected),
        "truncated": truncated,
    }


# ── Registration ────────────────────────────────────────────────────────────

_CODE_TOOL_NAMES = (
    "workspace_status",
    "workspace_list",
    "workspace_search",
    "workspace_read",
    "workspace_docs",
)


def _definition(name: str, description: str, handler: Any, timeout_ms: int) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema=_INPUT_SCHEMAS[name],
        handler=handler,
        permission="read",
        risk="low",
        timeout_ms=timeout_ms,
    )


def register_code_tools(registry: ToolRegistry) -> list[str]:
    """Register the five read tools. Returns the names added."""
    registry.register(_definition(
        "workspace_status",
        "Report which project Eclipse is looking at: its saved revision, current line of "
        "work, and any files that already differ from the last saved version (marked as "
        "pre-existing — this task changes nothing). Read-only.",
        _status, 15_000,
    ))
    registry.register(_definition(
        "workspace_list",
        "List a folder of the project, ignore-aware and bounded. Read-only; never opens "
        "or changes file contents.",
        _list, 15_000,
    ))
    registry.register(_definition(
        "workspace_search",
        "Search the project's file contents with a regular expression. Every hit is "
        "reported as path:line. Bounded by matches, files, bytes and a wall-clock "
        "deadline; a deadline yields partial results marked truncated. Read-only.",
        _search, 20_000,
    ))
    registry.register(_definition(
        "workspace_read",
        "Read a file with line numbers. Supports a continuation offset (startLine / "
        "nextStartLine). Refuses binary files, and redacts secret-shaped lines. Read-only.",
        _read, 15_000,
    ))
    registry.register(_definition(
        "workspace_docs",
        "Find ranked passages in the project's notes and documentation (docs/**). Returns "
        "bounded excerpts with their path:line range. A bounded scan per call — no index "
        "is built. Read-only.",
        _docs, 25_000,
    ))
    return list(_CODE_TOOL_NAMES)


__all__ = [
    "REDACT_MARKER",
    "register_code_tools",
    "emit_code_event",
    "WorkspaceStatusInput",
    "WorkspaceListInput",
    "WorkspaceSearchInput",
    "WorkspaceReadInput",
    "WorkspaceDocsInput",
]
