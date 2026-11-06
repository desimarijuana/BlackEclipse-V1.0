"""Code-task lifecycle over the ONE run lineage.

A task IS a run. Its durable boundaries are `RunCheckpoint` rows written by
`run_lineage.RunLineage` (never a new table):

  kind="task.created"     — the bound workspace + the autonomy profile
  kind="plan.accepted"    — the plan the operator accepted (plan_only path)
  kind="patch.applied"    — a patch id + the tree digest AFTER the apply
  kind="command.executed" — the command class + idempotency key + exit code
  kind="task.cancelled"   — the reason, with the worktree released
  kind="task.discarded"   — the branch/worktree removed, nothing kept

Resume reads `latest_checkpoint()` and REUSES the recorded tool result for any
(runId, stepIndex, toolCallId) already in `ToolExecutionIdempotency`, so a resumed
task never re-applies a patch and never re-runs a side-effecting command. The
resume guard itself lives in `graph.execute_run` (Phase 1); this module only
records the code-specific boundaries and derives the task view.

Nothing here is a second checkpoint mechanism — `run_lineage.py` is the one.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from ..persistence import now_iso

# The code-specific checkpoint kinds.
TASK_CREATED = "task.created"
PLAN_ACCEPTED = "plan.accepted"
PATCH_APPLIED = "patch.applied"
COMMAND_EXECUTED = "command.executed"
TASK_CANCELLED = "task.cancelled"
TASK_DISCARDED = "task.discarded"

# The autonomy a code run uses when the caller supplied none.
DEFAULT_AUTONOMY = "edit_verify"


def _bounded_list(values: Any, limit: int = 50) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(v) for v in values][:limit]


def _same_path(left: str, right: str) -> bool:
    """Two folder paths name the same project (Windows-safe)."""
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))
    except (OSError, ValueError):
        return left == right


def plan_digest(steps: list[dict[str, Any]]) -> str:
    """A stable digest of a plan (so an accepted plan can be proven unchanged)."""
    canonical = json.dumps(steps, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


class TaskStore:
    """Thin lifecycle helpers over the ONE run store + lineage.

    It does not own a table: every durable fact is a `RunCheckpoint` (via
    `RunLineage`) or a `HarnessRun`/`HarnessCommandExecution` row.
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        from ..run_lineage import RunLineage  # noqa: PLC0415

        self._lineage = RunLineage(store)

    # ── boundaries ──────────────────────────────────────────────────────────
    def record_created(
        self, run_id: str, *, workspace_id: Optional[str], root: str = "",
        base_revision: str = "", strategy: str = "", autonomy: str = DEFAULT_AUTONOMY,
        scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, TASK_CREATED, {
            "workspaceId": workspace_id, "root": root,
            "baseRevision": base_revision, "strategy": strategy, "autonomy": autonomy,
            "scopeId": scope_id,
        })

    def record_plan_accepted(
        self, run_id: str, *, steps: list[dict[str, Any]], check_classes: list[str],
    ) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, PLAN_ACCEPTED, {
            "planDigest": plan_digest(steps),
            "steps": steps[:20],
            "files": _bounded_list([f for s in steps for f in (s.get("files") or [])]),
            "checkClasses": _bounded_list(check_classes, 16),
        })

    def record_patch_applied(
        self, run_id: str, *, patch_id: str, tree_digest_after: str,
        files: Any, step_index: int = 0, tool_call_id: str = "",
    ) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, PATCH_APPLIED, {
            "patchId": patch_id, "treeDigestAfter": tree_digest_after,
            "files": _bounded_list(files), "stepIndex": int(step_index),
            "toolCallId": tool_call_id,
        })

    def record_command_executed(
        self, run_id: str, *, command_execution_id: str, command_class: str,
        exit_code: Optional[int], idempotency_key: str = "",
    ) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, COMMAND_EXECUTED, {
            "commandExecutionId": command_execution_id, "commandClass": command_class,
            "exitCode": exit_code, "idempotencyKey": idempotency_key,
        })

    def record_cancelled(self, run_id: str, *, reason: str, worktree_released: bool) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, TASK_CANCELLED, {
            "reason": reason, "worktreeReleased": bool(worktree_released), "at": now_iso(),
        })

    def record_discarded(self, run_id: str, *, reason: str, worktree_released: bool) -> dict[str, Any]:
        return self._lineage.save_checkpoint(run_id, TASK_DISCARDED, {
            "reason": reason, "worktreeReleased": bool(worktree_released), "at": now_iso(),
        })

    # ── reads ───────────────────────────────────────────────────────────────
    def latest_created(self, run_id: str) -> Optional[dict[str, Any]]:
        for checkpoint in reversed(self._lineage.list_checkpoints(run_id)):
            if checkpoint.get("kind") == TASK_CREATED:
                return checkpoint
        return None

    def _project_root(self, run_id: str) -> str:
        """The checkout this build belongs to, from its workspace row (or "")."""
        if getattr(self, "_code_store", None) is None:
            from .store import CodeWorkspaceStore  # noqa: PLC0415

            self._code_store = CodeWorkspaceStore(self._store)
        try:
            rows = self._code_store.list_workspaces(run_id=run_id, limit=1)
        except Exception:  # noqa: BLE001 - attribution is best-effort
            return ""
        return str((rows[0] or {}).get("checkoutRoot") or "") if rows else ""

    def view(self, run_id: str) -> Optional[dict[str, Any]]:
        """The task view for one run id, or None when no such run exists."""
        run = self._store.get_run(run_id)
        if run is None:
            return None
        checkpoints = self._lineage.list_checkpoints(run_id)
        created = next(
            (c for c in reversed(checkpoints) if c.get("kind") == TASK_CREATED), None,
        )
        # A task exists only when it has the `task.created` boundary. A plain chat
        # run that never built anything has no task view (it is not a build).
        if created is None:
            return None
        created_payload = (created or {}).get("payload") or {}
        plan = next(
            (c for c in reversed(checkpoints) if c.get("kind") == PLAN_ACCEPTED), None,
        )
        verification = run.get("codeVerification")
        repair = (verification or {}).get("repair") if isinstance(verification, dict) else None
        return {
            "id": run_id,
            "status": _task_status(run, checkpoints),
            "autonomy": created_payload.get("autonomy") or DEFAULT_AUTONOMY,
            "workspaceId": created_payload.get("workspaceId"),
            "projectRoot": self._project_root(run_id),
            "query": (run.get("input") or {}).get("query", ""),
            "plan": (plan or {}).get("payload"),
            "verification": verification,
            "repair": repair,
            "createdAt": run.get("createdAt"),
            "updatedAt": run.get("updatedAt"),
        }

    def list(
        self, *, limit: int = 50, status: Optional[str] = None,
        scope_id: Optional[str] = None, project_root: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Code tasks, optionally narrowed by a scope label or one project.

        The label maps to `HarnessRun.userId`; `project_root` maps to the
        workspace row's recorded checkout. Both narrow what is returned and
        NEVER authorize a mutation.
        """
        limit = max(1, min(int(limit), 200))
        views: list[dict[str, Any]] = []
        for run in self._store.list_runs(limit=200):
            # Any run with a `task.created` boundary is a build task: a Code task
            # or a writing chat build. `view` is None for a run that never built.
            if scope_id is not None and run.get("userId") != scope_id:
                continue
            view = self.view(run["id"])
            if view is None:
                continue
            if project_root and not _same_path(str(view.get("projectRoot") or ""), project_root):
                continue
            if status and view["status"] != status:
                continue
            views.append(view)
            if len(views) >= limit:
                break
        return views


def _task_status(run: dict[str, Any], checkpoints: list[dict[str, Any]]) -> str:
    """Derive a plain task status from the run + its checkpoints."""
    kinds = {c.get("kind") for c in checkpoints}
    run_status = run.get("status")
    if TASK_DISCARDED in kinds:
        return "discarded"
    if TASK_CANCELLED in kinds or run_status == "cancelled":
        return "cancelled"
    if run_status == "failed":
        return "failed"
    if run_status in ("created", "running"):
        return "plan_review" if PLAN_ACCEPTED in kinds else "created"
    if run_status == "completed":
        verification = run.get("codeVerification") or {}
        repair = verification.get("repair") or {} if isinstance(verification, dict) else {}
        if repair.get("status") == "passed":
            return "completed"
        return "completed"
    return "created"


__all__ = [
    "COMMAND_EXECUTED",
    "DEFAULT_AUTONOMY",
    "PATCH_APPLIED",
    "PLAN_ACCEPTED",
    "TASK_CANCELLED",
    "TASK_CREATED",
    "TASK_DISCARDED",
    "TaskStore",
    "plan_digest",
]
