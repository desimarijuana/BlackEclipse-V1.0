"""Bounded demo-execution mandates for unattended graph runs (P3).

A mandate is an operator-created, expiring authorization for ONE demo broker
connection. It names the symbols, a margin cap and a maximum number of orders.
It is not a standing approval for live trading: `create` refuses a live
connection, and the graph compiler still refuses live trading nodes.

Every use is counted atomically, so a graph that loops cannot exceed the mandate.
Revocation is immediate.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..persistence import now_iso
from .model import BrokerConnection, ConnectionMode, TradeRefused

MAX_TTL_SECONDS = 7 * 24 * 60 * 60
# A live mandate may never outlive a trading day; the connection arm is shorter
# still, so an unattended live strategy needs both to be renewed.
LIVE_MAX_TTL_SECONDS = 24 * 60 * 60
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MAX_ORDERS = 1000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS TradingMandate (
  id           TEXT PRIMARY KEY,
  connectionId TEXT NOT NULL,
  mode         TEXT NOT NULL DEFAULT 'demo',
  symbols      TEXT NOT NULL DEFAULT '["*"]',
  maxOrders    INTEGER NOT NULL DEFAULT 20,
  maxMargin    REAL NOT NULL DEFAULT 0,
  ordersUsed   INTEGER NOT NULL DEFAULT 0,
  expiresAt    TEXT NOT NULL,
  revokedAt    TEXT,
  createdBy    TEXT NOT NULL DEFAULT 'operator',
  note         TEXT,
  createdAt    TEXT NOT NULL,
  lastUsedAt   TEXT,
  workflowId   TEXT,
  workflowVersion INTEGER
);
CREATE INDEX IF NOT EXISTS idx_mandate_connection
  ON TradingMandate(connectionId, createdAt);
"""


def _loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "connectionId": row["connectionId"],
        "mode": row["mode"],
        "symbols": _loads(row["symbols"], ["*"]),
        "maxOrders": row["maxOrders"],
        "maxMargin": row["maxMargin"],
        "ordersUsed": row["ordersUsed"],
        "remainingOrders": max(0, int(row["maxOrders"]) - int(row["ordersUsed"])),
        "expiresAt": row["expiresAt"],
        "revokedAt": row["revokedAt"],
        "createdBy": row["createdBy"],
        "note": row["note"],
        "createdAt": row["createdAt"],
        "lastUsedAt": row["lastUsedAt"],
        "workflowId": row["workflowId"] if "workflowId" in row.keys() else None,
        "workflowVersion": row["workflowVersion"] if "workflowVersion" in row.keys() else None,
    }


def _parse(value: Any) -> Optional[datetime]:
    raw = str(value or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _active(row: Any) -> bool:
    if row["revokedAt"]:
        return False
    expires = _parse(row["expiresAt"])
    if expires is None or datetime.now(timezone.utc) >= expires:
        return False
    return int(row["ordersUsed"]) < int(row["maxOrders"])


def _covers_symbol(symbols: Any, symbol: str) -> bool:
    if not isinstance(symbols, list):
        return False
    wanted = str(symbol or "").upper()
    return any(str(item).strip().upper() in ("*", wanted) for item in symbols)


class TradingMandateStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        # Existing databases predate the workflow pin columns.
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(TradingMandate)")}
        if "workflowId" not in columns:
            self._db.execute("ALTER TABLE TradingMandate ADD COLUMN workflowId TEXT")
        if "workflowVersion" not in columns:
            self._db.execute("ALTER TABLE TradingMandate ADD COLUMN workflowVersion INTEGER")
        self._db.commit()

    def create(
        self,
        *,
        connection: BrokerConnection,
        symbols: list[str],
        max_orders: int,
        max_margin: float,
        ttl_seconds: int,
        note: str = "",
        created_by: str = "operator",
        workflow_id: str = "",
        workflow_version: int | None = None,
    ) -> dict[str, Any]:
        if connection.mode not in (ConnectionMode.DEMO, ConnectionMode.LIVE):
            raise TradeRefused(
                "MANDATE_MODE_UNKNOWN",
                "the connection has no execution mode; set it to demo or live",
                status_code=403,
            )
        mode = connection.mode.value
        if mode == "live" and (not workflow_id or not workflow_version):
            raise TradeRefused(
                "MANDATE_WORKFLOW_REQUIRED",
                "a live mandate must pin the workflow id and version it authorizes",
                status_code=400,
            )
        cleaned = sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
        if not cleaned:
            cleaned = ["*"]
        orders = max(1, min(int(max_orders or 20), MAX_ORDERS))
        margin = float(max_margin or 0)
        if margin <= 0:
            raise TradeRefused(
                "MANDATE_CAP_REQUIRED",
                "a mandate needs a positive maxMargin",
                status_code=400,
            )
        ceiling = LIVE_MAX_TTL_SECONDS if mode == "live" else MAX_TTL_SECONDS
        ttl = max(60, min(int(ttl_seconds or DEFAULT_TTL_SECONDS), ceiling))
        now = now_iso()
        mandate_id = f"mnd_{uuid.uuid4().hex[:12]}"
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat().replace(
            "+00:00", "Z"
        )
        self._db.execute(
            """INSERT INTO TradingMandate
               (id, connectionId, mode, symbols, maxOrders, maxMargin, ordersUsed,
                expiresAt, createdBy, note, createdAt, workflowId, workflowVersion)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)""",
            (
                mandate_id,
                connection.id,
                mode,
                json.dumps(cleaned),
                orders,
                margin,
                expires,
                created_by,
                str(note or "")[:400] or None,
                now,
                workflow_id or None,
                int(workflow_version) if workflow_version else None,
            ),
        )
        self._db.commit()
        return self.get(mandate_id)  # type: ignore[return-value]

    def get(self, mandate_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM TradingMandate WHERE id=?", (str(mandate_id or ""),)
        ).fetchone()
        return _row(row) if row else None

    def list(self, connection_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        if connection_id:
            rows = self._db.execute(
                "SELECT * FROM TradingMandate WHERE connectionId=? "
                "ORDER BY createdAt DESC LIMIT ?",
                (connection_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM TradingMandate ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(row) for row in rows]

    def list_active(
        self, connection_id: Optional[str] = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        active: list[dict[str, Any]] = []
        for data in self.list(connection_id, limit=limit):
            if data["revokedAt"] or int(data["remainingOrders"]) <= 0:
                continue
            expires = _parse(data["expiresAt"])
            if expires is not None and expires > now:
                active.append(data)
        return active

    def revoke(self, mandate_id: str) -> Optional[dict[str, Any]]:
        self._db.execute(
            "UPDATE TradingMandate SET revokedAt=? WHERE id=? AND revokedAt IS NULL",
            (now_iso(), str(mandate_id or "")),
        )
        self._db.commit()
        return self.get(mandate_id)

    def covers(self, mandate_id: str, *, connection_id: str, symbol: str) -> bool:
        """Active, same connection, symbol allowed. Margin is checked at submit."""
        row = self._db.execute(
            "SELECT * FROM TradingMandate WHERE id=?", (str(mandate_id or ""),)
        ).fetchone()
        if row is None:
            return False
        data = _row(row)
        return (
            data["connectionId"] == connection_id
            and _active(row)
            and _covers_symbol(data["symbols"], symbol)
        )

    def verify(
        self, mandate_id: str, *, connection_id: str, symbol: str, margin: float,
        mode: str = "", workflow_id: str = "",
    ) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM TradingMandate WHERE id=?", (str(mandate_id or ""),)
        ).fetchone()
        if row is None:
            raise TradeRefused("MANDATE_NOT_FOUND", "that mandate does not exist", status_code=404)
        data = _row(row)
        if data["connectionId"] != connection_id:
            raise TradeRefused("MANDATE_CONNECTION_MISMATCH", "the mandate is for another connection", status_code=409)
        if mode and data["mode"] != mode:
            raise TradeRefused(
                "MANDATE_MODE_MISMATCH",
                f"the mandate is for {data['mode']} execution, not {mode}",
                status_code=409,
            )
        pinned = str(data.get("workflowId") or "")
        if pinned and str(workflow_id or "") != pinned:
            raise TradeRefused(
                "MANDATE_WORKFLOW_MISMATCH",
                "the mandate is pinned to a different workflow",
                status_code=409,
            )
        if not _active(row):
            raise TradeRefused(
                "MANDATE_INACTIVE",
                "the mandate is expired, revoked or exhausted",
                status_code=409,
            )
        if not _covers_symbol(data["symbols"], symbol):
            raise TradeRefused(
                "MANDATE_SYMBOL_NOT_ALLOWED",
                f"the mandate does not allow {symbol}",
                status_code=403,
            )
        if float(margin or 0) > float(data["maxMargin"]):
            raise TradeRefused(
                "MANDATE_MARGIN_EXCEEDED",
                f"the order needs {float(margin):,.2f} margin, above the mandate's "
                f"{float(data['maxMargin']):,.2f} cap",
                status_code=403,
            )
        return data

    def consume(self, mandate_id: str) -> dict[str, Any]:
        """Atomically count one order against the mandate."""
        now = now_iso()
        cursor = self._db.execute(
            """UPDATE TradingMandate
               SET ordersUsed=ordersUsed+1, lastUsedAt=?
               WHERE id=? AND revokedAt IS NULL
                 AND ordersUsed < maxOrders
                 AND expiresAt > ?""",
            (now, str(mandate_id or ""), now),
        )
        self._db.commit()
        if cursor.rowcount <= 0:
            raise TradeRefused(
                "MANDATE_EXHAUSTED",
                "the mandate expired, was revoked, or reached its order limit",
                status_code=409,
            )
        row = self.get(mandate_id)
        if row is None:  # pragma: no cover - the update succeeded
            raise TradeRefused("MANDATE_NOT_FOUND", "the mandate disappeared", status_code=409)
        return row


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "LIVE_MAX_TTL_SECONDS",
    "MAX_ORDERS",
    "MAX_TTL_SECONDS",
    "TradingMandateStore",
]
