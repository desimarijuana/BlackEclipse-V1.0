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
  * **an approval is SINGLE-USE** (Tool-Loop Integrity ADR-H92): a successful
    authorization consumes it atomically, so one operator decision authorizes
    exactly ONE call. A second identical call is refused and produces a fresh
    PENDING request — never a silent pass and never a bare denial with no record.
  * a denial is terminal for that digest;
  * a prior approval, a tool description, or a model claim can never authorize a
    different action.

The store is `agent-memory.db` (the runtime's own database). It holds NO secret
material — only server/tool identity, an argument digest, and decisions.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger("harness.mcp.approvals")

# ── In-process pause/resume gates (approval cards) ─────────────────────────
# A pending approval id maps to an asyncio.Event. When the runtime's effect
# authorizer is in "ask" (pause) mode it creates the PENDING request, emits
# `approval.requested`, then awaits the gate. The decide route (same event loop)
# sets the event after committing the decision, so the run resumes IN PLACE with
# the operator's answer — the agent does not have to retry the whole step.
#
# The gate is intentionally in-process: if the runtime restarts mid-wait the run
# is cancelled and the persisted single-use approval remains, so the existing
# deny-and-retry path still works. No new authority is introduced — the gate only
# decides HOW LONG to wait, never WHETHER a call is authorized (that stays the
# single-use, digest-bound `consume`/`consume_kind`).
_GATES: dict[str, asyncio.Event] = {}


def _gate(approval_id: str) -> asyncio.Event:
    event = _GATES.get(approval_id)
    if event is None:
        event = asyncio.Event()
        _GATES[approval_id] = event
    return event


def notify_decision(approval_id: str) -> None:
    """Wake a paused run waiting on `approval_id`, if any. Safe to call always."""
    event = _GATES.get(approval_id)
    if event is not None:
        event.set()

# Effect classes that require an explicit approval. `unknown` is deliberately
# absent: an unknown effect can never be approved.
APPROVABLE_EFFECTS = {"write", "external_action"}

DEFAULT_TTL_SECONDS = 15 * 60
MAX_TTL_SECONDS = 24 * 60 * 60

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"
EXPIRED = "expired"
# An approval is single-use: once it authorizes a call it is moved to this
# terminal state, so the same operator decision can never authorize a second
# call. Distinct from `expired` so the audit trail says WHY it is inert.
CONSUMED = "consumed"


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


def claim_guarded(
    db: Any, *, table: str, kind: str, key_columns: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """The ADR-H92 single-use claim, in ONE place.

    A guarded ``UPDATE ... WHERE id=? AND status='approved'`` plus a rowcount
    check: at most one caller claims a given approval, even under concurrency
    (SQLite serializes the write, and the WHERE clause re-checks the state). The
    ``McpApproval`` path and the code-action path both call THIS function, so
    there is one implementation of 'single-use', not two.

    Returns the claimed row (status CONSUMED, ``usedAt`` stamped), or None when
    there is nothing to claim.
    """
    clauses = ["status = ?"]
    params: list[Any] = [APPROVED]
    for column, value in key_columns.items():
        clauses.append(f"{column} = ?")
        params.append(value)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    row = db.execute(
        f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} "
        "ORDER BY createdAt ASC LIMIT 1",
        tuple(params),
    ).fetchone()
    if row is None:
        return None
    used_at = _iso(_now())
    cursor = db.execute(
        f"UPDATE {table} SET status=?, usedAt=? WHERE id=? AND status=?",
        (CONSUMED, used_at, row["id"], APPROVED),
    )
    db.commit()
    if cursor.rowcount != 1:
        return None
    return dict(db.execute(f"SELECT * FROM {table} WHERE id=?", (row["id"],)).fetchone())


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
              risk           TEXT,
              usedAt         TEXT
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
        for name in ("actionSummary", "affectedData", "risk", "usedAt"):
            if name not in existing:
                self._db.execute(f"ALTER TABLE McpApproval ADD COLUMN {name} TEXT")
        # Phase 5: one approval store for two kinds. `kind` defaults to the
        # current meaning, so every existing row is correct without being touched;
        # `workspaceId` is set only for a `code_action` row.
        if "kind" not in existing:
            self._db.execute(
                "ALTER TABLE McpApproval ADD COLUMN kind TEXT NOT NULL DEFAULT 'mcp_tool'"
            )
        if "workspaceId" not in existing:
            self._db.execute("ALTER TABLE McpApproval ADD COLUMN workspaceId TEXT")
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
        # Re-use a PENDING request for the same call instead of spamming. A
        # CONSUMED approval is NOT returned here: it was already used once, so a
        # new call needs a new decision (fall through to create a fresh request).
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
        # The row's kind defaults to 'mcp_tool' in the DDL; make it explicit on
        # the returned record so a caller/tests can see it without a re-read.
        record["kind"] = "mcp_tool"
        record["workspaceId"] = None
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
        """Whether an APPROVED, unexpired approval exists — WITHOUT consuming it.

        A non-mutating probe (used by tests and the resource/prompt paths). The
        authorizing path is `consume`, which claims the approval atomically and
        is single-use.
        """
        return self.find_active(server_id, tool, args_digest(args)) is not None

    def _claim(self, server_id: str, tool: str, digest: str) -> Optional[dict[str, Any]]:
        """Atomically claim (consume) ONE approved, unexpired MCP approval.

        Delegates to the ONE `claim_guarded` primitive (so the MCP path and the
        code-action path share one implementation of 'single-use').
        """
        self._expire_stale()
        return claim_guarded(
            self._db, table="McpApproval", kind="mcp_tool",
            key_columns={"serverId": server_id, "tool": tool, "argsDigest": digest},
        )

    def consume(self, server_id: str, tool: str, args: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Claim the matching single-use approval for this exact call, or None.

        This is the authorizing operation. It is single-use: a successful claim
        means this call may proceed and a repeat of the same call is refused
        (until the operator approves a fresh request).
        """
        return self._claim(server_id, tool, args_digest(args))

    # -- one store, two kinds (Phase 5) --------------------------------------
    def request_kind(
        self,
        *,
        kind: str,
        request_key: str,
        digest: str,
        effect: str,
        run_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        action_summary: Optional[str] = None,
        affected_data: Optional[str] = None,
        risk: Optional[str] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> dict[str, Any]:
        """Create (or return the existing pending / terminal denial for) one
        approval of `kind`. The physical home is `McpApproval`; `kind` +
        `workspaceId` are additive. A PENDING request is reused; a CONSUMED one is
        not (a new call needs a fresh decision); a DENIAL is terminal for the
        digest. `serverId`/`tool` are overloaded for a code action: `serverId`
        carries the kind-qualified request key and `tool` the action name."""
        if effect not in APPROVABLE_EFFECTS:
            raise ValueError(f"effect {effect!r} is not approvable")
        pending = self._find_one_kind(kind, request_key, digest, PENDING)
        if pending is not None:
            return pending
        denied = self._find_one_kind(kind, request_key, digest, DENIED)
        if denied is not None:
            return denied
        import uuid

        ttl = max(30, min(int(ttl_seconds), MAX_TTL_SECONDS))
        now = _now()
        approval_id = f"appr_{uuid.uuid4().hex[:16]}"
        summary = action_summary or _default_action_summary(request_key, request_key, effect, {})
        affected_json = (
            json.dumps(affected_data, sort_keys=True, default=str) if affected_data is not None else None
        )
        self._db.execute(
            """INSERT INTO McpApproval
               (id, serverId, tool, eclipseTool, effect, argsDigest, argsPreview, status,
                createdAt, expiresAt, decidedAt, decidedBy, reason, requestedByRunId,
                actionSummary, affectedData, risk, kind, workspaceId)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                approval_id, request_key, request_key, request_key, effect, digest,
                "", PENDING, _iso(now), _iso(now + timedelta(seconds=ttl)),
                None, None, None, run_id, summary, affected_json, risk, kind, workspace_id,
            ),
        )
        self._db.commit()
        record = self.get(approval_id) or {}
        return record

    def _find_one_kind(self, kind: str, request_key: str, digest: str, status: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM McpApproval WHERE kind=? AND serverId=? AND argsDigest=? AND status=? "
            "ORDER BY createdAt DESC LIMIT 1",
            (kind, request_key, digest, status),
        ).fetchone()
        return self._row(row) if row else None

    def find_active_kind(self, kind: str, request_key: str, digest: str) -> Optional[dict[str, Any]]:
        """An APPROVED, unexpired approval of `kind` for this exact request."""
        self._expire_stale()
        return self._find_one_kind(kind, request_key, digest, APPROVED)

    def consume_kind(
        self, *, kind: str, request_key: str, digest: str, workspace_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Claim the matching single-use approval of `kind`. When `workspace_id` is
        given it MUST match the row's workspace, so an approval for workspace A is
        never claimed for workspace B."""
        self._expire_stale()
        keys: dict[str, Any] = {"serverId": request_key, "argsDigest": digest}
        if workspace_id is not None:
            keys["workspaceId"] = workspace_id
        return claim_guarded(self._db, table="McpApproval", kind=kind, key_columns=keys)

    def list_kind(self, kind: str, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM McpApproval WHERE kind=? AND status=? ORDER BY createdAt DESC LIMIT ?",
                (kind, status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM McpApproval WHERE kind=? ORDER BY createdAt DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        return [self._row(r) for r in rows]

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
        # Wake any run paused on this approval (approval-card pause mode). Done
        # AFTER the commit so a woken run that re-consults the store sees the
        # decision. A no-op when no run is waiting (deny-and-retry path).
        notify_decision(approval_id)
        return self.get(approval_id)

    # -- pause/resume (approval cards) ---------------------------------------

    async def wait_for_decision(self, approval_id: str, timeout_s: float = 900.0) -> Optional[dict[str, Any]]:
        """Block until the pending approval is decided (or `timeout_s` elapses).

        Returns the decided record when the status is no longer PENDING, else
        None (timeout/unavailable). Single-use authorization is NOT granted here:
        the caller re-claims through `consume`/`consume_kind` after waking, so a
        second identical call still needs its own approval.
        """
        gate = _gate(approval_id)
        try:
            await asyncio.wait_for(gate.wait(), timeout=max(1.0, float(timeout_s)))
        except asyncio.TimeoutError:
            return None
        finally:
            _GATES.pop(approval_id, None)
        current = self.get(approval_id)
        return current if current and current.get("status") != PENDING else None


async def invoke_effect_authorizer(authorizer: Any, tool: Any, args: dict[str, Any], ctx: Any) -> bool:
    """Call an effect authorizer, tolerating both signatures, never authorizing on error.

    The current authorizer takes `(tool, args, ctx)`; legacy test authorizers
    take `(tool, args)`. Arity is detected from the signature rather than guessed
    from a raised TypeError (which would mask a genuine bug inside the
    authorizer). Any exception yields False — a failing authorizer must never
    authorize.
    """
    try:
        try:
            params = len(inspect.signature(authorizer).parameters)
        except (TypeError, ValueError):
            params = 3
        if params >= 3:
            return bool(await authorizer(tool, args, ctx))
        return bool(await authorizer(tool, args))
    except Exception:  # noqa: BLE001 - a failing authorizer must not authorize
        return False


def make_effect_authorizer(approvals: ApprovalStore, run_id: str, emitter: Any = None):
    """Build the async authorizer attached to every run's ToolContext.

    Called for a tool whose permission is not `read`. An APPROVED, unexpired
    approval matching the exact server/tool/arguments authorizes the call and is
    CONSUMED (single-use, ADR-H92): the approval cannot authorize a second call.
    Otherwise a PENDING request is created/refreshed (so an operator can decide)
    and the call is refused — the model is told an approval is required, never
    that it succeeded.

    An effectful call is authorized at TWO seams — the registry gate
    (`ToolRegistry.execute`) and the MCP manager's `_execute` re-assert — both of
    which call this authorizer for the SAME call. To keep single-use from
    refusing a legitimate call at the second seam, the authorizer records the
    authorized argument digest on the shared `ctx` for the current call-scope; a
    later seam that sees the SAME digest authorizes without consuming again. The
    registry clears the scope at the start of each tool call, so every new call
    must claim its own approval.
    """

    async def authorize(tool: Any, clean_args: dict[str, Any], ctx: Any = None) -> bool:
        meta = getattr(tool, "effect_metadata", None) or {}
        server_id = str(meta.get("serverId") or "")
        original = str(meta.get("tool") or "")
        effect = str(getattr(tool, "effect", "") or "")
        if not server_id or not original or effect not in APPROVABLE_EFFECTS:
            return False
        digest = args_digest(clean_args)
        # Already authorized for THIS call-scope at an earlier seam: authorize
        # without consuming a second approval.
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True
        claimed = approvals.consume(server_id, original, clean_args)
        if claimed is not None:
            _mark_authorized(ctx, digest)
            if emitter is not None:
                await emitter.emit("mcp.tool.approved", {
                    "serverId": server_id, "tool": original,
                    "eclipseTool": getattr(tool, "name", ""), "effect": effect,
                    "approvalId": claimed.get("id"),
                    "singleUse": True,
                })
            return True
        # No claimable approval: create/refresh a pending request so the operator
        # can act on it.
        request: Optional[dict[str, Any]] = None
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
                await emitter.emit("approval.requested", {
                    "approvalId": request.get("id"),
                    "kind": "mcp_tool",
                    "title": f"Approve using {getattr(tool, 'name', original)}",
                    "summary": request.get("actionSummary") or _default_action_summary(
                        server_id, original, effect, clean_args,
                    ),
                    "effect": effect,
                    "risk": getattr(tool, "effect_risk", None),
                    "tool": original,
                    "serverId": server_id,
                })
                # Legacy event name, kept alongside the approval-card event so
                # existing consumers (architecture doc, MCP UI) are unchanged.
                await emitter.emit("mcp.tool.approval_required", {
                    "serverId": server_id, "tool": original,
                    "eclipseTool": getattr(tool, "name", ""), "effect": effect,
                    "approvalId": request.get("id"),
                })
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            log.warning("failed to record MCP approval request", exc_info=True)
        # Pause mode: wait for the operator's decision, then re-claim ONCE. This
        # is the approval card's blocking path; the decision itself still comes
        # from the single-use store, so a non-approval can never authorize.
        if request is not None and _pause_requested(ctx):
            await _await_then_reclaim(
                approvals, request.get("id"), lambda: approvals.consume(server_id, original, clean_args),
                emitter, ctx, digest, {
                    "serverId": server_id, "tool": original,
                    "eclipseTool": getattr(tool, "name", ""), "effect": effect,
                }, event_type="mcp.tool.approved",
            )
            if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
                return True
        return False

    return authorize


def _pause_requested(ctx: Any) -> bool:
    """Whether the run opted into blocking approval cards for this call."""
    return bool(ctx is not None and getattr(ctx, "pause_for_approval", False))


def _mark_authorized(ctx: Any, digest: str) -> None:
    if ctx is None:
        return
    try:
        ctx.effect_authorized_digest = digest
    except Exception:  # noqa: BLE001 - a frozen ctx must not break auth
        pass


async def _await_then_reclaim(
    approvals: ApprovalStore,
    approval_id: Optional[str],
    reclaim: Any,
    emitter: Any,
    ctx: Any,
    digest: str,
    approved_payload: dict[str, Any],
    *,
    event_type: str,
) -> Optional[dict[str, Any]]:
    """Pause on `approval_id`'s decision, then attempt ONE single-use reclaim.

    Shared by the MCP and code-action authorizers so the pause semantics live in
    ONE place. A denial, an expiry, or a timeout simply yields None and the call
    is refused (the pre-existing behavior); it never authorizes on a non-approval.
    """
    if not approval_id:
        return None
    timeout_s = float(getattr(ctx, "approval_timeout_s", 900.0) or 900.0)
    decided = await approvals.wait_for_decision(approval_id, timeout_s)
    if decided is None or decided.get("status") != APPROVED:
        if emitter is not None:
            await emitter.emit("approval.resolved", {
                "approvalId": approval_id,
                "approved": False,
                "reason": (decided or {}).get("reason") or "not approved",
            })
        return None
    claimed = reclaim()
    if claimed is not None:
        _mark_authorized(ctx, digest)
        if emitter is not None:
            await emitter.emit(event_type, {**approved_payload, "approvalId": claimed.get("id"), "singleUse": True})
            await emitter.emit("approval.resolved", {"approvalId": approval_id, "approved": True})
    return claimed


async def pause_for_decision(
    approvals: ApprovalStore,
    ctx: Any,
    approval_id: Optional[str],
    reclaim: Any,
    *,
    emitter: Any = None,
    digest: str = "",
    event_type: str = "approval.approved",
    approved_payload: Optional[dict[str, Any]] = None,
) -> bool:
    """Pause on an existing pending approval and reclaim it once, or return False.

    The ONE entry point for the shell/terminal authorizers' `ask` path, so the
    pause semantics are not re-implemented per command class.
    """
    if not approval_id or not _pause_requested(ctx):
        return False
    claimed = await _await_then_reclaim(
        approvals, approval_id, reclaim, emitter, ctx, digest,
        approved_payload or {}, event_type=event_type,
    )
    return claimed is not None
