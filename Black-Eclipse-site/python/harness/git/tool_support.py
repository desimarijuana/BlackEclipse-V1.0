"""Shared helpers for the Git agent tools.

Every `git_*` tool resolves the same things: the run's repository (from the bound
workspace, never from model input), the process-wide `GitService`, and the run's
id for the journal. These helpers are the ONE place that mapping lives, so a tool
handler stays a thin adapter over the service.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from ..tools import ToolContext
from .repository import Repository, discover
from .service import GitService, get_git_service, set_git_service


def resolve_root(ctx: ToolContext) -> Optional[Path]:
    """The repository root the git tools operate on for this run.

    Prefers the run's BOUND workspace (the same tree the agent edits — a disposable
    worktree shares the object DB and remotes, so a git op there is correct). Falls
    back to the server-resolved default root. NEVER a model-supplied path.
    """
    workspace = getattr(ctx, "workspace", None)
    root = getattr(workspace, "root", None)
    if root is not None:
        return Path(root)
    from ..code.workspace import default_root  # noqa: PLC0415

    return default_root()


def resolve_repository(ctx: ToolContext, *, required: bool = True) -> Optional[Repository]:
    root = resolve_root(ctx)
    if root is None:
        return None
    repo = discover(root)
    if repo is None and required:
        return None
    return repo


def service_for(ctx: ToolContext) -> GitService:
    """The process-wide Git service, or a per-run one bound to the run store."""
    service = get_git_service()
    if service is not None:
        return service
    store = getattr(ctx, "memory_store", None) or getattr(ctx, "code_store", None)
    service = GitService(store)
    set_git_service(service)
    return service


def run_of(ctx: ToolContext) -> Optional[str]:
    return getattr(ctx, "run_id", None) or None


def repository_unavailable(tool: str) -> dict[str, Any]:
    return {
        "success": False,
        "operation": tool,
        "error": {
            "code": "NOT_A_REPOSITORY",
            "message": "This folder is not set up to track versions yet.",
            "recoverable": False,
            "files": [],
        },
    }


def operation_text(outcome: Any) -> str:
    """One bounded, plain sentence summarising an operation outcome for the model."""
    data = outcome.to_dict()
    if outcome.success:
        extra = ""
        result = data.get("result") or {}
        if result.get("commit"):
            extra = f" commit {str(result['commit'])[:12]}"
        elif result.get("branch"):
            extra = f" branch {result['branch']}"
        return f"Done: {outcome.operation}{extra}."
    err = data.get("error") or {}
    files = err.get("files") or []
    suffix = f" ({', '.join(files[:5])})" if files else ""
    hint = f" {err.get('hint')}" if err.get("hint") else ""
    return f"Could not {outcome.operation}: {err.get('code')}{suffix}.{hint}"


__all__ = [
    "repository_unavailable",
    "operation_text",
    "resolve_repository",
    "resolve_root",
    "run_of",
    "service_for",
]
