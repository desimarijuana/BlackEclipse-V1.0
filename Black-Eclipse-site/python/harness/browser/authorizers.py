"""The browser subsystem's effect authorizer.

Every non-read browser tool is admitted HERE and its real check happens in the
handler's browser POLICY engine. This authorizer exists so the browser effectful
tools participate in the SAME authorizer chain as the git/terminal/code tools:
without it, the registry would refuse a non-read browser tool outright.

The admission is deliberately unconditional (return True for a browser effect
tool): a tool that merely NEEDS a permission can be attempted, and the handler
then enforces the per-permission verdict — including routing an ASK through the
single-use approval store or `browser_request_human`. This mirrors how
`command_run` and the fs write tools are admitted at the seam and re-checked in
the handler.
"""

from __future__ import annotations

from typing import Any


def make_browser_authorizer(inner: Any = None):
    """Compose the browser admission layer over an inner authorizer."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        from ..code.policy import is_browser_effect  # noqa: PLC0415

        name = str(getattr(tool, "name", ""))
        if is_browser_effect(name):
            return True
        if inner is not None:
            return bool(await inner(tool, args, ctx))
        return False

    return authorize


__all__ = ["make_browser_authorizer"]
