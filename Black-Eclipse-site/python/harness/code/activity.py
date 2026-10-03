"""Safe, bounded tool-activity summaries for the live stream.

A coding harness shows *what* a tool is doing while it runs — the command, the
file being read, the change being written — and a one-line result when it
finishes. Eclipse's raw `tool.requested` event carried only the tool NAME, so
the chat could show "Reading a file" but never "src/app.py".

This module derives a `detail` (what) and a `summary` (result) from a tool call,
as DATA plus a small pure function. It is deliberately conservative:

  * it reads ONLY a fixed, known set of argument fields per tool (a path, a
    command, a glob, a command class) — never the whole arg object;
  * it never includes file CONTENT: a `workspace_patch_apply` `content`/`new`
    field is summarized to the list of file PATHS and the operation names;
  * every string is bounded (a command is truncated; a path is truncated);
  * it is content-free for anything it does not explicitly recognise.

Nothing here executes or decides anything — `code/policy.py` owns the gates. A
`detail` is display metadata, never an authorization.
"""

from __future__ import annotations

from typing import Any, Optional

MAX_DETAIL_CHARS = 200
MAX_FILES = 12

# Argument fields that are safe to show verbatim (path/command/pattern), per tool.
_PATH_TOOLS = {
    "workspace_read": "path",
    "workspace_list": "path",
    "workspace_docs": "query",
    "workspace_search": "pattern",
    "workspace_diff": "base",
}
_COMMAND_TOOLS = {"command_run", "terminal_run"}


def _clip(text: Any, limit: int = MAX_DETAIL_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _files_from_ops(ops: Any) -> list[str]:
    if not isinstance(ops, list):
        return []
    names: list[str] = []
    for op in ops:
        if isinstance(op, dict):
            path = op.get("path") or op.get("fromPath")
            if path:
                names.append(str(path))
        if len(names) >= MAX_FILES:
            break
    return names


def tool_detail(tool_name: str, args: dict[str, Any]) -> Optional[str]:
    """The one-line "what" for a tool call, or None when there is nothing safe.

    Never returns file content. A `workspace_patch_apply` reports the affected
    PATHS; a terminal/command tool reports the command; a read/list reports the
    path. An unrecognised tool reports nothing rather than guessing.
    """
    if not isinstance(args, dict):
        return None
    name = str(tool_name or "")
    if name == "terminal_run":
        return _clip(args.get("command"))
    if name == "command_run":
        cls = args.get("command_class")
        return _clip(cls) if cls else None
    if name == "workspace_patch_apply":
        ops = args.get("operations")
        files = _files_from_ops(ops)
        if not files:
            return None
        joined = ", ".join(files)
        return _clip(joined + (" …" if len(files) >= MAX_FILES else ""))
    if name == "scaffold_kit":
        kit = args.get("kit") or args.get("kit_id") or args.get("name")
        return _clip(kit) if kit else None
    if name in _PATH_TOOLS:
        field = _PATH_TOOLS[name]
        value = args.get(field)
        return _clip(value) if value not in (None, "") else None
    return None


def tool_result_summary(tool_name: str, data: Any) -> Optional[str]:
    """A one-line result summary from a tool's structured `data`, or None.

    Recognises the shapes the code tools already return (exit code, files
    changed, bytes, counts). Anything unrecognised yields None — the UI then
    shows no summary rather than a fabricated one.
    """
    if not isinstance(data, dict):
        return None
    name = str(tool_name or "")
    if name in _COMMAND_TOOLS:
        if data.get("status") == "timed_out":
            return "timed out"
        exit_code = data.get("exitCode")
        if exit_code is None:
            return None
        return f"exit {exit_code}"
    if name == "workspace_patch_apply":
        changed = data.get("filesChanged")
        if isinstance(changed, list):
            return f"{len(changed)} file(s)"
        if isinstance(changed, int):
            return f"{changed} file(s)"
        applied = data.get("applied")
        if isinstance(applied, list):
            return f"{len(applied)} change(s)"
        return None
    if name == "workspace_diff":
        files = data.get("filesChanged")
        return f"{files} file(s) changed" if isinstance(files, int) else None
    if name == "workspace_search":
        count = data.get("count")
        return f"{count} match(es)" if isinstance(count, int) else None
    if name == "workspace_read":
        lines = data.get("lines")
        return f"{lines} line(s)" if isinstance(lines, int) else None
    if name == "workspace_list":
        count = data.get("count")
        return f"{count} entries" if isinstance(count, int) else None
    return None


__all__ = [
    "MAX_DETAIL_CHARS",
    "tool_detail",
    "tool_result_summary",
]
