"""The Vision subsystem's external-action authorizer.

`image_generate` is a PAID, external provider call. It is advertised to the
finance agent, so without an admission layer it fell through to the MCP authorizer
and was refused (`TOOL_FORBIDDEN`) while advertised — the same advertised-but-dead
defect class the runtime/portfolio families had. It is admitted HERE and requires
a single-use, digest-bound operator approval (kind `vision_external`); a changed
prompt needs a new approval.
"""

from __future__ import annotations

from typing import Any, Optional

from ..code import policy
from ..mcp.approvals import _await_then_reclaim, _mark_authorized, _pause_requested, args_digest

VISION_APPROVAL_KIND = "vision_external"


def make_vision_authorizer(
    approvals: Optional[Any], run_id: str, workspace_id: str = "",
    emitter: Any = None, inner: Any = None,
):
    """Compose the Vision external-action admission + approval layer over `inner`."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in policy.VISION_EXTERNAL_TOOLS:
            if inner is not None:
                return bool(await inner(tool, args, ctx))
            return False
        if approvals is None:
            return False
        digest = args_digest({"tool": name, "args": args or {}})
        request_key = f"vision:{name}"
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True
        claimed = approvals.consume_kind(kind=VISION_APPROVAL_KIND, request_key=request_key, digest=digest)
        if claimed is not None:
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("vision.action.approved", {
                    "tool": name, "approvalId": claimed.get("id"), "singleUse": True,
                })
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=VISION_APPROVAL_KIND, request_key=request_key, digest=digest,
                effect="external_action",
                run_id=run_id, workspace_id=workspace_id or None,
                action_summary=f"Generate an image with {name}",
                risk="medium",
            )
            if emitter is not None:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": VISION_APPROVAL_KIND,
                    "title": f"Approve {name.replace('_', ' ')}",
                    "summary": f"Generate an image with {name}",
                    "effect": "external_action", "risk": "medium", "tool": name,
                })
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            pending = None
        if pending is not None and ctx is not None and _pause_requested(ctx):
            await _await_then_reclaim(
                approvals, pending.get("id"),
                lambda: approvals.consume_kind(
                    kind=VISION_APPROVAL_KIND, request_key=request_key, digest=digest,
                ),
                emitter, ctx, digest, {"tool": name}, event_type="vision.action.approved",
            )
            if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
                return True
        return False

    return authorize


__all__ = ["VISION_APPROVAL_KIND", "make_vision_authorizer"]
