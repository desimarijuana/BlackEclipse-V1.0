"""The command_run handler (Phase 3) — extracted from code/tools.py.

Everything that runs goes through `code/sandbox.py`. The class table owns the
argv; the model supplies a class + typed args. A refusal is RECORDED (row +
`command.refused` event) — a block with no record is a failure, not a pass.

Extracted so `code/tools.py` stays under the 1200-line hard ceiling; the
behaviour and the registration are unchanged.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..tools import ToolContext
from . import policy
from . import backends as backend_mod
from . import sandbox as sandbox_mod
from .events import redact_output  # noqa: PLC0415
from .commands import CommandUnavailable, build_argv, resolve_class
from .sandbox import SandboxUnavailable
from .tools import (
    CommandRunInput,
    _ensure_code_workspace,
    _make_actor,
    _present,
    emit_code_event,
)
from .worktree import WorkspaceError

# The operator flag for the only gated class. Default OFF; an operator opts in by
# setting this env var (the same shape as HARNESS_WORKFLOWS_ENABLED).
_DEPENDENCY_INSTALL_FLAG_ENV = "HARNESS_DEPENDENCY_INSTALL_ENABLED"


def _operator_flags(ctx: ToolContext) -> dict[str, bool]:
    """Operator feature flags for command classes (dependency_install off)."""
    flags = getattr(ctx, "command_flags", None)
    merged = dict(flags) if isinstance(flags, dict) else {}
    merged.setdefault(
        "dependency_install",
        os.environ.get(_DEPENDENCY_INSTALL_FLAG_ENV) in ("1", "true", "True"),
    )
    return merged


def _autonomy_grants_command(ctx: ToolContext) -> bool:
    autonomy = getattr(ctx, "autonomy", None)
    return bool(autonomy and "command.execute" in policy.code_grants(str(autonomy)))


def _record_command(
    ctx: ToolContext, *,
    command_class: str, argv: list[str], cwd: str, exit_code: Optional[int],
    duration_ms: int, output: str, total_chars: int, backend: str,
    decision: dict[str, Any], timed_out: bool = False, truncated: bool = False,
    network: bool = False,
) -> str:
    """Record a command execution (row + ledger). Returns the execution id.

    The ledger entry is the PROOF the answer-path checks against; it is recorded
    only for an ALLOWED execution (a refusal is not evidence a check passed) and
    only when an exit code exists (a killed/timed-out run has none).
    """
    execution_id = ""
    store = getattr(ctx, "code_store", None)
    if store is not None:
        try:
            record = store.record_command_execution(
                run_id=str(getattr(ctx, "run_id", "")), command_class=command_class,
                argv=argv, cwd=cwd, exit_code=exit_code, duration_ms=duration_ms,
                output=output, total_chars=total_chars, sandbox_backend=backend,
                policy_decision=decision, timed_out=timed_out, truncated=truncated,
                network=network,
            )
            execution_id = str(record.get("id") or "")
        except Exception:  # noqa: BLE001 - a record failure must not crash the call
            pass
    ledger = getattr(ctx, "code_ledger", None)
    if ledger is not None and decision.get("allowed") and exit_code is not None:
        try:
            ledger.record(
                command_execution_id=execution_id, command_class=command_class,
                exit_code=int(exit_code), duration_ms=duration_ms, output=output, argv=tuple(argv),
            )
        except Exception:  # noqa: BLE001 - a ledger failure must not break the call
            pass
    return execution_id


def _command_refusal(
    code: str, reason: str, *, command_class: str = "", recovery: str = "",
) -> tuple[str, Any]:
    """A refusal carries BOTH the operator reason and the plain sentence + step."""
    from .commands import refusal_copy  # noqa: PLC0415

    copy = refusal_copy(code)
    plain = copy["reason"]
    step = recovery or copy.get("recovery", "")
    data = {
        "status": "refused", "code": code, "reason": reason, "message": plain,
        "recovery": step, "commandClass": command_class,
    }
    return f"REFUSED ({code}): {plain} {step}".strip(), data


async def command_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    model = CommandRunInput(**_present(args))
    ws = getattr(ctx, "workspace", None)
    if ws is None:
        await emit_code_event(ctx, "command.refused", {
            "commandClass": model.command_class, "code": "WORKSPACE_UNBOUND"})
        _record_command(ctx, command_class=model.command_class, argv=[], cwd="", exit_code=None,
                        duration_ms=0, output="", total_chars=0, backend="unavailable",
                        decision={"allowed": False, "code": "WORKSPACE_UNBOUND"})
        return _command_refusal(
            "WORKSPACE_UNBOUND", "there is no project folder to run a check in",
            command_class=model.command_class,
            recovery="Open a project first, then ask for the check again.",
        )
    if not _autonomy_grants_command(ctx):
        await emit_code_event(ctx, "command.refused", {
            "commandClass": model.command_class, "code": "PROFILE_DENIED"})
        _record_command(ctx, command_class=model.command_class, argv=[], cwd="", exit_code=None,
                        duration_ms=0, output="", total_chars=0, backend="unavailable",
                        decision={"allowed": False, "code": "PROFILE_DENIED"})
        return _command_refusal(
            "PROFILE_DENIED", "this task isn't set up to run checks",
            command_class=model.command_class,
            recovery="Ask for a check in a session that is allowed to run them.",
        )
    # The code workspace must exist (allocate one if the run has not written yet).
    try:
        cw, binding, resolved, _actor = _ensure_code_workspace(ctx)
    except WorkspaceError as exc:
        await emit_code_event(ctx, "command.refused", {
            "commandClass": model.command_class, "code": exc.code})
        return _command_refusal(exc.code, exc.reason, command_class=model.command_class)

    # Resolve the class (unknown / operator-gated / missing executable).
    try:
        command_class = resolve_class(model.command_class, operator_flags=_operator_flags(ctx))
        argv = build_argv(command_class, model.args)
    except CommandUnavailable as exc:
        await emit_code_event(ctx, "command.refused", {
            "commandClass": model.command_class, "code": exc.code})
        _record_command(ctx, command_class=model.command_class, argv=[], cwd=str(resolved.root),
                        exit_code=None, duration_ms=0, output="", total_chars=0,
                        backend="unavailable", decision={"allowed": False, "code": exc.code})
        return _command_refusal(exc.code, exc.reason, command_class=model.command_class)

    # Policy: the class's effect verb must be granted by the profile. The actor
    # is bound to the CODE WORKSPACE id, not the read-only request workspace id.
    actor = _make_actor(cw.id, getattr(ctx, "autonomy", None))
    decision = policy.decide_command(actor, binding, command_class.name, argv)
    if not decision.allowed:
        await emit_code_event(ctx, "command.refused", {
            "commandClass": command_class.name, "code": decision.code})
        _record_command(ctx, command_class=command_class.name, argv=argv, cwd=str(resolved.root),
                        exit_code=None, duration_ms=0, output="", total_chars=0,
                        backend="unavailable", decision={"allowed": False, "code": decision.code},
                        network=command_class.network)
        return _command_refusal(decision.code, decision.reason, command_class=command_class.name)

    spec = sandbox_mod.RunSpec(
        argv=argv, cwd=resolved.root, env=sandbox_mod.build_env(),
        timeout_s=command_class.timeout_s, output_cap_bytes=command_class.output_cap_bytes,
        network=command_class.network,
    )

    # Tier selection: a class that DECLARES network is never run by the local
    # primitive (it cannot contain it). It requires the container tier — and
    # refuses honestly when no container runtime is present. Everything else
    # keeps the local tier exactly as before (W4/ADR-H189).
    try:
        backend = backend_mod.select_for_spec(spec)
    except SandboxUnavailable:
        await emit_code_event(ctx, "command.refused", {
            "commandClass": command_class.name, "code": "SANDBOX_UNAVAILABLE"})
        _record_command(ctx, command_class=command_class.name, argv=argv, cwd=str(resolved.root),
                        exit_code=None, duration_ms=0, output="", total_chars=0,
                        backend="unavailable",
                        decision={"allowed": False, "code": "SANDBOX_UNAVAILABLE"},
                        network=command_class.network)
        return _command_refusal(
            "SANDBOX_UNAVAILABLE", "checks can't be run safely on this computer right now",
            command_class=command_class.name,
            recovery="Run the check on a machine where the runtime can isolate it.",
        )

    await emit_code_event(ctx, "command.started", {
        "commandClass": command_class.name, "timeoutS": command_class.timeout_s})
    raw = await backend.run(spec)
    exit_code = raw.exit_code
    event = "command.killed" if (raw.timed_out or raw.cancelled) else "command.completed"
    await emit_code_event(ctx, event, {
        "commandClass": command_class.name, "exitCode": exit_code,
        "durationMs": raw.duration_ms, "timedOut": raw.timed_out,
        "truncated": raw.truncated, "backend": raw.backend,
    })
    if raw.truncated:
        await emit_code_event(ctx, "command.truncated", {
            "commandClass": command_class.name, "totalChars": raw.total_chars})
    _record_command(
        ctx, command_class=command_class.name, argv=argv, cwd=str(resolved.root),
        exit_code=exit_code, duration_ms=raw.duration_ms, output=raw.output,
        total_chars=raw.total_chars, backend=raw.backend,
        decision={"allowed": True, "code": "OK"}, timed_out=raw.timed_out,
        truncated=raw.truncated, network=command_class.network,
    )
    # Round 3 / W9 (ADR-H297): a command's output is REDACTED before it
    # reaches the model, the run blob or the ledger - the same rule the file
    # reader has followed since Phase 1.
    clean_output, redacted_lines = redact_output(raw.output)
    if redacted_lines:
        await emit_code_event(ctx, "code.output.redacted", {
            "commandClass": command_class.name, "lines": redacted_lines,
        })
    status = "timed_out" if raw.timed_out else ("cancelled" if raw.cancelled else "ok")
    # Round 3 / W9 (ADR-H297): whether the network was actually CONTAINED is
    # published, not assumed. The container tier runs `--network none`, so it
    # contains it; the local tier cannot, and saying so is the honest answer.
    _backend_name = str(getattr(backend, "name", "") or "")
    network_contained = _backend_name == "container"
    header = (
        f"Ran {command_class.name}: exit={exit_code} durationMs={raw.duration_ms} "
        f"truncated={'yes' if raw.truncated else 'no'} totalChars={raw.total_chars}"
        f"{' TIMED OUT' if raw.timed_out else ''}"
    )
    text = header + ("\n" + raw.output if raw.output else "")
    data = {
        "status": status, "commandClass": command_class.name, "argv": argv,
        "cwd": str(resolved.root), "exitCode": exit_code, "durationMs": raw.duration_ms,
        "timedOut": raw.timed_out, "truncated": raw.truncated,
        "totalChars": raw.total_chars, "backend": raw.backend, "output": raw.output,
    }
    return text, data


__all__ = ["command_run"]
