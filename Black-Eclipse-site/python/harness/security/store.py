"""Durable security state on the ONE agent-memory connection.

Audit events, issued capabilities and policy version history live here — bound to
`AgentMemoryStore._db`, exactly like `fabric/store.py`, `tasks/store.py` and
`grants.py`. No second database is introduced.

Audit records are append-only and tamper-evident: each row stores the hash of the
previous row's canonical content plus its own, forming a hash chain that `verify()`
walks. A row edited or deleted out of band breaks the chain.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Optional

MAX_STORED_JSON = 100_000


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if len(text) > MAX_STORED_JSON:
        return text[:MAX_STORED_JSON] + "\n[TRUNCATED]"
    return text


def _load(text: Any, default: Any) -> Any:
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _hash_row(prev_hash: str, record: dict[str, Any]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + "\x00" + canonical).encode("utf-8")).hexdigest()


class SecurityStore:
    """Persist security audit events, capabilities and policy versions."""

    def __init__(self, store: Any) -> None:
        self._store = store
        # The agent-memory connection is shared (check_same_thread=False) and the
        # security store may be written from concurrent runs. Serialize our own
        # writes so the audit hash chain and unique capability rows cannot race.
        self._lock = threading.RLock()
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        db = self._db
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS SecurityAuditEvent (
              id            TEXT PRIMARY KEY,
              timestamp     REAL NOT NULL,
              category      TEXT NOT NULL,
              type          TEXT NOT NULL,
              actor         TEXT,
              userId        TEXT,
              tenantId      TEXT,
              agentId       TEXT,
              sessionId     TEXT,
              taskId        TEXT,
              tool          TEXT,
              action        TEXT,
              resource      TEXT,
              decision      TEXT,
              risk          TEXT,
              policy        TEXT,
              approvalId    TEXT,
              capabilityId  TEXT,
              result        TEXT,
              error         TEXT,
              prevHash      TEXT,
              hash          TEXT NOT NULL,
              payload       TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_secaudit_time ON SecurityAuditEvent(timestamp)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_secaudit_category ON SecurityAuditEvent(category, timestamp)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_secaudit_session ON SecurityAuditEvent(sessionId)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_secaudit_decision ON SecurityAuditEvent(decision, timestamp)")
        # Additive column for databases created before multi-tenancy.
        existing = {row["name"] for row in db.execute("PRAGMA table_info(SecurityAuditEvent)").fetchall()}
        if "tenantId" not in existing:
            db.execute("ALTER TABLE SecurityAuditEvent ADD COLUMN tenantId TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_secaudit_tenant ON SecurityAuditEvent(tenantId, timestamp)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS SecurityCapability (
              id        TEXT PRIMARY KEY,
              subject   TEXT NOT NULL,
              action    TEXT NOT NULL,
              resource  TEXT NOT NULL,
              scope     TEXT,
              data      TEXT NOT NULL,
              createdAt REAL NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_seccap_subject ON SecurityCapability(subject)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS SecurityPolicyVersion (
              id         TEXT PRIMARY KEY,
              version    INTEGER NOT NULL,
              profile    TEXT,
              document   TEXT,
              actor      TEXT,
              createdAt  REAL NOT NULL
            )
            """
        )
        db.commit()

    # ── audit (append-only hash chain) ───────────────────────────────────────
    def _last_hash(self) -> str:
        row = self._db.execute(
            "SELECT hash FROM SecurityAuditEvent ORDER BY timestamp DESC, rowid DESC LIMIT 1"
        ).fetchone()
        return str(row["hash"]) if row else ""

    def append_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": str(event.get("id") or f"secaudit_{int(time.time()*1000)}_{hashlib.sha1(str(event).encode()).hexdigest()[:8]}"),
            "timestamp": float(event.get("timestamp") or time.time()),
            "category": str(event.get("category") or "general"),
            "type": str(event.get("type") or "security.event"),
            "actor": event.get("actor"),
            "userId": event.get("userId"),
            "tenantId": event.get("tenantId"),
            "agentId": event.get("agentId"),
            "sessionId": event.get("sessionId"),
            "taskId": event.get("taskId"),
            "tool": event.get("tool"),
            "action": event.get("action"),
            "resource": event.get("resource"),
            "decision": event.get("decision"),
            "risk": event.get("risk"),
            "policy": event.get("policy"),
            "approvalId": event.get("approvalId"),
            "capabilityId": event.get("capabilityId"),
            "result": event.get("result"),
            "error": event.get("error"),
            "payload": event.get("payload"),
        }
        with self._lock:
            return self._insert_audit(record)

    def _insert_audit(self, record: dict[str, Any]) -> dict[str, Any]:
        prev = self._last_hash()
        record["prevHash"] = prev
        record["hash"] = _hash_row(
            prev, {k: v for k, v in record.items() if k not in ("hash", "prevHash")}
        )
        self._db.execute(
            """INSERT INTO SecurityAuditEvent
               (id, timestamp, category, type, actor, userId, tenantId, agentId, sessionId, taskId,
                tool, action, resource, decision, risk, policy, approvalId, capabilityId,
                result, error, prevHash, hash, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["timestamp"], record["category"], record["type"],
                record["actor"], record["userId"], record["tenantId"], record["agentId"],
                record["sessionId"], record["taskId"], record["tool"], record["action"],
                record["resource"], record["decision"], record["risk"], record["policy"],
                record["approvalId"], record["capabilityId"], record["result"], record["error"],
                record["prevHash"], record["hash"], _json(record["payload"]),
            ),
        )
        self._db.commit()
        return record

    def list_audit(
        self,
        *,
        category: Optional[str] = None,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        decision: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if session_id:
            clauses.append("sessionId = ?")
            params.append(session_id)
        if tenant_id:
            clauses.append("tenantId = ?")
            params.append(tenant_id)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM SecurityAuditEvent{where} ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row(r) for r in rows]

    def audit_counts(self) -> dict[str, int]:
        total = self._db.execute("SELECT COUNT(*) AS c FROM SecurityAuditEvent").fetchone()
        by_decision: dict[str, int] = {}
        for row in self._db.execute(
            "SELECT decision, COUNT(*) AS c FROM SecurityAuditEvent GROUP BY decision"
        ).fetchall():
            if row["decision"]:
                by_decision[str(row["decision"])] = int(row["c"])
        by_category: dict[str, int] = {}
        for row in self._db.execute(
            "SELECT category, COUNT(*) AS c FROM SecurityAuditEvent GROUP BY category"
        ).fetchall():
            by_category[str(row["category"])] = int(row["c"])
        return {
            "total": int(total["c"]) if total else 0,
            "byDecision": by_decision,
            "byCategory": by_category,
        }

    def verify_chain(self, limit: int = 10000) -> dict[str, Any]:
        """Walk the hash chain oldest→newest and report the first break, if any."""
        rows = self._db.execute(
            "SELECT * FROM SecurityAuditEvent ORDER BY timestamp ASC, rowid ASC LIMIT ?",
            (max(1, min(int(limit), 100000)),),
        ).fetchall()
        prev = ""
        checked = 0
        for row in rows:
            record = self._row(row)
            stored_hash = record.pop("hash")
            stored_prev = record.pop("prevHash")
            if stored_prev != prev:
                return {"valid": False, "checked": checked, "brokenAt": record.get("id"),
                        "reason": "prevHash mismatch"}
            recalculated = _hash_row(prev, record)
            if recalculated != stored_hash:
                return {"valid": False, "checked": checked, "brokenAt": record.get("id"),
                        "reason": "hash mismatch"}
            prev = stored_hash
            checked += 1
        return {"valid": True, "checked": checked, "head": prev}

    def _row(self, row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        data = dict(row)
        if "payload" in data:
            data["payload"] = _load(data.get("payload"), None)
        return data

    # ── capabilities ─────────────────────────────────────────────────────────
    def save_capability(self, cap: dict[str, Any]) -> None:
        with self._lock:
            self._save_capability(cap)

    def _save_capability(self, cap: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO SecurityCapability
               (id, subject, action, resource, scope, data, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(cap.get("id")), str(cap.get("subject") or ""), str(cap.get("action") or ""),
                str(cap.get("resource") or ""), str(cap.get("scope") or ""),
                _json(cap), float(cap.get("issuedAt") or time.time()),
            ),
        )
        self._db.commit()

    def list_capabilities(self, *, subject: Optional[str] = None) -> list[dict[str, Any]]:
        if subject:
            rows = self._db.execute(
                "SELECT data FROM SecurityCapability WHERE subject=? ORDER BY createdAt DESC", (subject,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT data FROM SecurityCapability ORDER BY createdAt DESC").fetchall()
        return [d for d in (_load(r["data"], None) for r in rows) if d is not None]

    def delete_capability(self, capability_id: str) -> bool:
        cursor = self._db.execute("DELETE FROM SecurityCapability WHERE id=?", (capability_id,))
        self._db.commit()
        return cursor.rowcount > 0

    # ── policy versions ──────────────────────────────────────────────────────
    def save_policy_version(self, record: dict[str, Any], document: Any) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO SecurityPolicyVersion
               (id, version, profile, document, actor, createdAt) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                f"policy_v{int(record.get('version') or 0)}",
                int(record.get("version") or 0),
                str(record.get("profile") or ""),
                _json(document), str(record.get("actor") or ""),
                float(record.get("at") or time.time()),
            ),
        )
        self._db.commit()

    def list_policy_versions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SecurityPolicyVersion ORDER BY version DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["document"] = _load(data.get("document"), None)
            out.append(data)
        return out


__all__ = ["SecurityStore"]
