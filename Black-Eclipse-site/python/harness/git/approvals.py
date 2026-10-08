"""The Git effect authorizer.

A LOCAL Git mutation (`effect="write"`) is admitted under the run's autonomy
profile — the allowlist already removed it at `plan_only`. But a mutation whose
catalog risk is `dangerous`/`destructive`/`critical` (a hard reset, a cleanup, a
`-f` branch delete, a rebase, a tag delete) additionally requires a SINGLE-USE
operator approval bound to the exact operation, so the model can never destroy
work on its own initiative.

A REMOTE action (`effect="external_action"`) always requires that approval — the
`approve_external` profile only makes the tool present; it is still claimed once
per call. A force push is `critical` and is never the default.

Approvals reuse the ONE store and the ONE guarded-claim primitive
(`mcp.approvals.claim_guarded`, via `request_kind`/`consume_kind`), keyed as
`kind="git_operation"` with `request_key="git:<tool>"` and a digest of the
workspace + tool + canonicalized args. A changed payload requires a new approval.
"""

from __future__ import annotations

from typing import Any, Optional

from ..mcp.approvals import _mark_authorized, _pause_requested, _await_then_reclaim, args_digest
from . import safety

GIT_APPROVAL_KIND = "git_operation"

# Risk levels that ALWAYS need an explicit approval, even for a local operation.
_APPROVAL_RISKS = frozenset({"dangerous", "destructive", "critical"})


def _operation_risk(tool_name: str, args: dict[str, Any], declared: str) -> str:
    """The risk of THIS call — a force push or a hard reset elevates it.

    `declared` is the ToolDefinition's OWN risk vocabulary (`none`/`low`/`medium`/
    `high`), NOT a Git risk level, so it is never compared against one. The Git
    catalog (with the force-push / hard-reset override) is authoritative.
    """
    force_push = tool_name == "git_push" and (bool(args.get("force")) or bool(args.get("forceWithLease")))
    if tool_name == "git_tag_push" and bool(args.get("force")):
        force_push = True
    hard_reset = tool_name == "git_reset" and str(args.get("mode") or "") == "hard"
    scope = args.get("scope")
    scope_list = [scope] if isinstance(scope, str) else (scope or [])
    global_config = tool_name == "git_config_set" and any(str(s) == "global" or str(s) == "--global" for s in scope_list)
    op = _OP_FOR_TOOL.get(tool_name, tool_name)
    return safety.assess_risk(
        op, force_push=force_push, hard_reset=hard_reset, global_config=global_config,
    ).risk


def needs_approval(tool_name: str, args: dict[str, Any], declared_risk: str, effect: Optional[str]) -> bool:
    if effect == "external_action":
        return True
    return _operation_risk(tool_name, args, declared_risk) in _APPROVAL_RISKS


def _digest(workspace_id: str, tool_name: str, args: dict[str, Any]) -> str:
    payload = {"workspaceId": workspace_id, "tool": tool_name, "args": args}
    return args_digest(payload)


def _summary(tool_name: str, args: dict[str, Any]) -> str:
    label = tool_name.replace("git_", "").replace("vcs_", "").replace("_", " ")
    detail = ""
    for key in ("target", "name", "remote", "message", "number", "mode", "ref"):
        if args.get(key):
            detail = f" ({args[key]})"
            break
    return f"Version-control action: {label}{detail}."


def make_git_authorizer(
    approvals: Any, run_id: str, workspace_id: str, emitter: Any = None,
    inner: Any = None,
):
    """Compose the Git authorizer over `inner` (the code/MCP authorizer)."""

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if not (name.startswith("git_") or name.startswith("vcs_")):
            if inner is not None:
                return bool(await inner(tool, args, ctx))
            return False
        effect = getattr(tool, "effect", None)
        meta = getattr(tool, "effect_metadata", None) or {}
        declared = str(meta.get("risk") or getattr(tool, "risk", "low"))
        if not needs_approval(name, args or {}, declared, effect):
            return True
        if approvals is None:
            return False
        ws_id = str(workspace_id or getattr(getattr(ctx, "workspace", None), "id", "") or "")
        digest = _digest(ws_id, name, args or {})
        # Already authorized for THIS call-scope at an earlier seam.
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True
        # A standing grant may remember a NON-dangerous operation (a remote
        # push/pull), never a destructive one (hard reset, cleanup, force delete).
        op_risk = _operation_risk(name, args or {}, declared)
        grant_pattern = name if op_risk not in _APPROVAL_RISKS else None
        grants = getattr(approvals, "grants", None)
        if grants is not None and grant_pattern and grants.matches("git_operation", ws_id, grant_pattern) is not None:
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("git.action.approved", {"tool": name, "grant": True})
            return True
        claimed = approvals.consume_kind(
            kind=GIT_APPROVAL_KIND, request_key=f"git:{name}", digest=digest,
            workspace_id=ws_id or None,
        )
        if claimed is not None:
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("git.action.approved", {
                    "tool": name, "approvalId": claimed.get("id"), "singleUse": True,
                })
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=GIT_APPROVAL_KIND, request_key=f"git:{name}", digest=digest,
                effect="external_action",
                run_id=run_id, workspace_id=ws_id or None,
                action_summary=_summary(name, args or {}),
                risk=declared,
                grant_kind="git_operation", grant_pattern=grant_pattern, grant_scope=ws_id or None,
            )
            if emitter is not None:
                await emitter.emit("approval.requested", {
                    "approvalId": pending.get("id"), "kind": GIT_APPROVAL_KIND,
                    "title": f"Approve {name.replace('_', ' ')}",
                    "summary": _summary(name, args or {}),
                    "effect": effect or "write", "risk": declared, "tool": name,
                    "workspaceId": ws_id,
                    "grantPattern": grant_pattern,
                    "grantLabel": f"Always allow `{name}` in this workspace" if grant_pattern else None,
                })
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            pass
        if pending is not None and ctx is not None and _pause_requested(ctx):
            await _await_then_reclaim(
                approvals, pending.get("id"),
                lambda: approvals.consume_kind(
                    kind=GIT_APPROVAL_KIND, request_key=f"git:{name}", digest=digest,
                    workspace_id=ws_id or None,
                ),
                emitter, ctx, digest, {"tool": name}, event_type="git.action.approved",
            )
            if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
                return True
        return False

    return authorize


# tool name → catalog operation (mirrors `git.tools._OP_FOR_TOOL`, kept here so
# the authorizer has no import cycle on the tool table).
_OP_FOR_TOOL: dict[str, str] = {
    "git_stage": "add", "git_unstage": "reset_paths", "git_commit": "commit",
    "git_generate_and_commit": "commit", "git_create_branch": "switch",
    "git_checkout": "switch", "git_delete_branch": "branch_delete",
    "git_rename_branch": "branch_rename", "git_set_upstream": "branch_set_upstream",
    "git_merge": "merge", "git_merge_abort": "merge_abort", "git_merge_continue": "merge_continue",
    "git_rebase": "rebase", "git_rebase_plan": "rebase_interactive", "git_rebase_abort": "rebase_abort",
    "git_rebase_continue": "rebase_continue", "git_rebase_skip": "rebase_skip",
    "git_stage_hunks": "apply_cached", "git_unstage_hunks": "apply_cached_reverse",
    "git_apply_patch": "apply_cached",
    "git_cherry_pick": "cherry_pick", "git_cherry_pick_abort": "cherry_pick_abort",
    "git_cherry_pick_continue": "cherry_pick_continue", "git_revert": "revert",
    "git_revert_abort": "revert_abort", "git_revert_continue": "revert_continue",
    "git_reset": "reset", "git_resolve_conflict": "add", "git_stash_push": "stash_push",
    "git_stash_apply": "stash_apply", "git_stash_pop": "stash_pop",
    "git_stash_drop": "stash_drop", "git_tag_create": "tag_create",
    "git_tag_delete": "tag_delete", "git_worktree_add": "worktree_add",
    "git_worktree_remove": "worktree_remove", "git_submodule_update": "submodule_update",
    "git_bisect_start": "bisect_start", "git_bisect_mark": "bisect_good",
    "git_bisect_reset": "bisect_reset", "git_clean": "clean", "git_config_set": "config_set",
    "git_fetch": "fetch", "git_pull": "pull", "git_push": "push",
    "git_remote_add": "remote_add", "git_remote_remove": "remote_remove",
    "git_remote_set_url": "remote_set_url", "git_tag_push": "tag_push",
    "git_abort_operation": "merge_abort", "git_continue_operation": "merge_continue",
    "git_move_path": "mv", "git_remove_paths": "rm", "git_restore": "restore",
    "git_unset_upstream": "branch_unset_upstream", "git_stash_branch": "stash_branch",
    "git_stash_clear": "stash_clear", "git_worktree_prune": "worktree_prune",
    "git_worktree_move": "worktree_move", "git_submodule_init": "submodule_init",
    "git_submodule_sync": "submodule_sync", "git_lfs_fetch": "lfs_fetch",
    "git_lfs_pull": "lfs_pull",
}

__all__ = [
    "GIT_APPROVAL_KIND",
    "make_git_authorizer",
    "needs_approval",
]
