"""Operator-approved effectful widening.

Two steps, two decisions:

1. `propose` records a named tool, a written justification, a short TTL and
   hard caps. It returns a one-time approval token (stored only as a hash).
2. `approve` consumes that token and creates a `widen_effect_tool` grant.

A grant only makes the tool visible to the agent. Every call STILL passes the
existing effect authorizer, and `check_call` enforces the caps before the
handler runs. There is no autonomous path to create or approve a grant.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import secrets
import uuid
from typing import Any, Optional

from ..persistence import now_iso
from .self_modification import SelfModificationAudit

_GRANTS: dict[str, dict[str, Any]] = {}

_ALLOWED_CAPS = {
    "maxCallsPerDay", "maxCallsTotal", "maxNotionalPerCall", "maxNotionalPerDay",
    "notionalField",
}


def _expiry(hours: int) -> str:
    moment = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=max(1, int(hours)))
    return moment.isoformat().replace("+00:00", "Z")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _detail(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(row.get("detail") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _key(agent_id: str, tool_name: str) -> str:
    return f"{agent_id}\0{tool_name}"


def _normalize_caps(caps: Optional[dict[str, Any]]) -> dict[str, Any]:
    raw = caps or {}
    unknown = set(raw) - _ALLOWED_CAPS
    if unknown:
        raise ValueError(f"unknown caps: {', '.join(sorted(unknown))}")
    per_day = int(raw.get("maxCallsPerDay") or 0)
    total = int(raw.get("maxCallsTotal") or 0)
    if not 1 <= per_day <= 100:
        raise ValueError("maxCallsPerDay must be 1..100")
    if not 1 <= total <= 500:
        raise ValueError("maxCallsTotal must be 1..500")
    normalized: dict[str, Any] = {"maxCallsPerDay": per_day, "maxCallsTotal": total}
    for key in ("maxNotionalPerCall", "maxNotionalPerDay"):
        if key in raw and raw[key] is not None:
            value = float(raw[key])
            if value <= 0:
                raise ValueError(f"{key} must be > 0")
            normalized[key] = value
    field = str(raw.get("notionalField") or "notional").strip()
    if not field or len(field) > 64 or not field.replace("_", "").isalnum():
        raise ValueError("notionalField must be a simple argument name")
    normalized["notionalField"] = field
    return normalized


class EffectfulProposalStore:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS EffectfulWideningProposal (
      id          TEXT PRIMARY KEY,
      toolName    TEXT NOT NULL,
      agentId     TEXT NOT NULL,
      status      TEXT NOT NULL,
      justification TEXT NOT NULL,
      caps        TEXT NOT NULL,
      tokenHash   TEXT NOT NULL,
      createdAt   TEXT NOT NULL,
      expiresAt   TEXT NOT NULL,
      approvedAt  TEXT,
      revokedAt   TEXT
    );
    CREATE TABLE IF NOT EXISTS EffectfulWideningCall (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      grantId   TEXT NOT NULL,
      toolName  TEXT NOT NULL,
      agentId   TEXT NOT NULL,
      day       TEXT NOT NULL,
      notional  REAL NOT NULL DEFAULT 0,
      createdAt TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_effect_call_grant ON EffectfulWideningCall(grantId, day);
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(self._SCHEMA)
        self._db.commit()

    @property
    def _db(self):
        return self._store._db

    def find(self, proposal_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EffectfulWideningProposal WHERE id=?", (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data.pop("tokenHash", None)
        return data

    def raw(self, proposal_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EffectfulWideningProposal WHERE id=?", (proposal_id,),
        ).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM EffectfulWideningProposal ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data.pop("tokenHash", None)
            out.append(data)
        return out


def propose(
    store: Any,
    registry: Any,
    tool_name: str,
    *,
    justification: str,
    caps: Optional[dict[str, Any]],
    ttl_hours: int = 4,
    agent_id: str = "eclipse-agent",
    already_allowed: tuple[str, ...] = (),
) -> dict[str, Any]:
    tool = registry.get(tool_name)
    if tool is None:
        return {"ok": False, "reason": "tool_not_registered"}
    if getattr(tool, "permission", "read") == "read":
        return {"ok": False, "reason": "tool_is_read_only; use the read-only widening queue"}
    if tool_name in already_allowed:
        return {"ok": False, "reason": "tool_already_on_surface"}
    text = str(justification or "").strip()
    if len(text) < 8:
        return {"ok": False, "reason": "justification_required"}
    if not 1 <= int(ttl_hours) <= 24:
        return {"ok": False, "reason": "ttl_hours_must_be_1..24"}
    try:
        normalized = _normalize_caps(caps)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "reason": str(exc)}
    token = secrets.token_urlsafe(24)
    proposal_id = "ewprop_" + uuid.uuid4().hex[:16]
    proposals = EffectfulProposalStore(store)
    proposals._db.execute(
        "INSERT INTO EffectfulWideningProposal "
        "(id, toolName, agentId, status, justification, caps, tokenHash, createdAt, expiresAt) "
        "VALUES (?, ?, ?, 'pending_approval', ?, ?, ?, ?, ?)",
        (
            proposal_id, tool_name, agent_id, text, json.dumps(normalized),
            _token_hash(token), now_iso(), _expiry(ttl_hours),
        ),
    )
    proposals._db.commit()
    return {
        "ok": True,
        "proposal": proposals.find(proposal_id),
        "approvalToken": token,
        "note": "give this token to the approving operator; it is shown once",
    }


def approve(store: Any, proposal_id: str, token: str) -> dict[str, Any]:
    proposals = EffectfulProposalStore(store)
    row = proposals.raw(proposal_id)
    if row is None:
        return {"ok": False, "reason": "proposal_not_found"}
    if row["status"] != "pending_approval":
        return {"ok": False, "reason": "proposal_not_pending", "status": row["status"]}
    if str(row["expiresAt"]) <= now_iso():
        return {"ok": False, "reason": "proposal_expired"}
    if not secrets.compare_digest(str(row["tokenHash"]), _token_hash(str(token or ""))):
        return {"ok": False, "reason": "approval_token_invalid"}
    caps = json.loads(row["caps"] or "{}")
    audit = SelfModificationAudit(store)
    grant_id = audit.record(
        kind="widen_effect_tool", subject=str(row["toolName"]),
        evidence=proposal_id, expires_at=str(row["expiresAt"]),
        detail={
            "agentId": row["agentId"], "proposalId": proposal_id,
            "caps": caps, "justification": row["justification"],
        },
    )
    proposals._db.execute(
        "UPDATE EffectfulWideningProposal SET status='active', approvedAt=? WHERE id=?",
        (now_iso(), proposal_id),
    )
    proposals._db.commit()
    refresh(store)
    return {
        "ok": True, "grantId": grant_id, "proposal": proposals.find(proposal_id),
        "expiresAt": row["expiresAt"],
    }


def refresh(store: Any) -> dict[str, dict[str, Any]]:
    audit = SelfModificationAudit(store)
    now = now_iso()
    current: dict[str, dict[str, Any]] = {}
    for row in audit.active("widen_effect_tool"):
        if str(row.get("expiresAt") or "") <= now:
            continue
        detail = _detail(row)
        key = _key(str(detail.get("agentId") or "eclipse-agent"), str(row.get("subject") or ""))
        current[key] = {
            "grantId": row.get("id"), "caps": detail.get("caps") or {},
            "expiresAt": row.get("expiresAt"), "proposalId": detail.get("proposalId"),
        }
    global _GRANTS
    _GRANTS = current
    return current


def granted_tools(agent_id: str) -> frozenset[str]:
    prefix = f"{agent_id}\0"
    now = now_iso()
    return frozenset(
        key[len(prefix):] for key, grant in _GRANTS.items()
        if key.startswith(prefix) and str(grant.get("expiresAt") or "") > now
    )


def _notional(args: dict[str, Any], field: str) -> float:
    value = args.get(field)
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def check_call(
    store: Any, agent_id: str, tool_name: str, args: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Enforce caps for a granted effectful tool. None = not a widening grant."""
    grant = _GRANTS.get(_key(agent_id, tool_name))
    if grant is None or str(grant.get("expiresAt") or "") <= now_iso():
        return None
    caps = grant.get("caps") or {}
    proposals = EffectfulProposalStore(store)
    day = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    counts = proposals._db.execute(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(notional), 0) AS notional "
        "FROM EffectfulWideningCall WHERE grantId=?",
        (grant.get("grantId"),),
    ).fetchone()
    today = proposals._db.execute(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(notional), 0) AS notional "
        "FROM EffectfulWideningCall WHERE grantId=? AND day=?",
        (grant.get("grantId"), day),
    ).fetchone()
    total_calls = int(counts["calls"] if counts else 0)
    today_calls = int(today["calls"] if today else 0)
    if total_calls >= int(caps.get("maxCallsTotal") or 0):
        return {"ok": False, "reason": "max_calls_total", "grantId": grant.get("grantId")}
    if today_calls >= int(caps.get("maxCallsPerDay") or 0):
        return {"ok": False, "reason": "max_calls_per_day", "grantId": grant.get("grantId")}
    notional = _notional(args, str(caps.get("notionalField") or "notional"))
    per_call = caps.get("maxNotionalPerCall")
    if per_call is not None and notional > float(per_call):
        return {"ok": False, "reason": "max_notional_per_call", "grantId": grant.get("grantId")}
    per_day = caps.get("maxNotionalPerDay")
    if per_day is not None and float(today["notional"] if today else 0) + notional > float(per_day):
        return {"ok": False, "reason": "max_notional_per_day", "grantId": grant.get("grantId")}
    proposals._db.execute(
        "INSERT INTO EffectfulWideningCall "
        "(grantId, toolName, agentId, day, notional, createdAt) VALUES (?, ?, ?, ?, ?, ?)",
        (grant.get("grantId"), tool_name, agent_id, day, notional, now_iso()),
    )
    proposals._db.commit()
    return {"ok": True, "grantId": grant.get("grantId")}


def revoke_grant(store: Any, grant_id: str) -> dict[str, Any]:
    row = SelfModificationAudit(store).revoke(grant_id)
    if row is None:
        return {"ok": False, "reason": "not_found_or_not_active"}
    proposals = EffectfulProposalStore(store)
    detail = _detail(row)
    proposal_id = str(detail.get("proposalId") or "")
    if proposal_id:
        proposals._db.execute(
            "UPDATE EffectfulWideningProposal SET status='revoked', revokedAt=? WHERE id=?",
            (now_iso(), proposal_id),
        )
        proposals._db.commit()
    refresh(store)
    return {"ok": True, "grant": row}


def expire_due(store: Any) -> list[str]:
    audit = SelfModificationAudit(store)
    now = now_iso()
    proposals = EffectfulProposalStore(store)
    expired: list[str] = []
    for row in audit.active("widen_effect_tool"):
        if str(row.get("expiresAt") or "") > now:
            continue
        if audit.revoke(str(row.get("id") or "")) is not None:
            expired.append(str(row.get("id") or ""))
            proposal_id = str(_detail(row).get("proposalId") or "")
            if proposal_id:
                proposals._db.execute(
                    "UPDATE EffectfulWideningProposal SET status='expired', revokedAt=? WHERE id=?",
                    (now, proposal_id),
                )
    if expired:
        proposals._db.commit()
        refresh(store)
    return expired


def list_grants(store: Any) -> list[dict[str, Any]]:
    rows = SelfModificationAudit(store).active("widen_effect_tool")
    for row in rows:
        row["detail"] = _detail(row)
    return rows


__all__ = [
    "EffectfulProposalStore", "approve", "check_call", "expire_due",
    "granted_tools", "list_grants", "propose", "refresh", "revoke_grant",
]
