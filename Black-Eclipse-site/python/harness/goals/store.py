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
from .model import (
    Claim,
    EvidenceHandle,
    Goal,
    GoalVerdict,
    Loop,
    Plan,
    PlanStep,
)

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
    Migration(
        id="2026-11-12-006-goal-autonomy",
        description="W4 goal contract/gates/verdicts + session loops",
        statements=(
            "ALTER TABLE GoalRecord ADD COLUMN contract TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN gates TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN maxTurns INTEGER NOT NULL DEFAULT 20",
            "ALTER TABLE GoalRecord ADD COLUMN usedTurns INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE GoalRecord ADD COLUMN lastVerdict TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN sessionId TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN nextRunAt TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN noProgressCount INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE GoalRecord ADD COLUMN modelProvider TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN modelName TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN modelBaseUrl TEXT",
            "ALTER TABLE GoalRecord ADD COLUMN workspaceId TEXT",
            """
            CREATE TABLE IF NOT EXISTS GoalVerdict (
              id          TEXT PRIMARY KEY,
              goalId      TEXT NOT NULL,
              runId       TEXT,
              turn        INTEGER NOT NULL,
              verdict     TEXT NOT NULL,
              reason      TEXT,
              evidence    TEXT,
              gateResults TEXT,
              usage       TEXT,
              createdAt   TEXT NOT NULL,
              FOREIGN KEY (goalId) REFERENCES GoalRecord(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS GoalGateRun (
              id         TEXT PRIMARY KEY,
              goalId     TEXT NOT NULL,
              verdictId  TEXT,
              gateId     TEXT NOT NULL,
              checkName  TEXT NOT NULL,
              exitCode   INTEGER,
              timedOut   INTEGER NOT NULL DEFAULT 0,
              durationMs INTEGER,
              outputTail TEXT,
              createdAt  TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS AutonomyLoop (
              id               TEXT PRIMARY KEY,
              sessionId        TEXT NOT NULL,
              kind             TEXT NOT NULL,
              prompt           TEXT NOT NULL,
              mode             TEXT NOT NULL,
              intervalSeconds  INTEGER NOT NULL,
              nextTickAt       TEXT,
              lastTickAt       TEXT,
              maxTicks         INTEGER NOT NULL DEFAULT 50,
              usedTicks        INTEGER NOT NULL DEFAULT 0,
              noChangeCount    INTEGER NOT NULL DEFAULT 0,
              lastDigest       TEXT,
              lastRunId        TEXT,
              status           TEXT NOT NULL,
              modelProvider    TEXT,
              modelName        TEXT,
              modelBaseUrl     TEXT,
              workspaceId      TEXT,
              createdAt        TEXT NOT NULL,
              updatedAt        TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_goal_verdict_goal ON GoalVerdict(goalId, createdAt)",
            "CREATE INDEX IF NOT EXISTS idx_goal_gate_goal ON GoalGateRun(goalId, createdAt)",
            "CREATE INDEX IF NOT EXISTS idx_loop_session ON AutonomyLoop(sessionId, status)",
            "CREATE INDEX IF NOT EXISTS idx_loop_next ON AutonomyLoop(status, nextTickAt)",
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
        goal_id: Optional[str] = None, plan_id: Optional[str] = None,
        contract: Optional[dict[str, Any]] = None,
        gates: Optional[list[dict[str, Any]]] = None, max_turns: int = 20,
        session_id: Optional[str] = None, model_provider: Optional[str] = None,
        model_name: Optional[str] = None, model_base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Goal:
        goal = Goal(
            id=goal_id or _uid("goal"),
            objective=str(objective)[:8_000],
            acceptance=tuple(str(item)[:500] for item in (acceptance or [])[:24]),
            task_id=task_id,
            plan_id=plan_id,
            status="active",
            budget=dict(budget or {}),
            contract=dict(contract) if isinstance(contract, dict) else None,
            gates=[dict(item) for item in (gates or [])[:24]],
            max_turns=max(1, int(max_turns)),
            session_id=session_id,
            model_provider=model_provider,
            model_name=model_name,
            model_base_url=model_base_url,
            workspace_id=workspace_id,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO GoalRecord "
            "(id, objective, acceptance, planId, taskId, status, budget, contract, "
            "gates, maxTurns, usedTurns, lastVerdict, sessionId, nextRunAt, "
            "noProgressCount, modelProvider, modelName, modelBaseUrl, workspaceId, "
            "createdAt, updatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                goal.id, goal.objective, _json(list(goal.acceptance)), goal.plan_id,
                goal.task_id, goal.status, _json(goal.budget),
                _json(goal.contract) if goal.contract is not None else None,
                _json(goal.gates), goal.max_turns, 0, None, goal.session_id, None,
                0, goal.model_provider, goal.model_name, goal.model_base_url,
                goal.workspace_id, goal.created_at, goal.updated_at,
            ),
        )
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        row = self._db.execute("SELECT * FROM GoalRecord WHERE id=?", (goal_id,)).fetchone()
        if row is None:
            return None
        loaded = dict(row)
        return Goal(
            id=row["id"], objective=row["objective"],
            acceptance=tuple(_load(row["acceptance"], [])),
            plan_id=row["planId"], task_id=row["taskId"], status=row["status"],
            budget=dict(_load(row["budget"], {})),
            contract=_load(loaded.get("contract"), None),
            gates=list(_load(loaded.get("gates"), []) or []),
            max_turns=int(loaded.get("maxTurns") or 20),
            used_turns=int(loaded.get("usedTurns") or 0),
            last_verdict=_load(loaded.get("lastVerdict"), None),
            session_id=loaded.get("sessionId"),
            next_run_at=loaded.get("nextRunAt"),
            no_progress=int(loaded.get("noProgressCount") or 0),
            model_provider=loaded.get("modelProvider"),
            model_name=loaded.get("modelName"),
            model_base_url=loaded.get("modelBaseUrl"),
            workspace_id=loaded.get("workspaceId"),
            created_at=row["createdAt"], updated_at=row["updatedAt"],
        )

    def list_goals(
        self, *, session_id: Optional[str] = None, status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Goal]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("sessionId = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.execute(
            f"SELECT id FROM GoalRecord{where} ORDER BY createdAt DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        out: list[Goal] = []
        for row in rows:
            goal = self.get_goal(row["id"])
            if goal is not None:
                out.append(goal)
        return out

    def set_goal_status(self, goal_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE GoalRecord SET status=?, updatedAt=? WHERE id=?",
            (status, now_iso(), goal_id),
        )

    def due_goals(self, now: str, *, limit: int = 8) -> list[Goal]:
        rows = self._db.execute(
            "SELECT id FROM GoalRecord WHERE status='paused' "
            "AND nextRunAt IS NOT NULL AND nextRunAt <= ? "
            "ORDER BY nextRunAt ASC LIMIT ?",
            (now, max(1, min(int(limit), 50))),
        ).fetchall()
        out: list[Goal] = []
        for row in rows:
            goal = self.get_goal(row["id"])
            if goal is not None:
                out.append(goal)
        return out

    def goal_for_task(self, task_id: str) -> Optional[Goal]:
        if not task_id:
            return None
        row = self._db.execute(
            "SELECT id FROM GoalRecord WHERE taskId=? ORDER BY updatedAt DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return self.get_goal(row["id"]) if row is not None else None

    def update_goal_fields(self, goal_id: str, fields: dict[str, Any]) -> None:
        """Update a small, WHITELISTED set of goal fields (W4)."""
        allowed = {
            "planId", "taskId", "status", "contract", "gates", "maxTurns",
            "usedTurns", "lastVerdict", "sessionId", "nextRunAt",
            "noProgressCount", "modelProvider", "modelName", "modelBaseUrl",
            "workspaceId",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ("contract", "gates", "lastVerdict") and value is not None:
                value = _json(value)
            sets.append(f"{key}=?")
            params.append(value)
        if not sets:
            return
        sets.append("updatedAt=?")
        params.append(now_iso())
        params.append(goal_id)
        self._db.execute(
            f"UPDATE GoalRecord SET {', '.join(sets)} WHERE id=?", tuple(params),
        )

    def add_goal_turn(self, goal_id: str, *, last_verdict: Optional[dict[str, Any]] = None,
                      next_run_at: Optional[str] = None,
                      no_progress: Optional[int] = None) -> None:
        sets = ["usedTurns = usedTurns + 1", "updatedAt=?"]
        params: list[Any] = [now_iso()]
        if last_verdict is not None:
            sets.append("lastVerdict=?")
            params.append(_json(last_verdict))
        if next_run_at is not None:
            sets.append("nextRunAt=?")
            params.append(next_run_at)
        if no_progress is not None:
            sets.append("noProgressCount=?")
            params.append(int(no_progress))
        params.append(goal_id)
        self._db.execute(
            f"UPDATE GoalRecord SET {', '.join(sets)} WHERE id=?", tuple(params),
        )

    # ── Goal verdicts / gate audit (W4) ──────────────────────────────────────
    def record_verdict(
        self, goal_id: str, *, verdict: str, reason: str = "",
        run_id: Optional[str] = None, turn: int = 1,
        evidence: Optional[list[Any]] = None,
        gate_results: Optional[list[dict[str, Any]]] = None,
        usage: Optional[dict[str, Any]] = None,
    ) -> GoalVerdict:
        record = GoalVerdict(
            id=_uid("gv"), goal_id=goal_id, run_id=run_id, turn=int(turn),
            verdict=str(verdict), reason=str(reason)[:2_000],
            evidence=[str(item) for item in (evidence or [])[:24]],
            gate_results=[dict(item) for item in (gate_results or [])[:24]],
            usage=dict(usage or {}), created_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO GoalVerdict "
            "(id, goalId, runId, turn, verdict, reason, evidence, gateResults, usage, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id, record.goal_id, record.run_id, record.turn,
                record.verdict, record.reason, _json(record.evidence),
                _json(record.gate_results), _json(record.usage), record.created_at,
            ),
        )
        return record

    def list_verdicts(self, goal_id: str, *, limit: int = 50) -> list[GoalVerdict]:
        rows = self._db.execute(
            "SELECT * FROM GoalVerdict WHERE goalId=? ORDER BY createdAt ASC LIMIT ?",
            (goal_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [
            GoalVerdict(
                id=row["id"], goal_id=row["goalId"], run_id=row["runId"],
                turn=int(row["turn"]), verdict=row["verdict"],
                reason=row["reason"] or "",
                evidence=list(_load(row["evidence"], [])),
                gate_results=list(_load(row["gateResults"], [])),
                usage=dict(_load(row["usage"], {})), created_at=row["createdAt"],
            )
            for row in rows
        ]

    def record_gate_run(
        self, goal_id: str, *, gate_id: str, check: str, verdict_id: str = "",
        exit_code: Optional[int] = None, timed_out: bool = False,
        duration_ms: int = 0, output_tail: str = "",
    ) -> None:
        self._db.execute(
            "INSERT INTO GoalGateRun "
            "(id, goalId, verdictId, gateId, checkName, exitCode, timedOut, durationMs, "
            "outputTail, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uid("gg"), goal_id, verdict_id or None, gate_id, check,
                exit_code, 1 if timed_out else 0, int(duration_ms),
                str(output_tail or "")[:4_000], now_iso(),
            ),
        )

    # ── Loops / heartbeats (W4) ──────────────────────────────────────────────
    def create_loop(
        self, session_id: str, *, kind: str, prompt: str, mode: str = "fixed",
        interval_seconds: int = 300, next_tick_at: Optional[str] = None,
        max_ticks: int = 50, model_provider: Optional[str] = None,
        model_name: Optional[str] = None, model_base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Loop:
        loop = Loop(
            id=_uid("loop"), session_id=session_id, kind=kind,
            prompt=str(prompt)[:8_000], mode=mode,
            interval_seconds=max(1, int(interval_seconds)),
            next_tick_at=next_tick_at, max_ticks=max(1, int(max_ticks)),
            status="active", model_provider=model_provider,
            model_name=model_name, model_base_url=model_base_url,
            workspace_id=workspace_id, created_at=now_iso(), updated_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO AutonomyLoop "
            "(id, sessionId, kind, prompt, mode, intervalSeconds, nextTickAt, lastTickAt, "
            "maxTicks, usedTicks, noChangeCount, lastDigest, lastRunId, status, "
            "modelProvider, modelName, modelBaseUrl, workspaceId, createdAt, updatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                loop.id, loop.session_id, loop.kind, loop.prompt, loop.mode,
                loop.interval_seconds, loop.next_tick_at, None, loop.max_ticks,
                0, 0, None, None, loop.status, loop.model_provider, loop.model_name,
                loop.model_base_url, loop.workspace_id, loop.created_at,
                loop.updated_at,
            ),
        )
        return loop

    def get_loop(self, loop_id: str) -> Optional[Loop]:
        row = self._db.execute(
            "SELECT * FROM AutonomyLoop WHERE id=?", (loop_id,),
        ).fetchone()
        if row is None:
            return None
        return Loop(
            id=row["id"], session_id=row["sessionId"], kind=row["kind"],
            prompt=row["prompt"], mode=row["mode"],
            interval_seconds=int(row["intervalSeconds"]),
            next_tick_at=row["nextTickAt"], last_tick_at=row["lastTickAt"],
            max_ticks=int(row["maxTicks"]),
            used_ticks=int(row["usedTicks"]),
            no_change_count=int(row["noChangeCount"]),
            last_digest=row["lastDigest"], last_run_id=row["lastRunId"],
            status=row["status"], model_provider=row["modelProvider"],
            model_name=row["modelName"], model_base_url=row["modelBaseUrl"],
            workspace_id=row["workspaceId"], created_at=row["createdAt"],
            updated_at=row["updatedAt"],
        )

    def list_loops(
        self, *, session_id: Optional[str] = None, status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Loop]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("sessionId = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.execute(
            f"SELECT * FROM AutonomyLoop{where} ORDER BY createdAt DESC LIMIT ?",
            tuple(params),
        ).fetchall()
        out: list[Loop] = []
        for row in rows:
            loaded = self.get_loop(row["id"])
            if loaded is not None:
                out.append(loaded)
        return out

    def due_loops(self, now: str, *, limit: int = 8) -> list[Loop]:
        rows = self._db.execute(
            "SELECT id FROM AutonomyLoop WHERE status='active' "
            "AND nextTickAt IS NOT NULL AND nextTickAt <= ? "
            "ORDER BY nextTickAt ASC LIMIT ?",
            (now, max(1, min(int(limit), 50))),
        ).fetchall()
        out: list[Loop] = []
        for row in rows:
            loaded = self.get_loop(row["id"])
            if loaded is not None:
                out.append(loaded)
        return out

    def update_loop_fields(self, loop_id: str, fields: dict[str, Any]) -> None:
        allowed = {
            "mode", "intervalSeconds", "nextTickAt", "lastTickAt", "maxTicks",
            "usedTicks", "noChangeCount", "lastDigest", "lastRunId", "status", "modelProvider",
            "modelName", "modelBaseUrl", "workspaceId",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            sets.append(f"{key}=?")
            params.append(value)
        if not sets:
            return
        sets.append("updatedAt=?")
        params.append(now_iso())
        params.append(loop_id)
        self._db.execute(
            f"UPDATE AutonomyLoop SET {', '.join(sets)} WHERE id=?", tuple(params),
        )

    def cancel_loops_for_session(self, session_id: str) -> int:
        cursor = self._db.execute(
            "UPDATE AutonomyLoop SET status='cancelled', updatedAt=? "
            "WHERE sessionId=? AND status IN ('active','paused')",
            (now_iso(), session_id),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

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
