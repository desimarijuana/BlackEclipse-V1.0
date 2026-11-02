"""The order-intent shape shared by every trading executor.

`order_intent`, `order_price` and `number_input` were private helpers inside
`trading_nodes.py`; they live here so the paper, broker and preview modules can
share one implementation without importing each other.
"""

from __future__ import annotations

from typing import Any

from .registry import NodeExecContext

MAX_QUANTITY = 1_000_000_000.0


def order_intent(context: NodeExecContext) -> dict[str, Any]:
    """Normalize and validate the `intent` input (symbol / side / quantity)."""
    raw = context.inputs.get("intent")
    if not isinstance(raw, dict):
        raise ValueError("an order intent is required on the intent input")
    symbol = str(raw.get("symbol") or "").strip().upper()
    side = str(raw.get("side") or "").strip().lower()
    if not symbol:
        raise ValueError("the order intent needs a symbol")
    if side not in ("buy", "sell"):
        raise ValueError("the order intent side must be buy or sell")
    try:
        quantity = float(raw.get("quantity"))
    except (TypeError, ValueError) as exc:
        raise ValueError("the order intent quantity must be a number") from exc
    if not 0 < quantity <= MAX_QUANTITY:
        raise ValueError(f"the order intent quantity must be in (0, {MAX_QUANTITY:g}]")
    out = dict(raw)
    out.update({"symbol": symbol, "side": side, "quantity": quantity})
    return out


def order_price(context: NodeExecContext, intent: dict[str, Any]) -> float:
    """The reference price: wired input, node config, then the intent itself."""
    raw = context.inputs.get("price", context.config.get("price"))
    if raw is None:
        raw = intent.get("price")
    try:
        price = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("price is required: wire a quote/number in or set the node's price") from exc
    if price <= 0:
        raise ValueError("price must be greater than zero")
    return price


def number_input(context: NodeExecContext, handle: str) -> float | None:
    """A wired number, or None. A non-numeric wire is a node data error."""
    raw = context.inputs.get(handle)
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise ValueError(f"{handle} must be a number, not a boolean")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{handle} must be a number") from exc


__all__ = ["MAX_QUANTITY", "number_input", "order_intent", "order_price"]
