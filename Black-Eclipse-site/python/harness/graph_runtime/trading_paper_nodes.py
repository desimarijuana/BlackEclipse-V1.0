"""PAPER execution and book nodes.

Split out of `trading_nodes.py` to keep every trading module small:

- `trading.paper_order` fills an approved order at a supplied reference price,
  applies slippage/commission and records it in the durable PAPER account.
- `trading.paper_account` reads that book (cash, positions, realized PnL).
- `trading.paper_valuation` marks it to prices the graph supplies.

No broker is contacted and nothing here can place a live order. All three run in
PAPER mode only, behind the operator's paper-trading confirmation.
"""

from __future__ import annotations

from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext
from .trading_common import number_input, order_intent, order_price
from .trading_store import claim_guard, release_guard, require_paper_store

_PAPER = (ExecutionMode.PAPER,)


def exec_paper_order(context: NodeExecContext) -> dict[str, Any]:
    intent = order_intent(context)
    decision = context.inputs.get("decision")
    if isinstance(decision, dict) and decision.get("allowed") is False:
        context.emit(f"paper {intent['side']} {intent['symbol']}: rejected by risk")
        return {
            "fill": None,
            "status": "REJECTED",
            "intent": intent,
            "account": None,
            "skipped": False,
            "reasons": list(decision.get("reasons") or []),
        }

    price = order_price(context, intent)
    commission_pct = float(context.config.get("commissionPct", 0.0) or 0)
    slippage_pct = float(context.config.get("slippagePct", 0.0) or 0)
    if commission_pct < 0 or slippage_pct < 0:
        raise ValueError("commissionPct and slippagePct cannot be negative")

    direction = 1.0 if intent["side"] == "buy" else -1.0
    fill_price = price * (1.0 + direction * slippage_pct / 100.0)
    notional = fill_price * float(intent["quantity"])
    commission = abs(notional) * commission_pct / 100.0
    account_id = str(context.config.get("accountId") or "paper").strip()[:80] or "paper"
    persist = bool(context.config.get("persist", True))
    _claimed, _guard_key = claim_guard(context, f"paper:{account_id}")
    if not _claimed:
        context.emit("paper order skipped: this idempotency key was already used")
        return {
            "fill": None,
            "status": "SKIPPED",
            "intent": intent,
            "account": None,
            "skipped": True,
            "reasons": ["this node already filled an order for the same key/period"],
        }
    account = None
    if persist:
        try:
            account = require_paper_store().apply_fill(
                account_id,
                symbol=intent["symbol"],
                side=intent["side"],
                quantity=float(intent["quantity"]),
                price=fill_price,
                commission=commission,
                initial_cash=float(context.config.get("initialCash", 100_000.0)),
                run_id=context.run_id,
                node_id=context.node_id,
            )
        except Exception:
            # A local write failure is not an ambiguous broker send: give the
            # slot back so the next run can retry the fill.
            release_guard(f"paper:{account_id}", _guard_key)
            raise
    fill = {
        "status": "FILLED",
        "mode": "paper",
        "symbol": intent["symbol"],
        "side": intent["side"],
        "quantity": float(intent["quantity"]),
        "referencePrice": price,
        "price": round(fill_price, 8),
        "notional": round(notional, 6),
        "commission": round(commission, 6),
        "slippagePct": slippage_pct,
        "cashDelta": round(-direction * (notional + commission), 6),
        "positionDelta": round(direction * float(intent["quantity"]), 8),
        "accountId": account_id if persist else None,
        "persisted": persist,
        "note": "Simulated paper fill; no broker was contacted and no live order was placed.",
    }
    context.emit(
        f"paper {intent['side']} {intent['quantity']:g} {intent['symbol']} @ {fill['price']}"
    )
    return {
        "fill": fill,
        "status": "FILLED",
        "intent": intent,
        "account": account,
        "skipped": False,
        "reasons": [],
    }


def exec_paper_account(context: NodeExecContext) -> dict[str, Any]:
    """Read the durable PAPER account snapshot (cash, positions, realized PnL)."""
    account_id = str(context.config.get("accountId") or "paper").strip()[:80] or "paper"
    initial_cash = float(context.config.get("initialCash", 100_000.0) or 0)
    account = require_paper_store().snapshot(account_id, initial_cash=initial_cash)
    exists = bool(account.get("createdAt"))
    rows = [
        {
            "symbol": symbol,
            "quantity": item.get("quantity"),
            "averagePrice": item.get("averagePrice"),
        }
        for symbol, item in sorted((account.get("positions") or {}).items())
        if isinstance(item, dict)
    ]
    context.emit(
        f"paper account {account_id}: cash {account['cash']:g}, {len(rows)} position(s)"
    )
    return {
        "account": account,
        "positions": rows,
        "exists": exists,
        "ok": True,
        "reason": "",
    }


def exec_paper_valuation(context: NodeExecContext) -> dict[str, Any]:
    """Mark the PAPER book to a supplied price map (never a fetched guess)."""
    account_id = str(context.config.get("accountId") or "paper").strip()[:80] or "paper"
    initial_cash = float(context.config.get("initialCash", 100_000.0) or 0)
    account = require_paper_store().snapshot(account_id, initial_cash=initial_cash)

    raw_prices = context.inputs.get("prices")
    prices: dict[str, float] = {}
    if isinstance(raw_prices, dict):
        for key, value in raw_prices.items():
            try:
                prices[str(key).strip().upper()] = float(value)
            except (TypeError, ValueError):
                continue
    single = number_input(context, "price")
    symbol = str(context.inputs.get("symbol") or context.config.get("symbol") or "").strip().upper()
    if single is not None and symbol:
        prices[symbol] = single
    if not prices:
        return {
            "valuation": None,
            "equity": None,
            "unrealizedPnl": None,
            "ok": False,
            "reason": (
                "no prices to mark against: wire a symbol→price map on `prices`, or "
                "a symbol with `price`"
            ),
        }

    rows: list[dict[str, Any]] = []
    market_value = 0.0
    unrealized = 0.0
    unpriced: list[str] = []
    for name, item in sorted((account.get("positions") or {}).items()):
        if not isinstance(item, dict):
            continue
        quantity = float(item.get("quantity") or 0)
        average = float(item.get("averagePrice") or 0)
        price = prices.get(str(name).upper())
        row = {
            "symbol": name,
            "quantity": quantity,
            "averagePrice": average,
            "price": price,
        }
        if price is None:
            unpriced.append(str(name))
            row["marketValue"] = None
            row["unrealizedPnl"] = None
        else:
            row["marketValue"] = round(quantity * price, 8)
            row["unrealizedPnl"] = round((price - average) * quantity, 8)
            market_value += quantity * price
            unrealized += (price - average) * quantity
        rows.append(row)

    realized = float(account.get("realizedPnl") or 0)
    equity = float(account.get("cash") or 0) + market_value
    valuation = {
        "accountId": account_id,
        "cash": account.get("cash"),
        "marketValue": round(market_value, 8),
        "equity": round(equity, 8),
        "unrealizedPnl": round(unrealized, 8),
        "realizedPnl": round(realized, 8),
        "totalPnl": round(realized + unrealized, 8),
        "positions": rows,
        "unpriced": unpriced,
        "basis": "supplied prices",
    }
    reason = (
        f"no price for {', '.join(unpriced)}; the book is valued without it"
        if unpriced else ""
    )
    context.emit(f"paper valuation {account_id}: equity {equity:g}")
    return {
        "valuation": valuation,
        "equity": round(equity, 8),
        "unrealizedPnl": round(unrealized, 8),
        "ok": True,
        "reason": reason,
    }


def build_paper_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="trading.paper_order", version="1.0.0", label="Paper order",
            category="trading",
            inputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="price", name="Price", type=PortType.NUMBER, optional=True),
                PortDef(id="decision", name="Risk decision", type=PortType.OBJECT, optional=True),
            ),
            outputs=(
                PortDef(id="fill", name="Fill", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="account", name="Paper account", type=PortType.OBJECT),
                PortDef(id="skipped", name="Skipped (already filled)", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("price", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
                ConfigField("commissionPct", "number", 0.0, minimum=0.0, maximum=10.0),
                ConfigField("slippagePct", "number", 0.0, minimum=0.0, maximum=10.0),
                ConfigField("accountId", "string", "paper", max_length=80),
                ConfigField("persist", "boolean", True),
                ConfigField("initialCash", "number", 100_000.0, minimum=0.0, maximum=1_000_000_000_000),
                ConfigField("dedupe", "enum", "none", enum=("none", "key", "day")),
                ConfigField("idempotencyKey", "string", "", max_length=120),
            ),
            capabilities=("trading.paper",),
            side_effects=SideEffect.TRADING,
            allowed_modes=_PAPER,
            executor=exec_paper_order,
            metadata={
                "docs": (
                    "PAPER-only execution adapter: fills at the supplied price with "
                    "slippage/commission and (by default) records the fill in the durable "
                    "paper account. No broker is contacted and no live order is placed. "
                    "Requires an explicit operator paper-trading grant. `dedupe` "
                    "(none/key/day) claims a guard row before the fill, so a scheduled "
                    "run that fires twice fills once; the second run returns SKIPPED."
                ),
            },
        ),
        NodeDef(
            type="trading.paper_account", version="1.0.0", label="Paper account",
            category="trading",
            outputs=(
                PortDef(id="account", name="Paper account", type=PortType.OBJECT),
                PortDef(id="positions", name="Position rows", type=PortType.ARRAY),
                PortDef(id="exists", name="Has activity", type=PortType.BOOLEAN),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("accountId", "string", "paper", max_length=80),
                ConfigField("initialCash", "number", 100_000.0, minimum=0.0, maximum=1_000_000_000_000),
            ),
            capabilities=("trading.paper",),
            side_effects=SideEffect.READ,
            allowed_modes=_PAPER,
            executor=exec_paper_account,
            metadata={
                "docs": (
                    "Reads the durable PAPER account: cash, positions and average "
                    "cost, realized PnL and book value. `positions` is also emitted "
                    "as rows so it can feed a risk check. `exists` is false until the "
                    "first fill; the hypothetical cash shown then is the configured "
                    "initial cash, not a trade."
                ),
            },
        ),
        NodeDef(
            type="trading.paper_valuation", version="1.0.0", label="Paper valuation",
            category="trading",
            inputs=(
                PortDef(id="prices", name="Prices (symbol → price)", type=PortType.OBJECT, optional=True),
                PortDef(id="price", name="Price", type=PortType.NUMBER, optional=True),
                PortDef(id="symbol", name="Symbol", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="valuation", name="Valuation", type=PortType.OBJECT),
                PortDef(id="equity", name="Equity", type=PortType.NUMBER),
                PortDef(id="unrealizedPnl", name="Unrealized PnL", type=PortType.NUMBER),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("accountId", "string", "paper", max_length=80),
                ConfigField("initialCash", "number", 100_000.0, minimum=0.0, maximum=1_000_000_000_000),
            ),
            capabilities=("trading.paper",),
            side_effects=SideEffect.READ,
            allowed_modes=_PAPER,
            executor=exec_paper_valuation,
            metadata={
                "docs": (
                    "Marks the durable PAPER book to the prices you supply (a "
                    "symbol→price map, or one symbol + price): equity, market value, "
                    "unrealized and total PnL per position. It never fetches a price, "
                    "so a missing symbol is reported in `unpriced` and valued at "
                    "nothing rather than at zero."
                ),
            },
        ),
    ]


__all__ = [
    "build_paper_nodes",
    "exec_paper_order",
    "exec_paper_account",
    "exec_paper_valuation",
]
