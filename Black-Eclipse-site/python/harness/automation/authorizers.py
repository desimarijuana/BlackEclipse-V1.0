"""The Automation (bots) subsystem's effect authorizer.

The four tools that can CREATE OR KEEP autonomous work running — `bot_create`,
`bot_update`, `bot_enable`, `bot_resume` — are admitted HERE and their real gate
happens in the handler: before an autonomous schedule is created or started, the
handler claims (or requests, and pauses for) a single-use operator approval of
kind `bot_schedule`. This authorizer exists so those tools participate in the
SAME authorizer chain as the git/terminal/code/browser/computer tools; without
it, the registry would refuse them.

Admission is deliberately unconditional, mirroring `command_run` and the browser
effectful tools: the handler owns the approval semantics, so the chain never
needs to know how a bot is scheduled.
"""

from __future__ import annotations

from typing import Any


def make_bot_authorizer(inner: Any = None):
    """Compose the Automation admission layer over an inner authorizer."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        from ..code.policy import is_automation_effect  # noqa: PLC0415

        name = str(getattr(tool, "name", ""))
        if is_automation_effect(name):
            return True
        if inner is not None:
            return bool(await inner(tool, args, ctx))
        return False

    return authorize


__all__ = ["make_bot_authorizer"]
