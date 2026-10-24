"""The `terminal_run` handler — generic command execution, gated (Phase D).

`terminal.py` owns classification (allow / ask / deny). This module owns the
tool handler: it re-checks the classification, refuses a `deny`, requires the
run's command-execute grant, requires a per-workspace SINGLE-USE approval for an
`ask` command, then runs through the ONE `TerminalManager` (the same subsystem
the UI and `execute_command` use) and records the execution exactly like
`command_run` (row + ledger), so a claim about it can be verified.

The approval for an `ask` command is consumed by the EFFECT AUTHORIZER
(`make_terminal_authorizer`) before the handler runs, keyed by kind
`terminal_command` + a digest of (workspace, command). A `deny` never reaches the
authorizer as approvable — it is refused in the handler AND at the authorizer.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..tools import ToolContext
from ..terminal import runtime as terminal_runtime
from . import policy
from . import terminal as terminal_mod
from .command_tools import _command_refusal, _record_command
from .tools import _present, emit_code_event
from .worktree import WorkspaceError
from .tools import _ensure_code_workspace

APPROVAL_KIND = "terminal_command"

# A persistent per-workspace shell session: the cwd and any `export`ed variables
# survive across `terminal_run` calls, so the model can `cd src`, export, and
# later commands run in that place with those variables. Reset by a fresh
# workspace id; confined to the worktree root (never escapes the binding).
_SESSIONS: dict[str, dict[str, Any]] = {}


def _session(ws_id: str) -> dict[str, Any]:
    sess = _SESSIONS.get(ws_id)
    if sess is None:
        sess = {"cwd": Path("."), "env": {}}
        _SESSIONS[ws_id] = sess
    return sess


def _resolve_session_cwd(root: Path, sess: dict[str, Any]) -> Path:
    candidate = (root / sess["cwd"]).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return root
    return candidate if candidate.is_dir() else root


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


def _terminal_manager(ctx: ToolContext) -> Optional[Any]:
    """The ONE terminal manager, or a lazily-built one for a headless run.

    The service installs the process-wide manager at boot. A direct
    `execute_run` (an eval, a test, the CLI) has no service boot, so build one
    over the run's own store rather than falling back to a second execution
    primitive.
    """
    manager = terminal_runtime.get_terminal_manager()
    if manager is not None:
        return manager
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return None
    from ..terminal.manager import TerminalManager  # noqa: PLC0415
    from ..terminal.store import TerminalStore  # noqa: PLC0415

    manager = TerminalManager(store=TerminalStore(store))
    terminal_runtime.set_terminal_manager(manager)
    return manager


def _context_meta(ctx: ToolContext) -> dict[str, Any]:
    ws = getattr(ctx, "workspace", None)
    return {
        "agentId": getattr(ctx, "agent_id", None),
        "runId": getattr(ctx, "run_id", None),
        "workspaceId": getattr(ws, "id", None) if ws is not None else None,
    }


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
        # Session mutations (cd / export / set / pwd) never spawn a process —
        # the handler rewrites them into session state, so they are always allow.
        head = command.strip().split(None, 1)[0].casefold() if command.strip() else ""
        if head in ("cd", "chdir", "export", "set", "pwd"):
            if head in ("export", "set"):
                import shlex as _shlex  # noqa: PLC0415
                try:
                    _shlex.split(command, posix=True)
                except ValueError:
                    return False
            return True
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
        # Standing grant ("always allow <program> in this workspace"). A `deny`
        # was already returned above, so a grant can never make a destructive
        # command run.
        grant_pattern = str(verdict.program or command.strip().split(None, 1)[0] or "").casefold()
        grants = getattr(approvals, "grants", None)
        if grants is not None and grant_pattern and grants.matches("command", ws_id, grant_pattern) is not None:
            try:
                from .tools import emit_code_event as _emit  # noqa: PLC0415
                await _emit(ctx, "approval.granted", {
                    "kind": APPROVAL_KIND, "grantPattern": grant_pattern,
                    "workspaceId": ws_id, "command": command[:180],
                })
            except Exception:  # noqa: BLE001
                pass
            return True
        claimed = approvals.consume_kind(
            kind=APPROVAL_KIND, request_key=ws_id, digest=digest, workspace_id=ws_id,
        )
        if claimed is not None:
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=APPROVAL_KIND, request_key=ws_id, digest=digest,
                effect="external_action",
                run_id=str(getattr(ctx, "run_id", "")),
                workspace_id=ws_id,
                action_summary=f"Run a command: {command[:180]}",
                risk="medium",
                grant_kind="command", grant_pattern=grant_pattern, grant_scope=ws_id,
            )
        except Exception:  # noqa: BLE001 - a request failure must not crash the call
            pass
        try:
            from .tools import emit_code_event as _emit  # noqa: PLC0415
            await _emit(ctx, "approval.requested", {
                "approvalId": (pending or {}).get("id"),
                "kind": APPROVAL_KIND,
                "title": "Approve running a command",
                "summary": f"Run in the project: {command[:180]}",
                "effect": "external_action",
                "risk": "medium",
                "command": command[:180],
                "workspaceId": ws_id,
                "grantPattern": grant_pattern,
                "grantLabel": f"Always allow `{grant_pattern}` in this workspace" if grant_pattern else None,
            })
        except Exception:  # noqa: BLE001
            pass
        # Pause mode: block for the operator's decision and re-claim once.
        if pending is not None:
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(
                    kind=APPROVAL_KIND, request_key=ws_id, digest=digest, workspace_id=ws_id,
                ),
                emitter=getattr(ctx, "emitter", None), digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": APPROVAL_KIND, "command": command[:180]},
            ):
                return True
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

    # Session mutations are handled WITHOUT spawning a process: `cd` moves the
    # persistent cwd, `export KEY=VAL` / `set KEY=VAL` persists an env var, and
    # `pwd` reports the persistent cwd. There is still no shell, so a `cd`
    # cannot be chained with another command.
    sess = _session(cw.id)
    try:
        tokens = terminal_mod.shlex.split(model.command.strip(), posix=True)
    except ValueError:
        tokens = []
    if tokens and tokens[0].casefold() in ("cd", "chdir"):
        target = tokens[1] if len(tokens) > 1 and tokens[1] not in ("", "~") else "."
        new_cwd = (resolved.root / sess["cwd"] / target).resolve() if target not in ("/", "\\") else resolved.root
        try:
            new_cwd.relative_to(resolved.root.resolve())
        except ValueError:
            return ("Refused: that folder is outside the workspace.", {"status": "refused", "code": "PATH_ESCAPE"})
        if not new_cwd.is_dir():
            return (f"There is no folder `{target}` here.", {"status": "not_found", "cwd": str(new_cwd)})
        sess["cwd"] = new_cwd.relative_to(resolved.root.resolve())
        return (f"cwd is now {sess['cwd'] or '.'}", {"status": "ok", "cwd": str(new_cwd)})
    if tokens and tokens[0].casefold() in ("export", "set") and len(tokens) > 1:
        for assignment in tokens[1:]:
            if "=" in assignment:
                key, _, value = assignment.partition("=")
                sess["env"][key] = value
        return (f"Set {len(tokens) - 1 if tokens else 0} variable(s) for this session.", {"status": "ok", "envKeys": sorted(sess['env'])})
    if tokens and tokens[0].casefold() == "pwd":
        cwd_now = _resolve_session_cwd(resolved.root, sess)
        return (str(cwd_now), {"status": "ok", "cwd": str(cwd_now)})

    session_cwd = _resolve_session_cwd(resolved.root, sess)
    manager = _terminal_manager(ctx)
    if manager is None:
        return _command_refusal(
            "RUNTIME_UNAVAILABLE", "the terminal isn't available right now",
            command_class="terminal",
        )

    meta = _context_meta(ctx)
    await emit_code_event(ctx, "command.started", {
        "commandClass": "terminal", "program": verdict.program, "verdict": verdict.kind,
        "timeoutS": int(model.timeoutS or 120),
    })
    # V2 terminal merge: run through the SAME TerminalManager the UI and the
    # `execute_command` tool use. The classifier above is still the single policy
    # decision; this removes the second execution primitive (a direct
    # `code/sandbox.run` call) from the code profile.
    raw = await asyncio.to_thread(
        manager.execute_command,
        command=model.command, cwd=str(session_cwd), runtime="local",
        timeout_ms=int((model.timeoutS or 120) * 1000),
        shell_mode=False,
        session_env=sess["env"] or None,
        agent_id=meta["agentId"], run_id=meta["runId"], workspace_id=meta["workspaceId"],
        purpose=model.note or None,
    )
    if raw.status == "unavailable":
        reason = raw.error.message if raw.error else "the terminal isn't available right now"
        return _command_refusal("RUNTIME_UNAVAILABLE", reason, command_class="terminal")

    event = "command.killed" if (raw.timed_out or raw.status == "cancelled") else "command.completed"
    await emit_code_event(ctx, event, {
        "commandClass": "terminal", "program": verdict.program, "exitCode": raw.exit_code,
        "durationMs": raw.duration_ms, "timedOut": raw.timed_out, "truncated": raw.truncated,
        "backend": raw.runtime,
    })
    _record_command(
        ctx, command_class="terminal", argv=[model.command], cwd=str(session_cwd),
        exit_code=raw.exit_code if raw.exit_code is not None else -1,
        duration_ms=raw.duration_ms, output=raw.stdout,
        total_chars=len(raw.stdout), backend=raw.runtime,
        decision={"allowed": True, "code": "OK", "verdict": verdict.kind},
        timed_out=raw.timed_out, truncated=raw.truncated,
    )
    header = (
        f"Ran `{verdict.program}`: exit={raw.exit_code} durationMs={raw.duration_ms} "
        f"truncated={'yes' if raw.truncated else 'no'}"
        f"{' TIMED OUT' if raw.timed_out else ''}"
    )
    text = header + ("\n" + raw.stdout if raw.stdout else "")
    if raw.error:
        text += f"\n[{raw.error.category}] {raw.error.message}"
    data = {
        "status": raw.status, "commandClass": "terminal", "program": verdict.program,
        "argv": [model.command], "cwd": str(session_cwd), "exitCode": raw.exit_code,
        "durationMs": raw.duration_ms, "timedOut": raw.timed_out,
        "truncated": raw.truncated, "totalChars": len(raw.stdout),
        "backend": raw.runtime, "output": raw.stdout,
        "executionId": raw.execution_id,
    }
    return text, data


def terminal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The exact command line to run, e.g. `python script.py` or `npm test`. "
                               "Runs without a shell. Safe tools run directly; others ask first; destructive ones are refused. "
                               "`cd <dir>`, `export KEY=VAL` and `pwd` persist across calls in this workspace's session.",
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
