"""Effectful-tool approvals (Phase 5G).

An MCP tool whose effect is `write` or `external_action` is NEVER run on the
model's say-so. The runtime creates a PENDING approval request bound to the exact
(server, tool, arguments-digest), and an operator decides it. Only an ACTIVE,
unexpired approval whose digest matches the exact approved arguments authorizes a
call.

Invariants (all enforced in code, never by prompt or server metadata):
  * unknown effect class is never approvable;
  * the digest covers the canonicalized validated arguments, so a changed payload
    requires a new approval;
  * an approval is scoped to one run (or explicitly run-less for a standing
    grant) and expires;
  * a denial is terminal for that digest;
  * a prior approval, a tool description, or a model claim can never authorize a
    different action.

The store is `agent-memory.db` (the runtime's own database). It holds NO secret
material — only server/tool identity, an argument digest, and decisions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger("harness.mcp.approvals")

# Effect classes that require an explicit approval. `unknown` is deliberately
# absent: an unknown effect can never be approved.
APPROVABLE_EFFECTS = {"write", "external_action"}

DEFAULT_TTL_SECONDS = 15 * 60
MAX_TTL_SECONDS = 24 * 60 * 60

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"
EXPIRED = "expired"


def args_digest(args: dict[str, Any]) -> str:
    """A stable digest of a call's canonicalized arguments.

    Two calls with the same JSON (key order/whitespace independent) share a
    digest; any changed value produces a different digest, so an old approval can
    never authorize a new payload.
    """
    canonical = json.dumps(args or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_action_summary(server_id: str, tool: str, effect: str, args: dict[str, Any]) -> str:
    """A plain-language one-liner of what an effectful call will do.

    Deliberately conservative and non-committal about intent (we only know the
    tool name and arguments), so it never overstates what will happen.
    """
    verb = {
        "write": "will write data",
        "external_action": "will perform an external action",
    }.get(effect, f"has effect {effect}")
    keys = ", ".join(sorted(str(k) for k in (args or {}).keys())) or "no arguments"
    return f"Tool `{tool}` on server `{server_id}` {verb} (arguments: {keys})."


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class ApprovalStore:
    """Persistence + decision logic for effectful MCP tool approvals.

    Bound to the runtime's `AgentMemoryStore` connection so it shares the ONE
    agent-memory database; this module owns only its table and rules.
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db  # the AgentMemoryStore's sqlite connection

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS McpApproval (
              id             TEXT PRIMARY KEY,
              serverId       TEXT NOT NULL,
              tool           TEXT NOT NULL,
              eclipseTool    TEXT NOT NULL,
              effect         TEXT NOT NULL,
              argsDigest     TEXT NOT NULL,
              argsPreview    TEXT,
              status         TEXT NOT NULL,
              createdAt      TEXT NOT NULL,
              expiresAt      TEXT,
              decidedAt      TEXT,
              decidedBy      TEXT,
              reason         TEXT,
              requestedByRunId TEXT,
              actionSummary  TEXT,
              affectedData   TEXT,
              risk           TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_approval_lookup "
            "ON McpApproval(serverId, tool, argsDigest, status)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mcp_approval_status ON McpApproval(status, createdAt)"
        )
        # Additive columns for databases created before the clarity fields.
        existing = {row["name"] for row in self._db.execute("PRAGMA table_info(McpApproval)").fetchall()}
        for name in ("actionSummary", "affectedData", "risk"):
            if name not in existing:
                self._db.execute(f"ALTER TABLE McpApproval ADD COLUMN {name} TEXT")
        self._db.commit()

    # -- creation ------------------------------------------------------------

    def request(
        self,
        *,
        server_id: str,
        tool: str,
        eclipse_tool: str,
        effect: str,
        args: dict[str, Any],
        run_id: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        args_preview: Optional[str] = None,
        action_summary: Optional[str] = None,
        affected_data: Optional[str] = None,
        risk: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create (or return an existing) pending approval for this exact call."""
        if effect not in APPROVABLE_EFFECTS:
            raise ValueError(f"effect {effect!r} is not approvable")
        digest = args_digest(args)
        existing = self.find_active(server_id, tool, digest)
        if existing is not None:
            return existing
        # Re-use a pending request for the same call instead of spamming.
        pending = self._find_one(server_id, tool, digest, PENDING)
        if pending is not None:
            return pending
        # A prior DENIAL is terminal for this exact call: re-requesting must not
        # silently re-open it.
        denied = self._find_one(server_id, tool, digest, DENIED)
        if denied is not None:
            return denied

        import uuid

        ttl = max(30, min(int(ttl_seconds), MAX_TTL_SECONDS))
        now = _now()
        approval_id = f"mcpappr_{uuid.uuid4().hex[:16]}"
        summary = action_summary or _default_action_summary(server_id, tool, effect, args)
        affected_json = (
            json.dumps(affected_data, sort_keys=True, default=str) if affected_data is not None else None
        )
        record = {
            "id": approval_id,
            "serverId": server_id,
            "tool": tool,
            "eclipseTool": eclipse_tool,
            "effect": effect,
            "argsDigest": digest,
            "argsPreview": (args_preview or "")[:400],
            "status": PENDING,
            "createdAt": _iso(now),
            "expiresAt": _iso(now + timedelta(seconds=ttl)),
            "decidedAt": None,
            "decidedBy": None,
            "reason": None,
            "requestedByRunId": run_id,
        }
        self._db.execute(
            """INSERT INTO McpApproval
               (id, serverId, tool, eclipseTool, effect, argsDigest, argsPreview, status,
                createdAt, expiresAt, decidedAt, decidedBy, reason, requestedByRunId,
                actionSummary, affectedData, risk)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], server_id, tool, eclipse_tool, effect, digest,
                record["argsPreview"], PENDING, record["createdAt"], record["expiresAt"],
                None, None, None, run_id, summary, affected_json, risk,
            ),
        )
        record["actionSummary"] = summary
        record["affectedData"] = affected_data
        record["risk"] = risk
        self._db.commit()
        return record

    # -- lookup --------------------------------------------------------------

    def _row(self, row: Any) -> dict[str, Any]:
        return dict(row) if row is not None else {}

    def _find_one(self, server_id: str, tool: str, digest: str, status: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM McpApproval WHERE serverId=? AND tool=? AND argsDigest=? AND status=? "
            "ORDER BY createdAt DESC LIMIT 1",
            (server_id, tool, digest, status),
        ).fetchone()
        return self._row(row) if row else None

    def _expire_stale(self) -> None:
        now = _iso(_now())
        self._db.execute(
            "UPDATE McpApproval SET status=? WHERE status=? AND expiresAt IS NOT NULL AND expiresAt < ?",
            (EXPIRED, APPROVED, now),
        )
        self._db.execute(
            "UPDATE McpApproval SET status=? WHERE status=? AND expiresAt IS NOT NULL AND expiresAt < ?",
            (EXPIRED, PENDING, now),
        )
        self._db.commit()

    def find_active(self, server_id: str, tool: str, digest: str) -> Optional[dict[str, Any]]:
        """An APPROVED, unexpired approval matching this exact call, or None."""
        self._expire_stale()
        return self._find_one(server_id, tool, digest, APPROVED)

    def is_authorized(self, server_id: str, tool: str, args: dict[str, Any]) -> bool:
        return self.find_active(server_id, tool, args_digest(args)) is not None

    def get(self, approval_id: str) -> Optional[dict[str, Any]]:
        self._expire_stale()
        row = self._db.execute("SELECT * FROM McpApproval WHERE id=?", (approval_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        self._expire_stale()
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM McpApproval WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM McpApproval ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    # -- decisions -----------------------------------------------------------

    def decide(self, approval_id: str, *, approve: bool, decided_by: str = "operator", reason: str = "") -> Optional[dict[str, Any]]:
        """Approve or deny a pending request. A decision is final for that digest."""
        current = self.get(approval_id)
        if current is None:
            return None
        if current["status"] != PENDING:
            return current  # already decided/expired — report the real state
        self._db.execute(
            "UPDATE McpApproval SET status=?, decidedAt=?, decidedBy=?, reason=? WHERE id=?",
            (APPROVED if approve else DENIED, _iso(_now()), decided_by, (reason or "")[:400], approval_id),
        )
        self._db.commit()
        return self.get(approval_id)


def make_effect_authorizer(approvals: ApprovalStore, run_id: str, emitter: Any = None):
    """Build the async authorizer attached to every run's ToolContext.

    Called by the registry for a tool whose `permission` is not `read`. If an
    APPROVED, unexpired approval matches the exact server/tool/arguments, the call
    proceeds. Otherwise it creates a PENDING approval request (so an operator can
    decide) and refuses the call — the model is told an approval is required,
    never that it succeeded.
    """

    async def authorize(tool: Any, clean_args: dict[str, Any]) -> bool:
        meta = getattr(tool, "effect_metadata", None) or {}
        server_id = str(meta.get("serverId") or "")
        original = str(meta.get("tool") or "")
        effect = str(getattr(tool, "effect", "") or "")
        if not server_id or not original or effect not in APPROVABLE_EFFECTS:
            return False
        if approvals.is_authorized(server_id, original, clean_args):
            if emitter is not None:
                await emitter.emit("mcp.tool.approved", {
                    "serverId": server_id, "tool": original,
                    "eclipseTool": getattr(tool, "name", ""), "effect": effect,
                })
            return True
        # Create/refresh a pending request so the operator can act on it, then deny.
        try:
            request = approvals.request(
                server_id=server_id,
                tool=original,
                eclipse_tool=str(getattr(tool, "name", "")),
                effect=effect,
                args=clean_args,
                run_id=run_id,
                action_summary=getattr(tool, "effect_action_summary", None),
                affected_data=getattr(tool, "effect_affected_data", None),
                risk=getattr(tool, "effect_risk", None),
            )
            if emitter is not None:
                await emitter.emit("mcp.tool.approval_required", {
                    "serverId": server_id, "tool": original,
                    "eclipseTool": getattr(tool, "name", ""), "effect": effect,
                    "approvalId": request.get("id"),
                })
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            log.warning("failed to record MCP approval request", exc_info=True)
        return False

    return authorize

