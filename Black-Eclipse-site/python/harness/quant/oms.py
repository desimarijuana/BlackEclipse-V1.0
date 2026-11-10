"""Order management state machine.

The OMS is the safety layer between a signal and a broker call. It provides:

- one idempotency key per logical order (strategy + bar + intent);
- an explicit state machine (no silent jumps);
- bracket validation (stop/target on the correct side);
- partial-fill accounting;
- reconciliation against broker state;
- transaction-cost analysis (slippage vs arrival price).

It is pure logic. It never sends an order.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATES = (
    "new", "validated", "sent", "acknowledged", "partial",
    "filled", "rejected", "cancelled", "expired", "unknown",
)
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "new": ("validated", "rejected", "cancelled"),
    "validated": ("sent", "rejected", "cancelled"),
    "sent": ("acknowledged", "filled", "partial", "rejected", "unknown", "cancelled"),
    "acknowledged": ("partial", "filled", "rejected", "cancelled", "expired", "unknown"),
    "partial": ("partial", "filled", "cancelled", "expired", "unknown"),
    "unknown": ("acknowledged", "partial", "filled", "rejected", "cancelled", "expired"),
    "filled": (),
    "rejected": (),
    "cancelled": (),
    "expired": (),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def order_key(*parts: Any) -> str:
    canonical = json.dumps([str(p) for p in parts], separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@dataclass
class OrderRecord:
    id: str
    idempotency_key: str
    intent: dict[str, Any]
    state: str = "new"
    ticket: int | None = None
    filled_volume: float = 0.0
    avg_price: float = 0.0
    error: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "idempotencyKey": self.idempotency_key,
            "intent": self.intent, "state": self.state, "ticket": self.ticket,
            "filledVolume": self.filled_volume, "avgPrice": self.avg_price,
            "error": self.error, "events": self.events,
            "createdAt": self.created_at, "updatedAt": self.updated_at,
        }


class OrderManager:
    def __init__(self) -> None:
        self._orders: dict[str, OrderRecord] = {}
        self._by_key: dict[str, str] = {}

    def create(self, intent: dict[str, Any], *, key: str) -> dict[str, Any]:
        if key in self._by_key:
            return {**self._orders[self._by_key[key]].to_dict(), "duplicate": True}
        record = OrderRecord(
            id=f"oms_{key[:16]}", idempotency_key=key, intent=dict(intent),
        )
        record.events.append({"state": "new", "at": _now()})
        self._orders[record.id] = record
        self._by_key[key] = record.id
        return {**record.to_dict(), "duplicate": False}

    def get(self, order_id: str) -> dict[str, Any]:
        return self._orders[order_id].to_dict()

    def transition(self, order_id: str, to_state: str, *,
                   detail: str = "", **fields: Any) -> dict[str, Any]:
        record = self._orders.get(order_id)
        if record is None:
            raise KeyError(f"order {order_id!r} not found")
        if to_state not in STATES:
            raise ValueError(f"unknown state {to_state!r}")
        if to_state not in _TRANSITIONS[record.state]:
            raise ValueError(
                f"illegal transition {record.state} -> {to_state}"
            )
        for name in ("ticket", "filled_volume", "avg_price", "error"):
            if name in fields:
                setattr(record, name, fields.pop(name))
        record.state = to_state
        record.updated_at = _now()
        record.events.append({"state": to_state, "at": record.updated_at,
                              "detail": detail})
        return record.to_dict()

    def reconcile(self, order_id: str, broker: dict[str, Any]) -> dict[str, Any]:
        """Map a broker order result onto the state machine, without guessing."""
        record = self._orders.get(order_id)
        if record is None:
            raise KeyError(f"order {order_id!r} not found")
        status = str(broker.get("status") or broker.get("retcodeName") or "").upper()
        filled = _num(broker.get("filledVolume") or broker.get("volume"))
        avg = _num(broker.get("avgPrice") or broker.get("price"))
        target = {
            "FILLED": "filled", "DONE": "filled", "FILL": "filled",
            "PLACED": "acknowledged", "PARTIAL": "partial",
            "REJECTED": "rejected", "CANCELLED": "cancelled",
            "CANCELED": "cancelled", "EXPIRED": "expired",
        }.get(status, "unknown")
        if target == "partial" and filled >= _num(record.intent.get("volume")):
            target = "filled"
        try:
            return self.transition(order_id, target,
                                   detail=f"broker={status}",
                                   ticket=broker.get("ticket"),
                                   filled_volume=filled,
                                   avg_price=avg)
        except ValueError:
            return {**record.to_dict(), "reconcileWarning": f"no legal transition to {target}"}

    @staticmethod
    def bracket(intent: dict[str, Any], *, stop_loss: float | None,
                take_profit: float | None) -> dict[str, Any]:
        side = str(intent.get("side") or "").lower()
        price = _num(intent.get("price") or intent.get("entryPrice"))
        out = dict(intent)
        if stop_loss is not None:
            if side == "buy" and price and stop_loss >= price:
                raise ValueError("a buy stop must be below entry")
            if side == "sell" and price and stop_loss <= price:
                raise ValueError("a sell stop must be above entry")
            out["stopLoss"] = float(stop_loss)
        if take_profit is not None:
            if side == "buy" and price and take_profit <= price:
                raise ValueError("a buy target must be above entry")
            if side == "sell" and price and take_profit >= price:
                raise ValueError("a sell target must be below entry")
            out["takeProfit"] = float(take_profit)
        return out

    @staticmethod
    def tca(order: dict[str, Any], arrival_price: float) -> dict[str, Any]:
        side = str((order.get("intent") or {}).get("side") or "").lower()
        fill = _num(order.get("avgPrice"))
        if fill <= 0 or arrival_price <= 0:
            return {"available": False, "reason": "fill and arrival price are required",
                    "slippageBps": None}
        slippage = (fill - arrival_price) if side == "buy" else (arrival_price - fill)
        bps = slippage / arrival_price * 10_000.0
        return {
            "available": True,
            "arrivalPrice": arrival_price,
            "fillPrice": fill,
            "slippage": slippage,
            "slippageBps": bps,
            "adverse": slippage > 0,
        }

    def open_orders(self) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self._orders.values()
                if o.state in ("new", "validated", "sent", "acknowledged",
                               "partial", "unknown")]


def transitions() -> dict[str, list[str]]:
    return {state: list(allowed) for state, allowed in _TRANSITIONS.items()}


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in _TRANSITIONS.get(from_state, ())


__all__ = ["OrderManager", "OrderRecord", "STATES", "can_transition",
           "order_key", "transitions"]
