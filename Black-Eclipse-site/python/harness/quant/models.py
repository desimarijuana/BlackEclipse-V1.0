"""Core value types for the quant engine.

These are the engine's internal, deterministic records — orders, fills,
positions, closed trades — plus the order state machine. They are plain
dataclasses (cheap to construct in the hot loop) and each serializes to a JSON
safe dict. The *external* contracts (strategy spec, backtest result envelope)
live in `strategy.py` / `engine.py` as pydantic models; these types are the
substrate those are built from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ── Vocabularies ─────────────────────────────────────────────────────────────

OrderSide = Literal["buy", "sell"]
OrderType = Literal[
    "market", "limit", "stop", "stop_limit", "take_profit", "stop_loss", "trailing_stop"
]
OrderStatus = Literal[
    "created", "submitted", "accepted", "partially_filled",
    "filled", "cancelled", "rejected", "expired",
]
TimeInForce = Literal["day", "gtc", "ioc", "fok"]
PositionSide = Literal["long", "short", "flat"]

# The legal order-state graph. Anything outside it is refused (never silently
# allowed). `filled`, `cancelled`, `rejected`, `expired` are terminal.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"submitted", "rejected", "cancelled", "expired"},
    "submitted": {"accepted", "rejected", "cancelled", "expired", "partially_filled", "filled"},
    "accepted": {"partially_filled", "filled", "cancelled", "rejected", "expired"},
    "partially_filled": {"partially_filled", "filled", "cancelled", "expired"},
    "filled": set(),
    "cancelled": set(),
    "rejected": set(),
    "expired": set(),
}

TERMINAL_STATUSES = frozenset({"filled", "cancelled", "rejected", "expired"})


def transition_allowed(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


# ── Records ──────────────────────────────────────────────────────────────────

@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: float
    status: OrderStatus = "created"
    created_index: int = -1
    created_ts: Optional[str] = None
    submitted_index: Optional[int] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_amount: Optional[float] = None
    trail_percent: Optional[float] = None
    time_in_force: TimeInForce = "gtc"
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    commission: float = 0.0
    # Bracket bookkeeping: the entry order a protective leg belongs to.
    parent_id: Optional[str] = None
    # Why the order exists / ended (for auditability).
    tag: str = ""
    reason: str = ""
    # The active stop price for a trailing stop (updated as price moves).
    current_stop: Optional[float] = None

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    @property
    def is_open(self) -> bool:
        return self.status not in TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "symbol": self.symbol, "side": self.side, "type": self.type,
            "quantity": self.quantity, "status": self.status, "tag": self.tag,
            "limitPrice": self.limit_price, "stopPrice": self.stop_price,
            "filledQuantity": self.filled_quantity, "avgFillPrice": self.avg_fill_price,
            "commission": self.commission, "createdIndex": self.created_index,
            "createdTs": self.created_ts, "parentId": self.parent_id, "reason": self.reason,
        }


@dataclass
class Fill:
    id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    slippage: float
    spread_cost: float
    impact: float
    index: int
    ts: Optional[str]
    reason: str = ""

    @property
    def notional(self) -> float:
        return self.price * self.quantity

    @property
    def total_cost(self) -> float:
        return self.commission + self.slippage + self.spread_cost + self.impact

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "orderId": self.order_id, "symbol": self.symbol, "side": self.side,
            "quantity": self.quantity, "price": self.price, "commission": self.commission,
            "slippage": self.slippage, "spreadCost": self.spread_cost, "impact": self.impact,
            "index": self.index, "ts": self.ts, "notional": self.notional, "reason": self.reason,
        }


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0            # signed: + long, - short
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    commission_paid: float = 0.0
    last_price: Optional[float] = None
    entry_index: Optional[int] = None
    entry_ts: Optional[str] = None
    # Running excursions, recorded against the bar close while open.
    mae: Optional[float] = None
    mfe: Optional[float] = None

    @property
    def side(self) -> PositionSide:
        if self.quantity > 0:
            return "long"
        if self.quantity < 0:
            return "short"
        return "flat"

    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-12

    def market_value(self, price: Optional[float] = None) -> float:
        px = price if price is not None else self.last_price
        if px is None:
            return 0.0
        return self.quantity * px

    def unrealized_pnl(self, price: Optional[float] = None) -> float:
        px = price if price is not None else self.last_price
        if px is None or self.is_flat:
            return 0.0
        return (px - self.avg_entry_price) * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "quantity": self.quantity, "side": self.side,
            "avgEntryPrice": self.avg_entry_price, "lastPrice": self.last_price,
            "marketValue": self.market_value(), "realizedPnl": self.realized_pnl,
            "unrealizedPnl": self.unrealized_pnl(), "commissionPaid": self.commission_paid,
            "entryIndex": self.entry_index, "entryTs": self.entry_ts,
        }


@dataclass
class TradeRecord:
    """One completed round-trip (a position opened then returned to flat)."""

    id: str
    symbol: str
    direction: PositionSide
    entry_ts: Optional[str]
    exit_ts: Optional[str]
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    commission: float
    bars_held: int
    pnl_pct: float
    exit_reason: str = ""
    mae: Optional[float] = None    # max adverse excursion (price)
    mfe: Optional[float] = None    # max favourable excursion (price)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "symbol": self.symbol, "direction": self.direction,
            "entryTs": self.entry_ts, "exitTs": self.exit_ts, "entryPrice": self.entry_price,
            "exitPrice": self.exit_price, "quantity": self.quantity, "grossPnl": self.gross_pnl,
            "netPnl": self.net_pnl, "commission": self.commission, "barsHeld": self.bars_held,
            "pnlPct": self.pnl_pct, "exitReason": self.exit_reason, "mae": self.mae, "mfe": self.mfe,
        }


@dataclass
class EquityPoint:
    index: int
    ts: Optional[str]
    equity: float
    cash: float
    positions_value: float
    gross_exposure: float
    net_exposure: float
    leverage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "ts": self.ts, "equity": self.equity, "cash": self.cash,
            "positionsValue": self.positions_value, "grossExposure": self.gross_exposure,
            "netExposure": self.net_exposure, "leverage": self.leverage,
        }


@dataclass
class Warning_:
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "EquityPoint",
    "Fill",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "TimeInForce",
    "TradeRecord",
    "Warning_",
    "transition_allowed",
]
