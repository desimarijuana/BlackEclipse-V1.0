"""Advisory Ledger persistence on the ONE `agent-memory.db` connection.

Every actionable recommendation the Fiduciary Gate found is a durable decision:
what was recommended, on what basis, and (later) how it turned out. This is the
"was that call right, and why did I make it?" record.

Follows `PortfolioStore`'s pattern exactly: it wraps the shared `AgentMemoryStore`
connection, adds no second database and no migration step, and creates its tables
idempotently. Decisions are private user/agent state and are never committed.

Immutable decisions: a decision is written once (idempotently, by a deterministic
id) and an OUTCOME is appended to it. A re-run of the same answer never duplicates
a decision; a later evaluation never rewrites its basis.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS AdvisoryDecision (
  id             TEXT PRIMARY KEY,
  runId          TEXT,
  portfolioId    TEXT,
  conversationId TEXT,
  ownerId        TEXT,
  createdAt      TEXT NOT NULL,
  action         TEXT NOT NULL,
  symbols        TEXT NOT NULL DEFAULT '[]',
  target         TEXT,
  thesis         TEXT,
  status         TEXT NOT NULL,
  truthReason    TEXT,
  method         TEXT,
  horizon        TEXT,
  dueAt          TEXT
);
CREATE INDEX IF NOT EXISTS idx_advisory_decision_created ON AdvisoryDecision(createdAt);
CREATE INDEX IF NOT EXISTS idx_advisory_decision_portfolio ON AdvisoryDecision(portfolioId);
CREATE INDEX IF NOT EXISTS idx_advisory_decision_owner ON AdvisoryDecision(ownerId);

CREATE TABLE IF NOT EXISTS AdvisoryBasis (
  id         TEXT PRIMARY KEY,
  decisionId TEXT NOT NULL,
  kind       TEXT NOT NULL,
  ref        TEXT,
  valueHash  TEXT,
  FOREIGN KEY (decisionId) REFERENCES AdvisoryDecision(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_advisory_basis_decision ON AdvisoryBasis(decisionId);

CREATE TABLE IF NOT EXISTS AdvisoryOutcome (
  decisionId      TEXT PRIMARY KEY,
  evaluatedAt     TEXT NOT NULL,
  horizon         TEXT,
  realizedReturn  TEXT,
  benchmarkReturn TEXT,
  verdict         TEXT NOT NULL,
  note            TEXT,
  FOREIGN KEY (decisionId) REFERENCES AdvisoryDecision(id) ON DELETE CASCADE
);
"""


def decision_id(run_id: Optional[str], action: str, symbols: tuple[str, ...] | list[str], target: Optional[str]) -> str:
    """A deterministic id so a re-run of the same answer never duplicates a decision."""
    raw = "|".join([str(run_id or ""), str(action), ",".join(symbols or []), str(target or "")])
    return "adv_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class AdvisoryStore:
    """CRUD over the advisory tables on the shared agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        # Additive columns for databases created before scoring horizons existed.
        existing = {
            row["name"]
            for row in self._db.execute("PRAGMA table_info(AdvisoryDecision)").fetchall()
        }
        for column in ("method", "horizon", "dueAt"):
            if column not in existing:
                self._db.execute(
                    f"ALTER TABLE AdvisoryDecision ADD COLUMN {column} TEXT"
                )
        self._db.commit()

    # ── Decisions ────────────────────────────────────────────────────────────
    def upsert_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        self._db.execute(
            """INSERT INTO AdvisoryDecision
               (id, runId, portfolioId, conversationId, ownerId, createdAt, action,
                symbols, target, thesis, status, truthReason, method, horizon, dueAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (
                decision["id"], decision.get("runId"), decision.get("portfolioId"),
                decision.get("conversationId"), decision.get("ownerId"),
                decision.get("createdAt") or now_iso(), decision["action"],
                json.dumps(list(decision.get("symbols") or [])),
                decision.get("target"), decision.get("thesis"),
                decision["status"], decision.get("truthReason"),
                decision.get("method"), decision.get("horizon"),
                decision.get("dueAt"),
            ),
        )
        self._db.commit()
        return self.get_decision(decision["id"])  # type: ignore[return-value]

    def get_decision(self, decision_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM AdvisoryDecision WHERE id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        record = self._decision_row(row)
        record["basis"] = self._basis(decision_id)
        record["outcome"] = self.get_outcome(decision_id)
        return record

    def list_decisions(
        self,
        *,
        portfolio_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if portfolio_id:
            clauses.append("portfolioId = ?")
            values.append(portfolio_id)
        if owner_id:
            clauses.append("(ownerId = ? OR ownerId IS NULL)")
            values.append(owner_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(int(limit))
        rows = self._db.execute(
            f"SELECT * FROM AdvisoryDecision {where} ORDER BY createdAt DESC LIMIT ?", values
        ).fetchall()
        return [self._decision_row(r) for r in rows]

    def backfill_scoring_fields(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Fill method/horizon on legacy rows without inventing an outcome.

        `method` falls back to the recorded action; `horizon` becomes the
        explicit `unscored` defect. `dueAt` stays NULL because no deadline was
        ever stated.
        """
        import datetime as _dt
        import os

        default_horizon = os.environ.get("HARNESS_ADVISORY_DEFAULT_HORIZON", "30d")
        method_by_status = {
            "computed": "portfolio_computation",
            "sourced": "portfolio_read",
            "unverified": "model_advice",
        }
        rows = self._db.execute(
            "SELECT id, action, status, method, horizon, createdAt FROM AdvisoryDecision "
            "WHERE method IS NULL OR method='unclassified' "
            "OR horizon IS NULL OR horizon='unscored'"
        ).fetchall()
        updates: list[str] = []
        for row in rows:
            method = (
                row["method"]
                if row["method"] and row["method"] != "unclassified"
                else method_by_status.get(str(row["status"]), "unclassified")
            )
            horizon = (
                row["horizon"]
                if row["horizon"] and row["horizon"] != "unscored"
                else default_horizon
            )
            due = None
            try:
                stamp = _dt.datetime.fromisoformat(
                    str(row["createdAt"]).replace("Z", "+00:00")
                )
                import re

                match = re.match(r"^(\d+)([dwmy])$", str(horizon).lower())
                units = {"d": 1, "w": 7, "m": 30, "y": 365}
                days = (
                    int(match.group(1)) * units[match.group(2)]
                    if match else None
                )
                if days is not None:
                    due = (stamp + _dt.timedelta(days=days)).isoformat()
            except (TypeError, ValueError):
                due = None
            updates.append(row["id"])
            if not dry_run:
                self._db.execute(
                    "UPDATE AdvisoryDecision SET method=?, horizon=?, dueAt=? "
                    "WHERE id=? AND (method IS NULL OR method='unclassified' "
                    "OR horizon IS NULL OR horizon='unscored')",
                    (method, horizon, due, row["id"]),
                )
        if not dry_run:
            self._db.commit()
        return {
            "ok": True,
            "dryRun": bool(dry_run),
            "backfilled": updates,
            "backfilledCount": len(updates),
        }

    # ── Basis ────────────────────────────────────────────────────────────────
    def add_basis(self, decision_id: str, entries: list[dict[str, Any]]) -> None:
        for index, entry in enumerate(entries):
            basis_id = f"advb_{decision_id}_{index}"
            self._db.execute(
                """INSERT INTO AdvisoryBasis (id, decisionId, kind, ref, valueHash)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING""",
                (basis_id, decision_id, entry.get("kind", "unknown"),
                 entry.get("ref"), entry.get("valueHash")),
            )
        self._db.commit()

    def _basis(self, decision_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM AdvisoryBasis WHERE decisionId = ? ORDER BY id", (decision_id,)
        ).fetchall()
        return [{"kind": r["kind"], "ref": r["ref"], "valueHash": r["valueHash"]} for r in rows]

    # ── Outcomes ─────────────────────────────────────────────────────────────
    def upsert_outcome(self, decision_id: str, outcome: dict[str, Any]) -> Optional[dict[str, Any]]:
        self._db.execute(
            """INSERT INTO AdvisoryOutcome
               (decisionId, evaluatedAt, horizon, realizedReturn, benchmarkReturn, verdict, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(decisionId) DO UPDATE SET
                 evaluatedAt=excluded.evaluatedAt, horizon=excluded.horizon,
                 realizedReturn=excluded.realizedReturn, benchmarkReturn=excluded.benchmarkReturn,
                 verdict=excluded.verdict, note=excluded.note""",
            (
                decision_id, outcome.get("evaluatedAt") or now_iso(),
                outcome.get("horizon"), _num(outcome.get("realizedReturn")),
                _num(outcome.get("benchmarkReturn")), outcome["verdict"], outcome.get("note"),
            ),
        )
        self._db.commit()
        return self.get_outcome(decision_id)

    def get_outcome(self, decision_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM AdvisoryOutcome WHERE decisionId = ?", (decision_id,)
        ).fetchone()
        return self._outcome_row(row) if row is not None else None

    def outcomes_for(self, decision_ids: list[str]) -> list[dict[str, Any]]:
        if not decision_ids:
            return []
        marks = ",".join("?" for _ in decision_ids)
        rows = self._db.execute(
            f"SELECT * FROM AdvisoryOutcome WHERE decisionId IN ({marks})", decision_ids
        ).fetchall()
        return [self._outcome_row(r) for r in rows]

    # ── row helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _decision_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"], "runId": row["runId"], "portfolioId": row["portfolioId"],
            "conversationId": row["conversationId"], "ownerId": row["ownerId"],
            "createdAt": row["createdAt"], "action": row["action"],
            "symbols": json.loads(row["symbols"] or "[]"), "target": row["target"],
            "thesis": row["thesis"], "status": row["status"], "truthReason": row["truthReason"],
            "method": row["method"] if "method" in row.keys() else None,
            "horizon": row["horizon"] if "horizon" in row.keys() else None,
            "dueAt": row["dueAt"] if "dueAt" in row.keys() else None,
        }

    @staticmethod
    def _outcome_row(row: Any) -> dict[str, Any]:
        return {
            "decisionId": row["decisionId"], "evaluatedAt": row["evaluatedAt"],
            "horizon": row["horizon"],
            "realizedReturn": _float_or_none(row["realizedReturn"]),
            "benchmarkReturn": _float_or_none(row["benchmarkReturn"]),
            "verdict": row["verdict"], "note": row["note"],
        }


def _num(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["AdvisoryStore", "decision_id"]
