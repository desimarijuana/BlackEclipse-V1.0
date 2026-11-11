"""Durable goal + evidence storage (C4).

The task runtime still owns execution (plan/task rows, leases, scheduling).
This store adds the GOAL-scoped plan view and the evidence ledger that proves a
step or an answer. It shares the ONE `agent-memory.db` connection and the
`HarnessMigration` ledger.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..migrations import Migration, MigrationRunner
from ..persistence import now_iso
from .model import Claim, EvidenceHandle, Goal, Plan, PlanStep

MAX_CLAIM_TEXT = 4_000
MAX_HANDLES = 24

GOAL_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id="2026-11-11-005-goal-evidence",
        description="Goal plan view + EvidenceClaim/Handle ledger",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS GoalRecord (
              id         TEXT PRIMARY KEY,
              objective  TEXT NOT NULL,
              acceptance TEXT,
              planId     TEXT,
              taskId     TEXT,
              status     TEXT NOT NULL,
              budget     TEXT,
              createdAt  TEXT NOT NULL,
              updatedAt  TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS GoalPlan (
              id         TEXT PRIMARY KEY,
              goalId     TEXT NOT NULL,
              iteration  INTEGER NOT NULL DEFAULT 1,
              status     TEXT NOT NULL,
              createdAt  TEXT NOT NULL,
              FOREIGN KEY (goalId) REFERENCES GoalRecord(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS GoalStep (
              id         TEXT PRIMARY KEY,
              planId     TEXT NOT NULL,
              idx        INTEGER NOT NULL,
              title      TEXT NOT NULL,
              objective  TEXT NOT NULL,
              acceptance TEXT,
              status     TEXT NOT NULL,
              runId      TEXT,
              createdAt  TEXT NOT NULL,
              updatedAt  TEXT NOT NULL,
              FOREIGN KEY (planId) REFERENCES GoalPlan(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS EvidenceClaim (
              id        TEXT PRIMARY KEY,
              runId     TEXT NOT NULL,
              stepId    TEXT,
              text      TEXT NOT NULL,
              status    TEXT NOT NULL,
              verifier  TEXT,
              createdAt TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS EvidenceHandleRow (
              id        TEXT PRIMARY KEY,
              claimId   TEXT NOT NULL,
              kind      TEXT NOT NULL,
              ref       TEXT NOT NULL,
              source    TEXT,
              digest    TEXT,
              at        TEXT NOT NULL,
              FOREIGN KEY (claimId) REFERENCES EvidenceClaim(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS PlanIteration (
              id        TEXT PRIMARY KEY,
              planId    TEXT NOT NULL,
              iteration INTEGER NOT NULL,
              trigger   TEXT,
              reason    TEXT,
              createdAt TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_goal_plan_goal ON GoalPlan(goalId, iteration)",
            "CREATE INDEX IF NOT EXISTS idx_goal_step_plan ON GoalStep(planId, idx)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_claim_run ON EvidenceClaim(runId, createdAt)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_handle_claim ON EvidenceHandleRow(claimId)",
        ),
    ),
)


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return "[]"


def _load(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class GoalStore:
    """Goal plan view + evidence ledger over the ONE agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db = getattr(store, "_db", store)
        MigrationRunner(self._db, "agent-memory").apply(GOAL_MIGRATIONS)

    # ── Goals ────────────────────────────────────────────────────────────────
    def create_goal(
        self, objective: str, *, acceptance: Optional[list[str]] = None,
        budget: Optional[dict[str, Any]] = None, task_id: Optional[str] = None,
        goal_id: Optional[str] = None,
    ) -> Goal:
        goal = Goal(
            id=goal_id or _uid("goal"),
            objective=str(objective)[:8_000],
            acceptance=tuple(str(item)[:500] for item in (acceptance or [])[:24]),
            task_id=task_id,
            status="active",
            budget=dict(budget or {}),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO GoalRecord "
            "(id, objective, acceptance, planId, taskId, status, budget, createdAt, updatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                goal.id, goal.objective, _json(list(goal.acceptance)), None,
                goal.task_id, goal.status, _json(goal.budget),
                goal.created_at, goal.updated_at,
            ),
        )
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        row = self._db.execute("SELECT * FROM GoalRecord WHERE id=?", (goal_id,)).fetchone()
        if row is None:
            return None
        return Goal(
            id=row["id"], objective=row["objective"],
            acceptance=tuple(_load(row["acceptance"], [])),
            plan_id=row["planId"], task_id=row["taskId"], status=row["status"],
            budget=dict(_load(row["budget"], {})),
            created_at=row["createdAt"], updated_at=row["updatedAt"],
        )

    def set_goal_status(self, goal_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE GoalRecord SET status=?, updatedAt=? WHERE id=?",
            (status, now_iso(), goal_id),
        )

    # ── Plans / steps ────────────────────────────────────────────────────────
    def create_plan(
        self, goal_id: str, steps: list[dict[str, Any]], *,
        iteration: int = 1, plan_id: Optional[str] = None,
    ) -> Plan:
        """Create a plan and its ordered steps.

        A step is `{title, objective, acceptance?}`. The caller owns the content;
        this store never invents a step.
        """
        plan = Plan(
            id=plan_id or _uid("plan"), goal_id=goal_id,
            iteration=max(1, int(iteration)), status="active",
            created_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO GoalPlan (id, goalId, iteration, status, createdAt) "
            "VALUES (?, ?, ?, ?, ?)",
            (plan.id, goal_id, plan.iteration, plan.status, plan.created_at),
        )
        self._db.execute(
            "UPDATE GoalRecord SET planId=?, updatedAt=? WHERE id=?",
            (plan.id, now_iso(), goal_id),
        )
        for index, raw in enumerate(steps or []):
            step = PlanStep(
                id=_uid("step"), plan_id=plan.id, index=index,
                title=str(raw.get("title") or f"Step {index + 1}")[:300],
                objective=str(raw.get("objective") or raw.get("title") or "")[:4_000],
                acceptance=tuple(
                    str(item)[:500] for item in (raw.get("acceptance") or [])[:24]
                ),
                created_at=now_iso(), updated_at=now_iso(),
            )
            self._db.execute(
                "INSERT INTO GoalStep "
                "(id, planId, idx, title, objective, acceptance, status, runId, createdAt, updatedAt) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    step.id, step.plan_id, step.index, step.title, step.objective,
                    _json(list(step.acceptance)), step.status, None,
                    step.created_at, step.updated_at,
                ),
            )
            plan.steps.append(step)
        return plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        row = self._db.execute("SELECT * FROM GoalPlan WHERE id=?", (plan_id,)).fetchone()
        if row is None:
            return None
        plan = Plan(
            id=row["id"], goal_id=row["goalId"], iteration=int(row["iteration"]),
            status=row["status"], created_at=row["createdAt"],
        )
        for step_row in self._db.execute(
            "SELECT * FROM GoalStep WHERE planId=? ORDER BY idx ASC", (plan_id,)
        ).fetchall():
            plan.steps.append(PlanStep(
                id=step_row["id"], plan_id=step_row["planId"], index=int(step_row["idx"]),
                title=step_row["title"], objective=step_row["objective"],
                acceptance=tuple(_load(step_row["acceptance"], [])),
                status=step_row["status"], run_id=step_row["runId"],
                created_at=step_row["createdAt"], updated_at=step_row["updatedAt"],
            ))
        return plan

    def set_step_status(
        self, step_id: str, status: str, *, run_id: Optional[str] = None,
    ) -> None:
        sets = ["status=?", "updatedAt=?"]
        params: list[Any] = [status, now_iso()]
        if run_id is not None:
            sets.insert(1, "runId=?")
            params.insert(1, run_id)
        params.append(step_id)
        self._db.execute(f"UPDATE GoalStep SET {', '.join(sets)} WHERE id=?", params)

    def set_plan_status(self, plan_id: str, status: str) -> None:
        self._db.execute("UPDATE GoalPlan SET status=? WHERE id=?", (status, plan_id))

    def count_iterations(self, plan_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM PlanIteration WHERE planId=?", (plan_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def record_iteration(
        self, plan_id: str, iteration: int, *, trigger: str = "", reason: str = "",
    ) -> None:
        self._db.execute(
            "INSERT INTO PlanIteration (id, planId, iteration, trigger, reason, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_uid("iter"), plan_id, int(iteration), trigger, reason, now_iso()),
        )
        self._db.execute(
            "UPDATE GoalPlan SET iteration=? WHERE id=? AND iteration<?",
            (int(iteration), plan_id, int(iteration)),
        )

    # ── Evidence ─────────────────────────────────────────────────────────────
    def record_claim(
        self,
        *,
        run_id: str,
        text: str,
        handles: Optional[list[dict[str, Any]]] = None,
        status: str = "unverified",
        verifier: str = "",
        step_id: Optional[str] = None,
    ) -> Claim:
        clean_handles = []
        for raw in (handles or [])[:MAX_HANDLES]:
            handle = EvidenceHandle.from_dict(raw)
            if handle.valid:
                clean_handles.append(handle)
        claim = Claim(
            id=_uid("claim"), run_id=str(run_id), step_id=step_id,
            text=str(text)[:MAX_CLAIM_TEXT], status=status, verifier=verifier,
            handles=clean_handles, created_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO EvidenceClaim (id, runId, stepId, text, status, verifier, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (claim.id, claim.run_id, claim.step_id, claim.text, claim.status,
             claim.verifier, claim.created_at),
        )
        for handle in clean_handles:
            self._db.execute(
                "INSERT INTO EvidenceHandleRow (id, claimId, kind, ref, source, digest, at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_uid("ehr"), claim.id, handle.kind, handle.ref, handle.source,
                 handle.digest, handle.at or now_iso()),
            )
        return claim

    def set_claim_status(self, claim_id: str, status: str, verifier: str = "") -> None:
        self._db.execute(
            "UPDATE EvidenceClaim SET status=?, verifier=? WHERE id=?",
            (status, verifier, claim_id),
        )

    def supersede_claims(self, run_id: str, step_id: Optional[str] = None) -> int:
        """Retire a failed draft's answer claims (tool-result evidence stays)."""
        sql = (
            "UPDATE EvidenceClaim SET status='superseded' "
            "WHERE runId=? AND status IN ('unsupported','unverified') "
            "AND (verifier IS NULL OR verifier != 'tool_result')"
        )
        params: list[Any] = [run_id]
        if step_id is not None:
            sql += " AND stepId=?"
            params.append(step_id)
        cursor = self._db.execute(sql, params)
        return int(getattr(cursor, "rowcount", 0) or 0)

    def list_claims(self, run_id: str, limit: int = 200) -> list[Claim]:
        rows = self._db.execute(
            "SELECT * FROM EvidenceClaim WHERE runId=? ORDER BY createdAt ASC LIMIT ?",
            (run_id, max(1, min(int(limit), 1_000))),
        ).fetchall()
        out: list[Claim] = []
        for row in rows:
            handles = [
                EvidenceHandle(
                    kind=h["kind"], ref=h["ref"], source=h["source"] or "",
                    digest=h["digest"], at=h["at"],
                )
                for h in self._db.execute(
                    "SELECT * FROM EvidenceHandleRow WHERE claimId=? ORDER BY id ASC",
                    (row["id"],),
                ).fetchall()
            ]
            out.append(Claim(
                id=row["id"], run_id=row["runId"], step_id=row["stepId"],
                text=row["text"], status=row["status"], verifier=row["verifier"] or "",
                handles=handles, created_at=row["createdAt"],
            ))
        return out

    def goal_for_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """The goal/plan step a run executed, or None for an ordinary run."""
        row = self._db.execute(
            "SELECT * FROM GoalStep WHERE runId=? ORDER BY updatedAt DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        plan_row = self._db.execute(
            "SELECT * FROM GoalPlan WHERE id=?", (row["planId"],),
        ).fetchone()
        if plan_row is None:
            return None
        goal_row = self._db.execute(
            "SELECT * FROM GoalRecord WHERE id=?", (plan_row["goalId"],),
        ).fetchone()
        return {
            "goalId": plan_row["goalId"],
            "objective": goal_row["objective"] if goal_row is not None else None,
            "planId": plan_row["id"],
            "iteration": int(plan_row["iteration"]),
            "stepId": row["id"],
            "stepTitle": row["title"],
            "stepStatus": row["status"],
        }

    def summary(self, run_id: str) -> dict[str, Any]:
        claims = self.list_claims(run_id)
        counts = {"supported": 0, "unsupported": 0, "unverified": 0}
        for claim in claims:
            counts[claim.status] = counts.get(claim.status, 0) + 1
        return {"runId": run_id, "claims": len(claims), "byStatus": counts}


__all__ = ["GOAL_MIGRATIONS", "GoalStore"]
