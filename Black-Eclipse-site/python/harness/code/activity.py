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
    # CIUE navigation: a symbol name or a file path — never file content.
    "code_get_definition": "name",
    "code_find_references": "name",
    "code_find_symbol": "name",
    "code_get_type": "name",
    "code_get_callers": "name",
    "code_get_callees": "name",
    "code_get_call_hierarchy": "name",
    "code_get_implementations": "name",
    "code_rename_symbol": "name",
    "code_search_symbols": "query",
    "code_get_relevant_context": "query",
    "code_get_document_symbols": "path",
    "code_get_imports": "path",
    "code_get_exports": "path",
    "code_parse_file": "path",
    "code_analyze_file": "path",
    "code_get_hover": "file",
    "code_get_diagnostics": "file",
}
_COMMAND_TOOLS = {"command_run", "terminal_run"}

# Vision tools whose QUESTION/TARGET is safe, useful display metadata.
_VISION_QUESTION_TOOLS = {
    "vision_analyze", "image_understand", "vision_answer",
    "screenshot_analyze", "clipboard_analyze", "chart_analyze",
    "document_vision", "visual_ground", "visual_localize",
    "visual_compare", "screen_compare",
}
# Vision tools whose SOURCE KIND is the safe detail (never the payload).
_VISION_SOURCE_TOOLS = {
    "vision_analyze", "image_understand", "ocr_extract", "image_metadata", "vision_answer",
}
# Vision-prefixed tools whose structured `data` follows the vision-result shape.
_VISION_RESULT_TOOLS = {
    "chart_analyze", "document_vision", "ocr_extract",
}


def _source_kind_hint(source: Any) -> Optional[str]:
    """A short, content-free source descriptor (never the base64 payload)."""
    text = str(source or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("data:"):
        return "data-uri"
    if lowered.startswith(("http://", "https://")):
        return "url"
    if len(text) >= 64 and " " not in text and "\\" not in text and "/" not in text:
        return "image-bytes"
    return "path"


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
    if name in _VISION_QUESTION_TOOLS:
        # Show the question/target, never the image bytes or a path dump.
        value = args.get("question") or args.get("target")
        return _clip(value) if value not in (None, "") else None
    if name in _VISION_SOURCE_TOOLS:
        # A short, safe descriptor of the source kind — never the payload.
        kind = args.get("source_kind") or _source_kind_hint(args.get("source"))
        return _clip(kind) if kind else None
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
    if name.startswith("code_"):
        # CIUE tools all return a `count` and an `engine`; the summary names how
        # many results and which kind of tool answered (never file content).
        count = data.get("count")
        engine = data.get("engine")
        if isinstance(count, int):
            suffix = f" ({engine})" if engine else ""
            return f"{count} result(s){suffix}"
        return None
    if name.startswith("vision_") or name in _VISION_RESULT_TOOLS:
        # A vision tool returns `{ok, mode, ...}`; summarize honestly.
        if data.get("ok") is False:
            error = data.get("error") or {}
            return f"unavailable ({error.get('errorClass', 'ERROR')})"
        mode = data.get("mode") or "vision"
        count = 0
        for key in ("observations", "text", "regions"):
            value = data.get(key)
            if isinstance(value, list):
                count += len(value)
        return f"{mode} · {count} item(s)" if count else mode
    return None


__all__ = [
    "MAX_DETAIL_CHARS",
    "tool_detail",
    "tool_result_summary",
]
