"""JSON input schemas for the Git agent tools.

The `ToolRegistry` builds a pydantic arg model from these schemas (types,
required, enum), so the shape here is the wire contract. Handlers re-validate
with their own pydantic model for stricter bounds (mirroring `code/tools.py`).
"""

from __future__ import annotations

from typing import Any

_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_STRS = {"type": "array", "items": {"type": "string"}}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object", "properties": properties, "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


SCHEMAS: dict[str, dict[str, Any]] = {
    # ── Discovery / read ───────────────────────────────────────────────────────
    "git_repository_info": _obj({}),
    "git_list_repositories": _obj({"maxDepth": {**_INT, "description": "How deep to search (1-6, default 3)."}}),
    "git_status": _obj({"full": {**_BOOL, "description": "Return every changed path, not just a summary."}}),
    "git_diff": _obj({
        "base": {**_STR, "description": "Revision to compare against (default: the index)."},
        "paths": _STRS, "contextLines": {**_INT, "description": "Lines of context (0-100)."},
    }),
    "git_diff_cached": _obj({"base": _STR, "paths": _STRS}),
    "git_diff_range": _obj({"from": _STR, "to": _STR, "paths": _STRS}, ["from", "to"]),
    "git_log": _obj({
        "rev": _STR, "maxCount": _INT, "skip": _INT, "author": _STR,
        "since": _STR, "until": _STR, "grep": _STR, "paths": _STRS,
    }),
    "git_show": _obj({"rev": _STR, "stat": _BOOL, "paths": _STRS}, ["rev"]),
    "git_commit_info": _obj({"rev": _STR}, ["rev"]),
    "git_blame": _obj({"path": _STR, "rev": _STR, "startLine": _INT, "endLine": _INT}, ["path"]),
    "git_reflog": _obj({"ref": _STR, "maxCount": _INT}),
    "git_branch_list": _obj({"includeRemote": _BOOL}),
    "git_conflicts": _obj({"path": {**_STR, "description": "Optional single file to expand."}}),
    "git_operation_state": _obj({}),
    "git_stash_list": _obj({}),
    "git_stash_show": _obj({"ref": _STR}),
    "git_tag_list": _obj({}),
    "git_remote_list": _obj({}),
    "git_worktree_list": _obj({}),
    "git_submodule_list": _obj({}),
    "git_config_get": _obj({"key": _STR, "scope": {**_STR, "enum": ["system", "global", "local", "worktree"]}}, ["key"]),
    "git_config_list": _obj({"scope": {**_STR, "enum": ["system", "global", "local", "worktree"]}}),
    "git_hooks": _obj({}),
    "git_lfs_status": _obj({}),
    "git_clean_preview": _obj({"directories": _BOOL}),
    "git_ignore_check": _obj({"path": _STR}, ["path"]),
    "git_generate_commit_message": _obj({"conventional": _BOOL}),
    "git_recovery_options": _obj({}),

    # ── Staging / commit ────────────────────────────────────────────────────────
    "git_stage": _obj({"paths": _STRS, "all": _BOOL}),
    "git_unstage": _obj({"paths": _STRS}),
    "git_list_hunks": _obj({"paths": _STRS}, None),
    "git_stage_hunks": _obj({
        "selection": {"type": "object", "description": "Map of file path to hunk indexes (-1 = all hunks in that file)."},
        "paths": _STRS,
    }, ["selection"]),
    "git_unstage_hunks": _obj({
        "selection": {"type": "object", "description": "Map of file path to hunk indexes to unstage."},
        "paths": _STRS,
    }, ["selection"]),
    "git_apply_patch": _obj({
        "patch": {**_STR, "description": "A unified diff to apply."},
        "toIndex": {**_BOOL, "description": "Apply to the index (stage) rather than the working tree."},
        "reverse": {**_BOOL, "description": "Reverse-apply (undo) the patch."},
    }, ["patch"]),
    "git_rebase_plan": _obj({
        "upstream": _STR,
        "onto": _STR,
        "actions": {
            "type": "array",
            "description": "Steps in final order: {commit, action, message?}.",
            "items": {"type": "object"},
        },
        "autosquash": _BOOL, "autostash": _BOOL,
    }, ["upstream", "actions"]),
    "git_commit": _obj({
        "message": _STR, "amend": _BOOL, "noEdit": _BOOL, "allowEmpty": _BOOL,
        "allowSecrets": _BOOL, "author": _STR,
    }),
    "git_generate_and_commit": _obj({
        "conventional": _BOOL, "allowEmpty": _BOOL, "allowSecrets": _BOOL,
    }),

    # ── Branches / checkout ──────────────────────────────────────────────────────
    "git_create_branch": _obj({"name": _STR, "start": _STR, "checkout": _BOOL}, ["name"]),
    "git_checkout": _obj({"target": _STR, "create": _STR, "detach": _BOOL}),
    "git_delete_branch": _obj({"name": _STR, "force": _BOOL}, ["name"]),
    "git_rename_branch": _obj({"old": _STR, "new": _STR}, ["old"]),
    "git_set_upstream": _obj({"upstream": _STR, "branch": _STR}, ["upstream"]),

    # ── Integration ───────────────────────────────────────────────────────────────
    "git_merge": _obj({"target": _STR, "message": _STR, "noFf": _BOOL, "ffOnly": _BOOL}, ["target"]),
    "git_merge_abort": _obj({}),
    "git_merge_continue": _obj({}),
    "git_rebase": _obj({"upstream": _STR, "onto": _STR, "autosquash": _BOOL, "autostash": _BOOL}, ["upstream"]),
    "git_rebase_abort": _obj({}),
    "git_rebase_continue": _obj({}),
    "git_rebase_skip": _obj({}),
    "git_cherry_pick": _obj({"commits": _STRS, "noCommit": _BOOL}, ["commits"]),
    "git_cherry_pick_abort": _obj({}),
    "git_cherry_pick_continue": _obj({}),
    "git_revert": _obj({"commits": _STRS, "noCommit": _BOOL}, ["commits"]),
    "git_revert_abort": _obj({}),
    "git_revert_continue": _obj({}),
    "git_reset": _obj({"mode": {**_STR, "enum": ["soft", "mixed", "hard"]}, "target": _STR}, ["mode"]),
    "git_resolve_conflict": _obj({"path": _STR, "content": _STR}, ["path", "content"]),
    "git_abort_operation": _obj({}),
    "git_continue_operation": _obj({}),

    # ── Stash / tags ────────────────────────────────────────────────────────────────
    "git_stash_push": _obj({"message": _STR, "includeUntracked": _BOOL, "paths": _STRS}),
    "git_stash_apply": _obj({"ref": _STR, "index": _BOOL}),
    "git_stash_pop": _obj({"ref": _STR, "index": _BOOL}),
    "git_stash_drop": _obj({"ref": _STR}, ["ref"]),
    "git_tag_create": _obj({"name": _STR, "message": _STR, "annotated": _BOOL, "target": _STR}, ["name"]),
    "git_tag_delete": _obj({"names": _STRS, "force": _BOOL}, ["names"]),

    # ── Remote ──────────────────────────────────────────────────────────────────────
    "git_fetch": _obj({"remote": _STR, "branch": _STR, "all": _BOOL, "prune": _BOOL, "tags": _BOOL}),
    "git_pull": _obj({"remote": _STR, "branch": _STR, "strategy": {**_STR, "enum": ["merge", "rebase", "ff-only"]}}),
    "git_push": _obj({
        "remote": _STR, "branch": _STR, "setUpstream": _BOOL,
        "forceWithLease": _BOOL, "force": _BOOL,
    }),
    "git_remote_add": _obj({"name": _STR, "url": _STR}, ["name", "url"]),
    "git_remote_remove": _obj({"name": _STR}, ["name"]),
    "git_remote_set_url": _obj({"name": _STR, "url": _STR}, ["name", "url"]),
    "git_tag_push": _obj({"remote": _STR, "name": _STR, "force": _BOOL}, ["remote", "name"]),

    # ── Advanced ─────────────────────────────────────────────────────────────────────
    "git_worktree_add": _obj({"path": _STR, "branch": _STR, "ref": _STR, "detach": _BOOL}, ["path"]),
    "git_worktree_remove": _obj({"path": _STR, "force": _BOOL}, ["path"]),
    "git_submodule_update": _obj({"remote": _BOOL, "paths": _STRS}),
    "git_bisect_start": _obj({"bad": _STR, "good": _STRS}),
    "git_bisect_mark": _obj({"verdict": {**_STR, "enum": ["good", "bad", "skip"]}, "rev": _STR}, ["verdict"]),
    "git_bisect_reset": _obj({"rev": _STR}),
    "git_clean": _obj({"directories": _BOOL, "confirm": _BOOL}),
    "git_config_set": _obj({"key": _STR, "value": _STR, "scope": {**_STR, "enum": ["global", "local", "worktree"]}}, ["key", "value"]),

    # ── Remote collaboration (VCS providers) ───────────────────────────────────────
    "vcs_status": _obj({}),
    "vcs_list_repositories": _obj({"provider": _STR, "limit": _INT}),
    "vcs_get_repository": _obj({"fullName": _STR}, ["fullName"]),
    "vcs_list_branches": _obj({"fullName": _STR}, ["fullName"]),
    "vcs_list_commits": _obj({"fullName": _STR, "ref": _STR, "limit": _INT}, ["fullName"]),
    "vcs_create_branch": _obj({"fullName": _STR, "name": _STR, "fromSha": _STR}, ["fullName", "name"]),
    "vcs_create_pull_request": _obj({
        "fullName": _STR, "title": _STR, "sourceBranch": _STR, "targetBranch": _STR,
        "description": _STR, "draft": _BOOL,
    }, ["fullName", "title", "sourceBranch", "targetBranch"]),
    "vcs_generate_pull_request": _obj({"base": _STR, "head": _STR, "issue": _STR}),
    "vcs_get_pull_request": _obj({"fullName": _STR, "number": _INT}, ["fullName", "number"]),
    "vcs_list_pull_requests": _obj({"fullName": _STR, "state": {**_STR, "enum": ["open", "closed", "merged"]}, "limit": _INT}, ["fullName"]),
    "vcs_update_pull_request": _obj({
        "fullName": _STR, "number": _INT, "title": _STR, "description": _STR,
        "state": {**_STR, "enum": ["open", "closed"]}, "targetBranch": _STR,
    }, ["fullName", "number"]),
    "vcs_close_pull_request": _obj({"fullName": _STR, "number": _INT}, ["fullName", "number"]),
    "vcs_merge_pull_request": _obj({
        "fullName": _STR, "number": _INT,
        "method": {**_STR, "enum": ["merge", "squash", "rebase"]}, "deleteBranch": _BOOL,
    }, ["fullName", "number"]),
    "vcs_request_review": _obj({"fullName": _STR, "number": _INT, "reviewers": _STRS}, ["fullName", "number", "reviewers"]),
    "vcs_list_reviews": _obj({"fullName": _STR, "number": _INT}, ["fullName", "number"]),
    "vcs_get_review_comments": _obj({"fullName": _STR, "number": _INT}, ["fullName", "number"]),
    "vcs_reply_review_comment": _obj({
        "fullName": _STR, "number": _INT, "commentId": _STR, "body": _STR,
    }, ["fullName", "number", "commentId", "body"]),
    "vcs_ci_status": _obj({"fullName": _STR, "ref": _STR}, ["fullName", "ref"]),
    "vcs_list_workflow_runs": _obj({"fullName": _STR, "ref": _STR, "limit": _INT}, ["fullName"]),
    "vcs_get_job_logs": _obj({"fullName": _STR, "jobId": _STR}, ["fullName", "jobId"]),
    "vcs_rerun_workflow": _obj({"fullName": _STR, "runId": _STR}, ["fullName", "runId"]),
    "vcs_cancel_workflow": _obj({"fullName": _STR, "runId": _STR}, ["fullName", "runId"]),

    # ── Long-tail capabilities (git/tools_extra.py) ──────────────────────────────
    "git_move_path": _obj({"src": _STR, "dst": _STR}, ["src", "dst"]),
    "git_remove_paths": _obj({"paths": _STRS, "cached": _BOOL}, ["paths"]),
    "git_restore": _obj({"paths": _STRS, "staged": _BOOL}, ["paths"]),
    "git_unset_upstream": _obj({"branch": _STR}),
    "git_stash_branch": _obj({"name": _STR, "ref": _STR}, ["name"]),
    "git_stash_clear": _obj({}),
    "git_tag_show": _obj({"name": _STR}, ["name"]),
    "git_worktree_prune": _obj({}),
    "git_worktree_move": _obj({"src": _STR, "dst": _STR}, ["src", "dst"]),
    "git_submodule_init": _obj({"paths": _STRS}),
    "git_submodule_sync": _obj({"paths": _STRS}),
    "git_lfs_fetch": _obj({"remote": _STR}),
    "git_lfs_pull": _obj({"remote": _STR}),
}


__all__ = ["SCHEMAS"]
