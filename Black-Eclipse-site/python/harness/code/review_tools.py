"""The `review_change` tool (Phase 19, ADR-H191).

Reports the repository's own rules over the change in this task's copy:
reachability of a new module, the size ratchet, translatable strings, protected
files, the change-log obligation, and touched tests. Findings are PLAIN WORDS;
the rule ids and paths ride the structured payload. Running the review RECORDS
it on the ledger, so a sentence like "I reviewed the change" is backed by a
record — or marked UNVERIFIED by the existing enforcement path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import worktree
from .review import diff_view_from_worktree, review_change

_MAX_LINES = 10


def _refusal(code: str, text: str) -> tuple[str, dict[str, Any]]:
    return text, {"ran": False, "code": code, "findings": [], "unevaluated": []}


async def review_change_tool(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Review the change in this task's own copy against the project's rules."""
    workspace = getattr(ctx, "workspace", None)
    if workspace is None:
        return _refusal(
            "WORKSPACE_UNBOUND",
            "There's no project folder bound to this task, so there's no change to review.",
        )
    workspace_id = str(getattr(workspace, "id", "") or "")
    strategy = str(getattr(workspace, "strategy", "worktree") or "worktree")
    try:
        diff_result = worktree.diff(workspace_id, strategy=strategy)
    except Exception as exc:  # noqa: BLE001 - a diff failure is an honest refusal
        return _refusal("REVIEW_FAILED", f"I couldn't read the change to review it: {exc}")

    if not diff_result.get("filesChanged"):
        return _refusal("NOTHING_TO_REVIEW", "There's no change to review yet.")

    root = Path(str(getattr(workspace, "root", ".") or "."))
    view = diff_view_from_worktree(diff_result, root=root)
    outcome = review_change(view, repo_root=root)

    ledger = getattr(ctx, "code_ledger", None)
    if ledger is not None:
        try:
            ledger.record_review({
                "ran": True,
                "filesReviewed": outcome.files_reviewed,
                "findings": [f.to_dict() for f in outcome.findings],
                "unevaluated": list(outcome.unevaluated),
            })
        except Exception:  # noqa: BLE001 - a ledger write must never fail the tool
            pass

    lines: list[str] = []
    if outcome.findings:
        lines.append(
            f"I reviewed the change ({outcome.files_reviewed} file(s)) — "
            f"{len(outcome.findings)} thing(s) to look at:"
        )
        for finding in outcome.findings[:_MAX_LINES]:
            location = f"{finding.path}: " if finding.path else ""
            lines.append(f"- {location}{finding.summary}")
        if len(outcome.findings) > _MAX_LINES:
            lines.append(f"- …and {len(outcome.findings) - _MAX_LINES} more.")
    else:
        lines.append(
            f"I reviewed the change ({outcome.files_reviewed} file(s)) — nothing to flag."
        )
    if outcome.unevaluated:
        lines.append(
            f"({len(outcome.unevaluated)} thing(s) I couldn't check: {outcome.unevaluated[0]})"
        )
    return "\n".join(lines), {"ran": True, **outcome.to_dict()}


def register_review_tools(registry: ToolRegistry) -> list[str]:
    """Register the change-review tool. Idempotent per name."""
    if registry.get("review_change") is not None:
        return []
    registry.register(ToolDefinition(
        name="review_change",
        description=(
            "Review the change made in this task's own copy against the project's "
            "rules (reachability, size limits, translatable strings, protected "
            "files, the change-log obligation, touched tests). Read-only; records "
            "the review so a claim about it can be checked."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=review_change_tool, permission="read", risk="none", timeout_ms=30_000,
    ))
    return ["review_change"]


__all__ = ["register_review_tools", "review_change_tool"]
