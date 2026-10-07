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

    if approvals is None or not workspace_id:
        return code_authorizer

    from .actions import make_code_action_authorizer  # noqa: PLC0415

    action_authorizer = make_code_action_authorizer(approvals, run_id, workspace_id, emitter)

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name.startswith("code_"):
            return bool(await action_authorizer(tool, args, ctx))
        return bool(await code_authorizer(tool, args, ctx))

    return authorize


__all__ = ["build_effect_authorizer"]
