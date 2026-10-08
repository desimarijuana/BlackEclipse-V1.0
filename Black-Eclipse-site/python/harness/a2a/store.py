"""Durable A2A persistence on the ONE agent-memory connection.

Agent definitions (versioned), messages + deliveries, delegations, events,
budgets, approvals and results all live here, bound to `store._db` exactly like
`tasks/store.py`, `orchestration/store.py` and `jobs/store.py`. No second
database is introduced.

Writes are idempotent where it matters: a message's `idempotencyKey` is UNIQUE, so
re-publishing the same logical message cannot create a second row.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso
from .model import (
    AgentBudget,
    AgentDefinition,
    AgentEnvelope,
    AgentStatus,
    A2AResult,
    ApprovalStatus,
    DelegationRecord,
    DelegationStatus,
    DeliveryStatus,
    new_envelope_id,
)

_MAX_JSON = 200_000


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    if len(text) > _MAX_JSON:
        return text[:_MAX_JSON] + "\n[TRUNCATED]"
    return text


def _load(text: Any, default: Any) -> Any:
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


class A2AStore:
    """Persist agent definitions, messages, delegations, budgets and results."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        db = self._db
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AAgent (
              id            TEXT PRIMARY KEY,
              latestVersion TEXT NOT NULL,
              status        TEXT NOT NULL,
              updatedAt     TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_agent_status ON A2AAgent(status)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AAgentVersion (
              id         TEXT NOT NULL,
              version    TEXT NOT NULL,
              definition TEXT NOT NULL,
              createdAt  TEXT NOT NULL,
              PRIMARY KEY (id, version)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AMessage (
              id                TEXT PRIMARY KEY,
              type              TEXT NOT NULL,
              runId             TEXT,
              taskId            TEXT,
              senderAgentId     TEXT NOT NULL,
              recipientAgentId  TEXT,
              correlationId     TEXT,
              replyTo           TEXT,
              timestamp         REAL NOT NULL,
              priority          TEXT NOT NULL,
              payload           TEXT,
              evidenceRefs      TEXT,
              permissions       TEXT,
              ttl               INTEGER NOT NULL,
              idempotencyKey    TEXT NOT NULL UNIQUE,
              createdAt         TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_msg_run ON A2AMessage(runId, createdAt)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_msg_recipient ON A2AMessage(recipientAgentId, createdAt)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AMessageDelivery (
              id                TEXT PRIMARY KEY,
              messageId         TEXT NOT NULL,
              recipientAgentId  TEXT NOT NULL,
              status            TEXT NOT NULL,
              attempts          INTEGER NOT NULL DEFAULT 0,
              lastError         TEXT,
              deliveredAt       TEXT,
              acknowledgedAt    TEXT,
              createdAt         TEXT NOT NULL,
              UNIQUE(messageId, recipientAgentId)
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_deliv ON A2AMessageDelivery(recipientAgentId, status)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2ADelegation (
              id             TEXT PRIMARY KEY,
              parentAgentId  TEXT NOT NULL,
              childAgentId   TEXT NOT NULL,
              parentRunId    TEXT NOT NULL,
              parentTaskId   TEXT,
              childTaskId    TEXT,
              childRunId     TEXT,
              objective      TEXT,
              status         TEXT NOT NULL,
              budget         TEXT,
              correlationId  TEXT,
              createdAt      TEXT NOT NULL,
              updatedAt      TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_dlg_run ON A2ADelegation(parentRunId, createdAt)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_dlg_child ON A2ADelegation(childTaskId)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AEvent (
              id     TEXT PRIMARY KEY,
              runId  TEXT NOT NULL,
              type   TEXT NOT NULL,
              seq    INTEGER NOT NULL,
              at     TEXT NOT NULL,
              data   TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_event_run ON A2AEvent(runId, seq)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2ABudget (
              rootRunId   TEXT PRIMARY KEY,
              budget      TEXT NOT NULL,
              createdAt   TEXT NOT NULL,
              updatedAt   TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AApproval (
              id          TEXT PRIMARY KEY,
              runId       TEXT NOT NULL,
              agentId     TEXT,
              taskId      TEXT,
              kind        TEXT NOT NULL,
              subject     TEXT NOT NULL,
              status      TEXT NOT NULL,
              detail      TEXT,
              requestedAt TEXT NOT NULL,
              decidedAt   TEXT,
              decidedBy   TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_appr_run ON A2AApproval(runId, status)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS A2AResult (
              id        TEXT PRIMARY KEY,
              runId     TEXT,
              taskId    TEXT,
              agentId   TEXT,
              status    TEXT NOT NULL,
              result    TEXT NOT NULL,
              createdAt TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_result_task ON A2AResult(taskId)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_a2a_result_run ON A2AResult(runId, createdAt)")
        db.commit()

    # ── agents ────────────────────────────────────────────────────────────────

    def save_agent(self, definition: AgentDefinition) -> AgentDefinition:
        now = now_iso()
        if not definition.created_at:
            definition.created_at = now
        definition.updated_at = now
        self._db.execute(
            "INSERT OR REPLACE INTO A2AAgentVersion (id, version, definition, createdAt) VALUES (?, ?, ?, ?)",
            (definition.id, definition.version, _json(definition.model_dump()), now),
        )
        self._db.execute(
            "INSERT OR REPLACE INTO A2AAgent (id, latestVersion, status, updatedAt) VALUES (?, ?, ?, ?)",
            (definition.id, definition.version, definition.status.value, now),
        )
        self._db.commit()
        return definition

    def get_agent(self, agent_id: str, version: Optional[str] = None) -> Optional[AgentDefinition]:
        # The status of record is the A2AAgent pointer's status column (a disable
        # does not rewrite every stored version), so overlay it here.
        if version:
            row = self._db.execute(
                "SELECT v.definition AS definition, a.status AS status FROM A2AAgentVersion v "
                "JOIN A2AAgent a ON a.id=v.id WHERE v.id=? AND v.version=?",
                (agent_id, version),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT v.definition AS definition, a.status AS status FROM A2AAgentVersion v "
                "JOIN A2AAgent a ON a.id=v.id AND a.latestVersion=v.version WHERE a.id=?",
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        definition = AgentDefinition(**_load(row["definition"], {}))
        if row["status"]:
            try:
                definition.status = AgentStatus(row["status"])
            except ValueError:
                pass
        return definition

    def list_agents(self, *, status: Optional[str] = None, limit: int = 200) -> list[AgentDefinition]:
        limit = max(1, min(int(limit), 1000))
        if status:
            rows = self._db.execute(
                "SELECT id, latestVersion FROM A2AAgent WHERE status=? ORDER BY id LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id, latestVersion FROM A2AAgent ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        out: list[AgentDefinition] = []
        for row in rows:
            definition = self.get_agent(row["id"], row["latestVersion"])
            if definition is not None:
                out.append(definition)
        return out

    def agent_versions(self, agent_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT version, createdAt FROM A2AAgentVersion WHERE id=? ORDER BY createdAt ASC",
            (agent_id,),
        ).fetchall()
        return [{"version": r["version"], "createdAt": r["createdAt"]} for r in rows]

    def set_agent_status(self, agent_id: str, status: AgentStatus) -> bool:
        cur = self._db.execute(
            "UPDATE A2AAgent SET status=?, updatedAt=? WHERE id=?",
            (status.value, now_iso(), agent_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_agent(self, agent_id: str) -> bool:
        cur = self._db.execute("DELETE FROM A2AAgent WHERE id=?", (agent_id,))
        self._db.execute("DELETE FROM A2AAgentVersion WHERE id=?", (agent_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── messages ──────────────────────────────────────────────────────────────

    def publish_message(self, envelope: AgentEnvelope) -> tuple[AgentEnvelope, bool]:
        """Persist an envelope idempotently. Returns (envelope, created)."""
        existing = self._db.execute(
            "SELECT id FROM A2AMessage WHERE idempotencyKey=?", (envelope.idempotency_key,)
        ).fetchone()
        if existing is not None:
            stored = self.get_message(existing["id"])
            return (stored or envelope), False
        row = envelope.to_row()
        self._db.execute(
            """INSERT INTO A2AMessage
               (id, type, runId, taskId, senderAgentId, recipientAgentId, correlationId, replyTo,
                timestamp, priority, payload, evidenceRefs, permissions, ttl, idempotencyKey, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row["type"], row["runId"], row["taskId"], row["senderAgentId"],
                row["recipientAgentId"], row["correlationId"], row["replyTo"], row["timestamp"],
                row["priority"], _json(row["payload"]), _json(row["evidenceRefs"]),
                _json(row["permissions"]), row["ttl"], row["idempotencyKey"], now_iso(),
            ),
        )
        recipients = [row["recipientAgentId"]] if row["recipientAgentId"] else self._broadcast_targets()
        for recipient in recipients:
            if not recipient:
                continue
            self._db.execute(
                """INSERT OR IGNORE INTO A2AMessageDelivery
                   (id, messageId, recipientAgentId, status, attempts, createdAt)
                   VALUES (?, ?, ?, 'PENDING', 0, ?)""",
                (_uid("del"), row["id"], recipient, now_iso()),
            )
        self._db.commit()
        return envelope, True

    def _broadcast_targets(self) -> list[str]:
        rows = self._db.execute(
            "SELECT id FROM A2AAgent WHERE status='ACTIVE'"
        ).fetchall()
        return [r["id"] for r in rows]

    def get_message(self, message_id: str) -> Optional[AgentEnvelope]:
        row = self._db.execute("SELECT * FROM A2AMessage WHERE id=?", (message_id,)).fetchone()
        if row is None:
            return None
        return self._message_from_row(_row(row))

    def _message_from_row(self, data: dict[str, Any]) -> AgentEnvelope:
        return AgentEnvelope.from_row({
            "id": data["id"], "type": data["type"], "runId": data.get("runId"),
            "taskId": data.get("taskId"), "senderAgentId": data.get("senderAgentId"),
            "recipientAgentId": data.get("recipientAgentId"),
            "correlationId": data.get("correlationId"), "replyTo": data.get("replyTo"),
            "timestamp": data.get("timestamp"), "priority": data.get("priority"),
            "payload": _load(data.get("payload"), {}),
            "evidenceRefs": _load(data.get("evidenceRefs"), []),
            "permissions": _load(data.get("permissions"), {}),
            "ttl": data.get("ttl"), "idempotencyKey": data.get("idempotencyKey"),
        })

    def list_messages(
        self, *, run_id: Optional[str] = None, recipient: Optional[str] = None,
        sender: Optional[str] = None, limit: int = 200,
    ) -> list[AgentEnvelope]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        for col, value in (("runId", run_id), ("recipientAgentId", recipient), ("senderAgentId", sender)):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM A2AMessage {where} ORDER BY createdAt ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return [self._message_from_row(_row(r)) for r in rows]

    # ── deliveries ────────────────────────────────────────────────────────────

    def pending_deliveries(self, recipient: str, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        rows = self._db.execute(
            """SELECT d.*, m.type, m.senderAgentId, m.correlationId, m.payload, m.evidenceRefs
               FROM A2AMessageDelivery d JOIN A2AMessage m ON m.id=d.messageId
               WHERE d.recipientAgentId=? AND d.status='PENDING'
               ORDER BY m.createdAt ASC LIMIT ?""",
            (recipient, limit),
        ).fetchall()
        return [_row(r) for r in rows]

    def mark_delivered(self, message_id: str, recipient: str) -> None:
        self._db.execute(
            """UPDATE A2AMessageDelivery SET status='DELIVERED',
               attempts=attempts+1, deliveredAt=? WHERE messageId=? AND recipientAgentId=?""",
            (now_iso(), message_id, recipient),
        )
        self._db.commit()

    def acknowledge(self, message_id: str, recipient: str, *, status: DeliveryStatus = DeliveryStatus.ACKNOWLEDGED) -> None:
        self._db.execute(
            """UPDATE A2AMessageDelivery SET status=?, acknowledgedAt=?
               WHERE messageId=? AND recipientAgentId=?""",
            (status.value, now_iso(), message_id, recipient),
        )
        self._db.commit()

    def reject(self, message_id: str, recipient: str, error: str) -> None:
        self._db.execute(
            """UPDATE A2AMessageDelivery SET status='REJECTED', attempts=attempts+1, lastError=?
               WHERE messageId=? AND recipientAgentId=?""",
            (error[:500], message_id, recipient),
        )
        self._db.commit()

    def dead_letter(self, message_id: str, recipient: str, error: str) -> None:
        self._db.execute(
            """UPDATE A2AMessageDelivery SET status='DEAD_LETTER', lastError=?
               WHERE messageId=? AND recipientAgentId=?""",
            (error[:500], message_id, recipient),
        )
        self._db.commit()

    def list_deliveries(self, *, recipient: Optional[str] = None, status: Optional[str] = None,
                        limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        for col, value in (("recipientAgentId", recipient), ("status", status)):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM A2AMessageDelivery {where} ORDER BY createdAt ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [_row(r) for r in rows]

    # ── delegations ───────────────────────────────────────────────────────────

    def save_delegation(self, record: DelegationRecord) -> DelegationRecord:
        now = now_iso()
        if not record.created_at:
            record.created_at = now
        record.updated_at = now
        self._db.execute(
            """INSERT OR REPLACE INTO A2ADelegation
               (id, parentAgentId, childAgentId, parentRunId, parentTaskId, childTaskId, childRunId,
                objective, status, budget, correlationId, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id, record.parent_agent_id, record.child_agent_id, record.parent_run_id,
                record.parent_task_id, record.child_task_id, record.child_run_id, record.objective,
                record.status.value, _json(record.budget), record.correlation_id,
                record.created_at, record.updated_at,
            ),
        )
        self._db.commit()
        return record

    def get_delegation(self, delegation_id: str) -> Optional[DelegationRecord]:
        row = self._db.execute("SELECT * FROM A2ADelegation WHERE id=?", (delegation_id,)).fetchone()
        return self._delegation_from_row(_row(row)) if row else None

    def list_delegations(self, *, parent_run_id: Optional[str] = None,
                         parent_agent_id: Optional[str] = None, child_task_id: Optional[str] = None,
                         limit: int = 200) -> list[DelegationRecord]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        for col, value in (
            ("parentRunId", parent_run_id), ("parentAgentId", parent_agent_id),
            ("childTaskId", child_task_id),
        ):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM A2ADelegation {where} ORDER BY createdAt ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return [self._delegation_from_row(_row(r)) for r in rows]

    def _delegation_from_row(self, data: dict[str, Any]) -> DelegationRecord:
        return DelegationRecord(
            id=data["id"], parent_agent_id=data["parentAgentId"], child_agent_id=data["childAgentId"],
            parent_run_id=data["parentRunId"], parent_task_id=data.get("parentTaskId"),
            child_task_id=data.get("childTaskId"), child_run_id=data.get("childRunId"),
            objective=data.get("objective") or "",
            status=_enum(DelegationStatus, data.get("status"), DelegationStatus.CREATED),
            budget=_load(data.get("budget"), {}), correlation_id=data.get("correlationId"),
            created_at=data["createdAt"], updated_at=data["updatedAt"],
        )

    # ── events ────────────────────────────────────────────────────────────────

    def append_event(self, run_id: str, event_type: str, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        seq_row = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM A2AEvent WHERE runId=?", (run_id,)
        ).fetchone()
        seq = int(seq_row["m"]) + 1
        event_id = _uid("aevt")
        at = now_iso()
        self._db.execute(
            "INSERT INTO A2AEvent (id, runId, type, seq, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, run_id, event_type, seq, at, _json(data or {})),
        )
        self._db.commit()
        return {"id": event_id, "runId": run_id, "type": event_type, "seq": seq, "at": at, "data": data or {}}

    def list_events(self, run_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        rows = self._db.execute(
            "SELECT * FROM A2AEvent WHERE runId=? ORDER BY seq ASC LIMIT ?", (run_id, limit)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = _row(row)
            data["data"] = _load(data.get("data"), {})
            out.append(data)
        return out

    def recent_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        rows = self._db.execute(
            "SELECT * FROM A2AEvent ORDER BY at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── budgets ───────────────────────────────────────────────────────────────

    def save_budget(self, root_run_id: str, budget: AgentBudget) -> None:
        now = now_iso()
        existing = self._db.execute(
            "SELECT rootRunId FROM A2ABudget WHERE rootRunId=?", (root_run_id,)
        ).fetchone()
        if existing is None:
            self._db.execute(
                "INSERT INTO A2ABudget (rootRunId, budget, createdAt, updatedAt) VALUES (?, ?, ?, ?)",
                (root_run_id, _json(budget.model_dump(by_alias=True)), now, now),
            )
        else:
            self._db.execute(
                "UPDATE A2ABudget SET budget=?, updatedAt=? WHERE rootRunId=?",
                (_json(budget.model_dump(by_alias=True)), now, root_run_id),
            )
        self._db.commit()

    def get_budget(self, root_run_id: str) -> Optional[AgentBudget]:
        row = self._db.execute(
            "SELECT budget FROM A2ABudget WHERE rootRunId=?", (root_run_id,)
        ).fetchone()
        if row is None:
            return None
        return AgentBudget(**_load(row["budget"], {}))

    # ── approvals ─────────────────────────────────────────────────────────────

    def save_approval(self, approval: dict[str, Any]) -> dict[str, Any]:
        approval = dict(approval)
        approval.setdefault("id", _uid("appr"))
        approval.setdefault("status", ApprovalStatus.PENDING.value)
        approval["requestedAt"] = approval.get("requestedAt") or now_iso()
        self._db.execute(
            """INSERT OR REPLACE INTO A2AApproval
               (id, runId, agentId, taskId, kind, subject, status, detail, requestedAt, decidedAt, decidedBy)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                approval["id"], approval.get("runId") or "", approval.get("agentId"),
                approval.get("taskId"), approval.get("kind") or "action",
                approval.get("subject") or "", approval["status"],
                _json(approval.get("detail") or {}), approval["requestedAt"],
                approval.get("decidedAt"), approval.get("decidedBy"),
            ),
        )
        self._db.commit()
        return approval

    def get_approval(self, approval_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM A2AApproval WHERE id=?", (approval_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["detail"] = _load(data.get("detail"), {})
        return data

    def list_approvals(self, *, run_id: Optional[str] = None, status: Optional[str] = None,
                       limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        for col, value in (("runId", run_id), ("status", status)):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM A2AApproval {where} ORDER BY requestedAt DESC LIMIT ?", (*params, limit)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = _row(row)
            data["detail"] = _load(data.get("detail"), {})
            out.append(data)
        return out

    def decide_approval(self, approval_id: str, decision: ApprovalStatus, *, decided_by: str = "operator") -> Optional[dict[str, Any]]:
        cur = self._db.execute(
            "UPDATE A2AApproval SET status=?, decidedAt=?, decidedBy=? WHERE id=? AND status='PENDING'",
            (decision.value, now_iso(), decided_by, approval_id),
        )
        self._db.commit()
        if cur.rowcount == 0:
            return None
        return self.get_approval(approval_id)

    # ── results ───────────────────────────────────────────────────────────────

    def save_result(self, result: A2AResult, *, run_id: Optional[str] = None) -> str:
        result_id = _uid("res")
        self._db.execute(
            "INSERT INTO A2AResult (id, runId, taskId, agentId, status, result, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (result_id, run_id, result.task_id, result.agent_id, result.status,
             _json(result.to_public()), now_iso()),
        )
        self._db.commit()
        return result_id

    def list_results(self, *, task_id: Optional[str] = None, run_id: Optional[str] = None,
                     limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        for col, value in (("taskId", task_id), ("runId", run_id)):
            if value is not None:
                clauses.append(f"{col} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM A2AResult {where} ORDER BY createdAt ASC LIMIT ?", (*params, limit)
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = _row(row)
            data["result"] = _load(data.get("result"), {})
            out.append(data)
        return out

    def find_result(self, task_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM A2AResult WHERE taskId=? ORDER BY createdAt DESC LIMIT 1", (task_id,)
        ).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["result"] = _load(data.get("result"), {})
        return data


def _enum(enum_cls: Any, value: Any, default: Any) -> Any:
    try:
        return enum_cls(str(value))
    except (ValueError, TypeError):
        return default


__all__ = ["A2AStore"]
