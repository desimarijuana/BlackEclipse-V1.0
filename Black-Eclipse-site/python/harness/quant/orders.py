"""Order engine — order lifecycle with an enforced state machine.

Every state change goes through `_transition`, which refuses an illegal move
(e.g. filling a cancelled order). Orders are cheap dataclasses; ids are
deterministic (`ord_000001`) so a curated dataset produces a reproducible order
ledger. The engine never silently drops an order: a rejected/expired order keeps
its reason for audit.
"""

from __future__ import annotations

from typing import Optional

from .errors import IllegalOrderTransition, InvalidOrder
from .models import (
    TERMINAL_STATUSES,
    Order,
    OrderSide,
    OrderType,
    TimeInForce,
    transition_allowed,
)


class OrderEngine:
    def __init__(self, *, id_prefix: str = "ord") -> None:
        self._orders: list[Order] = []
        self._by_id: dict[str, Order] = {}
        self._seq = 0
        self._id_prefix = id_prefix

    # ── Creation ─────────────────────────────────────────────────────────────
    def create(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,  # noqa: A002 - matches the domain vocabulary
        quantity: float,
        *,
        index: int = -1,
        ts: Optional[str] = None,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        trail_amount: Optional[float] = None,
        trail_percent: Optional[float] = None,
        time_in_force: TimeInForce = "gtc",
        tag: str = "",
        reason: str = "",
        parent_id: Optional[str] = None,
    ) -> Order:
        if side not in ("buy", "sell"):
            raise InvalidOrder(f"invalid order side {side!r}")
        if quantity is None or quantity <= 0:
            raise InvalidOrder("order quantity must be > 0", detail={"quantity": quantity})
        if type in ("limit", "stop_limit") and limit_price is None:
            raise InvalidOrder(f"{type} order requires limit_price")
        if type in ("stop", "stop_limit", "stop_loss", "take_profit") and stop_price is None:
            raise InvalidOrder(f"{type} order requires stop_price")
        if type == "trailing_stop" and trail_amount is None and trail_percent is None:
            raise InvalidOrder("trailing_stop requires trail_amount or trail_percent")
        self._seq += 1
        order = Order(
            id=f"{self._id_prefix}_{self._seq:06d}",
            symbol=symbol, side=side, type=type, quantity=float(quantity),
            created_index=index, created_ts=ts, limit_price=limit_price,
            stop_price=stop_price, trail_amount=trail_amount, trail_percent=trail_percent,
            time_in_force=time_in_force, tag=tag, reason=reason, parent_id=parent_id,
            current_stop=stop_price,
        )
        self._orders.append(order)
        self._by_id[order.id] = order
        return order

    # ── Lifecycle ────────────────────────────────────────────────────────────
    def _transition(self, order: Order, target: str, *, reason: str = "") -> None:
        if not transition_allowed(order.status, target):
            raise IllegalOrderTransition(
                f"cannot move order {order.id} from {order.status!r} to {target!r}",
                detail={"orderId": order.id, "from": order.status, "to": target},
            )
        order.status = target  # type: ignore[assignment]
        if reason:
            order.reason = reason

    def submit(self, order: Order, index: int) -> None:
        self._transition(order, "submitted")
        order.submitted_index = index

    def accept(self, order: Order, index: int) -> None:
        self._transition(order, "accepted")

    def reject(self, order: Order, reason: str) -> None:
        self._transition(order, "rejected", reason=reason)

    def cancel(self, order: Order, index: int, reason: str = "cancelled") -> None:
        self._transition(order, "cancelled", reason=reason)

    def expire(self, order: Order, reason: str = "expired") -> None:
        self._transition(order, "expired", reason=reason)

    def apply_fill(self, order: Order, quantity: float, price: float, commission: float) -> None:
        """Book a (partial or full) fill. Updates avg price + status atomically."""
        if order.status in TERMINAL_STATUSES:
            raise IllegalOrderTransition(
                f"cannot fill order {order.id} in terminal state {order.status!r}",
                detail={"orderId": order.id, "status": order.status},
            )
        if quantity <= 0 or quantity > order.remaining + 1e-9:
            raise InvalidOrder(
                f"fill quantity {quantity} exceeds order remaining {order.remaining}",
                detail={"orderId": order.id, "quantity": quantity, "remaining": order.remaining},
            )
        prior_notional = (order.avg_fill_price or 0.0) * order.filled_quantity
        order.filled_quantity += quantity
        order.avg_fill_price = (prior_notional + price * quantity) / order.filled_quantity
        order.commission += commission
        target = "filled" if order.remaining <= 1e-9 else "partially_filled"
        self._transition(order, target)

    # ── Queries ──────────────────────────────────────────────────────────────
    def open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        return [
            o for o in self._orders
            if o.is_open and (symbol is None or o.symbol == symbol)
        ]

    def orders_for(self, symbol: Optional[str] = None) -> list[Order]:
        return [o for o in self._orders if symbol is None or o.symbol == symbol]

    def all_orders(self) -> list[Order]:
        return list(self._orders)

    def get(self, order_id: str) -> Optional[Order]:
        return self._by_id.get(order_id)

    @property
    def count(self) -> int:
        return len(self._orders)

    def cancel_all(self, symbol: Optional[str] = None, *, index: int = -1,
                   reason: str = "cancelled") -> int:
        n = 0
        for order in self.open_orders(symbol):
            self.cancel(order, index, reason)
            n += 1
        return n


__all__ = ["OrderEngine"]
