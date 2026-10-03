"""The `terminal_run` handler — generic command execution, gated (Phase D).

`terminal.py` owns classification (allow / ask / deny) and builds the argv. This
module owns the tool handler: it re-checks the classification, refuses a `deny`,
requires the run's command-execute grant, requires a per-workspace SINGLE-USE
approval for an `ask` command, then runs through `code/sandbox.py` and records the
execution exactly like `command_run` (row + ledger), so a claim about it can be
verified.

The approval for an `ask` command is consumed by the EFFECT AUTHORIZER
(`make_terminal_authorizer`) before the handler runs, keyed by kind
`terminal_command` + a digest of (workspace, command). A `deny` never reaches the
authorizer as approvable — it is refused in the handler AND at the authorizer.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..tools import ToolContext
from . import policy
from . import sandbox as sandbox_mod
from . import terminal as terminal_mod
from .command_tools import _command_refusal, _record_command
from .sandbox import SandboxUnavailable
from .tools import _present, emit_code_event
from .worktree import WorkspaceError
from .tools import _ensure_code_workspace

APPROVAL_KIND = "terminal_command"


class TerminalRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., min_length=1, max_length=terminal_mod.MAX_COMMAND_CHARS)
    timeoutS: Optional[int] = Field(default=None, ge=1, le=terminal_mod.MAX_TIMEOUT_S)  # noqa: N815
    note: str = Field("", max_length=200)


def terminal_digest(workspace_id: str, command: str) -> str:
    """A stable digest of (workspace, command) — the approval key."""
    raw = f"{workspace_id}\x00{command.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _autonomy_grants_command(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "command.execute" in policy.code_grants(str(autonomy)))


def make_terminal_authorizer(inner: Any = None):
    """Compose the effect authorizer so an `allow` command runs, an `ask` command
    needs a single-use approval, and a `deny` is refused. Falls through to
    `inner` (the MCP/code authorizer) for every other non-read tool."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name != "terminal_run":
            if inner is not None:
                return bool(await inner(tool, args, ctx))
            return False
        command = str((args or {}).get("command") or "")
        verdict = terminal_mod.classify(command)
        if verdict.kind == "deny":
            return False
        if verdict.kind == "allow":
            return True
        # ask: require a single-use, workspace-bound approval for THIS command.
        # When none is approved yet, CREATE the pending request so it surfaces in
        # the approvals UI, then refuse this call. The model retries after the
        # user approves; the retry consumes the approval and runs.
        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        workspace = getattr(ctx, "workspace", None) if ctx is not None else None
        if approvals is None or workspace is None:
            return False
        ws_id = str(getattr(workspace, "id", ""))
        digest = terminal_digest(ws_id, command)
        claimed = approvals.consume_kind(
            kind=APPROVAL_KIND, request_key=ws_id, digest=digest, workspace_id=ws_id,
        )
        if claimed is not None:
            return True
        try:
            approvals.request_kind(
                kind=APPROVAL_KIND, request_key=ws_id, digest=digest,
                effect="external_action",
                run_id=str(getattr(ctx, "run_id", "")),
                workspace_id=ws_id,
                action_summary=f"Run a command: {command[:180]}",
                risk="medium",
            )
        except Exception:  # noqa: BLE001 - a request failure must not crash the call
            pass
        return False

    return authorize


async def terminal_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    model = TerminalRunInput(**_present(args))
    verdict = terminal_mod.classify(model.command)
    if verdict.kind == "deny":
        await emit_code_event(ctx, "command.refused", {"commandClass": "terminal", "code": "COMMAND_DENIED"})
        return _command_refusal("COMMAND_NOT_ALLOWLISTED", verdict.reason, command_class="terminal")

    ws = getattr(ctx, "workspace", None)
    if ws is None:
        return _command_refusal("WORKSPACE_UNBOUND", "there is no project folder to run in", command_class="terminal")
    if not _autonomy_grants_command(ctx):
        return _command_refusal("PROFILE_DENIED", "this task isn't set up to run commands", command_class="terminal")

    try:
        cw, binding, resolved, _actor = _ensure_code_workspace(ctx)
    except WorkspaceError as exc:
        return _command_refusal(exc.code, exc.reason, command_class="terminal")

    try:
        spec = terminal_mod.build_run_spec(model.command, cwd=resolved.root, timeout_s=model.timeoutS)
    except ValueError as exc:
        return _command_refusal("COMMAND_NOT_ALLOWLISTED", str(exc), command_class="terminal")

    actor = policy.WorkspaceBinding(id=cw.id, root=resolved.root, base_revision=cw.base_revision, strategy=cw.strategy)
    try:
        sandbox_mod.select_backend()
    except SandboxUnavailable:
        return _command_refusal("SANDBOX_UNAVAILABLE", "commands can't be run safely here right now", command_class="terminal")

    await emit_code_event(ctx, "command.started", {
        "commandClass": "terminal", "program": verdict.program, "verdict": verdict.kind,
        "timeoutS": spec.timeout_s,
    })
    raw = sandbox_mod.run(spec)
    event = "command.killed" if (raw.timed_out or raw.cancelled) else "command.completed"
    await emit_code_event(ctx, event, {
        "commandClass": "terminal", "program": verdict.program, "exitCode": raw.exit_code,
        "durationMs": raw.duration_ms, "timedOut": raw.timed_out, "truncated": raw.truncated,
        "backend": raw.backend,
    })
    _record_command(
        ctx, command_class="terminal", argv=spec.argv, cwd=str(resolved.root),
        exit_code=raw.exit_code, duration_ms=raw.duration_ms, output=raw.output,
        total_chars=raw.total_chars, backend=raw.backend,
        decision={"allowed": True, "code": "OK", "verdict": verdict.kind},
        timed_out=raw.timed_out, truncated=raw.truncated,
    )
    status = "timed_out" if raw.timed_out else ("cancelled" if raw.cancelled else "ok")
    header = (
        f"Ran `{verdict.program}`: exit={raw.exit_code} durationMs={raw.duration_ms} "
        f"truncated={'yes' if raw.truncated else 'no'}"
        f"{' TIMED OUT' if raw.timed_out else ''}"
    )
    text = header + ("\n" + raw.output if raw.output else "")
    data = {
        "status": status, "commandClass": "terminal", "program": verdict.program,
        "argv": spec.argv, "cwd": str(resolved.root), "exitCode": raw.exit_code,
        "durationMs": raw.duration_ms, "timedOut": raw.timed_out,
        "truncated": raw.truncated, "totalChars": raw.total_chars,
        "backend": raw.backend, "output": raw.output,
    }
    return text, data


def terminal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The exact command line to run, e.g. `python script.py` or `npm test`. "
                               "Runs without a shell. Safe tools run directly; others ask first; destructive ones are refused.",
            },
            "timeoutS": {"type": "integer", "description": "Wall-clock limit in seconds (default 120, max 900)."},
            "note": {"type": "string", "description": "Why this command is wanted; recorded in the trace."},
        },
        "required": ["command"],
        "additionalProperties": False,
    }


__all__ = [
    "APPROVAL_KIND",
    "TerminalRunInput",
    "make_terminal_authorizer",
    "terminal_digest",
    "terminal_run",
    "terminal_schema",
]
