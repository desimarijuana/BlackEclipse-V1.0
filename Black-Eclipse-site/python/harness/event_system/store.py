"""The durable event store (agent-memory.db).

Bound to the ONE `AgentMemoryStore` connection — same pattern as
`jobs/store.py`, `tasks/store.py` and `run_lineage.py`. Owns only its own tables
so `persistence.py` (pinned at its size ratchet) does not grow.

Tables:

    HarnessEventLog           the append-only event log (indexed columns)
    HarnessEventConsumer      per-consumer processing state (idempotency)
    HarnessEventDeadLetter    the DLQ (event + consumer + error + attempts)
    HarnessEventSubscription  declared subscriptions (discovery + UI)

Every event is stored with the queryable envelope columns beside a JSON payload,
so lookups by id/type/task/workflow/agent/correlation/time are indexed range
scans, never an unindexed blob scan.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso
from .envelope import EclipseEvent

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


def new_dlq_id() -> str:
    return "dlq_" + uuid.uuid4().hex[:20]


class EventStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS HarnessEventLog (
              id            TEXT PRIMARY KEY,
              type          TEXT NOT NULL,
              version       INTEGER NOT NULL DEFAULT 1,
              timestamp     TEXT NOT NULL,
              source        TEXT,
              correlationId TEXT,
              causationId   TEXT,
              traceId       TEXT,
              actorType     TEXT,
              actorId       TEXT,
              sessionId     TEXT,
              taskId        TEXT,
              workflowId    TEXT,
              agentId       TEXT,
              priority      TEXT NOT NULL DEFAULT 'normal',
              payload       TEXT,
              metadata      TEXT,
              depth         INTEGER NOT NULL DEFAULT 0,
              replay        INTEGER NOT NULL DEFAULT 0,
              createdAt     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_eventlog_type        ON HarnessEventLog(type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_eventlog_created      ON HarnessEventLog(createdAt);
            CREATE INDEX IF NOT EXISTS idx_eventlog_correlation  ON HarnessEventLog(correlationId, timestamp);
            CREATE INDEX IF NOT EXISTS idx_eventlog_trace        ON HarnessEventLog(traceId);
            CREATE INDEX IF NOT EXISTS idx_eventlog_causation    ON HarnessEventLog(causationId);
            CREATE INDEX IF NOT EXISTS idx_eventlog_task         ON HarnessEventLog(taskId, timestamp);
            CREATE INDEX IF NOT EXISTS idx_eventlog_workflow     ON HarnessEventLog(workflowId, timestamp);
            CREATE INDEX IF NOT EXISTS idx_eventlog_agent        ON HarnessEventLog(agentId, timestamp);
            CREATE INDEX IF NOT EXISTS idx_eventlog_priority     ON HarnessEventLog(priority);

            CREATE TABLE IF NOT EXISTS HarnessEventConsumer (
              id           TEXT PRIMARY KEY,
              eventId      TEXT NOT NULL,
              consumerId   TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'processed',
              attempts     INTEGER NOT NULL DEFAULT 1,
              firstFailedAt TEXT,
              lastFailedAt  TEXT,
              error        TEXT,
              errorClass   TEXT,
              processedAt  TEXT,
              updatedAt    TEXT NOT NULL,
              UNIQUE(eventId, consumerId)
            );
            CREATE INDEX IF NOT EXISTS idx_eventconsumer_consumer ON HarnessEventConsumer(consumerId, updatedAt);
            CREATE INDEX IF NOT EXISTS idx_eventconsumer_event    ON HarnessEventConsumer(eventId);

            CREATE TABLE IF NOT EXISTS HarnessEventDeadLetter (
              id           TEXT PRIMARY KEY,
              eventId      TEXT NOT NULL,
              consumerId   TEXT NOT NULL,
              eventType    TEXT,
              error        TEXT,
              errorClass   TEXT,
              attempts     INTEGER NOT NULL DEFAULT 0,
              firstFailedAt TEXT,
              lastFailedAt  TEXT,
              stackTrace   TEXT,
              status       TEXT NOT NULL DEFAULT 'pending',
              createdAt    TEXT NOT NULL,
              replayedAt   TEXT,
              UNIQUE(eventId, consumerId)
            );
            CREATE INDEX IF NOT EXISTS idx_eventdlq_status ON HarnessEventDeadLetter(status, createdAt);
            CREATE INDEX IF NOT EXISTS idx_eventdlq_event  ON HarnessEventDeadLetter(eventId);

            CREATE TABLE IF NOT EXISTS HarnessEventSubscription (
              id            TEXT PRIMARY KEY,
              subscriberId  TEXT NOT NULL,
              subscriberType TEXT NOT NULL DEFAULT 'internal',
              patterns      TEXT NOT NULL,
              predicate     TEXT,
              source        TEXT,
              scopeId       TEXT,
              enabled       INTEGER NOT NULL DEFAULT 1,
              createdAt     TEXT NOT NULL,
              updatedAt     TEXT NOT NULL,
              UNIQUE(subscriberId, patterns)
            );
            CREATE INDEX IF NOT EXISTS idx_eventsub_enabled ON HarnessEventSubscription(enabled);
            """
        )
        self._db.commit()

    # ── Event log ────────────────────────────────────────────────────────────
    def append(self, event: EclipseEvent) -> bool:
        """Append an event. Returns False when the id already exists (idempotent)."""
        row = event.to_row()
        cur = self._db.execute(
            """INSERT OR IGNORE INTO HarnessEventLog
               (id, type, version, timestamp, source, correlationId, causationId, traceId,
                actorType, actorId, sessionId, taskId, workflowId, agentId, priority,
                payload, metadata, depth, replay, createdAt)
               VALUES (:id, :type, :version, :timestamp, :source, :correlationId, :causationId,
                       :traceId, :actorType, :actorId, :sessionId, :taskId, :workflowId,
                       :agentId, :priority, :payload, :metadata, :depth, :replay, :createdAt)""",
            row,
        )
        self._db.commit()
        return cur.rowcount > 0

    def get(self, event_id: str) -> Optional[EclipseEvent]:
        row = self._db.execute("SELECT * FROM HarnessEventLog WHERE id=?", (event_id,)).fetchone()
        return EclipseEvent.from_row(row) if row else None

    def query(
        self,
        *,
        type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = _DEFAULT_LIMIT,
        offset: int = 0,
        ascending: bool = False,
    ) -> list[EclipseEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if namespace:
            clauses.append("(type = ? OR type LIKE ?)")
            params.extend([namespace, f"{namespace}.%"])
        for column, value in (
            ("correlationId", correlation_id),
            ("causationId", causation_id),
            ("traceId", trace_id),
            ("taskId", task_id),
            ("workflowId", workflow_id),
            ("agentId", agent_id),
            ("sessionId", session_id),
            ("priority", priority),
            ("source", source),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ASC" if ascending else "DESC"
        limit = max(1, min(int(limit), _MAX_LIMIT))
        offset = max(0, int(offset))
        rows = self._db.execute(
            f"SELECT * FROM HarnessEventLog {where} ORDER BY timestamp {order}, rowid {order} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [EclipseEvent.from_row(r) for r in rows]

    def count(self, *, type: Optional[str] = None, since: Optional[str] = None) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self._db.execute(f"SELECT COUNT(*) AS n FROM HarnessEventLog {where}", params).fetchone()
        return int(row["n"]) if row else 0

    def types(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT type, COUNT(*) AS n, MAX(timestamp) AS lastAt FROM HarnessEventLog GROUP BY type ORDER BY n DESC"
        ).fetchall()
        return [{"type": r["type"], "count": int(r["n"]), "lastAt": r["lastAt"]} for r in rows]

    def graph(self, *, correlation_id: Optional[str] = None, trace_id: Optional[str] = None, limit: int = 500) -> dict[str, Any]:
        """Build a causation graph for one correlation/trace.

        Edges come from `causationId` → `id` relationships, never timestamp
        guesses. Nodes with no recorded parent hang off a synthetic root.
        """
        events = self.query(
            correlation_id=correlation_id,
            trace_id=trace_id if not correlation_id else None,
            limit=limit,
            ascending=True,
        )
        if not events and (correlation_id or trace_id):
            # A trace may span correlations; fall back to a broad scan by trace.
            events = self.query(trace_id=trace_id, limit=limit, ascending=True) if trace_id else []
        nodes = [
            {
                "id": e.id,
                "type": e.type,
                "timestamp": e.timestamp,
                "source": e.source,
                "taskId": e.task_id,
                "workflowId": e.workflow_id,
                "agentId": e.agent_id,
                "priority": e.priority,
            }
            for e in events
        ]
        ids = {e.id for e in events}
        edges = []
        for e in events:
            if e.causation_id and e.causation_id in ids:
                edges.append({"from": e.causation_id, "to": e.id})
        return {"nodes": nodes, "edges": edges, "root": (nodes[0]["id"] if nodes else None)}

    # ── Retention ────────────────────────────────────────────────────────────
    def prune(self, *, before_iso: str, types: Optional[list[str]] = None) -> int:
        if types:
            placeholders = ",".join("?" for _ in types)
            cur = self._db.execute(
                f"DELETE FROM HarnessEventLog WHERE timestamp < ? AND type IN ({placeholders})",
                (before_iso, *types),
            )
        else:
            cur = self._db.execute("DELETE FROM HarnessEventLog WHERE timestamp < ?", (before_iso,))
        self._db.commit()
        return cur.rowcount

    # ── Consumer idempotency ─────────────────────────────────────────────────
    def has_processed(self, event_id: str, consumer_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM HarnessEventConsumer WHERE eventId=? AND consumerId=? AND status='processed'",
            (event_id, consumer_id),
        ).fetchone()
        return row is not None

    def mark_processed(self, event_id: str, consumer_id: str) -> bool:
        """Record processing. Returns True when this is the FIRST success.

        A duplicate delivery sees the existing row and returns False, so the
        handler must not run twice. A prior FAILURE row is upgraded to processed.
        """
        now = now_iso()
        cur = self._db.execute(
            """INSERT INTO HarnessEventConsumer
               (id, eventId, consumerId, status, attempts, processedAt, updatedAt)
               VALUES (?, ?, ?, 'processed', 1, ?, ?)
               ON CONFLICT(eventId, consumerId) DO UPDATE SET
                 status='processed', attempts=HarnessEventConsumer.attempts + 1,
                 processedAt=excluded.processedAt, updatedAt=excluded.updatedAt
               WHERE HarnessEventConsumer.status != 'processed'""",
            (f"cons_{uuid.uuid4().hex[:20]}", event_id, consumer_id, now, now),
        )
        self._db.commit()
        if cur.rowcount > 0:
            return True
        # No row updated ⇒ it was already 'processed'.
        return False

    def record_failure(self, event_id: str, consumer_id: str, *, error: str, error_class: str) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT INTO HarnessEventConsumer
               (id, eventId, consumerId, status, attempts, firstFailedAt, lastFailedAt, error, errorClass, updatedAt)
               VALUES (?, ?, ?, 'failed', 1, ?, ?, ?, ?, ?)
               ON CONFLICT(eventId, consumerId) DO UPDATE SET
                 status='failed', attempts=HarnessEventConsumer.attempts + 1,
                 lastFailedAt=excluded.lastFailedAt, error=excluded.error,
                 errorClass=excluded.errorClass, updatedAt=excluded.updatedAt
               WHERE HarnessEventConsumer.status != 'processed'""",
            (f"cons_{uuid.uuid4().hex[:20]}", event_id, consumer_id, now, now, error[:2000], error_class, now),
        )
        self._db.commit()

    def list_consumers(self, *, event_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), _MAX_LIMIT))
        if event_id:
            rows = self._db.execute(
                "SELECT * FROM HarnessEventConsumer WHERE eventId=? ORDER BY updatedAt DESC LIMIT ?",
                (event_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                """SELECT consumerId, status, COUNT(*) AS n, SUM(attempts) AS attempts,
                          MAX(updatedAt) AS lastAt
                   FROM HarnessEventConsumer GROUP BY consumerId, status ORDER BY lastAt DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Dead letter queue ────────────────────────────────────────────────────
    def record_dead_letter(
        self,
        *,
        event_id: str,
        consumer_id: str,
        event_type: str,
        error: str,
        error_class: str,
        attempts: int,
        first_failed_at: Optional[str],
        stack_trace: Optional[str] = None,
    ) -> str:
        now = now_iso()
        dlq_id = new_dlq_id()
        self._db.execute(
            """INSERT INTO HarnessEventDeadLetter
               (id, eventId, consumerId, eventType, error, errorClass, attempts,
                firstFailedAt, lastFailedAt, stackTrace, status, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
               ON CONFLICT(eventId, consumerId) DO UPDATE SET
                 error=excluded.error, errorClass=excluded.errorClass,
                 attempts=excluded.attempts, lastFailedAt=excluded.lastFailedAt,
                 stackTrace=excluded.stackTrace, status='pending'""",
            (dlq_id, event_id, consumer_id, event_type, error[:4000], error_class, attempts,
             first_failed_at or now, now, (stack_trace or "")[:8000], now),
        )
        self._db.commit()
        return dlq_id

    def list_dead_letters(self, *, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), _MAX_LIMIT))
        if status:
            rows = self._db.execute(
                "SELECT * FROM HarnessEventDeadLetter WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessEventDeadLetter ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._dlq_view(r) for r in rows]

    def get_dead_letter(self, dlq_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM HarnessEventDeadLetter WHERE id=?", (dlq_id,)).fetchone()
        return self._dlq_view(row) if row else None

    def set_dead_letter_status(self, dlq_id: str, status: str) -> bool:
        cur = self._db.execute(
            "UPDATE HarnessEventDeadLetter SET status=?, replayedAt=? WHERE id=?",
            (status, now_iso() if status == "replayed" else None, dlq_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_dead_letter(self, dlq_id: str) -> bool:
        cur = self._db.execute("DELETE FROM HarnessEventDeadLetter WHERE id=?", (dlq_id,))
        self._db.commit()
        return cur.rowcount > 0

    def dlq_count(self) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM HarnessEventDeadLetter WHERE status='pending'"
        ).fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _dlq_view(row: Any) -> dict[str, Any]:
        d = dict(row)
        d["firstFailedAt"] = d.pop("firstFailedAt", None)
        return d

    # ── Declared subscriptions ───────────────────────────────────────────────
    def save_subscription(
        self,
        *,
        subscriber_id: str,
        subscriber_type: str,
        patterns: list[str],
        predicate: Optional[str] = None,
        source: Optional[str] = None,
        scope_id: Optional[str] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = now_iso()
        patterns_json = json.dumps(sorted(patterns))
        self._db.execute(
            """INSERT INTO HarnessEventSubscription
               (id, subscriberId, subscriberType, patterns, predicate, source, scopeId, enabled, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(subscriberId, patterns) DO UPDATE SET
                 predicate=excluded.predicate, source=excluded.source,
                 scopeId=excluded.scopeId, enabled=excluded.enabled, updatedAt=excluded.updatedAt""",
            (f"sub_{uuid.uuid4().hex[:20]}", subscriber_id, subscriber_type, patterns_json,
             predicate, source, scope_id, 1 if enabled else 0, now, now),
        )
        self._db.commit()
        return {
            "subscriberId": subscriber_id,
            "subscriberType": subscriber_type,
            "patterns": sorted(patterns),
            "predicate": predicate,
            "source": source,
            "scopeId": scope_id,
            "enabled": enabled,
        }

    def list_subscriptions(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE enabled=1" if enabled_only else ""
        rows = self._db.execute(
            f"SELECT * FROM HarnessEventSubscription {where} ORDER BY subscriberId"
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "subscriberId": r["subscriberId"],
                "subscriberType": r["subscriberType"],
                "patterns": json.loads(r["patterns"] or "[]"),
                "predicate": r["predicate"],
                "source": r["source"],
                "scopeId": r["scopeId"] if "scopeId" in r.keys() else None,
                "enabled": bool(r["enabled"]),
                "updatedAt": r["updatedAt"],
            })
        return out

    def delete_subscription(self, subscriber_id: str) -> int:
        cur = self._db.execute(
            "DELETE FROM HarnessEventSubscription WHERE subscriberId=?", (subscriber_id,)
        )
        self._db.commit()
        return cur.rowcount


__all__ = ["EventStore", "new_dlq_id"]
