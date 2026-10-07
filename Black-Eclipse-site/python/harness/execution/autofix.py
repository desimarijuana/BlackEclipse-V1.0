"""Opt-in, bounded model autofix for the verification loop.

This is the ONE place a verification run may edit code to repair a failure. It is:

  * **off by default** (`HARNESS_EXEC_AUTOFIX=1` enables it per deployment), and it
    only runs when the run carries model settings;
  * **diagnostic-driven** — it edits the ONE file named by the first actionable
    diagnostic, never a blind whole-repo rewrite;
  * **schema-validated** — the model must return a JSON edit object
    (`{"file","old","new"}` or `{"file","content"}`); anything else is a refusal,
    so a hallucinated blob never reaches disk;
  * **confined** — the target path goes through `policy.resolve_within` and the edit
    goes through the existing `FileSystemService` (which re-checks the binding,
    autonomy profile and per-path policy);
  * **honest** — if the model is unavailable, returns nothing parseable, or the path
    is not writable, it returns `None` and the loop stops instead of retrying forever.

A security/infrastructure failure is never autofixed (the verifier stops first).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from ..tools import ToolContext
from .models import ExecutionResult

MAX_FILE_CHARS = 20_000
MAX_OUTPUT_CHARS = 6_000
MAX_NEW_CHARS = 20_000

_SYSTEM = (
    "You repair a single failing project file. You are given one file's contents and "
    "the build/test failure. Reply with ONLY a JSON object and no prose:\n"
    '{"file": "<same path>", "old": "<exact existing substring to replace>", "new": "<replacement>"}\n'
    "The `old` string MUST appear verbatim in the file. Make the smallest change that fixes the failure. "
    "If you cannot fix it from the information given, reply with {\"abort\": true}."
)
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def autofix_enabled() -> bool:
    return os.environ.get("HARNESS_EXEC_AUTOFIX") in ("1", "true", "True")


def _first_actionable(result: ExecutionResult) -> Optional[Any]:
    for diag in result.diagnostics:
        if diag.file and diag.file not in ("", "."):
            return diag
    return None


def _read_confined(root: Path, rel: str) -> Optional[str]:
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    try:
        resolved = resolve_within(root, rel)
    except PolicyDenial:
        return None
    if not resolved.is_file():
        return None
    try:
        return resolved.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
    except OSError:
        return None


def _apply_edit(root: Path, edit: dict[str, Any], binding: Any, actor: Any) -> Optional[str]:
    rel = str(edit.get("file") or "")
    if not rel:
        return None
    from ..code.fs.service import FileSystemService  # noqa: PLC0415
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415
    from ..code.workspace import ResolvedWorkspace  # noqa: PLC0415

    try:
        resolve_within(root, rel)
    except PolicyDenial:
        return None
    ws = ResolvedWorkspace(
        id=getattr(binding, "id", "autofix"), root=Path(root),
        base_revision=getattr(binding, "base_revision", "unknown"),
        strategy="direct", binding=binding,
    )
    service = FileSystemService(ws, binding, actor)
    if "content" in edit:
        content = str(edit.get("content") or "")
        if len(content) > MAX_NEW_CHARS:
            return None
        service.write_file(rel, content)
        return f"rewrote {rel}"
    old = str(edit.get("old") or "")
    new = str(edit.get("new") or "")
    if not old or len(new) > MAX_NEW_CHARS:
        return None
    service.replace_text(rel, old, new)
    return f"patched {rel}"


async def _ask_model(ctx: ToolContext, prompt: str) -> Optional[str]:
    """One bounded model call using the RUN's own provider/credentials."""
    settings = getattr(ctx, "model_settings", None)
    if settings is None:
        return None
    try:
        from langchain_core.messages import HumanMessage  # noqa: PLC0415

        from ..model_runtime import get_runtime  # noqa: PLC0415
        from ..models import build_chat_model  # noqa: PLC0415

        runtime = get_runtime()
        resolution = runtime.resolve_for_run(settings, task="simple_chat")
        model = runtime.build(resolution.settings, builder=build_chat_model, adapter=resolution.adapter)
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", None)
        if isinstance(content, list):
            return "\n".join(str(getattr(b, "text", b)) for b in content)
        return str(content if content is not None else response)
    except Exception:  # noqa: BLE001 - an unavailable model is simply no fix
        return None


def make_model_fix(ctx: ToolContext, root: Path, binding: Any, actor: Any):
    """Return an ASYNC `FixFn` bound to this run, or None when autofix is off."""

    async def fix(result: ExecutionResult, iteration: int) -> Optional[str]:
        if not autofix_enabled() or getattr(ctx, "model_settings", None) is None:
            return None
        diag = _first_actionable(result)
        if diag is None:
            return None
        source = _read_confined(root, diag.file)
        if source is None:
            return None
        failure = (diag.message or result.status)[:MAX_OUTPUT_CHARS]
        prompt = (
            f"{_SYSTEM}\n\nFile: {diag.file}\n"
            f"Failure ({diag.category}/{diag.severity}) at line {diag.line}: {failure}\n\n"
            f"----- FILE CONTENT -----\n{source}"
        )
        raw = await _ask_model(ctx, prompt)
        if not raw:
            return None
        match = _JSON.search(raw)
        if not match:
            return None
        try:
            edit = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if not isinstance(edit, dict) or edit.get("abort"):
            return None
        edit.setdefault("file", diag.file)
        try:
            return _apply_edit(root, edit, binding, actor)
        except Exception:  # noqa: BLE001 - a failed edit is not a fix
            return None

    return fix


__all__ = ["autofix_enabled", "make_model_fix"]
