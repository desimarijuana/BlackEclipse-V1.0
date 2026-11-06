"""Durable build sessions over the ONE run lineage (Phase 22 / S2).

A build session is not a second store. It is a *lens* over an existing code run:

  * the run row (``HarnessRun``) is the durable identity;
  * ``RunCheckpoint`` rows are the boundaries (``code/tasks.py`` owns the code
    ones; this module adds exactly one, ``session.created``);
  * resume is the existing ``POST /runs/{id}/resume`` path, with the existing
    ``CHECKPOINT_NOT_FOUND`` / ``RESUME_CONFLICT`` semantics.

What it adds is the missing budget ladder. A chat code turn is bounded at 24
steps / 10 minutes, which is right for a small change and wrong for a real one.
A session states its budget up front (``small`` / ``standard`` / ``deep``), the
request carries it as additive fields, and the graph applies it with a hard cap -
so a deep session can run 240 steps / 3 hours without widening the autonomy
floor or the tool surface by one byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .tasks import TaskStore

#: The durable boundary this module owns. One checkpoint, no table.
SESSION_CREATED = "session.created"


@dataclass(frozen=True)
class SessionBudget:
    """One budget profile: a step ceiling and a wall-clock ceiling."""

    profile: str
    max_steps: int
    run_timeout_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "maxSteps": self.max_steps,
            "runTimeoutSeconds": self.run_timeout_s,
        }


#: The budget profiles, as DATA. The runtime never accepts an arbitrary number
#: from the caller: it accepts a profile name and reads the numbers here.
BUDGET_LADDER: dict[str, SessionBudget] = {
    "small": SessionBudget("small", 24, 600.0),
    "standard": SessionBudget("standard", 80, 2_700.0),
    "deep": SessionBudget("deep", 240, 10_800.0),
}

DEFAULT_PROFILE = "standard"

#: A chat turn that may write is a build, not small talk: it buys the standard
#: profile instead of the 24-step chat budget. Planning keeps the chat budget.
CHAT_BUILD_PROFILE = "standard"
BUILD_AUTONOMIES: tuple[str, ...] = ("edit_verify", "approve_external")

#: Absolute caps. A session profile can never exceed these, and a direct caller
#: cannot either - the graph clamps to them.
HARD_MAX_STEPS = 240
HARD_RUN_TIMEOUT_S = 10_800.0


class SessionError(Exception):
    """A session refusal with a stable code (never a bare string)."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def resolve_budget(profile: Optional[str]) -> SessionBudget:
    """Resolve a profile name to its budget. Unknown names are refused."""
    key = (profile or DEFAULT_PROFILE).strip().lower()
    budget = BUDGET_LADDER.get(key)
    if budget is None:
        raise SessionError(
            "UNKNOWN_BUDGET_PROFILE",
            f"Unknown budget profile {profile!r}. Use one of: {', '.join(BUDGET_LADDER)}.",
        )
    return budget


def budget_for_autonomy(autonomy: Optional[str]) -> Optional[SessionBudget]:
    """The build budget a writing autonomy earns; None keeps the chat budget.

    Pure and conservative: the caller still goes through ``apply_budget``
    (additive) and the graph's hard caps. `plan_only`, an empty autonomy and an
    unknown string all keep the ordinary chat budget.
    """
    if (autonomy or "").strip().lower() in BUILD_AUTONOMIES:
        return BUDGET_LADDER[CHAT_BUILD_PROFILE]
    return None


def apply_chat_build_budget(request: Any) -> None:
    """Give a writing chat turn the build budget floor. No-op otherwise."""
    budget = budget_for_autonomy(getattr(request, "autonomy", None))
    if budget is not None:
        apply_budget(request, budget)


def record_chat_build(store: Any, request: Any, *, agent_id: str = "eclipse-agent") -> bool:
    """Make a writing chat turn a DURABLE build (Phase 24 / P3).

    A chat build is a run, and the scorecard's own definition of a build is "a run
    with a `session.created` checkpoint". Code tasks already write one; a chat
    build did not, so it could not be resumed and never appeared in the scorecard.

    The checkpoint has a FOREIGN KEY on the run row, so the row is created first
    when it does not exist yet (`execute_run` re-uses a pre-created row). An
    existing session is left alone — the Code task path owns its own.
    """
    budget = budget_for_autonomy(getattr(request, "autonomy", None))
    run_id = str(getattr(request, "runId", "") or "")
    if budget is None or not run_id:
        return False
    sessions = SessionStore(store)
    if sessions.latest(run_id) is not None:
        return True
    try:
        store.create_run(
            run_id, agent_id, request.input.model_dump(), request.userId,
            request.modelSettings.provider, request.modelSettings.model,
            session_id=getattr(request, "sessionId", None),
            profile_id=getattr(request, "profileId", None),
            project_id=getattr(request, "projectId", None),
        )
    except Exception:  # noqa: BLE001 - an existing row is re-used by execute_run
        pass
    try:
        sessions.record(
            run_id,
            goal=str(getattr(getattr(request, "input", None), "query", "") or ""),
            budget=budget,
            workspace_id=getattr(request, "workspaceId", None),
        )
    except Exception:  # noqa: BLE001 - a missing session must never fail the run
        return False
    # A chat build is a BUILD: give it the same `task.created` boundary a Code
    # task has, so it appears in Builds (diff, checks, preview, undo) instead of
    # existing only as a chat transcript.
    try:
        TaskStore(store).record_created(
            run_id,
            workspace_id=getattr(request, "workspaceId", None),
            autonomy=str(getattr(request, "autonomy", "") or "edit_verify"),
        )
    except Exception:  # noqa: BLE001 - the session is already durable
        pass
    return True


def apply_budget(request: Any, budget: SessionBudget) -> None:
    """Put a session budget on a RunRequest, ADDITIVELY.

    It can only raise a caller's explicit value, never lower it: a session is a
    floor on the work budget, not a way to shrink someone else's run. The graph
    clamps the result to ``HARD_MAX_STEPS`` / ``HARD_RUN_TIMEOUT_S``.
    """
    current_steps = int(getattr(request, "maxSteps", 0) or 0)
    request.maxSteps = max(current_steps, min(budget.max_steps, HARD_MAX_STEPS))
    current_ms = int(getattr(request, "runTimeoutMs", 0) or 0)
    wanted_ms = int(min(budget.run_timeout_s, HARD_RUN_TIMEOUT_S) * 1000)
    request.runTimeoutMs = max(current_ms, wanted_ms)


def _bounded_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _bounded_list(values: Any, limit: int = 20, item_limit: int = 300) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(item).strip()[:item_limit] for item in values[:limit] if str(item).strip()]


class SessionStore:
    """Read/write the session lens for one run. Never owns a table."""

    def __init__(self, store: Any) -> None:
        self._store = store
        from ..run_lineage import RunLineage  # noqa: PLC0415

        self._lineage = RunLineage(store)
        self._tasks = TaskStore(store)

    def record(
        self,
        run_id: str,
        *,
        goal: str,
        budget: SessionBudget,
        acceptance: Optional[list[str]] = None,
        workspace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record the goal, the acceptance list and the budget at creation."""
        return self._lineage.save_checkpoint(run_id, SESSION_CREATED, {
            "goal": _bounded_text(goal, 2_000),
            "acceptance": _bounded_list(acceptance),
            "budget": budget.to_dict(),
            "workspaceId": workspace_id,
        })

    def latest(self, run_id: str) -> Optional[dict[str, Any]]:
        for checkpoint in reversed(self._lineage.list_checkpoints(run_id)):
            if checkpoint.get("kind") == SESSION_CREATED:
                return checkpoint
        return None

    def view(self, run_id: str) -> Optional[dict[str, Any]]:
        """The session block for one run, or None when it is not a session."""
        created = self.latest(run_id)
        if created is None:
            return None
        payload = created.get("payload") or {}
        run = self._store.get_run(run_id)
        if run is None:
            return None
        checkpoints = self._lineage.list_checkpoints(run_id)
        boundaries = [
            checkpoint for checkpoint in checkpoints
            if checkpoint.get("kind") in (
                "plan.accepted", "patch.applied", "command.executed",
            )
        ]
        status = str(run.get("status") or "created")
        resumable = status not in ("completed", "failed", "cancelled")
        land_record = next(
            (c for c in reversed(checkpoints) if c.get("kind") == "land.verified"), None,
        )
        land_payload = (land_record or {}).get("payload") or {}
        land = None
        if land_record is not None:
            land = {
                "ok": bool(land_payload.get("ok")),
                "full": bool(land_payload.get("full")),
                "failed": land_payload.get("failed"),
                "at": land_record.get("createdAt"),
            }
        phase, next_action = derive_phase(status, len(boundaries), land)
        return {
            "id": run_id,
            "goal": payload.get("goal") or "",
            "acceptance": list(payload.get("acceptance") or []),
            "budget": payload.get("budget") or {},
            "workspaceId": payload.get("workspaceId"),
            "status": status,
            "phase": phase,
            "nextAction": next_action,
            "land": land,
            "progress": {
                "boundaries": len(boundaries),
                "lastBoundary": boundaries[-1]["kind"] if boundaries else None,
                "checkpoints": len(checkpoints),
                "createdAt": created.get("createdAt"),
            },
            "resume": {
                "resumable": resumable,
                "code": None if resumable else "RESUME_CONFLICT",
                "checkpointId": checkpoints[-1]["id"] if checkpoints else None,
            },
        }


def derive_phase(
    status: str, boundaries: int, land: Optional[dict[str, Any]],
) -> tuple[str, str]:
    """One honest state machine, from facts the runtime already records.

    The phase is derived, never stored: a stale status label is how a UI starts
    lying. `nextAction` is the ONE thing the user can do next.
    """
    if status in ("cancelled", "discarded"):
        return "cancelled", "none"
    if status == "failed":
        return "blocked", "fix_checks"
    if status == "plan_review":
        return "planning", "review_plan"
    if status == "completed":
        if land and land.get("ok") and land.get("full"):
            return "done", "review_change"
        return "checking", "run_checks"
    if land and not land.get("ok"):
        return "checking", "fix_checks"
    if boundaries > 0:
        return "editing", "run_checks"
    return "planning", "run_checks"


__all__ = [
    "BUILD_AUTONOMIES",
    "BUDGET_LADDER",
    "CHAT_BUILD_PROFILE",
    "DEFAULT_PROFILE",
    "HARD_MAX_STEPS",
    "HARD_RUN_TIMEOUT_S",
    "SESSION_CREATED",
    "SessionBudget",
    "SessionError",
    "SessionStore",
    "apply_budget",
    "apply_chat_build_budget",
    "budget_for_autonomy",
    "derive_phase",
    "record_chat_build",
    "resolve_budget",
]
