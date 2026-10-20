"""Immutable harness states for the RSL hill climb.

A `HarnessState` is one evaluated point in harness space: a snapshot digest plus
the metric snapshot and utility that justified it. States are append-only —
a promotion supersedes the previous current row, it never rewrites it. The store
is bound to the ONE agent-memory database, matching `EvolutionStore` and
`EvaluationStore`; this is not a second store.

Only an operator promotion may make a candidate the current state. The hill
climb itself can stage candidates; it cannot self-promote in production.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso

STATUSES: tuple[str, ...] = ("candidate", "current", "superseded", "retired")
_CURRENT = "current"


def new_state_id() -> str:
    return "hstate_" + uuid.uuid4().hex[:16]


def new_activation_id() -> str:
    return "hact_" + uuid.uuid4().hex[:16]


def _loads(raw: Any) -> Any:
    if raw in (None, ""):
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _activation_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "stateId": row["stateId"],
        "scope": row["scope"],
        "snapshot": _loads(row["snapshotJson"]),
        "base": _loads(row["baseJson"]),
        "previousStateId": row["previousStateId"],
        "activatedAt": row["activatedAt"],
        "rolledBackAt": row["rolledBackAt"],
    }


def _state_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "parentStateId": row["parentStateId"],
        "scope": row["scope"],
        "snapshotDigest": row["snapshotDigest"],
        "candidateId": row["candidateId"],
        "acceptedRunId": row["acceptedRunId"],
        "utility": row["utility"],
        "metrics": _loads(row["metricsJson"]),
        "status": row["status"],
        "createdAt": row["createdAt"],
        "promotedAt": row["promotedAt"],
    }


class HarnessStateStore:
    """Append-only `HarnessState` rows on the shared agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessState (
              id              TEXT PRIMARY KEY,
              parentStateId   TEXT,
              scope           TEXT NOT NULL DEFAULT 'global',
              snapshotDigest  TEXT NOT NULL,
              candidateId     TEXT,
              acceptedRunId   TEXT,
              utility         REAL,
              metricsJson     TEXT NOT NULL DEFAULT '{}',
              status          TEXT NOT NULL DEFAULT 'candidate',
              createdAt       TEXT NOT NULL,
              promotedAt      TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_harness_state_scope "
            "ON HarnessState(scope, status, createdAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_harness_state_parent "
            "ON HarnessState(parentStateId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessActivation (
              id              TEXT PRIMARY KEY,
              stateId         TEXT NOT NULL,
              scope           TEXT NOT NULL DEFAULT 'global',
              snapshotJson    TEXT NOT NULL,
              baseJson        TEXT NOT NULL,
              previousStateId TEXT,
              activatedAt     TEXT NOT NULL,
              rolledBackAt    TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_harness_activation_scope "
            "ON HarnessActivation(scope, activatedAt)"
        )
        self._db.commit()

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Insert one immutable state row. A `current` row is never overwritten."""
        scope = str(state.get("scope") or "global").strip() or "global"
        digest = str(state.get("snapshotDigest") or "").strip()
        if not digest:
            raise ValueError("a harness state requires a snapshotDigest")
        status = str(state.get("status") or "candidate")
        if status not in STATUSES:
            raise ValueError(f"unknown harness state status {status!r}")
        state_id = str(state.get("id") or new_state_id())
        created = str(state.get("createdAt") or now_iso())
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if status == _CURRENT:
                self._db.execute(
                    "UPDATE HarnessState SET status='superseded' "
                    "WHERE scope=? AND status='current'",
                    (scope,),
                )
            self._db.execute(
                """INSERT INTO HarnessState
                   (id, parentStateId, scope, snapshotDigest, candidateId,
                    acceptedRunId, utility, metricsJson, status, createdAt, promotedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state_id, state.get("parentStateId"), scope, digest,
                    state.get("candidateId"), state.get("acceptedRunId"),
                    state.get("utility"),
                    json.dumps(state.get("metrics") or {}, sort_keys=True, default=str),
                    status, created, state.get("promotedAt"),
                ),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_state(state_id) or {**state, "id": state_id}

    def get_state(self, state_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessState WHERE id=?", (state_id,)
        ).fetchone()
        return _state_row(row) if row else None

    def current(self, scope: str = "global") -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessState WHERE scope=? AND status=? "
            "ORDER BY createdAt DESC LIMIT 1",
            (str(scope or "global"), _CURRENT),
        ).fetchone()
        return _state_row(row) if row else None

    def current_states(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessState WHERE status='current' "
            "ORDER BY scope, createdAt DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [_state_row(row) for row in rows]

    def list_states(
        self,
        *,
        scope: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("scope=?")
            params.append(scope)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM HarnessState {where} ORDER BY createdAt DESC LIMIT ?",
            params,
        ).fetchall()
        return [_state_row(row) for row in rows]

    def lineage(self, state_id: str) -> list[dict[str, Any]]:
        """The parent chain from the named state back to its root."""
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: Optional[str] = state_id
        while current and current not in seen:
            seen.add(current)
            row = self.get_state(current)
            if row is None:
                break
            chain.append(row)
            current = row.get("parentStateId")
        return chain

    def promote(self, state_id: str, *, promoted_at: Optional[str] = None) -> dict[str, Any]:
        """Make one state current for its scope; supersede the prior current row.

        This is the operator decision. The state must already exist; promotion
        never creates a state and never changes the metrics it was accepted on.
        """
        state = self.get_state(state_id)
        if state is None:
            raise ValueError(f"unknown harness state {state_id!r}")
        if state["status"] not in ("candidate", "current"):
            raise ValueError(f"state {state_id!r} is {state['status']!r}, not promotable")
        stamp = promoted_at or now_iso()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                "UPDATE HarnessState SET status='superseded' "
                "WHERE scope=? AND status='current' AND id<>?",
                (state["scope"], state_id),
            )
            self._db.execute(
                "UPDATE HarnessState SET status='current', promotedAt=? WHERE id=?",
                (stamp, state_id),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_state(state_id) or state

    def retire(self, state_id: str) -> dict[str, Any]:
        state = self.get_state(state_id)
        if state is None:
            raise ValueError(f"unknown harness state {state_id!r}")
        if state["status"] == "retired":
            return state
        self._db.execute(
            "UPDATE HarnessState SET status='retired' WHERE id=?", (state_id,)
        )
        self._db.commit()
        return self.get_state(state_id) or state

    def activate_surface(
        self,
        state_id: str,
        *,
        snapshot: dict[str, Any],
        base: dict[str, Any],
        activated_at: Optional[str] = None,
    ) -> dict[str, Any]:
        """Promote a measured surface state and record its validated snapshot.

        The snapshot and base are already validated by the caller. This method
        only makes the state current and writes the activation row; it never
        writes code. Rolling back restores the previous current state.
        """
        state = self.get_state(state_id)
        if state is None:
            raise ValueError(f"unknown harness state {state_id!r}")
        if state["status"] not in ("candidate", "current"):
            raise ValueError(f"state {state_id!r} is {state['status']!r}, not activatable")
        previous = self.current(state["scope"])
        previous_id = previous["id"] if previous and previous["id"] != state_id else None
        activation_id = new_activation_id()
        stamp = activated_at or now_iso()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                "UPDATE HarnessState SET status='superseded' "
                "WHERE scope=? AND status='current' AND id<>?",
                (state["scope"], state_id),
            )
            self._db.execute(
                "UPDATE HarnessState SET status='current', promotedAt=? WHERE id=?",
                (stamp, state_id),
            )
            self._db.execute(
                """INSERT INTO HarnessActivation
                   (id, stateId, scope, snapshotJson, baseJson, previousStateId,
                    activatedAt, rolledBackAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    activation_id, state_id, state["scope"],
                    json.dumps(snapshot, sort_keys=True, default=str),
                    json.dumps(base, sort_keys=True, default=str),
                    previous_id, stamp,
                ),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_activation(activation_id) or {}

    def get_activation(self, activation_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessActivation WHERE id=?", (activation_id,)
        ).fetchone()
        return _activation_row(row) if row else None

    def _active_row_for_scope(self, scope: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessActivation WHERE scope=? AND rolledBackAt IS NULL "
            "ORDER BY activatedAt DESC LIMIT 1",
            (scope,),
        ).fetchone()
        if row is None:
            return None
        current = self.current(scope)
        if current is None or current["id"] != row["stateId"]:
            return None
        return _activation_row(row)

    def active_activation(self, scope: str = "global") -> Optional[dict[str, Any]]:
        """The active surface for a scope, preferring the specific agent scope.

        An activation is only active while its state is the current state for
        that scope. A separate promotion supersedes it, so the live surface stops
        applying without needing a second rollback call.
        """
        wanted = str(scope or "global")
        row = self._active_row_for_scope(wanted)
        if row is None and wanted != "global":
            row = self._active_row_for_scope("global")
        return row

    def list_activations(
        self, *, scope: Optional[str] = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        if scope:
            rows = self._db.execute(
                "SELECT * FROM HarnessActivation WHERE scope=? "
                "ORDER BY activatedAt DESC LIMIT ?",
                (scope, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessActivation ORDER BY activatedAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = _activation_row(row)
            current = self.current(item["scope"])
            item["active"] = bool(
                item.get("rolledBackAt") is None
                and current is not None
                and current["id"] == item["stateId"]
            )
            out.append(item)
        return out

    def rollback_activation(self, activation_id: str) -> dict[str, Any]:
        activation = self.get_activation(activation_id)
        if activation is None:
            raise ValueError(f"unknown activation {activation_id!r}")
        if activation.get("rolledBackAt"):
            return activation
        stamp = now_iso()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                "UPDATE HarnessActivation SET rolledBackAt=? WHERE id=?",
                (stamp, activation_id),
            )
            previous_id = activation.get("previousStateId")
            if previous_id:
                self._db.execute(
                    "UPDATE HarnessState SET status='superseded' "
                    "WHERE scope=? AND status='current' AND id<>?",
                    (activation["scope"], previous_id),
                )
                self._db.execute(
                    "UPDATE HarnessState SET status='current', promotedAt=? WHERE id=?",
                    (stamp, previous_id),
                )
            else:
                self._db.execute(
                    "UPDATE HarnessState SET status='retired' "
                    "WHERE scope=? AND status='current'",
                    (activation["scope"],),
                )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.get_activation(activation_id) or activation


__all__ = [
    "HarnessStateStore",
    "STATUSES",
    "new_activation_id",
    "new_state_id",
]
