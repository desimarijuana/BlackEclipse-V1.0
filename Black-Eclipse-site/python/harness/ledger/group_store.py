"""Entity groups — which ledgers consolidate together, and at what ownership.

A group is not a ledger and does not post. It names member ledgers and the
percentage of each that is included; the consolidation report does the arithmetic.
Separate file from the subledger only to keep both readable — it is the same
`agent-memory.db` connection.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS LedgerGroup (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  baseCurrency  TEXT NOT NULL DEFAULT 'USD',
  ownerId       TEXT,
  notes         TEXT,
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_group_owner ON LedgerGroup(ownerId);

CREATE TABLE IF NOT EXISTS LedgerGroupMember (
  id             TEXT PRIMARY KEY,
  groupId        TEXT NOT NULL,
  ledgerId       TEXT NOT NULL,
  ownershipPct   TEXT NOT NULL DEFAULT '100',
  createdAt      TEXT NOT NULL,
  FOREIGN KEY (groupId) REFERENCES LedgerGroup(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_group_member
  ON LedgerGroupMember(groupId, ledgerId);
"""


class GroupStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def create_group(self, group_id: str, name: str, *, base_currency: str = "USD",
                     owner_id: Optional[str] = None,
                     notes: Optional[str] = None) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            """INSERT INTO LedgerGroup (id, name, baseCurrency, ownerId, notes, createdAt)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, name, base_currency, owner_id, notes, now),
        )
        self._db.commit()
        return {"id": group_id, "name": name, "baseCurrency": base_currency,
                "ownerId": owner_id, "notes": notes, "createdAt": now}

    def get_group(self, group_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LedgerGroup WHERE id=?", (group_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "name": row["name"], "baseCurrency": row["baseCurrency"],
            "ownerId": row["ownerId"], "notes": row["notes"], "createdAt": row["createdAt"],
        }

    def list_groups(self, owner_id: Optional[str] = None) -> list[dict[str, Any]]:
        if owner_id:
            rows = self._db.execute(
                "SELECT * FROM LedgerGroup WHERE ownerId=? OR ownerId IS NULL "
                "ORDER BY createdAt DESC", (owner_id,),
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM LedgerGroup ORDER BY createdAt DESC").fetchall()
        return [self.get_group(row["id"]) for row in rows if row is not None]

    def add_member(self, member_id: str, group_id: str, ledger_id: str,
                   ownership_pct: str) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            """INSERT INTO LedgerGroupMember
               (id, groupId, ledgerId, ownershipPct, createdAt)
               VALUES (?, ?, ?, ?, ?)""",
            (member_id, group_id, ledger_id, ownership_pct, now),
        )
        self._db.commit()
        return {"id": member_id, "groupId": group_id, "ledgerId": ledger_id,
                "ownershipPct": ownership_pct, "createdAt": now}

    def list_members(self, group_id: str) -> list[dict[str, Any]]:
        # `createdAt` has millisecond precision, so two inserts in the same tick
        # tie; `rowid` restores deterministic insertion order.
        rows = self._db.execute(
            "SELECT * FROM LedgerGroupMember WHERE groupId=? ORDER BY createdAt, rowid",
            (group_id,),
        ).fetchall()
        return [
            {"id": row["id"], "groupId": row["groupId"], "ledgerId": row["ledgerId"],
             "ownershipPct": row["ownershipPct"], "createdAt": row["createdAt"]}
            for row in rows
        ]

    def get_member(self, group_id: str, ledger_id: str) -> Optional[dict[str, Any]]:
        for member in self.list_members(group_id):
            if member["ledgerId"] == ledger_id:
                return member
        return None

    def remove_member(self, group_id: str, ledger_id: str) -> bool:
        cursor = self._db.execute(
            "DELETE FROM LedgerGroupMember WHERE groupId=? AND ledgerId=?",
            (group_id, ledger_id),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def delete_group(self, group_id: str) -> bool:
        self._db.execute("DELETE FROM LedgerGroupMember WHERE groupId=?", (group_id,))
        cursor = self._db.execute("DELETE FROM LedgerGroup WHERE id=?", (group_id,))
        self._db.commit()
        return cursor.rowcount > 0

    def purge_ledger(self, ledger_id: str) -> None:
        """Drop memberships of a deleted ledger (a group must not point at a ghost)."""
        self._db.execute("DELETE FROM LedgerGroupMember WHERE ledgerId=?", (ledger_id,))
        self._db.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


__all__ = ["GroupStore", "new_id"]
