"""Additional Git agent tools — the path-level and long-tail capabilities.

Kept in a separate module from `git/tools.py` so each stays under the harness size
ceiling. These are registered by `git/register.py` on the SAME registry and are
gated by the SAME policy authority + effect authorizer. Read tools are `read`;
mutations are `write` (local) or `external_action` (remote).

Every handler resolves the repository from the run's bound workspace (never model
input) and returns `(text, data)` with the deterministic operation envelope.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .schemas import SCHEMAS
from .tool_support import operation_text, repository_unavailable, resolve_repository, run_of, service_for


def _no_repo(tool: str) -> tuple[str, Any]:
    return ("I can't work with versions here: this folder is not tracked yet.",
            repository_unavailable(tool))


def _outcome(tool: str, outcome: Any) -> tuple[str, Any]:
    return operation_text(outcome), outcome.to_dict()


# ── Handlers ───────────────────────────────────────────────────────────────────

async def _move_path(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_move_path")
    return _outcome("git_move_path", service_for(ctx)._mutate(
        repo, "mv", {"src": args["src"], "dst": args["dst"]}, run_id=run_of(ctx)))


async def _remove_paths(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_remove_paths")
    return _outcome("git_remove_paths", service_for(ctx)._mutate(
        repo, "rm", {"paths": args["paths"], "flags": ["--cached"] if args.get("cached") else []},
        run_id=run_of(ctx)))


async def _restore_paths(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_restore")
    flags = ["--staged"] if args.get("staged") else ["--worktree"]
    return _outcome("git_restore", service_for(ctx)._mutate(
        repo, "restore", {"flags": flags, "paths": args["paths"]}, run_id=run_of(ctx)))


async def _unset_upstream(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_unset_upstream")
    return _outcome("git_unset_upstream", service_for(ctx).unset_upstream(
        repo, branch=args.get("branch"), run_id=run_of(ctx)))


async def _stash_branch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_stash_branch")
    return _outcome("git_stash_branch", service_for(ctx).stash_branch(
        repo, args["name"], ref=args.get("ref"), run_id=run_of(ctx)))


async def _stash_clear(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_stash_clear")
    return _outcome("git_stash_clear", service_for(ctx).stash_clear(repo, run_id=run_of(ctx)))


async def _tag_show(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_tag_show")
    data = service_for(ctx).show_tag(repo, args["name"])
    return (data.get("object", "")[:4000] if data.get("available") else "I can't read that marker here.",
            {"success": bool(data.get("available")), "operation": "tag_show", **data})


async def _worktree_prune(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_worktree_prune")
    return _outcome("git_worktree_prune", service_for(ctx).worktree_prune(repo, run_id=run_of(ctx)))


async def _worktree_move(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_worktree_move")
    return _outcome("git_worktree_move", service_for(ctx).worktree_move(
        repo, args["src"], args["dst"], run_id=run_of(ctx)))


async def _submodule_init(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_submodule_init")
    return _outcome("git_submodule_init", service_for(ctx).submodule_init(
        repo, paths=args.get("paths"), run_id=run_of(ctx)))


async def _submodule_sync(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_submodule_sync")
    return _outcome("git_submodule_sync", service_for(ctx).submodule_sync(
        repo, paths=args.get("paths"), run_id=run_of(ctx)))


async def _lfs_pull(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_lfs_pull")
    return _outcome("git_lfs_pull", service_for(ctx).lfs_pull(repo, remote=args.get("remote"), run_id=run_of(ctx)))


async def _lfs_fetch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx)
    if repo is None:
        return _no_repo("git_lfs_fetch")
    return _outcome("git_lfs_fetch", service_for(ctx).lfs_fetch(repo, remote=args.get("remote"), run_id=run_of(ctx)))


# ── Registration ─────────────────────────────────────────────────────────────

_TOOLS: list[tuple[str, str, Callable, str, str, Optional[str], int]] = [
    ("git_move_path", "Move or rename a tracked file or folder.", _move_path, "write", "medium", "write", 30_000),
    ("git_remove_paths", "Remove tracked files (optionally keeping them on disk).", _remove_paths, "write", "medium", "write", 30_000),
    ("git_restore", "Restore files, discarding their unsaved changes. Prefer setting them aside first.", _restore_paths, "write", "high", "write", 30_000),
    ("git_unset_upstream", "Clear which server branch a local branch follows.", _unset_upstream, "write", "medium", "write", 30_000),
    ("git_stash_branch", "Start a new line of work from a set-aside change.", _stash_branch, "write", "medium", "write", 30_000),
    ("git_stash_clear", "Discard all set-aside changes. Destructive.", _stash_clear, "write", "high", "write", 30_000),
    ("git_tag_show", "Show a version marker's details. Read-only.", _tag_show, "read", "low", None, 20_000),
    ("git_worktree_prune", "Remove stale linked-working-copy records.", _worktree_prune, "write", "medium", "write", 30_000),
    ("git_worktree_move", "Move a linked working copy to another folder inside the project's area.", _worktree_move, "write", "medium", "write", 30_000),
    ("git_submodule_init", "Register nested projects so they can be checked out.", _submodule_init, "write", "medium", "write", 30_000),
    ("git_submodule_sync", "Re-point nested projects at their configured addresses.", _submodule_sync, "write", "medium", "write", 30_000),
    ("git_lfs_fetch", "Download large-file-storage objects without checking them out.", _lfs_fetch, "write", "medium", "external_action", 600_000),
    ("git_lfs_pull", "Download and check out large-file-storage objects.", _lfs_pull, "write", "medium", "external_action", 600_000),
]

EXTRA_GIT_TOOL_NAMES: tuple[str, ...] = tuple(spec[0] for spec in _TOOLS)

# tool → catalog operation (risk classification).
EXTRA_OP_FOR_TOOL: dict[str, str] = {
    "git_move_path": "mv", "git_remove_paths": "rm", "git_restore": "restore",
    "git_unset_upstream": "branch_unset_upstream", "git_stash_branch": "stash_branch",
    "git_stash_clear": "stash_clear", "git_worktree_prune": "worktree_prune",
    "git_worktree_move": "worktree_move", "git_submodule_init": "submodule_init",
    "git_submodule_sync": "submodule_sync", "git_lfs_fetch": "lfs_fetch",
    "git_lfs_pull": "lfs_pull",
}


def register_extra_git_tools(registry: ToolRegistry) -> list[str]:
    from . import safety  # noqa: PLC0415

    added: list[str] = []
    for name, description, handler, permission, risk, effect, timeout_ms in _TOOLS:
        metadata = None
        if effect:
            op = EXTRA_OP_FOR_TOOL.get(name)
            op_risk = safety.assess_risk(op).risk if op else risk
            metadata = {"gitOperation": op or name, "risk": op_risk, "mutating": True}
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=SCHEMAS[name], handler=handler,
            permission=permission, risk=risk, timeout_ms=timeout_ms, effect=effect,
            effect_metadata=metadata,
        ))
        added.append(name)
    return added


__all__ = ["EXTRA_GIT_TOOL_NAMES", "EXTRA_OP_FOR_TOOL", "register_extra_git_tools"]
