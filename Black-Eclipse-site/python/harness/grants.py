"""Standing grants — an explicit, operator-only "always allow" permission.

This is the deliberate counterpart to the SINGLE-USE approval (ADR-H92). A
`McpApproval` still authorizes exactly ONE call; a `StandingGrant` is a separate,
persisted, *labeled* record that an operator chose to remember so the SAME
program / tool in the SAME workspace stops asking. It is additive over the
single-use store — the store is unchanged, the grant only short-circuits the
*asking*, never the effect classification:

  * a `deny`-classified command is refused BEFORE a grant is ever consulted, so
    a grant can never make a destructive command run;
  * a grant is scoped to one `(kind, scope, pattern)`; a different program, a
    different workspace, or a different tool is unaffected;
  * only an effectful action the operator could have approved by hand is ever
    grantable (the authorizers set the pattern), so `external_action` remote
    operations and dangerous Git ops are never remembered;
  * every grant is listed and revocable from the Permissions surface;
  * a grant is inert for authorization of a *different* digest — it removes the
    prompt, it does not bypass the store.

The store rides the runtime's OWN `agent-memory.db` (the same connection as
`McpApproval`), like `mcp/approvals.py` and `run_lineage.py`.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Optional

from .persistence import now_iso

# Grant kinds. `command` deliberately covers the generic terminal, the shell, the
# terminal subsystem and `open_shell`, so one "always allow python3" applies to
# every surface that runs a command.
GRANT_COMMAND = "command"
GRANT_MCP_TOOL = "mcp_tool"
GRANT_GIT_OPERATION = "git_operation"

_GRANT_DDL = """
CREATE TABLE IF NOT EXISTS StandingGrant (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  scope      TEXT NOT NULL DEFAULT '',
  pattern    TEXT NOT NULL,
  label      TEXT,
  risk       TEXT,
  source     TEXT,
  createdBy  TEXT,
  createdAt  TEXT NOT NULL,
  lastUsedAt TEXT
)
"""


def grant_id(kind: str, scope: str, pattern: str) -> str:
    raw = f"{kind}\x00{scope}\x00{pattern}"
    return "grant_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class GrantStore:
    """Standing grants over the ONE agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(_GRANT_DDL)
        self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_standing_grant_key "
            "ON StandingGrant(kind, scope, pattern)"
        )
        self._db.commit()

    # -- writes --------------------------------------------------------------
    def add(
        self,
        *,
        kind: str,
        pattern: str,
        scope: str = "",
        label: Optional[str] = None,
        risk: Optional[str] = None,
        source: Optional[str] = None,
        created_by: str = "operator",
    ) -> dict[str, Any]:
        """Create or refresh a standing grant. Idempotent by `(kind, scope, pattern)`."""
        pattern = str(pattern or "").strip()
        if not kind or not pattern:
            raise ValueError("a grant needs a kind and a pattern")
        scope = str(scope or "")
        existing = self.get(grant_id(kind, scope, pattern))
        if existing is not None:
            self._db.execute(
                "UPDATE StandingGrant SET label=COALESCE(?, label), risk=COALESCE(?, risk), "
                "source=COALESCE(?, source), createdBy=? WHERE id=?",
                (label, risk, source, created_by, existing["id"]),
            )
            self._db.commit()
            return self.get(existing["id"]) or existing
        record = {
            "id": grant_id(kind, scope, pattern),
            "kind": kind,
            "scope": scope,
            "pattern": pattern,
            "label": label or pattern,
            "risk": risk,
            "source": source,
            "created_by": created_by,
            "created_at": now_iso(),
        }
        self._db.execute(
            "INSERT OR REPLACE INTO StandingGrant "
            "(id, kind, scope, pattern, label, risk, source, createdBy, createdAt, lastUsedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record["id"], kind, scope, pattern, record["label"], risk, source,
             created_by, record["created_at"], None),
        )
        self._db.commit()
        return self.get(record["id"]) or record

    def touch(self, grant_id_value: str) -> None:
        """Stamp `lastUsedAt` when a grant short-circuits a prompt."""
        self._db.execute(
            "UPDATE StandingGrant SET lastUsedAt=? WHERE id=?", (now_iso(), grant_id_value)
        )
        self._db.commit()

    def revoke(self, grant_id_value: str) -> bool:
        cursor = self._db.execute("DELETE FROM StandingGrant WHERE id=?", (grant_id_value,))
        self._db.commit()
        return cursor.rowcount > 0

    # -- reads ---------------------------------------------------------------
    def get(self, grant_id_value: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM StandingGrant WHERE id=?", (grant_id_value,)).fetchone()
        return dict(row) if row else None

    def find(self, kind: str, scope: str, pattern: str) -> Optional[dict[str, Any]]:
        """The exact grant for this `(kind, scope, pattern)`, or None."""
        row = self._db.execute(
            "SELECT * FROM StandingGrant WHERE kind=? AND scope=? AND pattern=?",
            (kind, str(scope or ""), str(pattern or "").strip()),
        ).fetchone()
        return dict(row) if row else None

    def matches(self, kind: str, scope: str, pattern: str) -> Optional[dict[str, Any]]:
        """Whether a live grant authorizes this call. Stamps `lastUsedAt` on a hit."""
        grant = self.find(kind, scope, pattern)
        if grant is not None:
            self.touch(grant["id"])
        return grant

    def list(self, scope: Optional[str] = None) -> list[dict[str, Any]]:
        if scope is None:
            rows = self._db.execute(
                "SELECT * FROM StandingGrant ORDER BY createdAt DESC"
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM StandingGrant WHERE scope=? ORDER BY createdAt DESC",
                (str(scope),),
            ).fetchall()
        return [dict(r) for r in rows]


def grant_kind_for_approval_kind(approval_kind: str) -> str:
    """Map an approval `kind` to the grant namespace it may create."""
    if approval_kind in ("terminal_command", "shell_command"):
        return GRANT_COMMAND
    if approval_kind == "mcp_tool":
        return GRANT_MCP_TOOL
    if approval_kind == "git_operation":
        return GRANT_GIT_OPERATION
    return approval_kind


__all__ = [
    "GRANT_COMMAND",
    "GRANT_GIT_OPERATION",
    "GRANT_MCP_TOOL",
    "GrantStore",
    "grant_id",
    "grant_kind_for_approval_kind",
]
