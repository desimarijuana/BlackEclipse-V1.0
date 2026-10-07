"""The Git agent tools — the local Git surface.

`register_git_tools(registry)` exposes the full structured Git capability:

  * read: repository info, status, diff (worktree/cached/range), log, show,
    commit info, blame, reflog, branch list, conflicts, operation state, stash
    list/show, tag list, remotes, worktrees, submodules, config, hooks, LFS,
    clean preview, ignore check, and deterministic message generation;
  * write (local mutation): stage/unstage, commit/amend, branch create/delete/
    rename/set-upstream, checkout, merge/rebase/cherry-pick/revert (+ abort/
    continue/skip), reset, stash, tags, worktree add/remove, submodule update,
    bisect, clean, config set, conflict resolution;
  * external_action: fetch, pull, push, tag push, remote add/remove/set-url.

Every handler resolves the repository from the run's BOUND workspace (never model
input), calls the `GitService`, emits a `git.*` event, and returns
`(text, data)`. A mutating tool is `permission="write"` (effect `write` or
`external_action`); the registry routes it through the Git effect authorizer,
which admits a `safe`/`caution` op under the run's autonomy and requires a
single-use operator approval for a `dangerous`/`destructive`/`critical` op.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from ..code.events import emit_code_event
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import readers
from .executor import run
from .schemas import SCHEMAS
from .service import GitService
from .tool_support import (
    operation_text, repository_unavailable, resolve_repository, resolve_root,
    run_of, service_for,
)

# A conservative default remote/branch when the model omits one.
def _ctx_repo(ctx: ToolContext):
    return resolve_repository(ctx)


def _no_repo(tool: str) -> tuple[str, Any]:
    return (
        "I can't work with versions here: this folder is not tracked yet.",
        repository_unavailable(tool),
    )


async def _emit(ctx: ToolContext, event: str, data: dict[str, Any]) -> None:
    await emit_code_event(ctx, event, data)


def _outcome(tool: str, outcome: Any, extra: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    data = outcome.to_dict()
    if extra:
        data["result"] = {**(data.get("result") or {}), **extra}
    return operation_text(outcome), data


# ── Read handlers ────────────────────────────────────────────────────────────

async def _repository_info(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = service_for(ctx)
    root = resolve_root(ctx)
    if root is None:
        return _no_repo("git_repository_info")
    info = service.info(root)
    if not info.get("is_repository"):
        return _no_repo("git_repository_info")
    branch = info.get("branch") or "(no branch yet)"
    lines = [
        f"Repository: {Path(info['root']).name}",
        f"Branch: {branch}",
        f"Head: {info.get('head') or '(no commits yet)'}",
    ]
    if info.get("bare"):
        lines.append("This is a bare repository (no working files).")
    if info.get("linked_worktree"):
        lines.append("This is a linked worktree.")
    if info.get("operation"):
        lines.append(f"An operation is open: {info['operation'].get('operation')} ({info['operation'].get('status')})")
    await _emit(ctx, "git.repository.bound", {"repository": info["root"], "branch": info.get("branch")})
    return "\n".join(lines), {"success": True, "operation": "repository_info", **info}


async def _list_repositories(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    service = service_for(ctx)
    root = resolve_root(ctx)
    if root is None:
        return _no_repo("git_list_repositories")
    result = service.list_repositories(root, max_depth=int(args.get("maxDepth") or 3))
    lines = [f"{result['count']} repository(ies) found:"]
    lines += [f"  {r}" for r in result["repositories"]]
    return "\n".join(lines), {"success": True, "operation": "list_repositories", **result}


async def _status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_status")
    service = service_for(ctx)
    data = service.status(repo, full=bool(args.get("full")))
    if not data.get("available"):
        return ("I can't read the version state here.", {"success": False, "operation": "status", **data})
    await _emit(ctx, "git.status", {
        "branch": data.get("branch"), "clean": data.get("clean"),
        "staged": len(data.get("staged", [])), "unstaged": len(data.get("unstaged", [])),
        "untracked": len(data.get("untracked", [])), "conflicts": len(data.get("conflicts", [])),
    })
    lines = [f"On branch {data.get('branch') or '(detached)'}"
             + (f" tracking {data['upstream']}" if data.get("upstream") else "")]
    if data.get("ahead") or data.get("behind"):
        lines.append(f"{data.get('ahead', 0)} ahead, {data.get('behind', 0)} behind.")
    counts = data.get("summary") or {}
    if data.get("clean"):
        lines.append("Working tree clean.")
    else:
        lines.append(
            f"{counts.get('staged', 0)} staged, {counts.get('unstaged', 0)} modified, "
            f"{counts.get('untracked', 0)} untracked, {counts.get('conflicts', 0)} conflicted."
        )
    return "\n".join(lines), {**data, "success": True, "operation": "status"}


async def _diff(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_diff")
    data = readers.diff_worktree(repo, base=args.get("base"), paths=args.get("paths"),
                                 context=args.get("contextLines"))
    if not data.get("available"):
        return ("I can't show the change here.", {"success": False, "operation": "diff", **data})
    await _emit(ctx, "git.diff", {"filesChanged": data["files_changed"], "insertions": data["insertions"]})
    text = (f"{data['files_changed']} file(s) changed, +{data['insertions']}/-{data['deletions']}.\n"
            + data["patch"])
    return text, {"success": True, "operation": "diff", **data}


async def _diff_cached(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_diff_cached")
    data = readers.diff_cached(repo, base=args.get("base"), paths=args.get("paths"))
    if not data.get("available"):
        return ("I can't show the staged change here.", {"success": False, "operation": "diff_cached", **data})
    text = (f"{data['files_changed']} file(s) staged, +{data['insertions']}/-{data['deletions']}.\n"
            + data["patch"])
    return text, {"success": True, "operation": "diff_cached", **data}


async def _diff_range(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_diff_range")
    data = readers.diff_range(repo, args["from"], args["to"], paths=args.get("paths"))
    if not data.get("available"):
        return ("I can't compare those versions here.", {"success": False, "operation": "diff_range", **data})
    text = (f"{data['files_changed']} file(s) differ, +{data['insertions']}/-{data['deletions']}.\n"
            + data["patch"])
    return text, {"success": True, "operation": "diff_range", **data}


async def _log(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_log")
    data = readers.log(
        repo, rev=args.get("rev"), max_count=int(args.get("maxCount") or 50),
        skip=int(args.get("skip") or 0), author=args.get("author"), since=args.get("since"),
        until=args.get("until"), grep=args.get("grep"), paths=args.get("paths"),
    )
    if not data.get("available"):
        return ("I can't read the history here.", {"success": False, "operation": "log", **data})
    lines = [f"{data['count']} commit(s):"]
    for commit in data["commits"]:
        lines.append(f"  {commit['short_sha']} {commit['subject']} — {commit['author']}")
    return "\n".join(lines), {"success": True, "operation": "log", **data}


async def _show(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_show")
    data = readers.show(repo, args["rev"], stat=bool(args.get("stat")), paths=args.get("paths"))
    if not data.get("available"):
        return ("I can't show that commit here.", {"success": False, "operation": "show", **data})
    text = f"Commit {data.get('sha', args['rev'])[:12]}\n{data.get('patch', '')}"
    return text, {"success": True, "operation": "show", **data}


async def _commit_info(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_commit_info")
    data = readers.commit_info(repo, args["rev"])
    if not data.get("available"):
        return ("I can't read that commit here.", {"success": False, "operation": "commit_info", **data})
    commit = data.get("commit") or {}
    text = f"{commit.get('short_sha', args['rev'])} {commit.get('subject', '')}"
    return text, {"success": True, "operation": "commit_info", **data}


async def _blame(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_blame")
    data = readers.blame(repo, args["path"], rev=args.get("rev"),
                         start_line=args.get("startLine"), end_line=args.get("endLine"))
    if not data.get("available"):
        return ("I can't read that file's history here.", {"success": False, "operation": "blame", **data})
    lines = [f"{len(data['lines'])} line(s) attributed:"]
    for item in data["lines"][:200]:
        lines.append(f"  {item['line']}: {item['commit'][:8]} {item['author']}")
    return "\n".join(lines), {"success": True, "operation": "blame", **data}


async def _reflog(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_reflog")
    data = readers.reflog(repo, ref=args.get("ref"), max_count=int(args.get("maxCount") or 50))
    if not data.get("available"):
        return ("I can't read the reference history here.", {"success": False, "operation": "reflog", **data})
    return f"{len(data['entries'])} reference update(s).", {"success": True, "operation": "reflog", **data}


async def _branch_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_branch_list")
    include_remote = args.get("includeRemote")
    data = readers.branches(repo, include_remote=True if include_remote is None else bool(include_remote))
    if not data.get("available"):
        return ("I can't list the branches here.", {"success": False, "operation": "branch_list", **data})
    lines = ["Local branches:"]
    for b in data["branches"]:
        mark = "*" if b.get("current") else " "
        track = f" → {b['upstream']}" if b.get("upstream") else ""
        lines.append(f"  {mark} {b['name']}{track}")
    if data.get("remoteBranches"):
        lines.append("Remote branches:")
        lines += [f"  {b['name']}" for b in data["remoteBranches"]]
    return "\n".join(lines), {"success": True, "operation": "branch_list", **data}


async def _conflicts(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_conflicts")
    data = readers.conflicts(repo)
    if args.get("path"):
        data = {**data, "blocks": {args["path"]: data["blocks"].get(args["path"], [])}}
    if not data["conflictedFiles"]:
        return "No conflicts right now.", {"success": True, "operation": "conflicts", **data}
    lines = [f"{data['count']} file(s) with conflicts:"]
    for rel in data["conflictedFiles"]:
        blocks = data["blocks"].get(rel) or []
        lines.append(f"  {rel} ({len(blocks)} conflict(s))")
    return "\n".join(lines), {"success": True, "operation": "conflicts", **data}


async def _operation_state(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_operation_state")
    data = readers.operation_state(repo)
    if data.get("operation") is None:
        return "No multi-step operation is open.", {"success": True, "operation": "operation_state", **data}
    return (f"{data['operation']} is open ({data['status']}).",
            {"success": True, "operation": "operation_state", **data})


async def _stash_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_stash_list")
    data = _stash_list_impl(repo)
    lines = [f"{data['count']} stash(es):"] + [f"  {s['selector']} {s['subject']}" for s in data["stashes"]]
    return "\n".join(lines), {"success": True, "operation": "stash_list", **data}


def _stash_list_impl(repo) -> dict[str, Any]:
    result = run(repo.root, "stash_list")
    stashes: list[dict[str, Any]] = []
    if result.ok:
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\x00")
            if len(parts) >= 4:
                stashes.append({"selector": parts[0], "sha": parts[1], "subject": parts[2], "date": parts[3]})
    return {"available": result.ok, "stashes": stashes, "count": len(stashes)}


async def _stash_show(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_stash_show")
    result = run(repo.root, "stash_show", {"ref": args.get("ref")})
    if not result.ok:
        return ("I can't show that stash here.",
                {"success": False, "operation": "stash_show",
                 "error": (result.error.to_dict() if result.error else {"code": "GIT_FAILED"})})
    return result.stdout[:4000], {"success": True, "operation": "stash_show",
                                  "patch": result.stdout, "truncated": result.truncated}


async def _tag_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_tag_list")
    data = readers.tags(repo)
    lines = [f"{len(data.get('tags', []))} tag(s):"] + [f"  {t['name']}" for t in data.get("tags", [])]
    return "\n".join(lines), {"success": True, "operation": "tag_list", **data}


async def _remote_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_remote_list")
    data = readers.remotes(repo)
    lines = [f"{len(data.get('remotes', []))} remote(s):"]
    for r in data.get("remotes", []):
        lines.append(f"  {r['name']} {r.get('fetchUrl') or '(no url)'}")
    return "\n".join(lines), {"success": True, "operation": "remote_list", **data}


async def _worktree_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_worktree_list")
    data = readers.worktrees(repo)
    return f"{len(data.get('worktrees', []))} worktree(s).", {"success": True, "operation": "worktree_list", **data}


async def _submodule_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_submodule_list")
    data = readers.submodules(repo)
    return f"{len(data.get('submodules', []))} submodule(s).", {"success": True, "operation": "submodule_list", **data}


async def _config_get(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_config_get")
    scope = [f"--{args['scope']}"] if args.get("scope") else []
    result = run(repo.root, "config_get", {"key": args["key"], "scope": scope})
    if not result.ok:
        return (f"No value for {args['key']}.",
                {"success": True, "operation": "config_get", "key": args["key"], "value": None})
    return f"{args['key']} = {result.stdout.strip()[:400]}", {
        "success": True, "operation": "config_get", "key": args["key"], "value": result.stdout.strip()[:400],
    }


async def _config_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_config_list")
    scope = [f"--{args['scope']}"] if args.get("scope") else []
    data = readers.config(repo, scope=scope)
    return f"{len(data.get('entries', []))} config entries.", {"success": True, "operation": "config_list", **data}


async def _hooks(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_hooks")
    data = readers.hooks(repo)
    return f"{len(data.get('hooks', []))} active hook(s).", {"success": True, "operation": "hooks", **data}


async def _lfs_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_lfs_status")
    data = readers.lfs_status(repo)
    return f"Large-file storage used: {data.get('usesLfs')}.", {"success": True, "operation": "lfs_status", **data}


async def _clean_preview(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_clean_preview")
    data = service_for(ctx).clean_preview(repo, directories=bool(args.get("directories")))
    if not data.get("available"):
        return ("I can't preview cleanup here.", {"success": False, "operation": "clean_preview", **data})
    lines = ["Would delete:"] + [f"  {p}" for p in data["wouldDelete"]]
    if not data["wouldDelete"]:
        lines = ["Nothing to clean."]
    return "\n".join(lines), {"success": True, "operation": "clean_preview", **data}


async def _ignore_check(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_ignore_check")
    data = readers.ignore_check(repo, args["path"])
    return (f"{args['path']} is {'ignored' if data['ignored'] else 'not ignored'}.",
            {"success": True, "operation": "ignore_check", **data})


async def _generate_commit_message(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_generate_commit_message")
    data = service_for(ctx).generate_commit_message(repo, conventional=args.get("conventional"))
    return data["message"], {"success": True, "operation": "generate_commit_message", **data}


async def _recovery_options(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_recovery_options")
    from .recovery import recovery_options  # noqa: PLC0415

    data = recovery_options(repo).to_dict()
    return f"{len(data['operations'])} option(s) available.", {
        "success": True, "operation": "recovery_options", **data}


# ── Mutation handlers ─────────────────────────────────────────────────────────

def _mutate_handler(tool: str, method: str, *, wrap: Optional[Callable[[dict], dict]] = None):
    async def handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
        repo = _ctx_repo(ctx)
        if repo is None:
            return _no_repo(tool)
        service: GitService = service_for(ctx)
        call_args = wrap(args) if wrap is not None else args
        outcome = getattr(service, method)(repo, run_id=run_of(ctx), **call_args)
        await _emit(ctx, f"git.{method}", {
            "success": outcome.success,
            "operation": outcome.operation,
            "error": (outcome.error or {}).get("code"),
        })
        return _outcome(tool, outcome)
    handler.__name__ = tool
    return handler


async def _stage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_stage")
    outcome = service_for(ctx).stage(repo, args.get("paths") or [], all=bool(args.get("all")), run_id=run_of(ctx))
    return _outcome("git_stage", outcome)


async def _unstage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_unstage")
    outcome = service_for(ctx).unstage(repo, args.get("paths"), run_id=run_of(ctx))
    return _outcome("git_unstage", outcome)


async def _list_hunks(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_list_hunks")
    data = service_for(ctx).list_hunks(repo, args.get("paths"))
    if not data.get("available"):
        return ("I can't read the change to list its parts here.", {"success": False, "operation": "list_hunks", **data})
    lines = [f"{data.get('fileCount', 0)} file(s), {data.get('hunkCount', 0)} change part(s):"]
    for f in data.get("files", []):
        lines.append(f"  {f['path']} ({f['hunks']} part(s): indexes {f['hunkIndexes']})")
    return "\n".join(lines), {"success": True, "operation": "list_hunks", **data}


async def _stage_hunks(args: dict[str, Any], ctx: ToolContext, *, reverse: bool = False) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    tool = "git_unstage_hunks" if reverse else "git_stage_hunks"
    if repo is None:
        return _no_repo(tool)
    selection = args.get("selection") or {}
    if not isinstance(selection, dict):
        return (f"REFUSED (INVALID_ARGUMENT): the selection must map files to part indexes.",
                {"success": False, "operation": tool,
                 "error": {"code": "INVALID_ARGUMENT", "message": "selection must be an object.", "recoverable": False, "files": []}})
    parsed = {str(k): [int(i) for i in (v or [])] for k, v in selection.items()}
    service = service_for(ctx)
    if reverse:
        outcome = service.unstage_hunks(repo, parsed, paths=args.get("paths"), run_id=run_of(ctx))
    else:
        outcome = service.stage_hunks(repo, parsed, paths=args.get("paths"), run_id=run_of(ctx))
    return _outcome(tool, outcome)


async def _stage_hunks_fwd(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _stage_hunks(args, ctx, reverse=False)


async def _stage_hunks_rev(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _stage_hunks(args, ctx, reverse=True)


async def _apply_patch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_apply_patch")
    to_index = args.get("toIndex")
    outcome = service_for(ctx).apply_patch(
        repo, args["patch"], to_index=True if to_index is None else bool(to_index),
        reverse=bool(args.get("reverse")), run_id=run_of(ctx))
    return _outcome("git_apply_patch", outcome)


async def _rebase_plan(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_rebase_plan")
    actions = args.get("actions") or []
    if not isinstance(actions, list):
        return ("REFUSED (INVALID_ARGUMENT): actions must be a list of steps.",
                {"success": False, "operation": "rebase_plan",
                 "error": {"code": "INVALID_ARGUMENT", "message": "actions must be a list.", "recoverable": False, "files": []}})
    outcome = service_for(ctx).rebase_plan(
        repo, args["upstream"], actions, onto=args.get("onto"),
        autosquash=bool(args.get("autosquash")), autostash=bool(args.get("autostash")),
        run_id=run_of(ctx))
    return _outcome("git_rebase_plan", outcome)


async def _commit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_commit")
    outcome = service_for(ctx).commit(
        repo, args.get("message") or "", amend=bool(args.get("amend")),
        no_edit=bool(args.get("noEdit")), allow_empty=bool(args.get("allowEmpty")),
        allow_secrets=bool(args.get("allowSecrets")), author=args.get("author"), run_id=run_of(ctx),
    )
    await _emit(ctx, "git.commit", {"success": outcome.success, "commit": (outcome.result or {}).get("commit")})
    return _outcome("git_commit", outcome)


async def _generate_and_commit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_generate_and_commit")
    service = service_for(ctx)
    generated = service.generate_commit_message(repo, conventional=args.get("conventional"))
    outcome = service.commit(
        repo, generated["message"], allow_empty=bool(args.get("allowEmpty")),
        allow_secrets=bool(args.get("allowSecrets")), run_id=run_of(ctx),
    )
    return _outcome("git_generate_and_commit", outcome, extra={"generatedMessage": generated["message"]})


async def _create_branch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_create_branch")
    checkout = args.get("checkout")
    outcome = service_for(ctx).create_branch(
        repo, args["name"], start=args.get("start"),
        checkout=True if checkout is None else bool(checkout), run_id=run_of(ctx),
    )
    return _outcome("git_create_branch", outcome)


async def _checkout(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_checkout")
    outcome = service_for(ctx).checkout(
        repo, args.get("target"), create=args.get("create"),
        detach=bool(args.get("detach")), run_id=run_of(ctx),
    )
    return _outcome("git_checkout", outcome)


async def _delete_branch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_delete_branch")
    outcome = service_for(ctx).delete_branch(
        repo, args["name"], force=bool(args.get("force")), run_id=run_of(ctx))
    return _outcome("git_delete_branch", outcome)


async def _rename_branch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_rename_branch")
    outcome = service_for(ctx).rename_branch(repo, args["old"], args.get("new"), run_id=run_of(ctx))
    return _outcome("git_rename_branch", outcome)


async def _set_upstream(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_set_upstream")
    outcome = service_for(ctx).set_upstream(repo, args["upstream"], branch=args.get("branch"), run_id=run_of(ctx))
    return _outcome("git_set_upstream", outcome)


async def _merge(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_merge")
    outcome = service_for(ctx).merge(
        repo, args["target"], message=args.get("message"),
        no_ff=bool(args.get("noFf")), ff_only=bool(args.get("ffOnly")), run_id=run_of(ctx))
    return _outcome("git_merge", outcome)


async def _rebase(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_rebase")
    outcome = service_for(ctx).rebase(
        repo, args["upstream"], onto=args.get("onto"),
        autosquash=bool(args.get("autosquash")), autostash=bool(args.get("autostash")), run_id=run_of(ctx))
    return _outcome("git_rebase", outcome)

async def _cherry_pick(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_cherry_pick")
    outcome = service_for(ctx).cherry_pick(
        repo, args["commits"], no_commit=bool(args.get("noCommit")), run_id=run_of(ctx))
    return _outcome("git_cherry_pick", outcome)


async def _revert(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_revert")
    outcome = service_for(ctx).revert(
        repo, args["commits"], no_commit=bool(args.get("noCommit")), run_id=run_of(ctx))
    return _outcome("git_revert", outcome)


async def _reset(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_reset")
    mode = args.get("mode", "mixed")
    if mode == "hard" and not args.get("confirm"):
        return ("Hard reset can discard work and needs explicit confirmation (confirm=true).",
                {"success": False, "operation": "reset",
                 "error": {"code": "DESTRUCTIVE_REQUIRES_AUTHORIZATION", "message": "Hard reset needs confirmation.",
                           "recoverable": False, "files": []}})
    outcome = service_for(ctx).reset(repo, mode, target=args.get("target"), run_id=run_of(ctx))
    return _outcome("git_reset", outcome)


async def _resolve_conflict(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_resolve_conflict")
    outcome = service_for(ctx).resolve_conflict(repo, args["path"], args["content"], run_id=run_of(ctx))
    return _outcome("git_resolve_conflict", outcome)


async def _stash_push(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_stash_push")
    outcome = service_for(ctx).stash_push(
        repo, message=args.get("message"), include_untracked=bool(args.get("includeUntracked")),
        paths=args.get("paths"), run_id=run_of(ctx))
    return _outcome("git_stash_push", outcome)


async def _stash_apply_pop(args: dict[str, Any], ctx: ToolContext, *, pop: bool) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    tool = "git_stash_pop" if pop else "git_stash_apply"
    if repo is None:
        return _no_repo(tool)
    outcome = service_for(ctx).stash_apply(repo, args.get("ref") or "stash@{0}", pop=pop, run_id=run_of(ctx))
    return _outcome(tool, outcome)


async def _stash_apply(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _stash_apply_pop(args, ctx, pop=False)


async def _stash_pop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _stash_apply_pop(args, ctx, pop=True)


async def _stash_drop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_stash_drop")
    outcome = service_for(ctx).stash_drop(repo, args["ref"], run_id=run_of(ctx))
    return _outcome("git_stash_drop", outcome)


async def _tag_create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_tag_create")
    outcome = service_for(ctx).tag_create(
        repo, args["name"], message=args.get("message"), annotated=bool(args.get("annotated")),
        target=args.get("target"), run_id=run_of(ctx))
    return _outcome("git_tag_create", outcome)


async def _tag_delete(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_tag_delete")
    outcome = service_for(ctx).tag_delete(repo, args["names"], force=bool(args.get("force")), run_id=run_of(ctx))
    return _outcome("git_tag_delete", outcome)


async def _fetch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_fetch")
    outcome = service_for(ctx).fetch(
        repo, remote=args.get("remote"), branch=args.get("branch"),
        all=bool(args.get("all")), prune=bool(args.get("prune")), tags=bool(args.get("tags")),
        run_id=run_of(ctx))
    return _outcome("git_fetch", outcome)


async def _pull(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_pull")
    outcome = service_for(ctx).pull(
        repo, remote=args.get("remote"), branch=args.get("branch"),
        strategy=args.get("strategy") or "merge", run_id=run_of(ctx))
    return _outcome("git_pull", outcome)


async def _push(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_push")
    force = bool(args.get("force"))
    outcome = service_for(ctx).push(
        repo, remote=args.get("remote"), branch=args.get("branch"),
        set_upstream=bool(args.get("setUpstream")),
        force_with_lease=bool(args.get("forceWithLease")), force=force, run_id=run_of(ctx))
    return _outcome("git_push", outcome)


async def _remote_add(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_remote_add")
    outcome = service_for(ctx).remote_add(repo, args["name"], args["url"], run_id=run_of(ctx))
    return _outcome("git_remote_add", outcome)


async def _remote_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_remote_remove")
    outcome = service_for(ctx).remote_remove(repo, args["name"], run_id=run_of(ctx))
    return _outcome("git_remote_remove", outcome)


async def _remote_set_url(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_remote_set_url")
    outcome = service_for(ctx).remote_set_url(repo, args["name"], args["url"], run_id=run_of(ctx))
    return _outcome("git_remote_set_url", outcome)


async def _tag_push(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_tag_push")
    outcome = service_for(ctx)._mutate(
        repo, "tag_push",
        {"remote": args["remote"], "name": args["name"], "force": "true" if args.get("force") else None},
        run_id=run_of(ctx), network=True, force_push=bool(args.get("force")),
        post=lambda r: {"pushed": args["name"]},
    )
    return _outcome("git_tag_push", outcome)


async def _worktree_add(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_worktree_add")
    outcome = service_for(ctx).worktree_add(
        repo, args["path"], branch=args.get("branch"), ref=args.get("ref"),
        detach=bool(args.get("detach")), run_id=run_of(ctx))
    return _outcome("git_worktree_add", outcome)


async def _worktree_remove(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_worktree_remove")
    outcome = service_for(ctx).worktree_remove(
        repo, args["path"], force=bool(args.get("force")), run_id=run_of(ctx))
    return _outcome("git_worktree_remove", outcome)


async def _submodule_update(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_submodule_update")
    outcome = service_for(ctx).submodule_update(
        repo, remote=bool(args.get("remote")), paths=args.get("paths"), run_id=run_of(ctx))
    return _outcome("git_submodule_update", outcome)


async def _bisect_start(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_bisect_start")
    outcome = service_for(ctx).bisect_start(
        repo, bad=args.get("bad"), good=args.get("good"), run_id=run_of(ctx))
    return _outcome("git_bisect_start", outcome)


async def _bisect_mark(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_bisect_mark")
    outcome = service_for(ctx).bisect_mark(
        repo, args["verdict"], rev=args.get("rev"), run_id=run_of(ctx))
    return _outcome("git_bisect_mark", outcome)


async def _bisect_reset(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_bisect_reset")
    outcome = service_for(ctx).bisect_reset(repo, rev=args.get("rev"), run_id=run_of(ctx))
    return _outcome("git_bisect_reset", outcome)


async def _clean(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_clean")
    if not args.get("confirm"):
        preview = service_for(ctx).clean_preview(repo, directories=bool(args.get("directories")))
        return ("Cleanup deletes untracked files and needs confirmation (confirm=true). Preview included.",
                {"success": False, "operation": "clean",
                 "error": {"code": "DESTRUCTIVE_REQUIRES_AUTHORIZATION",
                           "message": "Cleanup needs confirmation.", "recoverable": False, "files": []},
                 "preview": preview.get("wouldDelete", [])})
    outcome = service_for(ctx).clean(repo, directories=bool(args.get("directories")), run_id=run_of(ctx))
    return _outcome("git_clean", outcome)


async def _config_set(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_config_set")
    outcome = service_for(ctx).config_set(repo, args["key"], args["value"], scope=args.get("scope"), run_id=run_of(ctx))
    return _outcome("git_config_set", outcome)


# ── Operation continue/abort dispatch ─────────────────────────────────────────

async def _abort_operation(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_abort_operation")
    from . import state as state_mod  # noqa: PLC0415

    active = state_mod.active_operation(repo)
    if active is None or active.operation is None:
        return ("There is no operation to abort.",
                {"success": False, "operation": "abort_operation",
                 "error": {"code": "NO_OPERATION_IN_PROGRESS",
                           "message": "There is no operation to abort.", "recoverable": False, "files": []}})
    method = {
        "merge": "merge_abort", "rebase": "rebase_abort",
        "cherry_pick": "cherry_pick_abort", "revert": "revert_abort",
    }.get(active.operation)
    if method is None:
        # A bisect ends with `reset`.
        outcome = service_for(ctx).bisect_reset(repo, run_id=run_of(ctx))
    else:
        outcome = getattr(service_for(ctx), method)(repo, run_id=run_of(ctx))
    return _outcome("git_abort_operation", outcome, extra={"aborted": active.operation})


async def _continue_operation(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = _ctx_repo(ctx)
    if repo is None:
        return _no_repo("git_continue_operation")
    from . import state as state_mod  # noqa: PLC0415

    active = state_mod.active_operation(repo)
    if active is None or active.operation is None:
        return ("There is no operation to continue.",
                {"success": False, "operation": "continue_operation",
                 "error": {"code": "NO_OPERATION_IN_PROGRESS",
                           "message": "There is no operation to continue.", "recoverable": False, "files": []}})
    if active.conflicts:
        return ("Resolve the conflicts first, then continue.",
                {"success": False, "operation": "continue_operation",
                 "error": {"code": "UNMERGED_PATHS",
                           "message": "Conflicts remain.", "recoverable": True,
                           "files": list(active.conflicted_files)}})
    method = {
        "merge": "merge_continue", "rebase": "rebase_continue",
        "cherry_pick": "cherry_pick_continue", "revert": "revert_continue",
    }.get(active.operation)
    if method is None:
        return ("There is nothing to continue for this operation.",
                {"success": False, "operation": "continue_operation",
                 "error": {"code": "NO_OPERATION_IN_PROGRESS",
                           "message": "Nothing to continue.", "recoverable": False, "files": []}})
    outcome = getattr(service_for(ctx), method)(repo, run_id=run_of(ctx))
    return _outcome("git_continue_operation", outcome, extra={"continued": active.operation})


# ── Registration ─────────────────────────────────────────────────────────────


def _definition(name: str, description: str, handler: Callable, *,
                permission: str = "read", risk: str = "low", effect: Optional[str] = None,
                timeout_ms: int = 30_000, metadata: Optional[dict[str, Any]] = None) -> ToolDefinition:
    return ToolDefinition(
        name=name, description=description, input_schema=SCHEMAS[name], handler=handler,
        permission=permission, risk=risk, timeout_ms=timeout_ms, effect=effect,
        effect_metadata=metadata,
    )


# A table of (name, description, handler, permission, risk, effect, ms) for the
# tools. Mutating handlers declare effect="write"; remote handlers declare
# effect="external_action".
_TOOL_TABLE: list[tuple[str, str, Callable, str, str, Optional[str], int]] = [
    # Reads
    ("git_repository_info", "Report which project folder this is: its root, current branch, saved revision, and whether a merge/rebase is open. Read-only.", _repository_info, "read", "low", None, 15_000),
    ("git_list_repositories", "Find project folders that track versions under the current one. Read-only.", _list_repositories, "read", "low", None, 20_000),
    ("git_status", "Report the structured state of the project: current branch, ahead/behind, staged, modified, untracked and conflicted files. Read-only.", _status, "read", "low", None, 15_000),
    ("git_diff", "Show the change in the working files (or against a base) as a unified change plus counts. Read-only.", _diff, "read", "low", None, 30_000),
    ("git_diff_cached", "Show what is currently chosen to save (staged) as a unified change plus counts. Read-only.", _diff_cached, "read", "low", None, 30_000),
    ("git_diff_range", "Compare two saved revisions as a unified change plus counts. Read-only.", _diff_range, "read", "low", None, 30_000),
    ("git_log", "Read the saved history of the project, newest first, with filters. Read-only.", _log, "read", "low", None, 20_000),
    ("git_show", "Show one saved revision: its message and its change. Read-only.", _show, "read", "low", None, 20_000),
    ("git_commit_info", "Report one saved revision's details, files and counts. Read-only.", _commit_info, "read", "low", None, 20_000),
    ("git_blame", "Report which revision and author last changed each line of a file. Read-only.", _blame, "read", "low", None, 30_000),
    ("git_reflog", "Read the reference update history — where the project has pointed recently. Read-only.", _reflog, "read", "low", None, 15_000),
    ("git_branch_list", "List the project's lines of work (local and remote) with tracking. Read-only.", _branch_list, "read", "low", None, 15_000),
    ("git_conflicts", "List files that still disagree, with each conflict's blocks. Read-only.", _conflicts, "read", "low", None, 20_000),
    ("git_operation_state", "Report whether a multi-step operation (merge/rebase/cherry-pick/revert/bisect) is open. Read-only.", _operation_state, "read", "low", None, 15_000),
    ("git_stash_list", "List set-aside changes. Read-only.", _stash_list, "read", "low", None, 15_000),
    ("git_stash_show", "Show a set-aside change's contents. Read-only.", _stash_show, "read", "low", None, 15_000),
    ("git_tag_list", "List version markers. Read-only.", _tag_list, "read", "low", None, 15_000),
    ("git_remote_list", "List the configured servers, with any sign-in details removed. Read-only.", _remote_list, "read", "low", None, 15_000),
    ("git_worktree_list", "List the linked working copies of the project. Read-only.", _worktree_list, "read", "low", None, 15_000),
    ("git_submodule_list", "List nested projects and their state. Read-only.", _submodule_list, "read", "low", None, 15_000),
    ("git_config_get", "Read one git setting. Read-only.", _config_get, "read", "low", None, 15_000),
    ("git_config_list", "List git settings, with sign-in details removed. Read-only.", _config_list, "read", "low", None, 15_000),
    ("git_hooks", "Report which project scripts would run on a version action. Read-only.", _hooks, "read", "low", None, 15_000),
    ("git_lfs_status", "Report whether the project uses large-file storage. Read-only.", _lfs_status, "read", "low", None, 15_000),
    ("git_clean_preview", "Preview which untracked files a cleanup would delete. Read-only.", _clean_preview, "read", "low", None, 15_000),
    ("git_ignore_check", "Report whether a path is ignored. Read-only.", _ignore_check, "read", "low", None, 15_000),
    ("git_generate_commit_message", "Draft a commit message from the chosen changes. Read-only.", _generate_commit_message, "read", "low", None, 15_000),
    ("git_recovery_options", "List the honest options for recovering from the current state. Read-only.", _recovery_options, "read", "low", None, 15_000),
    # Local mutations
    ("git_stage", "Choose files to include in the next saved revision. A file list, or all.", _stage, "write", "medium", "write", 30_000),
    ("git_unstage", "Take files back out of the next saved revision. Keeps the working files.", _unstage, "write", "medium", "write", 30_000),
    ("git_list_hunks", "List the individual parts (hunks) of the current changes, so you can choose some and not others. Read-only.", _list_hunks, "read", "low", None, 30_000),
    ("git_stage_hunks", "Choose only specific parts of a file's changes for the next saved revision (no terminal needed).", _stage_hunks_fwd, "write", "medium", "write", 30_000),
    ("git_unstage_hunks", "Take only specific parts of a file's changes back out of the next saved revision.", _stage_hunks_rev, "write", "medium", "write", 30_000),
    ("git_apply_patch", "Apply a unified change (a patch) to the chosen changes or the working files, after checking every path is inside the project.", _apply_patch, "write", "medium", "write", 30_000),
    ("git_commit", "Save the chosen changes as a new revision. Warns about secrets and large files first.", _commit, "write", "medium", "write", 30_000),
    ("git_generate_and_commit", "Draft a message from the chosen changes and save them in one step.", _generate_and_commit, "write", "medium", "write", 30_000),
    ("git_create_branch", "Start a new line of work, optionally switching to it.", _create_branch, "write", "medium", "write", 30_000),
    ("git_checkout", "Switch to a line of work, or create one. Refuses when it would overwrite unsaved work.", _checkout, "write", "medium", "write", 30_000),
    ("git_delete_branch", "Delete a line of work.", _delete_branch, "write", "high", "write", 30_000),
    ("git_rename_branch", "Rename a line of work.", _rename_branch, "write", "medium", "write", 30_000),
    ("git_set_upstream", "Record which server branch a local branch follows.", _set_upstream, "write", "medium", "write", 30_000),
    ("git_merge", "Combine another line of work into the current one; reports conflicts structurally.", _merge, "write", "high", "write", 60_000),
    ("git_merge_abort", "Undo an in-progress merge, restoring the state before it.", _mutate_handler("git_merge_abort", "merge_abort"), "write", "high", "write", 30_000),
    ("git_merge_continue", "Finish a merge after resolving its conflicts.", _mutate_handler("git_merge_continue", "merge_continue"), "write", "medium", "write", 30_000),
    ("git_rebase", "Replay the current line of work on top of another; reports conflicts structurally. Rewrites local history.", _rebase, "write", "high", "write", 120_000),
    ("git_rebase_plan", "Replay the current line of work on top of another WITH a plan: squash, fixup, drop, reorder or reword specific commits. Fully automated; no terminal needed.", _rebase_plan, "write", "high", "write", 120_000),
    ("git_rebase_abort", "Undo an in-progress rebase, restoring the state before it.", _mutate_handler("git_rebase_abort", "rebase_abort"), "write", "high", "write", 30_000),
    ("git_rebase_continue", "Finish a rebase after resolving its conflicts.", _mutate_handler("git_rebase_continue", "rebase_continue"), "write", "medium", "write", 30_000),
    ("git_rebase_skip", "Skip the current step of a rebase.", _mutate_handler("git_rebase_skip", "rebase_skip"), "write", "medium", "write", 30_000),
    ("git_cherry_pick", "Copy one or more saved revisions onto the current line of work.", _cherry_pick, "write", "medium", "write", 60_000),
    ("git_cherry_pick_abort", "Undo an in-progress copy, restoring the state before it.", _mutate_handler("git_cherry_pick_abort", "cherry_pick_abort"), "write", "high", "write", 30_000),
    ("git_cherry_pick_continue", "Finish a copy after resolving its conflicts.", _mutate_handler("git_cherry_pick_continue", "cherry_pick_continue"), "write", "medium", "write", 30_000),
    ("git_revert", "Create new revisions that undo earlier ones. The safe way to undo published work.", _revert, "write", "medium", "write", 60_000),
    ("git_revert_abort", "Undo an in-progress revert, restoring the state before it.", _mutate_handler("git_revert_abort", "revert_abort"), "write", "high", "write", 30_000),
    ("git_revert_continue", "Finish a revert after resolving its conflicts.", _mutate_handler("git_revert_continue", "revert_continue"), "write", "medium", "write", 30_000),
    ("git_reset", "Move the current pointer. 'hard' discards unsaved work and requires confirmation.", _reset, "write", "high", "write", 30_000),
    ("git_resolve_conflict", "Write the resolved content for one conflicted file and choose it for saving.", _resolve_conflict, "write", "medium", "write", 30_000),
    ("git_abort_operation", "Undo whatever multi-step operation is currently open.", _abort_operation, "write", "high", "write", 30_000),
    ("git_continue_operation", "Finish whatever multi-step operation is currently open, once conflicts are resolved.", _continue_operation, "write", "medium", "write", 30_000),
    ("git_stash_push", "Set aside current changes to work on something else.", _stash_push, "write", "medium", "write", 30_000),
    ("git_stash_apply", "Bring back set-aside changes, keeping the set-aside copy.", _stash_apply, "write", "medium", "write", 30_000),
    ("git_stash_pop", "Bring back set-aside changes and discard the set-aside copy.", _stash_pop, "write", "medium", "write", 30_000),
    ("git_stash_drop", "Discard a set-aside change.", _stash_drop, "write", "high", "write", 30_000),
    ("git_tag_create", "Mark a revision with a name.", _tag_create, "write", "medium", "write", 30_000),
    ("git_tag_delete", "Remove a version marker.", _tag_delete, "write", "high", "write", 30_000),
    ("git_worktree_add", "Create a second working copy of the project beside the current one.", _worktree_add, "write", "medium", "write", 60_000),
    ("git_worktree_remove", "Remove a linked working copy.", _worktree_remove, "write", "high", "write", 60_000),
    ("git_submodule_update", "Fetch and check out a nested project's contents.", _submodule_update, "write", "medium", "external_action", 180_000),
    ("git_bisect_start", "Begin finding which revision introduced a problem.", _bisect_start, "write", "high", "write", 30_000),
    ("git_bisect_mark", "Mark the current step of a problem-finding run good, bad, or skip.", _bisect_mark, "write", "medium", "write", 30_000),
    ("git_bisect_reset", "End a problem-finding run.", _bisect_reset, "write", "medium", "write", 30_000),
    ("git_clean", "Delete untracked files. Requires confirmation; preview with git_clean_preview.", _clean, "write", "high", "write", 30_000),
    ("git_config_set", "Change a git setting.", _config_set, "write", "medium", "write", 30_000),
    # Remote (external_action)
    ("git_fetch", "Get the latest from the server without changing the working files.", _fetch, "write", "medium", "external_action", 180_000),
    ("git_pull", "Get the latest from the server and combine it into the current line of work.", _pull, "write", "medium", "external_action", 180_000),
    ("git_push", "Send saved revisions to the server. Overwriting history requires approval.", _push, "write", "high", "external_action", 180_000),
    ("git_remote_add", "Add a server connection.", _remote_add, "write", "medium", "external_action", 30_000),
    ("git_remote_remove", "Remove a server connection.", _remote_remove, "write", "medium", "external_action", 30_000),
    ("git_remote_set_url", "Change a server connection's address.", _remote_set_url, "write", "medium", "external_action", 30_000),
    ("git_tag_push", "Send a version marker to the server.", _tag_push, "write", "high", "external_action", 180_000),
]


GIT_TOOL_NAMES: tuple[str, ...] = tuple(spec[0] for spec in _TOOL_TABLE)


def register_git_tools(registry: ToolRegistry) -> list[str]:
    """Register every local Git tool. Returns the names added."""
    from . import safety as safety_mod  # noqa: PLC0415

    added: list[str] = []
    for name, description, handler, permission, risk, effect, timeout_ms in _TOOL_TABLE:
        metadata = None
        if effect == "external_action":
            metadata = {"gitOperation": name, "risk": risk, "mutating": True}
        elif effect == "write":
            # The authorizer reads the operation's catalog risk to decide whether a
            # confirmation is required.
            op_name = _OP_FOR_TOOL.get(name)
            op_risk = safety_mod.assess_risk(op_name).risk if op_name else risk
            metadata = {"gitOperation": op_name or name, "risk": op_risk, "mutating": True}
        registry.register(_definition(
            name, description, handler, permission=permission, risk=risk,
            effect=effect, timeout_ms=timeout_ms, metadata=metadata,
        ))
        added.append(name)
    return added


# Map each tool to the catalog operation whose risk classification applies. A
# missing entry falls back to the tool's declared risk.
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
}


__all__ = ["GIT_TOOL_NAMES", "register_git_tools"]
