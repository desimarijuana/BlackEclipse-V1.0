"""The Computer Use subsystem's effect authorizer.

An elevated computer tool (a financial mutation via `computer_finance_prepare`, a
human `computer_takeover`) is admitted HERE and its real check happens in the
handler's COMPUTER POLICY engine and the FINANCE FIREWALL. This authorizer exists
so the elevated computer tools participate in the SAME authorizer chain as the
git/terminal/code/browser tools: without it, the registry would refuse them.

Admission is deliberately unconditional for a computer effect tool: the handler
routes an ASK through the single-use approval store and the firewall blocks a
mutation. This mirrors how `command_run` and the browser effectful tools are
admitted at the seam and re-checked in the handler.
"""

from __future__ import annotations

from typing import Any


def make_computer_authorizer(inner: Any = None):
    """Compose the Computer Use admission layer over an inner authorizer."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        from ..code.policy import is_computer_effect  # noqa: PLC0415

        name = str(getattr(tool, "name", ""))
        if is_computer_effect(name):
            return True
        if inner is not None:
            return bool(await inner(tool, args, ctx))
        return False

    return authorize


__all__ = ["make_computer_authorizer"]
