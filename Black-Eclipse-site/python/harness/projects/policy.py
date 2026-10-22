"""The auto-run policy — the rule that lets a project act on its own.

A project that proposes its next step is useful. A project that *runs* it
without being asked is a different thing entirely, and it is only safe if the
bounds are explicit, visible and enforced **by the runtime** rather than by the
model's good intentions.

This module owns the policy and the ledger:

- **the policy** (per project): off by default, and when on it says how many
  runs a day, how many seconds a day, how far apart two runs must be, and
  which tools may be run at all;
- **the ledger**: every automatic run, with its tool, its status and its
  outcome, so "the project ran this at 03:14" is a fact, not a story.

The policy is deliberately narrow. A project may only run tools that COMPUTE
(`AUTO_RUNNABLE_TOOLS`); it can never run anything with an effect on the
world, because the whole point is to let a project act unattended without
letting it act *dangerously*.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

#: The only tools a project may run on its own. Every one of them COMPUTES:
#: a backtest, a sweep, a rule evaluation. None of them touches the world.
AUTO_RUNNABLE_TOOLS: tuple[str, ...] = (
    "run_backtest",
    "run_sensitivity_analysis",
    "run_robustness_analysis",
    "run_monte_carlo",
    "run_prop_firm_simulation",
)

#: The default budget. Deliberately small: a project that acts unattended
#: should act rarely, and the operator can widen it per project.
DEFAULT_MAX_RUNS_PER_DAY = 2
DEFAULT_MAX_SECONDS_PER_DAY = 600
DEFAULT_MIN_INTERVAL_MINUTES = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: Optional[datetime] = None) -> str:
    return (moment or _now()).isoformat()


@dataclass
class AutoRunPolicy:
    """When a project may act on its own, and how much."""

    project_id: str
    enabled: bool = False
    max_runs_per_day: int = DEFAULT_MAX_RUNS_PER_DAY
    max_seconds_per_day: int = DEFAULT_MAX_SECONDS_PER_DAY
    min_interval_minutes: int = DEFAULT_MIN_INTERVAL_MINUTES
    allowed_tools: list[str] = field(default_factory=lambda: list(AUTO_RUNNABLE_TOOLS))
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "enabled": self.enabled,
            "maxRunsPerDay": self.max_runs_per_day,
            "maxSecondsPerDay": self.max_seconds_per_day,
            "minIntervalMinutes": self.min_interval_minutes,
            "allowedTools": list(self.allowed_tools),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def may_run(self, tool: str) -> bool:
        return tool in self.allowed_tools and tool in AUTO_RUNNABLE_TOOLS


_DDL = """
CREATE TABLE IF NOT EXISTS ProjectPolicy (
  projectId         TEXT PRIMARY KEY,
  enabled           INTEGER NOT NULL DEFAULT 0,
  maxRunsPerDay     INTEGER NOT NULL DEFAULT 2,
  maxSecondsPerDay  INTEGER NOT NULL DEFAULT 600,
  minIntervalMin    INTEGER NOT NULL DEFAULT 60,
  allowedToolsJson  TEXT NOT NULL DEFAULT '[]',
  createdAt         TEXT NOT NULL,
  updatedAt         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ProjectAutoRun (
  id           TEXT PRIMARY KEY,
  projectId    TEXT NOT NULL,
  proposalId  TEXT NOT NULL,
  tool         TEXT NOT NULL,
  status       TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  experimentId TEXT,
  startedAt    TEXT NOT NULL,
  finishedAt   TEXT NOT NULL,
  durationMs   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_project_autorun_project
  ON ProjectAutoRun(projectId, startedAt);
"""


class AutoRunStore:
    """The auto-run policies and the ledger of what they did."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_DDL)
        self._db.commit()

    # ── the policy ───────────────────────────────────────────────────────────

    def get_policy(self, project_id: str) -> AutoRunPolicy:
        row = self._db.execute(
            "SELECT * FROM ProjectPolicy WHERE projectId=?", (str(project_id),)).fetchone()
        if row is None:
            return AutoRunPolicy(project_id=str(project_id))
        try:
            tools = json.loads(row["allowedToolsJson"] or "[]")
        except (TypeError, ValueError):
            tools = []
        return AutoRunPolicy(
            project_id=row["projectId"],
            enabled=bool(row["enabled"]),
            max_runs_per_day=int(row["maxRunsPerDay"]),
            max_seconds_per_day=int(row["maxSecondsPerDay"]),
            min_interval_minutes=int(row["minIntervalMin"]),
            allowed_tools=[t for t in tools if t in AUTO_RUNNABLE_TOOLS] or
            list(AUTO_RUNNABLE_TOOLS),
            created_at=row["createdAt"] or "",
            updated_at=row["updatedAt"] or "",
        )

    def set_policy(self, project_id: str, **patch: Any) -> AutoRunPolicy:
        policy = self.get_policy(project_id)
        if "enabled" in patch and patch["enabled"] is not None:
            policy.enabled = bool(patch["enabled"])
        if "maxRunsPerDay" in patch and patch["maxRunsPerDay"] is not None:
            policy.max_runs_per_day = max(0, int(patch["maxRunsPerDay"]))
        if "maxSecondsPerDay" in patch and patch["maxSecondsPerDay"] is not None:
            policy.max_seconds_per_day = max(0, int(patch["maxSecondsPerDay"]))
        if "minIntervalMinutes" in patch and patch["minIntervalMinutes"] is not None:
            policy.min_interval_minutes = max(0, int(patch["minIntervalMinutes"]))
        if "allowedTools" in patch and patch["allowedTools"] is not None:
            requested = [str(t) for t in patch["allowedTools"]]
            policy.allowed_tools = [t for t in requested if t in AUTO_RUNNABLE_TOOLS]
        now = _iso()
        if not policy.created_at:
            policy.created_at = now
        policy.updated_at = now
        self._db.execute(
            "INSERT INTO ProjectPolicy (projectId,enabled,maxRunsPerDay,maxSecondsPerDay,"
            "minIntervalMin,allowedToolsJson,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(projectId) DO UPDATE SET enabled=excluded.enabled, "
            "maxRunsPerDay=excluded.maxRunsPerDay, maxSecondsPerDay=excluded.maxSecondsPerDay, "
            "minIntervalMin=excluded.minIntervalMin, allowedToolsJson=excluded.allowedToolsJson, "
            "updatedAt=excluded.updatedAt",
            (policy.project_id, int(policy.enabled), policy.max_runs_per_day,
             policy.max_seconds_per_day, policy.min_interval_minutes,
             json.dumps(policy.allowed_tools), policy.created_at, policy.updated_at),
        )
        self._db.commit()
        return policy

    def enabled_policies(self) -> list[AutoRunPolicy]:
        rows = self._db.execute(
            "SELECT * FROM ProjectPolicy WHERE enabled=1").fetchall()
        out: list[AutoRunPolicy] = []
        for row in rows:
            try:
                tools = json.loads(row["allowedToolsJson"] or "[]")
            except (TypeError, ValueError):
                tools = []
            out.append(AutoRunPolicy(
                project_id=row["projectId"], enabled=True,
                max_runs_per_day=int(row["maxRunsPerDay"]),
                max_seconds_per_day=int(row["maxSecondsPerDay"]),
                min_interval_minutes=int(row["minIntervalMin"]),
                allowed_tools=[t for t in tools if t in AUTO_RUNNABLE_TOOLS] or
                list(AUTO_RUNNABLE_TOOLS),
                created_at=row["createdAt"] or "", updated_at=row["updatedAt"] or "",
            ))
        return out

    # ── the ledger ───────────────────────────────────────────────────────────

    def record_run(self, project_id: str, proposal_id: str, tool: str, status: str,
                   *, summary: str = "", experiment_id: Optional[str] = None,
                   started_at: Optional[str] = None,
                   duration_ms: int = 0) -> str:
        run_id = f"parun_{uuid.uuid4().hex[:12]}"
        self._db.execute(
            "INSERT INTO ProjectAutoRun (id,projectId,proposalId,tool,status,summary,"
            "experimentId,startedAt,finishedAt,durationMs) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, str(project_id), str(proposal_id), str(tool), str(status),
             str(summary)[:400], experiment_id, started_at or _iso(), _iso(),
             int(duration_ms)),
        )
        self._db.commit()
        return run_id

    def runs_since(self, project_id: str, since: datetime) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM ProjectAutoRun WHERE projectId=? AND startedAt>=? "
            "ORDER BY startedAt ASC",
            (str(project_id), since.isoformat())).fetchall()
        return [dict(row) for row in rows]

    def last_run(self, project_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ProjectAutoRun WHERE projectId=? "
            "ORDER BY startedAt DESC LIMIT 1", (str(project_id),)).fetchone()
        return dict(row) if row else None

    def budget_state(self, policy: AutoRunPolicy, *, now: Optional[datetime] = None
                     ) -> dict[str, Any]:
        """What the policy has left today, and whether a run may happen now."""
        moment = now or _now()
        since = moment - timedelta(days=1)
        runs = self.runs_since(policy.project_id, since)
        used_runs = len(runs)
        used_seconds = sum(int(r.get("durationMs") or 0) for r in runs) / 1000.0
        last = self.last_run(policy.project_id)
        wait_seconds = 0.0
        if last and policy.min_interval_minutes > 0:
            try:
                started = datetime.fromisoformat(str(last.get("startedAt")))
            except (TypeError, ValueError):
                started = None
            if started is not None:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                elapsed = (moment - started).total_seconds()
                wait_seconds = max(0.0, policy.min_interval_minutes * 60 - elapsed)
        reasons = []
        if used_runs >= policy.max_runs_per_day:
            reasons.append("daily_run_budget")
        if used_seconds >= policy.max_seconds_per_day:
            reasons.append("daily_second_budget")
        if wait_seconds > 0:
            reasons.append("min_interval")
        return {
            "usedRuns": used_runs,
            "maxRunsPerDay": policy.max_runs_per_day,
            "usedSeconds": round(used_seconds, 3),
            "maxSecondsPerDay": policy.max_seconds_per_day,
            "waitSeconds": round(wait_seconds, 3),
            "mayRun": not reasons,
            "blockedBy": reasons,
            "lastRunAt": (last or {}).get("startedAt"),
        }


#: The process-wide auto-run store. A singleton (like the Artifact Center's)
#: so the auto-run can act from a boot loop, where there is no run context to
#: carry it in.
_AUTO_RUN_STORE: Optional["AutoRunStore"] = None


def set_auto_run_store(store: Optional["AutoRunStore"]) -> None:
    global _AUTO_RUN_STORE
    _AUTO_RUN_STORE = store


def get_auto_run_store() -> Optional["AutoRunStore"]:
    return _AUTO_RUN_STORE


__all__ = [
    "AUTO_RUNNABLE_TOOLS",
    "get_auto_run_store",
    "set_auto_run_store",
    "AutoRunPolicy",
    "AutoRunStore",
    "DEFAULT_MAX_RUNS_PER_DAY",
    "DEFAULT_MAX_SECONDS_PER_DAY",
    "DEFAULT_MIN_INTERVAL_MINUTES",
]
