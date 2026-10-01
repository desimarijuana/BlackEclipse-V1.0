"""Operator-gated external actions for a code task (Phase 5, approve_external).

An external action — commit, push, open a PR, deploy — is NEVER run on the
model's say-so. It is an effectful tool whose effect class is `external_action`
and whose authorization is a SINGLE-USE approval bound to the exact
(kind, action, workspace, args-digest), reusing the McpApproval store and the
ONE guarded-claim primitive (`mcp.approvals.claim_guarded`). A changed action or
payload requires a new approval; a denial is terminal for that digest.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..mcp.approvals import args_digest

# The approval kind discriminator (one store, two kinds).
CODE_ACTION_KIND = "code_action"

CodeActionKind = Literal["commit", "push", "open_pr", "deploy"]
CODE_ACTION_KINDS: tuple[str, ...] = ("commit", "push", "open_pr", "deploy")


class CodeActionRequest(BaseModel):
    """The exact action an approval is bound to.

    `workspaceId` is part of the canonicalized payload, so an approval for a
    commit in workspace A can NEVER authorize the same commit in workspace B.
    """

    kind: CodeActionKind
    workspaceId: str  # noqa: N815
    argv: list[str] = Field(default_factory=list)
    message: Optional[str] = None        # commit message / PR title
    baseRef: Optional[str] = None        # noqa: N815  PR base
    headRef: Optional[str] = None        # noqa: N815  pushed branch
    runId: str = ""  # noqa: N815


def code_action_digest(request: CodeActionRequest) -> str:
    """sha256 over the canonicalized request INCLUDING the workspace id.

    Reuses `mcp.approvals.args_digest` — the SAME canonicalization — so the two
    kinds can never disagree about what 'the same payload' means.
    """
    payload = {
        "kind": request.kind,
        "workspaceId": request.workspaceId,
        "argv": list(request.argv),
        "message": request.message,
        "baseRef": request.baseRef,
        "headRef": request.headRef,
    }
    return args_digest(payload)


def _request_key(request: CodeActionRequest) -> str:
    """The kind-qualified lookup key (an action kind, not an MCP server)."""
    return f"code:{request.kind}"


def request_code_action(
    approvals: Any, request: CodeActionRequest, *, ttl_seconds: int = 900,
    action_summary: Optional[str] = None, affected_data: Optional[str] = None,
) -> dict[str, Any]:
    """Create (or return the existing pending / terminal denial for) a code-action
    approval. Delegates to the shared store with kind='code_action'."""
    return approvals.request_kind(
        kind=CODE_ACTION_KIND,
        request_key=_request_key(request),
        digest=code_action_digest(request),
        effect="external_action",
        run_id=request.runId or None,
        workspace_id=request.workspaceId,
        action_summary=action_summary,
        affected_data=affected_data,
        ttl_seconds=ttl_seconds,
    )


def consume_code_action(approvals: Any, request: CodeActionRequest) -> Optional[dict[str, Any]]:
    """The authorizing operation. Single-use, via the ONE guarded claim, bound to
    the exact action AND workspace."""
    return approvals.consume_kind(
        kind=CODE_ACTION_KIND,
        request_key=_request_key(request),
        digest=code_action_digest(request),
        workspace_id=request.workspaceId,
    )


def make_code_action_authorizer(
    approvals: Any, run_id: str, workspace_id: str, emitter: Any = None,
):
    """The async authorizer attached to ToolContext when the profile is
    approve_external. Resolves the call to a CodeActionRequest (including the
    workspace id), consumes it ONCE, and otherwise refuses — emitting
    code.action.approval_required / code.action.approved. Uses the same
    two-seam digest-scope trick as the MCP authorizer so a legitimate call is not
    double-consumed."""

    async def authorize(tool: Any, clean_args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        meta = getattr(tool, "effect_metadata", None) or {}
        action_kind = str(meta.get("actionKind") or "")
        if not action_kind or action_kind not in CODE_ACTION_KINDS:
            return False
        request = _request_from_call(action_kind, workspace_id, run_id, clean_args)
        digest = code_action_digest(request)
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True
        claimed = consume_code_action(approvals, request) if approvals is not None else None
        if claimed is not None:
            if ctx is not None:
                try:
                    ctx.effect_authorized_digest = digest
                except Exception:  # noqa: BLE001 - a frozen ctx must not break auth
                    pass
            if emitter is not None:
                await emitter.emit("code.action.approved", {
                    "action": action_kind, "workspaceId": workspace_id,
                    "approvalId": claimed.get("id"), "singleUse": True,
                })
            return True
        # No claimable approval: create/refresh a pending request, then refuse.
        if approvals is not None:
            try:
                pending = request_code_action(approvals, request)
                if emitter is not None:
                    await emitter.emit("code.action.approval_required", {
                        "action": action_kind, "workspaceId": workspace_id,
                        "approvalId": pending.get("id"),
                    })
            except Exception:  # noqa: BLE001 - a store failure must never authorize
                pass
        return False

    return authorize


def _request_from_call(
    action_kind: str, workspace_id: str, run_id: str, clean_args: dict[str, Any],
) -> CodeActionRequest:
    return CodeActionRequest(
        kind=action_kind,  # type: ignore[arg-type]
        workspaceId=workspace_id,
        argv=[str(a) for a in (clean_args.get("argv") or [])],
        message=clean_args.get("message"),
        baseRef=clean_args.get("baseRef"),
        headRef=clean_args.get("headRef"),
        runId=run_id,
    )


__all__ = [
    "CODE_ACTION_KIND",
    "CODE_ACTION_KINDS",
    "CodeActionKind",
    "CodeActionRequest",
    "code_action_digest",
    "consume_code_action",
    "make_code_action_authorizer",
    "request_code_action",
]
