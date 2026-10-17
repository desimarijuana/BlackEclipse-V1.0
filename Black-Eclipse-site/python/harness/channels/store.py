"""The durable Channel Gateway store (agent-memory.db).

Bound to the ONE `AgentMemoryStore` connection — the same pattern as
`event_system/store.py`, `jobs/store.py` and `tasks/store.py`. It owns only its
own tables so `persistence.py` (pinned at its size ratchet) does not grow.

Tables:

    ChannelBinding       verified external-account → Eclipse-identity links
    ChannelLinkCode      short-lived single-use codes minted in the UI
    ChannelSeen          inbound idempotency (platform message ids)
    ChannelMessage       inbound/outbound history
    ChannelConfirmation  pending/confirmed single-use mutation confirmations
    ChannelConfig        per-channel enable flag + non-secret JSON config

Secrets (bot tokens, SMTP passwords) live in the JSON config for Phase 1, mirroring
the existing TS `alert_channels` behaviour; a value may also be a `secret://`
reference resolved through the Security Gateway's secrets manager at send time.
Config values are NEVER returned by the API (only booleans / presence flags).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso
from .model import (
    ChannelBinding,
    Confirmation,
    LinkCode,
    new_id,
)

_MAX_MESSAGES = 1000


class ChannelStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS ChannelBinding (
              id           TEXT PRIMARY KEY,
              kind         TEXT NOT NULL,
              externalId   TEXT NOT NULL,
              externalChat TEXT NOT NULL,
              displayName  TEXT,
              userId       TEXT,
              tenantId     TEXT,
              scope        TEXT NOT NULL DEFAULT 'viewer',
              status       TEXT NOT NULL DEFAULT 'active',
              createdAt    TEXT NOT NULL,
              lastSeenAt   TEXT,
              UNIQUE(kind, externalId)
            );
            CREATE INDEX IF NOT EXISTS idx_channelbinding_kind   ON ChannelBinding(kind, status);
            CREATE INDEX IF NOT EXISTS idx_channelbinding_user   ON ChannelBinding(userId);
            CREATE INDEX IF NOT EXISTS idx_channelbinding_tenant ON ChannelBinding(tenantId);

            CREATE TABLE IF NOT EXISTS ChannelLinkCode (
              code       TEXT PRIMARY KEY,
              kind       TEXT NOT NULL,
              userId     TEXT,
              tenantId   TEXT,
              scope      TEXT NOT NULL DEFAULT 'viewer',
              createdAt  TEXT NOT NULL,
              expiresAt  TEXT NOT NULL,
              usedAt     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_channellinkcode_kind ON ChannelLinkCode(kind, expiresAt);

            CREATE TABLE IF NOT EXISTS ChannelSeen (
              kind              TEXT NOT NULL,
              platformMessageId TEXT NOT NULL,
              seenAt            TEXT NOT NULL,
              PRIMARY KEY (kind, platformMessageId)
            );

            CREATE TABLE IF NOT EXISTS ChannelMessage (
              id                TEXT PRIMARY KEY,
              kind              TEXT NOT NULL,
              direction         TEXT NOT NULL,
              externalId        TEXT,
              externalChat      TEXT,
              bindingId         TEXT,
              platformMessageId TEXT,
              text              TEXT,
              status            TEXT NOT NULL,
              runId             TEXT,
              detail            TEXT,
              createdAt         TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_channelmessage_binding ON ChannelMessage(bindingId, createdAt);
            CREATE INDEX IF NOT EXISTS idx_channelmessage_kind    ON ChannelMessage(kind, createdAt);

            CREATE TABLE IF NOT EXISTS ChannelConfirmation (
              token       TEXT PRIMARY KEY,
              bindingId   TEXT NOT NULL,
              commandText TEXT NOT NULL,
              action      TEXT NOT NULL,
              resource    TEXT NOT NULL,
              createdAt   TEXT NOT NULL,
              expiresAt   TEXT NOT NULL,
              status      TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE INDEX IF NOT EXISTS idx_channelconfirmation_binding ON ChannelConfirmation(bindingId, status);

            CREATE TABLE IF NOT EXISTS ChannelConfig (
              channel   TEXT PRIMARY KEY,
              enabled   INTEGER NOT NULL DEFAULT 0,
              config    TEXT NOT NULL DEFAULT '{}',
              updatedAt TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ChannelSecret (
              channel    TEXT NOT NULL,
              name       TEXT NOT NULL,
              ciphertext TEXT NOT NULL,
              updatedAt  TEXT NOT NULL,
              PRIMARY KEY (channel, name)
            );
            """
        )

    # ── Bindings ─────────────────────────────────────────────────────────────
    @staticmethod
    def _binding(row: Any) -> ChannelBinding:
        return ChannelBinding(
            id=row["id"],
            kind=row["kind"],
            external_id=row["externalId"],
            external_chat=row["externalChat"],
            display_name=row["displayName"] or "",
            user_id=row["userId"],
            tenant_id=row["tenantId"],
            scope=row["scope"],
            status=row["status"],
            created_at=row["createdAt"],
            last_seen_at=row["lastSeenAt"],
        )

    def find_binding(self, kind: str, external_id: str) -> Optional[ChannelBinding]:
        row = self._db.execute(
            "SELECT * FROM ChannelBinding WHERE kind=? AND externalId=?", (kind, external_id)
        ).fetchone()
        return self._binding(row) if row else None

    def get_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        row = self._db.execute("SELECT * FROM ChannelBinding WHERE id=?", (binding_id,)).fetchone()
        return self._binding(row) if row else None

    def list_bindings(self, *, kind: Optional[str] = None, limit: int = 200) -> list[ChannelBinding]:
        if kind:
            rows = self._db.execute(
                "SELECT * FROM ChannelBinding WHERE kind=? ORDER BY createdAt DESC LIMIT ?",
                (kind, max(1, min(int(limit), 1000))),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM ChannelBinding ORDER BY createdAt DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [self._binding(r) for r in rows]

    def upsert_binding(
        self,
        *,
        kind: str,
        external_id: str,
        external_chat: str,
        display_name: str,
        user_id: Optional[str],
        tenant_id: Optional[str],
        scope: str,
    ) -> ChannelBinding:
        existing = self.find_binding(kind, external_id)
        now = now_iso()
        if existing is not None:
            self._db.execute(
                "UPDATE ChannelBinding SET externalChat=?, displayName=?, userId=?, tenantId=?, "
                "scope=?, status='active', lastSeenAt=? WHERE id=?",
                (external_chat, display_name, user_id, tenant_id, scope, now, existing.id),
            )
            self._db.commit()
            return self.get_binding(existing.id)  # type: ignore[return-value]
        binding_id = new_id("chb")
        self._db.execute(
            "INSERT INTO ChannelBinding "
            "(id, kind, externalId, externalChat, displayName, userId, tenantId, scope, status, createdAt, lastSeenAt) "
            "VALUES (?,?,?,?,?,?,?,?, 'active', ?, ?)",
            (binding_id, kind, external_id, external_chat, display_name, user_id, tenant_id, scope, now, now),
        )
        self._db.commit()
        return self.get_binding(binding_id)  # type: ignore[return-value]

    def set_binding_scope(self, binding_id: str, scope: str) -> bool:
        cur = self._db.execute("UPDATE ChannelBinding SET scope=? WHERE id=?", (scope, binding_id))
        self._db.commit()
        return cur.rowcount > 0

    def revoke_binding(self, binding_id: str) -> bool:
        cur = self._db.execute(
            "UPDATE ChannelBinding SET status='revoked' WHERE id=?", (binding_id,)
        )
        self._db.commit()
        return cur.rowcount > 0

    def touch_binding(self, binding_id: str) -> None:
        self._db.execute(
            "UPDATE ChannelBinding SET lastSeenAt=? WHERE id=?", (now_iso(), binding_id)
        )
        self._db.commit()

    # ── Link codes ───────────────────────────────────────────────────────────
    def create_link_code(
        self, *, code: str, kind: str, user_id: Optional[str], tenant_id: Optional[str],
        scope: str, expires_at: str,
    ) -> LinkCode:
        now = now_iso()
        self._db.execute(
            "INSERT OR REPLACE INTO ChannelLinkCode "
            "(code, kind, userId, tenantId, scope, createdAt, expiresAt, usedAt) "
            "VALUES (?,?,?,?,?,?,?, NULL)",
            (code, kind, user_id, tenant_id, scope, now, expires_at),
        )
        self._db.commit()
        return LinkCode(code, kind, user_id, tenant_id, scope, now, expires_at)

    def get_link_code(self, code: str) -> Optional[LinkCode]:
        row = self._db.execute(
            "SELECT * FROM ChannelLinkCode WHERE code=?", (code,)
        ).fetchone()
        if row is None:
            return None
        return LinkCode(
            code=row["code"],
            kind=row["kind"],
            user_id=row["userId"],
            tenant_id=row["tenantId"],
            scope=row["scope"],
            created_at=row["createdAt"],
            expires_at=row["expiresAt"],
            used_at=row["usedAt"],
        )

    def consume_link_code(self, code: str) -> bool:
        """Mark a code used. Returns True only the FIRST time (atomic single-use)."""
        cur = self._db.execute(
            "UPDATE ChannelLinkCode SET usedAt=? WHERE code=? AND usedAt IS NULL",
            (now_iso(), code),
        )
        self._db.commit()
        return cur.rowcount > 0

    def prune_link_codes(self, *, before_iso: str) -> int:
        cur = self._db.execute("DELETE FROM ChannelLinkCode WHERE expiresAt < ?", (before_iso,))
        self._db.commit()
        return cur.rowcount

    # ── Idempotency ──────────────────────────────────────────────────────────
    def mark_seen(self, kind: str, platform_message_id: str) -> bool:
        """Record an inbound platform message id. True if NEW, False if a duplicate."""
        try:
            self._db.execute(
                "INSERT INTO ChannelSeen (kind, platformMessageId, seenAt) VALUES (?,?,?)",
                (kind, platform_message_id, now_iso()),
            )
        except Exception:  # noqa: BLE001 - UNIQUE violation ⇒ already seen
            try:
                self._db.rollback()
            except Exception:  # noqa: BLE001 - a rollback failure is still "already seen"
                pass
            return False
        self._db.commit()
        return True

    # ── Messages ─────────────────────────────────────────────────────────────
    def record_message(
        self,
        *,
        kind: str,
        direction: str,
        external_id: Optional[str],
        external_chat: Optional[str],
        binding_id: Optional[str],
        platform_message_id: Optional[str],
        text: str,
        status: str,
        run_id: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> str:
        message_id = new_id("chm")
        self._db.execute(
            "INSERT INTO ChannelMessage "
            "(id, kind, direction, externalId, externalChat, bindingId, platformMessageId, "
            " text, status, runId, detail, createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                message_id, kind, direction, external_id, external_chat, binding_id,
                platform_message_id, text[:8000], status, run_id,
                json.dumps(detail or {}, default=str)[:8000], now_iso(),
            ),
        )
        self._db.commit()
        return message_id

    def list_messages(
        self, *, kind: Optional[str] = None, binding_id: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if binding_id:
            clauses.append("bindingId = ?")
            params.append(binding_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit), _MAX_MESSAGES))
        rows = self._db.execute(
            f"SELECT * FROM ChannelMessage {where} ORDER BY createdAt DESC, rowid DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "kind": r["kind"],
                "direction": r["direction"],
                "externalId": r["externalId"],
                "externalChat": r["externalChat"],
                "bindingId": r["bindingId"],
                "platformMessageId": r["platformMessageId"],
                "text": r["text"],
                "status": r["status"],
                "runId": r["runId"],
                "detail": json.loads(r["detail"]) if r["detail"] else {},
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    # ── Confirmations ────────────────────────────────────────────────────────
    def create_confirmation(
        self, *, token: str, binding_id: str, command_text: str, action: str,
        resource: str, expires_at: str,
    ) -> Confirmation:
        now = now_iso()
        self._db.execute(
            "INSERT INTO ChannelConfirmation "
            "(token, bindingId, commandText, action, resource, createdAt, expiresAt, status) "
            "VALUES (?,?,?,?,?,?,?, 'pending')",
            (token, binding_id, command_text, action, resource, now, expires_at),
        )
        self._db.commit()
        return Confirmation(token, binding_id, command_text, action, resource, now, expires_at)

    def get_confirmation(self, token: str) -> Optional[Confirmation]:
        row = self._db.execute(
            "SELECT * FROM ChannelConfirmation WHERE token=?", (token,)
        ).fetchone()
        if row is None:
            return None
        return Confirmation(
            token=row["token"],
            binding_id=row["bindingId"],
            command_text=row["commandText"],
            action=row["action"],
            resource=row["resource"],
            created_at=row["createdAt"],
            expires_at=row["expiresAt"],
            status=row["status"],
        )

    def claim_confirmation(self, token: str) -> Optional[Confirmation]:
        """Atomically mark a PENDING confirmation confirmed. None if not pending."""
        cur = self._db.execute(
            "UPDATE ChannelConfirmation SET status='confirmed' WHERE token=? AND status='pending'",
            (token,),
        )
        self._db.commit()
        if cur.rowcount == 0:
            return None
        return self.get_confirmation(token)

    def set_confirmation_status(self, token: str, status: str) -> None:
        self._db.execute("UPDATE ChannelConfirmation SET status=? WHERE token=?", (status, token))
        self._db.commit()

    def expire_confirmations(self, *, before_iso: str) -> int:
        cur = self._db.execute(
            "UPDATE ChannelConfirmation SET status='expired' WHERE status='pending' AND expiresAt < ?",
            (before_iso,),
        )
        self._db.commit()
        return cur.rowcount

    # ── Config ───────────────────────────────────────────────────────────────
    def get_config(self, channel: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ChannelConfig WHERE channel=?", (channel,)
        ).fetchone()
        if row is None:
            return None
        return {
            "channel": row["channel"],
            "enabled": bool(row["enabled"]),
            "config": json.loads(row["config"]) if row["config"] else {},
            "updatedAt": row["updatedAt"],
        }

    def list_configs(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM ChannelConfig").fetchall()
        return [
            {
                "channel": r["channel"],
                "enabled": bool(r["enabled"]),
                "config": json.loads(r["config"]) if r["config"] else {},
                "updatedAt": r["updatedAt"],
            }
            for r in rows
        ]

    def set_config(self, channel: str, *, enabled: bool, config: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            "INSERT INTO ChannelConfig (channel, enabled, config, updatedAt) VALUES (?,?,?,?) "
            "ON CONFLICT(channel) DO UPDATE SET enabled=excluded.enabled, config=excluded.config, "
            "updatedAt=excluded.updatedAt",
            (channel, 1 if enabled else 0, json.dumps(config or {}, default=str), now),
        )
        self._db.commit()
        return self.get_config(channel)  # type: ignore[return-value]

    def delete_config(self, channel: str) -> bool:
        cur = self._db.execute("DELETE FROM ChannelConfig WHERE channel=?", (channel,))
        self._db.commit()
        return cur.rowcount > 0

    # ── Encrypted secrets (ciphertext only; plaintext never touches the DB) ────
    def set_secret(self, channel: str, name: str, ciphertext: str) -> None:
        self._db.execute(
            "INSERT INTO ChannelSecret (channel, name, ciphertext, updatedAt) VALUES (?,?,?,?) "
            "ON CONFLICT(channel, name) DO UPDATE SET ciphertext=excluded.ciphertext, updatedAt=excluded.updatedAt",
            (channel, name, ciphertext, now_iso()),
        )
        self._db.commit()

    def get_secret_ciphertext(self, channel: str, name: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT ciphertext FROM ChannelSecret WHERE channel=? AND name=?", (channel, name)
        ).fetchone()
        return row["ciphertext"] if row else None

    def list_secret_names(self, channel: str) -> list[str]:
        rows = self._db.execute(
            "SELECT name FROM ChannelSecret WHERE channel=? ORDER BY name", (channel,)
        ).fetchall()
        return [r["name"] for r in rows]

    def delete_secrets(self, channel: str) -> int:
        cur = self._db.execute("DELETE FROM ChannelSecret WHERE channel=?", (channel,))
        self._db.commit()
        return cur.rowcount


__all__ = ["ChannelStore"]
