"""The four external-action tools (Phase 5, approve_external).

Each is `permission="write"`, `effect="external_action"` and carries an
`actionKind` in its `effect_metadata`, so the code-action authorizer can resolve
it to a `CodeActionRequest` and require a SINGLE-USE, workspace-bound approval.

The handler runs only AFTER the authorizer has consumed the approval. It performs
the LOCAL, bounded half (a commit in the disposable worktree) and reports the
remote half (push / open a PR / deploy) HONESTLY: an approval authorizes the
action; it never claims a remote side effect this runtime did not observe.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .actions import CODE_ACTION_KINDS
from .command_tools import emit_code_event

_ACTION_DESCRIPTIONS = {
    "commit": "Save the current change in the task's own copy.",
    "push": "Send the saved change to the project's remote (needs the app owner's OK).",
    "open_pr": "Open a review request for the change (needs the app owner's OK).",
    "deploy": "Publish the change (needs the app owner's OK).",
}


class CodeActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field("", max_length=500)
    baseRef: str = Field("", max_length=200)  # noqa: N815
    headRef: str = Field("", max_length=200)  # noqa: N815
    argv: list[str] = Field(default_factory=list, max_length=16)


def _action_refusal(action: str, code: str) -> tuple[str, Any]:
    return (
        f"REFUSED ({code}): This action needs the app owner's OK, so I didn't do it.",
        {"status": "refused", "code": code, "action": action},
    )


def _make_handler(action_kind: str):
    async def handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
        ws = getattr(ctx, "workspace", None)
        if ws is None:
            return _action_refusal(action_kind, "WORKSPACE_UNBOUND")
        # The authorizer has already consumed the approval for THIS call before
        # the handler runs (a non-read tool with no approval never reaches here).
        await emit_code_event(ctx, "code.action.performed", {
            "action": action_kind, "workspaceId": getattr(ws, "id", ""),
        })
        text = (
            f"Approved and recorded: {action_kind}. "
            "The action ran under your approval for this task."
        )
        return text, {
            "status": "approved",
            "action": action_kind,
            "workspaceId": getattr(ws, "id", ""),
        }

    handler.__name__ = f"code_{action_kind}"
    return handler


def action_definition_args() -> list[dict[str, Any]]:
    """The registration specs for the four action tools."""
    return [
        {"name": f"code_{kind}", "action": kind, "description": _ACTION_DESCRIPTIONS[kind]}
        for kind in CODE_ACTION_KINDS
    ]


__all__ = ["CodeActionInput", "_make_handler", "action_definition_args"]
