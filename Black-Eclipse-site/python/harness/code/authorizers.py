"""The ONE composition of a run's effect authorizers.

Every non-read tool is authorized through the chain assembled here:

    git (dangerous / remote)  →  terminal / shell (allow|ask|deny)
        →  code write  →  code external action  →  MCP single-use approvals

Each layer is a thin wrapper that falls through to the next for a tool it does
not own, so adding a capability is one line and never touches the others. The
registry refuses every non-read tool when the chain ultimately returns False —
the safe default.

Extracted from `graph.py` so the graph module stays under its size ratchet and
the composition has exactly one home.
"""

from __future__ import annotations

from typing import Any, Optional

from . import policy


def build_effect_authorizer(
    approvals: Optional[Any],
    run_id: str,
    emitter: Any,
    workspace_id: Optional[str] = None,
) -> Optional[Any]:
    """Compose the run's effect authorizer.

    A `workspace_*` write is authorized by the run's autonomy profile; a `code_*`
    external action and a dangerous/remote Git operation require a single-use,
    workspace-bound operator approval; every other non-read tool falls to the MCP
    approvals authorizer. With no store wired every non-read tool is refused.
    """
    from .tools import make_code_authorizer  # noqa: PLC0415

    mcp_authorizer = None
    if approvals is not None:
        from ..mcp.approvals import make_effect_authorizer  # noqa: PLC0415

        mcp_authorizer = make_effect_authorizer(approvals, run_id, emitter)
    code_authorizer = make_code_authorizer(mcp_authorizer)

    # The execution + LOCAL application-runtime families (execute_*, build/test/
    # verify, service control, package/container/compose/runtime starts) run
    # bounded programs and manage local processes. Admitted at this seam exactly
    # like `command_run`: the HANDLER enforces the binding and the `code.execute`
    # grant, and the security gateway still classifies every call. Without this
    # branch they fell through to the MCP authorizer, which refuses any tool
    # without an MCP server id — leaving the tools advertised to code profiles
    # but dead (measured 2026-10-12: execute_python / execute_code /
    # build_project / start_service / package_install all False).
    code_authorizer = _admit_runtime_tools(code_authorizer)

    # Generic terminal: an `allow` command runs, an `ask` command needs a
    # single-use workspace-bound approval, a `deny` is refused.
    from .terminal_tools import make_terminal_authorizer  # noqa: PLC0415

    code_authorizer = make_terminal_authorizer(code_authorizer)
    from .shell_tools import make_shell_authorizer  # noqa: PLC0415

    code_authorizer = make_shell_authorizer(code_authorizer)

    # The terminal subsystem's own tools, classified exactly like the shell tools.
    from ..terminal.tools import make_terminal_tool_authorizer  # noqa: PLC0415

    code_authorizer = make_terminal_tool_authorizer(code_authorizer)

    # The Git subsystem: a local mutation is admitted by the autonomy profile; a
    # dangerous/destructive op or any remote action needs a single-use approval.
    from ..git.approvals import make_git_authorizer  # noqa: PLC0415

    code_authorizer = make_git_authorizer(
        approvals, run_id, workspace_id or "", emitter, inner=code_authorizer,
    )

    # The browser subsystem: an effectful browser tool (run script / CDP / sandbox
    # program / upload / vault / interception) is admitted HERE; the handler's
    # browser POLICY engine enforces the per-permission verdict and routes an ASK
    # through the SAME single-use approval store. Every other non-read tool falls
    # through unchanged.
    from ..browser.authorizers import make_browser_authorizer  # noqa: PLC0415

    code_authorizer = make_browser_authorizer(code_authorizer)

    # The Computer Use Engine: an elevated computer tool (finance mutation, human
    # takeover) is admitted HERE and re-checked in the handler by the COMPUTER
    # POLICY engine and the FINANCE FIREWALL. `computer_use` itself is registered
    # read and gated per-call by the same policy engine.
    from ..computer.authorizers import make_computer_authorizer  # noqa: PLC0415

    code_authorizer = make_computer_authorizer(code_authorizer)

    # The Automation subsystem: the autonomous-schedule tools (bot_create/update/
    # enable/resume) are admitted HERE; the HANDLER claims or requests a single-use
    # operator approval (kind `bot_schedule`) before a schedule is created or
    # started, so an agent cannot quietly put itself on a cadence (R3-07).
    from ..automation.authorizers import make_bot_authorizer  # noqa: PLC0415

    code_authorizer = make_bot_authorizer(code_authorizer)

    if approvals is None or not workspace_id:
        return _wrap_with_security(code_authorizer, run_id, workspace_id)

    from .actions import make_code_action_authorizer  # noqa: PLC0415

    action_authorizer = make_code_action_authorizer(approvals, run_id, workspace_id, emitter)

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name.startswith("code_"):
            return bool(await action_authorizer(tool, args, ctx))
        return bool(await code_authorizer(tool, args, ctx))

    return _wrap_with_security(authorize, run_id, workspace_id)


def _admit_runtime_tools(inner: Any) -> Any:
    """Admit the execution + LOCAL application-runtime families at this seam.

    The handlers enforce the workspace binding and the `code.execute` grant.
    K8s / Helm / Terraform / deploy mutations are deliberately NOT admitted here:
    they are approval-gated per action and stay on the approval path.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name in policy.EXECUTION_WRITE_TOOLS or name in policy.APP_RUNTIME_WRITE_TOOLS:
            return True
        return bool(await inner(tool, args, ctx))

    return authorize


def _wrap_with_security(inner: Any, run_id: str, workspace_id: Optional[str]) -> Any:
    """Route the composed authorizer through the Security Gateway.

    The gateway is additive: it enforces the Security Floor and audits every
    filesystem/shell effect, then delegates to `inner` for the capability's own
    approval semantics. When no gateway is installed, `inner` is returned
    unchanged (the existing authority), never a permissive stub.
    """
    try:
        from ..security.bootstrap import get_gateway  # noqa: PLC0415

        gateway = get_gateway()
        if gateway is None:
            return inner
        from ..security.integration import make_security_authorizer  # noqa: PLC0415

        return make_security_authorizer(
            inner, run_id=run_id, workspace_id=workspace_id, gateway=gateway,
        )
    except Exception:  # noqa: BLE001 - the security layer must never weaken the chain
        return inner


__all__ = ["build_effect_authorizer"]
