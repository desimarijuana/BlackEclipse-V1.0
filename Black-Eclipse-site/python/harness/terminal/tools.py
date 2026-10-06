"""The terminal tools — the agent's execution surface.

Every handler is a thin adapter over the shared `TerminalManager`
(`terminal/runtime.py`). Two invariants hold for all of them:

  * the WORKSPACE and the autonomy profile are enforced in the handler (the
    registry authorizer only decides whether the call may reach the handler);
  * any command that runs is classified first — safe runs directly, unknown asks
    the user (through the existing single-use approval store), destructive is
    refused — reusing `code/terminal.py` and `code/shell_tools.py` verbatim.

Output handed to the model is bounded and secret-redacted by the manager, never
here.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..code import policy
from ..code.policy import PolicyDenial
from ..tools import ToolContext
from . import runtime as runtime_mod
from .types import RuntimeName

_TERMINAL_TOOL_NAMES = (
    "execute_command",
    "open_shell", "close_shell", "list_terminal_sessions", "terminal_session_status",
    "run_shell_command", "write_shell_input", "read_shell_output", "resize_shell",
    "send_shell_control",
    "start_process", "stop_process", "restart_process", "kill_process",
    "list_processes", "process_status", "read_process_output",
    "write_process_input", "send_signal", "process_tree", "process_health",
    "list_ports", "terminal_capabilities", "system_info", "resource_report",
)

_PROFILE_DENIED = ("PROFILE_DENIED", "this task isn't set up to run commands")
_NO_WORKSPACE = ("WORKSPACE_UNAVAILABLE", "there is no project folder to work in")
_NO_RUNTIME = ("RUNTIME_UNAVAILABLE", "the terminal isn't available right now")


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    return (f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason})


def _manager() -> Any:
    return runtime_mod.get_terminal_manager()


def _owned_process(manager: Any, ctx: ToolContext, process_id: str) -> Optional[dict[str, Any]]:
    """Fetch a process only if THIS run's workspace owns it (multi-agent isolation).

    A process started with no workspace id (a UI/operator process) is control-only
    by an operator run; an agent-bound run may only touch processes bound to its
    own workspace. This stops one agent writing into another's process.
    """
    info = manager.get_process(process_id)
    if info is None:
        return None
    ws = getattr(ctx, "workspace", None)
    owner = getattr(ws, "id", None) if ws is not None else None
    process_ws = info.get("workspaceId")
    if process_ws is not None and owner is not None and process_ws != owner:
        return None
    return info


def _owned_session(manager: Any, ctx: ToolContext, session_id: str) -> Optional[dict[str, Any]]:
    info = manager.get_shell(session_id)
    if info is None:
        return None
    ws = getattr(ctx, "workspace", None)
    owner = getattr(ws, "id", None) if ws is not None else None
    session_ws = info.get("workspaceId")
    if session_ws is not None and owner is not None and session_ws != owner:
        return None
    return info


def _grants_command(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "command.execute" in policy.code_grants(str(autonomy)))


def _workspace_root(ctx: ToolContext) -> Optional[Path]:
    """The confined root where terminal work happens, or None.

    Uses the same disposable/selected tree the write tools use, so a process sees
    the agent's edits. Never the operator checkout unless the run is direct.
    """
    from ..code.tools import _ensure_code_workspace  # noqa: PLC0415
    from ..code.worktree import WorkspaceError  # noqa: PLC0415

    if getattr(ctx, "workspace", None) is None:
        return None
    try:
        _cw, _binding, resolved, _actor = _ensure_code_workspace(ctx)
    except WorkspaceError:
        return None
    return Path(resolved.root)


def _confine(root: Path, requested: Optional[str]) -> Optional[Path]:
    """Resolve a cwd under ``root``; None when it escapes or does not exist."""
    if not requested:
        return root
    candidate = (root / requested).resolve() if not os.path.isabs(str(requested)) else Path(str(requested)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _context_meta(ctx: ToolContext) -> dict[str, Any]:
    ws = getattr(ctx, "workspace", None)
    return {
        "agentId": getattr(ctx, "agent_id", None),
        "runId": getattr(ctx, "run_id", None),
        "workspaceId": getattr(ws, "id", None) if ws is not None else None,
    }


# ── Input models ─────────────────────────────────────────────────────────────


class ExecuteCommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., min_length=1, max_length=4_000)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815
    purpose: str = Field(default="", max_length=64)


class OpenShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    rows: int = Field(default=24, ge=1, le=500)
    columns: int = Field(default=80, ge=1, le=500)


class SessionIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815


class ShellInputInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    input: str = Field(..., max_length=10_000)
    newline: bool = True


class RunShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    command: str = Field(..., min_length=1, max_length=4_000)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815


class ReadShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    stream: Optional[str] = Field(default=None, max_length=16)
    tail: Optional[int] = Field(default=None, ge=0, le=10_000)
    cursor: Optional[int] = Field(default=None, ge=0)
    byteLimit: Optional[int] = Field(default=None, ge=0, le=1_000_000)  # noqa: N815


class ResizeShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    rows: int = Field(..., ge=1, le=500)
    columns: int = Field(..., ge=1, le=500)


class ShellControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    key: str = Field(..., min_length=1, max_length=8)  # "c" | "d" | "z"


class StartProcessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., min_length=1, max_length=4_000)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    purpose: str = Field(default="", max_length=64)


class ProcessIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processId: str = Field(..., min_length=1, max_length=128)  # noqa: N815


class ReadProcessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    stream: Optional[str] = Field(default=None, max_length=16)
    tail: Optional[int] = Field(default=None, ge=0, le=10_000)
    cursor: Optional[int] = Field(default=None, ge=0)
    byteLimit: Optional[int] = Field(default=None, ge=0, le=1_000_000)  # noqa: N815


class ProcessInputInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    input: str = Field(..., max_length=10_000)
    newline: bool = True


class SignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    signal: str = Field(..., min_length=1, max_length=16)


class ListPortsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: Optional[int] = Field(default=None, ge=1, le=65535)


class ProcessHealthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processId: str = Field(..., min_length=1, max_length=128)  # noqa: N815
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    url: Optional[str] = Field(default=None, max_length=2_000)


# ── Handlers: one-shot execution ────────────────────────────────────────────


async def execute_command(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_command(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _workspace_root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = ExecuteCommandInput(**_present(args))
    cwd = _confine(root, model.cwd)
    if cwd is None:
        return _refusal("WORKSPACE_ESCAPE", "that working directory is outside the project folder")
    # Defense in depth: re-classify in the handler. A `deny` shape never runs even
    # if the effect authorizer is bypassed; an `ask` was already approved upstream.
    from ..code.shell_tools import _verdict  # noqa: PLC0415
    from .runtimes import RuntimeUnavailable, select_runtime  # noqa: PLC0415

    verdict = _verdict(model.command)
    if verdict.kind == "deny":
        return _refusal("COMMAND_NOT_ALLOWLISTED", verdict.reason)
    try:
        select_runtime(model.runtime)
    except RuntimeUnavailable as exc:
        return _refusal("RUNTIME_UNAVAILABLE", exc.reason)
    from ..code.tools import emit_code_event  # noqa: PLC0415

    meta = _context_meta(ctx)
    result = await asyncio.to_thread(
        manager.execute_command,
        command=model.command, cwd=str(cwd), shell=model.shell, runtime=model.runtime,
        timeout_ms=int(model.timeoutMs or 120_000), purpose=model.purpose or None,
        agent_id=meta["agentId"], run_id=meta["runId"], workspace_id=meta["workspaceId"],
    )
    await emit_code_event(ctx, "terminal.command", {
        "executionId": getattr(result, "execution_id", None),
        "runtime": model.runtime, "status": getattr(result, "status", None),
        "exitCode": getattr(result, "exit_code", None),
    })
    data = result.to_dict()
    header = (
        f"Ran `{model.command}`: status={data['status']} exit={data['exitCode']} "
        f"durationMs={data['durationMs']}{' TIMED OUT' if data['timedOut'] else ''}"
        f"{' (output truncated)' if data['truncated'] else ''}"
    )
    text = header + (f"\n{data['stdout']}" if data["stdout"] else "")
    if data.get("error"):
        text = f"{header}\n[{data['error']['category']}] {data['error']['message']}"
    return text, data


# ── Handlers: persistent sessions ────────────────────────────────────────────


async def open_shell(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_command(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _workspace_root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = OpenShellInput(**_present(args))
    try:
        from .runtimes import select_runtime  # noqa: PLC0415

        selected = select_runtime(model.runtime)
        if not getattr(selected, "available", False):
            return _refusal("RUNTIME_UNAVAILABLE", f"the {model.runtime} runtime is not available on this computer")
    except Exception as exc:  # noqa: BLE001 - unavailable runtime refuses honestly
        return _refusal("RUNTIME_UNAVAILABLE", str(exc))
    cwd = _confine(root, model.cwd)
    if cwd is None:
        return _refusal("WORKSPACE_ESCAPE", "that working directory is outside the project folder")
    meta = _context_meta(ctx)
    try:
        info = manager.open_shell(
            shell_name=model.shell, runtime=model.runtime, cwd=str(cwd),
            workspace_id=meta["workspaceId"], agent_id=meta["agentId"],
            rows=model.rows, columns=model.columns,
        )
    except Exception as exc:  # noqa: BLE001 - a failed shell start is a refusal
        return _refusal("SHELL_NOT_FOUND", f"the shell could not be started: {exc}")
    text = (
        f"Opened a {info['shell']} session {info['sessionId']} in {info['cwd']} "
        f"(pid {info['pid']}, pty={info['pty']}). It keeps its working directory and variables "
        f"between commands."
    )
    return text, {"status": "ok", **info}


async def close_shell(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = SessionIdInput(**_present(args))
    if not manager.close_shell(model.sessionId):
        return _refusal("NOT_FOUND", "there is no session with that id")
    return f"Closed session {model.sessionId}.", {"status": "ok", "sessionId": model.sessionId}


async def list_terminal_sessions(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    ws = getattr(ctx, "workspace", None)
    sessions = manager.list_shells(workspace_id=getattr(ws, "id", None) if ws is not None else None)
    text = "\n".join(
        f"{s['sessionId']}  {s['shell']:<10}  {s['status']:<8}  {s['cwd']}" for s in sessions
    ) or "No open sessions."
    return text, {"status": "ok", "sessions": sessions}


async def terminal_session_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = SessionIdInput(**_present(args))
    info = _owned_session(manager, ctx, model.sessionId)
    if info is None:
        return _refusal("NOT_FOUND", "there is no session with that id")
    return f"Session {info['sessionId']}: {info['status']} in {info['cwd']}.", {"status": "ok", **info}


async def run_shell_command(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_command(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _workspace_root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = RunShellInput(**_present(args))
    # Defense in depth: a destructive shape never reaches the session. Builtins
    # (cd/export/set/pwd) are handled natively upstream of this check.
    from ..code.shell_tools import _verdict  # noqa: PLC0415

    head = model.command.strip().split(None, 1)[0].casefold() if model.command.strip() else ""
    if head not in ("cd", "chdir", "export", "set", "pwd") and _verdict(model.command).kind == "deny":
        return _refusal("COMMAND_NOT_ALLOWLISTED", "that command could damage the computer, so I did not run it.")
    timeout_s = int((model.timeoutMs or 120_000) // 1000) or 1
    result = await asyncio.to_thread(
        manager.run_in_shell, model.sessionId, model.command, timeout_s=timeout_s, workspace_root=str(root),
    )
    if result is None:
        return _refusal("NOT_FOUND", "there is no session with that id")
    data = result.get("data")
    text = result.get("text", "")
    if result.get("timedOut"):
        text += "\n[the command is still running; it did not finish in time]"
    status = "ok" if not result.get("timedOut") else "running"
    return text, {"status": status, "sessionId": model.sessionId, **(data if isinstance(data, dict) else {})}


async def read_shell_output(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ReadShellInput(**_present(args))
    window = manager.read_shell_output(
        model.sessionId, stream=model.stream, tail=model.tail,
        cursor=model.cursor, byte_limit=model.byteLimit,
    )
    if window is None:
        return _refusal("NOT_FOUND", "there is no session with that id")
    header = f"Session {model.sessionId}: showing {window['count']} of {window['totalLines']} lines; next cursor {window['nextSequence']}"
    return header + "\n" + window["text"], {"status": "ok", **window}


async def write_shell_input(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ShellInputInput(**_present(args))
    if _owned_session(manager, ctx, model.sessionId) is None or not manager.write_shell_input(model.sessionId, model.input, newline=model.newline):
        return _refusal("NOT_FOUND", "that session is not open")
    return f"Wrote input to session {model.sessionId}.", {"status": "ok", "sessionId": model.sessionId}


async def resize_shell(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ResizeShellInput(**_present(args))
    if _owned_session(manager, ctx, model.sessionId) is None:
        return _refusal("NOT_FOUND", "there is no session with that id")
    resized = manager.resize_shell(model.sessionId, model.rows, model.columns)
    return (
        f"Session {model.sessionId} is now {model.rows}x{model.columns}.",
        {"status": "ok", "resized": resized, "sessionId": model.sessionId, "rows": model.rows, "columns": model.columns},
    )


async def send_shell_control(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ShellControlInput(**_present(args))
    if _owned_session(manager, ctx, model.sessionId) is None or not manager.send_control(model.sessionId, model.key):
        return _refusal("NOT_FOUND", "that session is not open")
    return f"Sent Ctrl+{model.key.upper()} to session {model.sessionId}.", {"status": "ok"}


# ── Handlers: background processes ────────────────────────────────────────────


async def start_process(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    if not _grants_command(ctx):
        return _refusal(*_PROFILE_DENIED)
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    root = _workspace_root(ctx)
    if root is None:
        return _refusal(*_NO_WORKSPACE)
    model = StartProcessInput(**_present(args))
    cwd = _confine(root, model.cwd)
    if cwd is None:
        return _refusal("WORKSPACE_ESCAPE", "that working directory is outside the project folder")
    # Defense in depth: a destructive shape never starts, even if the authorizer
    # is bypassed. An `ask` command was already approved upstream.
    from ..code.shell_tools import _verdict  # noqa: PLC0415
    from .runtimes import RuntimeUnavailable, select_runtime  # noqa: PLC0415

    verdict = _verdict(model.command)
    if verdict.kind == "deny":
        return _refusal("COMMAND_NOT_ALLOWLISTED", verdict.reason)
    try:
        select_runtime(model.runtime)
    except RuntimeUnavailable as exc:
        return _refusal("RUNTIME_UNAVAILABLE", exc.reason)
    meta = _context_meta(ctx)
    info = manager.start_process(
        command=model.command, cwd=str(cwd), shell=model.shell, runtime=model.runtime,
        workspace_id=meta["workspaceId"], agent_id=meta["agentId"], run_id=meta["runId"],
        purpose=model.purpose or None,
    )
    if info.get("state") == "FAILED":
        err = info.get("error") or {}
        return _refusal(err.get("category", "PROCESS_FAILED"), err.get("message", "the process could not be started"))
    text = (
        f"Started {info['processId']} (pid {info['pid']}, state {info['state']}). "
        f"Read its output with read_process_output; stop it with stop_process."
    )
    return text, {"status": "ok", **info}


async def stop_process(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessIdInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None or not manager.stop_process(model.processId):
        return _refusal("NOT_FOUND", "there is no running process with that id")
    return f"Stopping process {model.processId}.", {"status": "ok", "processId": model.processId}


async def kill_process(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessIdInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None or not manager.kill_process(model.processId):
        return _refusal("NOT_FOUND", "there is no process with that id")
    return f"Killed process {model.processId}.", {"status": "ok", "processId": model.processId}


async def restart_process(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessIdInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    info = manager.restart_process(model.processId)
    if info is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    return f"Restarted as {info['processId']} (pid {info.get('pid')}).", {"status": "ok", **info}


async def list_processes(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    ws = getattr(ctx, "workspace", None)
    processes = manager.list_processes(workspace_id=getattr(ws, "id", None) if ws is not None else None)
    text = "\n".join(
        f"{p['processId']}  {p['state']:<9}  pid={p.get('pid')}  {p['command']}" for p in processes
    ) or "No background processes."
    return text, {"status": "ok", "processes": processes}


async def process_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessIdInput(**_present(args))
    info = _owned_process(manager, ctx, model.processId)
    if info is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    text = f"{info['processId']}: {info['state']} pid={info.get('pid')} exit={info.get('exitCode')} ports={info.get('ports')}"
    return text, {"status": "ok", **info}


async def read_process_output(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ReadProcessInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    window = manager.read_process_output(
        model.processId, stream=model.stream, tail=model.tail,
        cursor=model.cursor, byte_limit=model.byteLimit,
    )
    if window is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    header = (
        f"{model.processId} [{window.get('status')}] showing {window['count']} of "
        f"{window['totalLines']} lines; next cursor {window['nextSequence']}"
    )
    return header + "\n" + window["text"], {"status": "ok", **window}


async def write_process_input(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessInputInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None or not manager.write_process_input(model.processId, model.input, newline=model.newline):
        return _refusal("NOT_FOUND", "that process is not accepting input")
    return f"Wrote input to {model.processId}.", {"status": "ok"}


async def send_signal(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = SignalInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    result = manager.send_signal(model.processId, model.signal)
    if not result.get("ok"):
        return _refusal(result.get("code", "SIGNAL_FAILED"), result.get("reason", "the signal could not be sent"))
    return f"Sent {result.get('signal')} to {model.processId}.", {"status": "ok", **result}


async def process_tree(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessIdInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    tree = manager.process_tree(model.processId)
    if tree is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    return f"Process tree for {model.processId}.", {"status": "ok", "tree": tree}


# ── Handlers: ports / capabilities ─────────────────────────────────────────────


async def process_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ProcessHealthInput(**_present(args))
    if _owned_process(manager, ctx, model.processId) is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    import asyncio as _asyncio

    result = await _asyncio.to_thread(manager.processes.health, model.processId, port=model.port, url=model.url)
    if result is None:
        return _refusal("NOT_FOUND", "there is no process with that id")
    state = "READY" if result.get("ready") else ("RUNNING" if result.get("pidAlive") else result.get("state"))
    text = f"{model.processId}: {state}"
    if model.port is not None:
        text += f" (port {model.port} {'listening' if result.get('portListening') else 'not listening'})"
    return text, {"status": "ok", **result}


async def list_ports(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    model = ListPortsInput(**_present(args))
    if model.port is not None:
        conflict = manager.find_port_conflict(model.port)
        if conflict is None:
            return f"Port {model.port} is free.", {"status": "ok", "port": model.port, "inUse": False}
        if conflict.get("pid"):
            text = f"Port {model.port} is in use by pid {conflict['pid']}"
            if conflict.get("processId"):
                text += f" (process {conflict['processId']})"
            text += "."
        else:
            text = f"Port {model.port} is in use by an unknown process."
        return text, {"status": "ok", "port": model.port, "inUse": True, "owner": conflict}
    ports = manager.list_ports()
    summary = manager.port_summary()
    text = "\n".join(
        f"{p['port']:<6} pid={str(p.get('pid')):<8} {p.get('address') or ''}" for p in ports
    ) or "No listening ports."
    return text, {"status": "ok", "ports": ports, "summary": summary}


async def terminal_capabilities(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    caps = manager.capabilities()
    shells = ", ".join(caps.get("availableShells", [])) or "none"
    text = (
        f"Platform {caps['platform']} ({caps['architecture']}); shells: {shells}; "
        f"runtimes: {', '.join(caps['runtimes'])}; pty={caps['pty']}; "
        f"docker={caps['docker']}; ssh={caps['ssh']}."
    )
    return text, {"status": "ok", **caps}


async def system_info(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    import asyncio as _asyncio

    caps = manager.capabilities()
    processes = manager.list_processes()
    ports = manager.list_ports()
    resources = await _asyncio.to_thread(manager.processes.resource_report)
    running = [p for p in processes if p["state"] == "RUNNING"]
    data = {
        "platform": caps["platform"],
        "architecture": caps["architecture"],
        "defaultShell": caps["defaultShell"],
        "shells": caps["availableShells"],
        "wsl": caps["wsl"],
        "runtimes": caps["runtimes"],
        "pty": caps["pty"],
        "processCount": len(processes),
        "runningCount": len(running),
        "sessionCount": len(manager.list_shells()),
        "listeningPorts": len(ports),
        "cpuCount": resources["system"]["cpuCount"],
        "memoryUsedPct": resources["system"]["memoryUsedPct"],
        "resourceLimits": resources["limits"],
    }
    text = (
        f"{data['platform']}/{data['architecture']}: {data['runningCount']} running process(es), "
        f"{data['sessionCount']} session(s), {data['listeningPorts']} listening port(s); "
        f"memory {data['memoryUsedPct']}% used."
    )
    return text, {"status": "ok", **data}


async def resource_report(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    manager = _manager()
    if manager is None:
        return _refusal(*_NO_RUNTIME)
    import asyncio as _asyncio

    report = await _asyncio.to_thread(manager.processes.resource_report)
    system = report["system"]
    text = (
        f"{system['cpuCount']} CPUs; memory {system['memoryUsedPct']}% used; "
        f"{report['activeProcesses']} active process(es) (limit {report['limits']['maxProcesses']})."
    )
    runaway = [p["processId"] for p in report["processes"] if p.get("runaway")]
    if runaway:
        text += f" Possibly running away: {', '.join(runaway)}."
    return text, {"status": "ok", **report}


# ── Schemas ──────────────────────────────────────────────────────────────────


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def terminal_schemas() -> dict[str, dict[str, Any]]:
    strp = {"type": "string"}
    intp = {"type": "integer"}
    return {
        "execute_command": _obj({
            "command": {"type": "string", "description": "The command line to run in the project folder. Safe tools run directly; others ask first; destructive ones are refused."},
            "cwd": {"type": "string", "description": "Working directory, relative to the project root. Must stay inside it."},
            "shell": {"type": "string", "description": "Which shell to use (powershell, cmd, wsl, bash). Defaults to the host shell."},
            "runtime": {"type": "string", "description": "Where to run: local (default) or wsl."},
            "timeoutMs": {"type": "integer", "description": "Wall-clock limit in milliseconds (default 120000, max 900000)."},
            "purpose": {"type": "string", "description": "Short reason for the command (e.g. install_dependencies, run_tests)."},
        }, ["command"]),
        "open_shell": _obj({
            "shell": strp, "runtime": strp, "cwd": strp,
            "rows": intp, "columns": intp,
        }),
        "close_shell": _obj({"sessionId": strp}, ["sessionId"]),
        "list_terminal_sessions": _obj({}),
        "terminal_session_status": _obj({"sessionId": strp}, ["sessionId"]),
        "run_shell_command": _obj({
            "sessionId": strp,
            "command": {"type": "string", "description": "A command to run inside the persistent session (keeps its cwd and variables)."},
            "timeoutMs": intp,
        }, ["sessionId", "command"]),
        "write_shell_input": _obj({"sessionId": strp, "input": strp, "newline": {"type": "boolean"}}, ["sessionId", "input"]),
        "read_shell_output": _obj({
            "sessionId": strp, "stream": strp, "tail": intp, "cursor": intp, "byteLimit": intp,
        }, ["sessionId"]),
        "resize_shell": _obj({"sessionId": strp, "rows": intp, "columns": intp}, ["sessionId", "rows", "columns"]),
        "send_shell_control": _obj({"sessionId": strp, "key": {"type": "string", "enum": ["c", "d", "z"]}}, ["sessionId", "key"]),
        "start_process": _obj({
            "command": {"type": "string", "description": "A long-running command to start in the background (e.g. a development server)."},
            "cwd": strp, "shell": strp, "runtime": strp,
            "purpose": {"type": "string", "description": "Short reason (e.g. start_development_server)."},
        }, ["command"]),
        "stop_process": _obj({"processId": strp}, ["processId"]),
        "kill_process": _obj({"processId": strp}, ["processId"]),
        "restart_process": _obj({"processId": strp}, ["processId"]),
        "list_processes": _obj({}),
        "process_status": _obj({"processId": strp}, ["processId"]),
        "read_process_output": _obj({
            "processId": strp, "stream": strp, "tail": intp, "cursor": intp, "byteLimit": intp,
        }, ["processId"]),
        "write_process_input": _obj({"processId": strp, "input": strp, "newline": {"type": "boolean"}}, ["processId", "input"]),
        "send_signal": _obj({"processId": strp, "signal": {"type": "string", "description": "SIGINT, SIGTERM or SIGKILL."}}, ["processId", "signal"]),
        "process_tree": _obj({"processId": strp}, ["processId"]),
        "process_health": _obj({
            "processId": strp,
            "port": {"type": "integer", "description": "Optional: a port the process should be listening on."},
            "url": {"type": "string", "description": "Optional: an HTTP URL to check (e.g. a local server health endpoint)."},
        }, ["processId"]),
        "list_ports": _obj({"port": {"type": "integer", "description": "Optional: report whether one specific port is in use."}}),
        "terminal_capabilities": _obj({}),
        "system_info": _obj({}),
        "resource_report": _obj({}),
    }


def _present(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if v is not None}


def register_terminal_tools(registry: Any) -> list[str]:
    """Register the terminal tools on the shared registry. Returns the names added."""
    from ..tools import ToolDefinition  # noqa: PLC0415

    schemas = terminal_schemas()
    read_tools = {
        "list_terminal_sessions", "terminal_session_status", "read_shell_output",
        "list_processes", "process_status", "read_process_output", "process_tree", "process_health",
        "list_ports", "terminal_capabilities", "system_info", "resource_report",
    }
    handlers = {
        "execute_command": execute_command,
        "open_shell": open_shell, "close_shell": close_shell,
        "list_terminal_sessions": list_terminal_sessions,
        "terminal_session_status": terminal_session_status,
        "run_shell_command": run_shell_command,
        "write_shell_input": write_shell_input,
        "read_shell_output": read_shell_output,
        "resize_shell": resize_shell,
        "send_shell_control": send_shell_control,
        "start_process": start_process, "stop_process": stop_process,
        "restart_process": restart_process, "kill_process": kill_process,
        "list_processes": list_processes, "process_status": process_status,
        "read_process_output": read_process_output, "write_process_input": write_process_input,
        "send_signal": send_signal, "process_tree": process_tree, "process_health": process_health,
        "list_ports": list_ports, "terminal_capabilities": terminal_capabilities,
        "system_info": system_info, "resource_report": resource_report,
    }
    descriptions = {
        "execute_command": "Run a command in the project folder and wait for it to finish. Returns bounded stdout, the exit code and a structured error when it fails.",
        "open_shell": "Open a persistent shell session that keeps its working directory and variables between commands. Use it to run several related commands in one context.",
        "close_shell": "Close a persistent shell session.",
        "list_terminal_sessions": "List the open persistent shell sessions. Read-only.",
        "terminal_session_status": "Show one persistent shell session. Read-only.",
        "run_shell_command": "Run a command inside a persistent shell session, keeping its working directory and variables.",
        "write_shell_input": "Type input into a persistent shell session (e.g. answering a prompt).",
        "read_shell_output": "Read a bounded window of a persistent session's output, with a cursor. Read-only.",
        "resize_shell": "Resize a persistent session's terminal window (rows/columns).",
        "send_shell_control": "Send Ctrl+C, Ctrl+D or Ctrl+Z to a persistent shell session.",
        "start_process": "Start a long-running command in the background (e.g. a development server) and get a process id immediately. Read its output later with read_process_output.",
        "stop_process": "Ask a background process to stop, then kill its tree if it does not.",
        "kill_process": "Kill a background process and its whole process tree.",
        "restart_process": "Stop a background process and start it again with the same command and folder.",
        "list_processes": "List the background processes Eclipse started. Read-only.",
        "process_status": "Show one background process's state, exit code and ports. Read-only.",
        "read_process_output": "Read a bounded window of a background process's output, with a cursor so nothing is read twice. Read-only.",
        "write_process_input": "Type input into a background process (e.g. answering a prompt).",
        "send_signal": "Send SIGINT, SIGTERM or SIGKILL to a background process.",
        "process_tree": "Show a background process and the child processes Eclipse started from it. Read-only.",
        "process_health": "Report whether a background process is READY: running, listening on its port, and answering an HTTP check. Read-only.",
        "list_ports": "List the ports currently in use, or report who holds one specific port. Read-only.",
        "terminal_capabilities": "Report what this computer can actually do: shells, runtimes, pty, docker, ssh. Read-only.",
        "system_info": "Report the host and the current terminal activity (processes, sessions, ports). Read-only.",
        "resource_report": "Report CPU, memory and how many processes are running, plus any that look like they are running away. Read-only.",
    }
    added: list[str] = []
    for name in _TERMINAL_TOOL_NAMES:
        permission = "read" if name in read_tools else "write"
        effect = None if name in read_tools else "external_action"
        register_ctx = None
        try:
            register_ctx = ToolDefinition(
                name=name, description=descriptions[name], input_schema=schemas[name],
                handler=handlers[name], permission=permission, risk=("low" if name in read_tools else "high"),
                timeout_ms=(30_000 if name in read_tools else 600_000), effect=effect,
            )
        except TypeError:  # pragma: no cover - older signature guard
            register_ctx = ToolDefinition(
                name=name, description=descriptions[name], input_schema=schemas[name],
                handler=handlers[name], permission=permission, risk=("low" if name in read_tools else "high"),
                timeout_ms=(30_000 if name in read_tools else 600_000),
            )
        registry.register(register_ctx)
        added.append(name)
    return added


# ── Effect authorizer ──────────────────────────────────────────────────────────
#
# The registry calls this for every NON-read terminal tool. A command-executing
# tool is classified exactly like the existing `shell_run`/`terminal_run` path: an
# `allow` runs, an `ask` needs a single-use workspace-bound approval, a `deny` is
# refused. Opening a shell needs an approval too. Lifecycle control of a process
# the run already started is admitted. Every other tool falls through to `inner`,
# so this composition changes nothing for the rest of the runtime.

_APPROVAL_KIND = "terminal_command"

# Tools that mutate a process/session the runtime already created. They are
# admitted here; the handler and the manager's workspace scoping bound their reach.
_CONTROL_TOOLS = frozenset({
    "close_shell", "resize_shell", "stop_process", "kill_process", "restart_process",
    "send_signal", "write_process_input", "write_shell_input", "send_shell_control",
})


def make_terminal_tool_authorizer(inner: Any = None) -> Any:
    """Authorize the terminal tool names, delegating everything else to `inner`."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in _TERMINAL_TOOL_NAMES:
            if inner is not None:
                return bool(await inner(tool, args, ctx))
            return False
        if name in _CONTROL_TOOLS:
            return True
        # Command-executing tools go through the SAME classification the shell
        # tools use (pipes/redirection are legitimate for a shell command).
        from ..code.shell_tools import _verdict  # noqa: PLC0415

        if name == "open_shell":
            return await _request_or_claim(ctx, args, key="open_shell", command="open a shell")
        command = str((args or {}).get("command") or "")
        verdict = _verdict(command)
        if verdict.kind == "deny":
            return False
        if verdict.kind == "allow":
            return True
        return await _request_or_claim(ctx, args, key=command, command=command)

    return authorize


async def _request_or_claim(ctx: Any, args: dict[str, Any], *, key: str, command: str) -> bool:
    approvals = getattr(ctx, "approvals", None) if ctx is not None else None
    workspace = getattr(ctx, "workspace", None) if ctx is not None else None
    if approvals is None or workspace is None:
        return False
    import hashlib as _hashlib

    ws_id = str(getattr(workspace, "id", ""))
    digest = _hashlib.sha256(f"{ws_id}\x00{key.strip()}".encode("utf-8")).hexdigest()
    if approvals.consume_kind(kind=_APPROVAL_KIND, request_key=ws_id, digest=digest, workspace_id=ws_id) is not None:
        return True
    pending = None
    try:
        pending = approvals.request_kind(
            kind=_APPROVAL_KIND, request_key=ws_id, digest=digest, effect="external_action",
            run_id=str(getattr(ctx, "run_id", "")), workspace_id=ws_id,
            action_summary=f"Run a command: {command[:180]}", risk="medium",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..code.tools import emit_code_event  # noqa: PLC0415

        await emit_code_event(ctx, "approval.requested", {
            "approvalId": (pending or {}).get("id"),
            "kind": _APPROVAL_KIND,
            "title": "Approve running a command",
            "summary": f"Run in the project: {command[:180]}",
            "effect": "external_action",
            "risk": "medium",
            "command": command[:180],
            "workspaceId": ws_id,
        })
    except Exception:  # noqa: BLE001
        pass
    if pending is not None:
        from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

        if await pause_for_decision(
            approvals, ctx, pending.get("id"),
            lambda: approvals.consume_kind(
                kind=_APPROVAL_KIND, request_key=ws_id, digest=digest, workspace_id=ws_id,
            ),
            emitter=getattr(ctx, "emitter", None), digest=digest,
            event_type="approval.approved",
            approved_payload={"kind": _APPROVAL_KIND, "command": command[:180]},
        ):
            return True
    return False


__all__ = [
    "make_terminal_tool_authorizer",
    "register_terminal_tools",
    "terminal_schemas",
    "execute_command",
]
