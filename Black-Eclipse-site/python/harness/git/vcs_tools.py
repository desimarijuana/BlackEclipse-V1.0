"""The remote-collaboration (VCS provider) agent tools.

`register_vcs_tools(registry)` exposes the provider layer: repositories, branches,
pull/merge requests, reviews, comments and CI. A provider is resolved from the
run's `origin` remote host (github/gitlab/bitbucket), or an explicit `provider`.
When no provider matches, or no sign-in is configured, the tool returns a
structured failure — a remote action is never faked.

Read tools are `permission="read"`. Remote mutations (create a PR, merge, request
a review, rerun a workflow) are `permission="write"`, `effect="external_action"`,
and therefore routed through the single-use operator approval gate.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..code.events import emit_code_event
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .executor import run
from .readers import remotes
from .schemas import SCHEMAS
from .tool_support import resolve_repository
from .vcs import ProviderError, ProviderRegistry, parse_remote


def _registry() -> ProviderRegistry:
    return ProviderRegistry()


def _resolve_provider(ctx: ToolContext, args: dict[str, Any]) -> tuple[Optional[Any], str, Optional[dict[str, Any]]]:
    """Resolve `(provider, default_full_name, error)` for a call."""
    repo = resolve_repository(ctx, required=False)
    remote = None
    if repo is not None:
        data = remotes(repo)
        for entry in data.get("remotes", []) if data.get("available") else []:
            url = entry.get("fetchUrl") or entry.get("pushUrl") or ""
            parsed = parse_remote(url)
            if parsed is not None:
                remote = parsed
                break
    provider_name = str(args.get("provider") or (remote.provider if remote else "") or "")
    registry = _registry()
    provider = registry.get(provider_name, host=(remote.host if remote else ""))
    if provider is None:
        return None, "", {
            "code": "PROVIDER_UNAVAILABLE",
            "message": "No sign-in is configured for this service, or the service is not supported.",
            "recoverable": False,
        }
    default_full = remote.full_name if remote else ""
    if not provider.authenticated:
        return provider, default_full, {
            "code": "AUTHENTICATION_FAILED",
            "message": "No sign-in is configured for this service.",
            "recoverable": False,
        }
    return provider, default_full, None


def _failure(operation: str, error: dict[str, Any]) -> tuple[str, Any]:
    return (f"Could not {operation}: {error.get('code')}. {error.get('message', '')}".strip(),
            {"success": False, "operation": operation, "error": error})


async def _emit(ctx: ToolContext, event: str, data: dict[str, Any]) -> None:
    await emit_code_event(ctx, event, data)


def _provider_error(operation: str, exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, ProviderError):
        return _failure(operation, exc.to_dict())
    return _failure(operation, {"code": "PROVIDER_UNAVAILABLE", "message": str(exc), "recoverable": False})


def _full_name(args: dict[str, Any], default: str) -> str:
    return str(args.get("fullName") or default or "")


# ── Handlers ───────────────────────────────────────────────────────────────────

async def _vcs_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, full_name, error = _resolve_provider(ctx, args)
    if provider is None:
        return _failure("check the service", error or {})
    info = provider.describe()
    return (f"{info['provider']} at {info['host']} — signed in: {info['authenticated']}.",
            {"success": True, "operation": "vcs_status", "service": info, "defaultRepository": full_name or None})


async def _vcs_list_repositories(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, _, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list repositories", error or {})
    try:
        repos = provider.list_repositories(limit=int(args.get("limit") or 50))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list repositories", exc)
    await _emit(ctx, "vcs.repositories.listed", {"provider": provider.name, "count": len(repos)})
    return (f"{len(repos)} repository(ies).",
            {"success": True, "operation": "list_repositories",
             "repositories": [r.to_dict() for r in repos]})


async def _vcs_get_repository(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("read the repository", error or {})
    full_name = _full_name(args, default)
    if not full_name:
        return _failure("read the repository", {"code": "VALIDATION_FAILED", "message": "No repository was named.", "recoverable": False})
    try:
        repo = provider.get_repository(full_name)
    except Exception as exc:  # noqa: BLE001
        return _provider_error("read the repository", exc)
    return f"{repo.full_name} (default branch {repo.default_branch}).", {
        "success": True, "operation": "get_repository", "repository": repo.to_dict()}


async def _vcs_list_branches(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list branches", error or {})
    full_name = _full_name(args, default)
    try:
        branches = provider.get_branches(full_name)
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list branches", exc)
    return f"{len(branches)} branch(es).", {
        "success": True, "operation": "list_branches", "branches": [b.to_dict() for b in branches]}


async def _vcs_list_commits(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list commits", error or {})
    full_name = _full_name(args, default)
    try:
        commits = provider.get_commits(full_name, ref=str(args.get("ref") or ""), limit=int(args.get("limit") or 30))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list commits", exc)
    return f"{len(commits)} commit(s).", {
        "success": True, "operation": "list_commits", "commits": [c.to_dict() for c in commits]}


async def _vcs_create_branch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("create the branch", error or {})
    full_name = _full_name(args, default)
    try:
        branch = provider.create_branch(full_name, args["name"], from_sha=str(args.get("fromSha") or ""))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("create the branch", exc)
    await _emit(ctx, "vcs.branch.created", {"provider": provider.name, "branch": args["name"]})
    return f"Branch {branch.name} created on the server.", {
        "success": True, "operation": "create_branch", "branch": branch.to_dict()}


async def _vcs_generate_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    repo = resolve_repository(ctx, required=False)
    if repo is None:
        return _failure("draft the request", {"code": "NOT_A_REPOSITORY", "message": "This folder is not tracked yet.", "recoverable": False})
    from .messages import generate_pull_request  # noqa: PLC0415

    draft = generate_pull_request(
        repo, base=str(args.get("base") or "main"), head=args.get("head"), issue=args.get("issue"))
    return f"{draft['title']}\n\n{draft['body']}", {
        "success": True, "operation": "generate_pull_request", "draft": draft}


async def _vcs_create_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("open the request", error or {})
    full_name = _full_name(args, default)
    try:
        pr = provider.create_pull_request(
            full_name, title=args["title"], source_branch=args["sourceBranch"],
            target_branch=args["targetBranch"], description=str(args.get("description") or ""),
            draft=bool(args.get("draft")),
        )
    except Exception as exc:  # noqa: BLE001
        return _provider_error("open the request", exc)
    await _emit(ctx, "vcs.pull_request.opened", {
        "provider": provider.name, "number": pr.number, "url": pr.url})
    return f"Opened {pr.kind} #{pr.number}: {pr.title} ({pr.url}).", {
        "success": str(pr.status) == "open", "operation": "create_pull_request", "pullRequest": pr.to_dict()}


async def _vcs_get_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("read the request", error or {})
    full_name = _full_name(args, default)
    try:
        pr = provider.get_pull_request(full_name, int(args["number"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("read the request", exc)
    checks = "" if not pr.checks else f" {len(pr.checks)} check(s)."
    return f"{pr.kind} #{pr.number} {pr.status}: {pr.title}.{checks}", {
        "success": True, "operation": "get_pull_request", "pullRequest": pr.to_dict()}


async def _vcs_list_pull_requests(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list requests", error or {})
    full_name = _full_name(args, default)
    try:
        prs = provider.list_pull_requests(
            full_name, state=str(args.get("state") or "open"), limit=int(args.get("limit") or 30))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list requests", exc)
    return f"{len(prs)} request(s).", {
        "success": True, "operation": "list_pull_requests",
        "pullRequests": [p.to_dict() for p in prs]}


async def _vcs_update_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("update the request", error or {})
    full_name = _full_name(args, default)
    try:
        pr = provider.update_pull_request(
            full_name, int(args["number"]), title=args.get("title"),
            description=args.get("description"), state=args.get("state"),
            target_branch=args.get("targetBranch"))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("update the request", exc)
    return f"Updated {pr.kind} #{pr.number}.", {
        "success": True, "operation": "update_pull_request", "pullRequest": pr.to_dict()}


async def _vcs_close_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("close the request", error or {})
    full_name = _full_name(args, default)
    try:
        pr = provider.close_pull_request(full_name, int(args["number"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("close the request", exc)
    return f"Closed {pr.kind} #{pr.number}.", {
        "success": True, "operation": "close_pull_request", "pullRequest": pr.to_dict()}


async def _vcs_merge_pull_request(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("merge the request", error or {})
    full_name = _full_name(args, default)
    try:
        pr = provider.merge_pull_request(
            full_name, int(args["number"]), method=str(args.get("method") or "merge"),
            delete_branch=bool(args.get("deleteBranch")))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("merge the request", exc)
    await _emit(ctx, "vcs.pull_request.merged", {"provider": provider.name, "number": args["number"]})
    return f"Merged {pr.kind} #{pr.number}.", {
        "success": True, "operation": "merge_pull_request", "pullRequest": pr.to_dict()}


async def _vcs_request_review(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("request a review", error or {})
    full_name = _full_name(args, default)
    try:
        result = provider.request_review(full_name, int(args["number"]), [str(r) for r in args["reviewers"]])
    except Exception as exc:  # noqa: BLE001
        return _provider_error("request a review", exc)
    return f"Requested {len(result.get('requested', []))} review(s).", {
        "success": True, "operation": "request_review", **result}


async def _vcs_list_reviews(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list reviews", error or {})
    full_name = _full_name(args, default)
    try:
        reviews = provider.list_reviews(full_name, int(args["number"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list reviews", exc)
    return f"{len(reviews)} review(s).", {
        "success": True, "operation": "list_reviews", "reviews": [r.to_dict() for r in reviews]}


async def _vcs_get_review_comments(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("read review comments", error or {})
    full_name = _full_name(args, default)
    try:
        comments = provider.get_review_comments(full_name, int(args["number"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("read review comments", exc)
    return f"{len(comments)} comment(s).", {
        "success": True, "operation": "get_review_comments", "comments": comments}


async def _vcs_reply_review_comment(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("reply to the comment", error or {})
    full_name = _full_name(args, default)
    try:
        result = provider.reply_review_comment(
            full_name, int(args["number"]), str(args["commentId"]), str(args["body"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("reply to the comment", exc)
    return "Replied to the comment.", {"success": True, "operation": "reply_review_comment", **result}


async def _vcs_ci_status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("read the checks", error or {})
    full_name = _full_name(args, default)
    try:
        checks = provider.get_checks(full_name, str(args["ref"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("read the checks", exc)
    failing = [c for c in checks if c.conclusion in ("failure", "cancelled", "timed_out")]
    summary = f"{len(checks)} check(s), {len(failing)} failing."
    await _emit(ctx, "vcs.checks", {"provider": provider.name, "total": len(checks), "failing": len(failing)})
    return summary, {"success": True, "operation": "ci_status", "checks": [c.to_dict() for c in checks]}


async def _vcs_list_workflow_runs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("list workflow runs", error or {})
    full_name = _full_name(args, default)
    try:
        runs = provider.get_workflow_runs(
            full_name, ref=str(args.get("ref") or ""), limit=int(args.get("limit") or 20))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("list workflow runs", exc)
    return f"{len(runs)} run(s).", {
        "success": True, "operation": "list_workflow_runs", "runs": [r.to_dict() for r in runs]}


async def _vcs_get_job_logs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("read the logs", error or {})
    full_name = _full_name(args, default)
    try:
        result = provider.get_job_logs(full_name, str(args["jobId"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("read the logs", exc)
    from .journal import redact_text  # noqa: PLC0415

    log = redact_text(str(result.get("log", "")))
    return log[-4000:], {"success": True, "operation": "get_job_logs", **{**result, "log": log}}


async def _vcs_rerun_workflow(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("rerun the workflow", error or {})
    full_name = _full_name(args, default)
    try:
        result = provider.rerun_workflow(full_name, str(args["runId"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("rerun the workflow", exc)
    return "Requested a rerun.", {"success": True, "operation": "rerun_workflow", **result}


async def _vcs_cancel_workflow(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    provider, default, error = _resolve_provider(ctx, args)
    if provider is None or error is not None:
        return _failure("cancel the workflow", error or {})
    full_name = _full_name(args, default)
    try:
        result = provider.cancel_workflow(full_name, str(args["runId"]))
    except Exception as exc:  # noqa: BLE001
        return _provider_error("cancel the workflow", exc)
    return "Requested a cancel.", {"success": True, "operation": "cancel_workflow", **result}


# ── Registration ─────────────────────────────────────────────────────────────

_VCS_TOOLS: list[tuple[str, str, Callable, str, str, Optional[str], int]] = [
    ("vcs_status", "Report which code-hosting service is connected, with sign-in details removed. Read-only.", _vcs_status, "read", "low", None, 15_000),
    ("vcs_list_repositories", "List repositories the connected account can see. Read-only.", _vcs_list_repositories, "read", "low", None, 30_000),
    ("vcs_get_repository", "Report a repository's details on the hosting service. Read-only.", _vcs_get_repository, "read", "low", None, 20_000),
    ("vcs_list_branches", "List the branches of a hosted repository. Read-only.", _vcs_list_branches, "read", "low", None, 20_000),
    ("vcs_list_commits", "List the commits of a hosted repository. Read-only.", _vcs_list_commits, "read", "low", None, 20_000),
    ("vcs_generate_pull_request", "Draft a review request (title, summary, changes, tests, risk) from the branch change. Read-only.", _vcs_generate_pull_request, "read", "low", None, 30_000),
    ("vcs_get_pull_request", "Read a review request, including its checks. Read-only.", _vcs_get_pull_request, "read", "low", None, 30_000),
    ("vcs_list_pull_requests", "List review requests. Read-only.", _vcs_list_pull_requests, "read", "low", None, 30_000),
    ("vcs_list_reviews", "List the reviews on a request. Read-only.", _vcs_list_reviews, "read", "low", None, 30_000),
    ("vcs_get_review_comments", "Read the comments on a request. Read-only.", _vcs_get_review_comments, "read", "low", None, 30_000),
    ("vcs_ci_status", "Report the build/check results for a revision. Read-only; never claims success without evidence. Read-only.", _vcs_ci_status, "read", "low", None, 30_000),
    ("vcs_list_workflow_runs", "List the automated runs for a repository or branch. Read-only.", _vcs_list_workflow_runs, "read", "low", None, 30_000),
    ("vcs_get_job_logs", "Read the logs of one automated job. Read-only.", _vcs_get_job_logs, "read", "low", None, 30_000),
    # Remote mutations — external_action, single-use approval.
    ("vcs_create_branch", "Create a branch on the hosting service.", _vcs_create_branch, "write", "medium", "external_action", 30_000),
    ("vcs_create_pull_request", "Open a review request for a branch.", _vcs_create_pull_request, "write", "medium", "external_action", 30_000),
    ("vcs_update_pull_request", "Change a review request's title, description, target or state.", _vcs_update_pull_request, "write", "medium", "external_action", 30_000),
    ("vcs_close_pull_request", "Close a review request without merging.", _vcs_close_pull_request, "write", "medium", "external_action", 30_000),
    ("vcs_merge_pull_request", "Merge a review request when authorized.", _vcs_merge_pull_request, "write", "high", "external_action", 60_000),
    ("vcs_request_review", "Ask specific people to review a request.", _vcs_request_review, "write", "medium", "external_action", 30_000),
    ("vcs_reply_review_comment", "Reply to a review comment.", _vcs_reply_review_comment, "write", "medium", "external_action", 30_000),
    ("vcs_rerun_workflow", "Re-run an automated workflow.", _vcs_rerun_workflow, "write", "medium", "external_action", 30_000),
    ("vcs_cancel_workflow", "Cancel an automated workflow.", _vcs_cancel_workflow, "write", "medium", "external_action", 30_000),
]

VCS_TOOL_NAMES: tuple[str, ...] = tuple(spec[0] for spec in _VCS_TOOLS)


def register_vcs_tools(registry: ToolRegistry) -> list[str]:
    """Register the remote-collaboration tools. Returns the names added."""
    added: list[str] = []
    for name, description, handler, permission, risk, effect, timeout_ms in _VCS_TOOLS:
        metadata = {"vcsOperation": name, "risk": risk} if effect == "external_action" else None
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=SCHEMAS[name], handler=handler,
            permission=permission, risk=risk, timeout_ms=timeout_ms, effect=effect,
            effect_metadata=metadata,
        ))
        added.append(name)
    return added


__all__ = ["VCS_TOOL_NAMES", "register_vcs_tools"]
