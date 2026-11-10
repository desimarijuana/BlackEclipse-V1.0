"""Durable OMS records.

The in-memory `OrderManager` is useful for tests. A live system needs the order
state on disk so a restart cannot lose an open order or resend it. This store
uses the SAME state machine and the SAME idempotency key.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .oms import can_transition, order_key
from .store import QuantStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantOrder (
  id TEXT PRIMARY KEY,
  idempotencyKey TEXT NOT NULL UNIQUE,
  intentJson TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'new',
  ticket INTEGER,
  filledVolume REAL NOT NULL DEFAULT 0,
  avgPrice REAL NOT NULL DEFAULT 0,
  error TEXT,
  eventsJson TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qorder_state ON QuantOrder(state);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class OrderStore:
    def __init__(self, store: QuantStore) -> None:
        self.store = store
        self._db = store._db
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def create(self, intent: dict[str, Any], *, key: str) -> dict[str, Any]:
        existing = self._db.execute(
            "SELECT * FROM QuantOrder WHERE idempotencyKey=?", (key,)
        ).fetchone()
        if existing:
            return {**self._row(existing), "duplicate": True}
        order_id = f"oms_{uuid.uuid4().hex[:16]}"
        now = _now()
        events = [{"state": "new", "at": now}]
        self._db.execute(
            "INSERT INTO QuantOrder "
            "(id,idempotencyKey,intentJson,state,ticket,filledVolume,avgPrice,"
            "error,eventsJson,createdAt,updatedAt) "
            "VALUES (?,?,?,'new',NULL,0,0,NULL,?,?,?)",
            (order_id, key, json.dumps(intent, sort_keys=True), 
             json.dumps(events), now, now),
        )
        self._db.commit()
        return {**self.get(order_id), "duplicate": False}

    def get(self, order_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantOrder WHERE id=?", (order_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"order {order_id!r} not found")
        return self._row(row)

    def _row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "idempotencyKey": row["idempotencyKey"],
            "intent": json.loads(row["intentJson"] or "{}"),
            "state": row["state"],
            "ticket": row["ticket"],
            "filledVolume": row["filledVolume"],
            "avgPrice": row["avgPrice"],
            "error": row["error"],
            "events": json.loads(row["eventsJson"] or "[]"),
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    def transition(self, order_id: str, to_state: str, *,
                   detail: str = "", **fields: Any) -> dict[str, Any]:
        current = self.get(order_id)
        if not can_transition(current["state"], to_state):
            raise ValueError(f"illegal transition {current['state']} -> {to_state}")
        ticket = fields.get("ticket", current["ticket"])
        filled = _num(fields.get("filled_volume"), current["filledVolume"])
        avg = _num(fields.get("avg_price"), current["avgPrice"])
        error = fields.get("error", current["error"])
        events = list(current["events"])
        events.append({"state": to_state, "at": _now(), "detail": detail})
        self._db.execute(
            "UPDATE QuantOrder SET state=?, ticket=?, filledVolume=?, avgPrice=?, "
            "error=?, eventsJson=?, updatedAt=? WHERE id=?",
            (to_state, ticket, filled, avg, error, json.dumps(events),
             _now(), order_id),
        )
        self._db.commit()
        return self.get(order_id)

    def reconcile(self, order_id: str, broker: dict[str, Any]) -> dict[str, Any]:
        current = self.get(order_id)
        status = str(broker.get("status") or broker.get("retcodeName") or "").upper()
        target = {
            "FILLED": "filled", "DONE": "filled", "FILL": "filled",
            "PLACED": "acknowledged", "PARTIAL": "partial",
            "REJECTED": "rejected", "CANCELLED": "cancelled",
            "CANCELED": "cancelled", "EXPIRED": "expired",
        }.get(status, "unknown")
        if target == "partial" and _num(broker.get("filledVolume")) >= _num(
                current["intent"].get("volume")):
            target = "filled"
        try:
            return self.transition(
                order_id, target, detail=f"broker={status}",
                ticket=broker.get("ticket"),
                filled_volume=broker.get("filledVolume") or broker.get("volume"),
                avg_price=broker.get("avgPrice") or broker.get("price"),
            )
        except ValueError:
            return {**current, "reconcileWarning": f"no legal transition to {target}"}

    def open_orders(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantOrder WHERE state IN "
            "('new','validated','sent','acknowledged','partial','unknown') "
            "ORDER BY createdAt"
        ).fetchall()
        return [self._row(r) for r in rows]

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM QuantOrder ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row(r) for r in rows]


def new_order_key(*parts: Any) -> str:
    return order_key(*parts)


__all__ = ["OrderStore", "new_order_key"]
