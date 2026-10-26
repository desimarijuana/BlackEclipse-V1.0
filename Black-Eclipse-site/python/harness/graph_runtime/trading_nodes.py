"""Paper-trading & safety nodes.

Phase 8 adds a PAPER execution adapter on top of the existing quant risk engine:

- `trading.risk_check` is a pure pre-trade gate (no side effect). It may reduce
  an order's size or reject it, always naming the reason.
- `trading.paper_order` is the execution adapter. It fills an approved order at
  a supplied reference price, applies slippage/commission, and returns a paper
  fill. It never contacts a broker and it only runs in PAPER mode behind an
  explicit operator grant.

There is no live adapter. The compiler refuses LIVE mode and refuses any trading
node in a test run; the front door refuses a trading graph unless the operator
explicitly confirms paper trading.
"""

from __future__ import annotations

from typing import Any

from ..quant.risk import RiskContext, RiskEngine
from ..quant.strategy import RiskRules
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_PAPER = (ExecutionMode.PAPER,)
MAX_QUANTITY = 1_000_000_000.0

_paper_store: Any = None


def set_paper_store(store: Any) -> None:
    global _paper_store
    _paper_store = store


def _require_paper_store() -> Any:
    if _paper_store is None:
        raise ValueError("the paper account store is not configured in this runtime")
    return _paper_store


def _intent(context: NodeExecContext) -> dict[str, Any]:
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


def _price(context: NodeExecContext, intent: dict[str, Any]) -> float:
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


def _optional_pct(value: Any) -> float | None:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("risk limits must be numbers (0 disables a limit)") from exc
    return number if number > 0 else None


def _risk_rules(config: dict[str, Any]) -> RiskRules:
    positions = int(config.get("maxOpenPositions", 0) or 0)
    return RiskRules(
        max_position_pct=_optional_pct(config.get("maxPositionPct")),
        max_gross_exposure=_optional_pct(config.get("maxGrossExposure")),
        max_leverage=_optional_pct(config.get("maxLeverage")),
        max_open_positions=positions if positions > 0 else None,
        max_daily_loss_pct=_optional_pct(config.get("maxDailyLossPct")),
        max_risk_per_trade_pct=_optional_pct(config.get("maxRiskPerTradePct")),
        require_stop=bool(config.get("requireStop", False)),
        allow_long=bool(config.get("allowLong", True)),
        allow_short=bool(config.get("allowShort", True)),
    )


def exec_risk_check(context: NodeExecContext) -> dict[str, Any]:
    intent = _intent(context)
    price = _price(context, intent)
    config = context.config
    stop_distance = float(config.get("stopDistance", 0) or 0) or None
    try:
        decision = RiskEngine(_risk_rules(config)).evaluate(RiskContext(
            equity=float(config.get("equity", 100_000.0)),
            side=intent["side"],
            price=price,
            proposed_quantity=float(intent["quantity"]),
            is_opening=bool(config.get("isOpening", True)),
            current_symbol_value=float(config.get("currentSymbolValue", 0.0)),
            gross_exposure=float(config.get("grossExposure", 0.0)),
            open_positions=int(config.get("openPositions", 0)),
            stop_distance=stop_distance,
            has_stop=bool(config.get("hasStop", False)) or stop_distance is not None,
            daily_pnl=float(config.get("dailyPnl", 0.0)),
            daily_start_equity=float(config.get("dailyStartEquity", 0.0)) or None,
        ))
    except Exception as exc:  # noqa: BLE001 - a bad limit is a node data error
        raise ValueError(f"risk check failed: {exc}") from exc

    adjusted = dict(intent)
    adjusted["quantity"] = decision.quantity if decision.allowed else 0.0
    adjusted["price"] = price
    context.emit(
        f"risk {intent['side']} {intent['symbol']}: "
        + ("approved" if decision.allowed else "rejected")
    )
    return {
        "intent": adjusted,
        "decision": decision.to_dict(),
        "approved": decision.allowed,
    }


def exec_paper_order(context: NodeExecContext) -> dict[str, Any]:
    intent = _intent(context)
    decision = context.inputs.get("decision")
    if isinstance(decision, dict) and decision.get("allowed") is False:
        context.emit(f"paper {intent['side']} {intent['symbol']}: rejected by risk")
        return {
            "fill": None,
            "status": "REJECTED",
            "intent": intent,
            "account": None,
            "reasons": list(decision.get("reasons") or []),
        }

    price = _price(context, intent)
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
    account = None
    if persist:
        account = _require_paper_store().apply_fill(
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
        "reasons": [],
    }


def build_trading_nodes() -> list[NodeDef]:
    risk_fields = (
        ConfigField("equity", "number", 100_000.0, minimum=1.0, maximum=1_000_000_000_000),
        ConfigField("price", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
        ConfigField("currentSymbolValue", "number", 0.0, minimum=-1_000_000_000_000, maximum=1_000_000_000_000),
        ConfigField("grossExposure", "number", 0.0, minimum=0.0, maximum=1_000_000_000_000),
        ConfigField("openPositions", "integer", 0, minimum=0, maximum=10_000),
        ConfigField("stopDistance", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
        ConfigField("hasStop", "boolean", False),
        ConfigField("isOpening", "boolean", True),
        ConfigField("dailyPnl", "number", 0.0, minimum=-1_000_000_000_000, maximum=1_000_000_000_000),
        ConfigField("dailyStartEquity", "number", 0.0, minimum=0.0, maximum=1_000_000_000_000),
        ConfigField("maxPositionPct", "number", 0.0, minimum=0.0, maximum=100.0),
        ConfigField("maxGrossExposure", "number", 0.0, minimum=0.0, maximum=100.0),
        ConfigField("maxLeverage", "number", 0.0, minimum=0.0, maximum=100.0),
        ConfigField("maxOpenPositions", "integer", 0, minimum=0, maximum=1_000),
        ConfigField("maxDailyLossPct", "number", 0.0, minimum=0.0, maximum=100.0),
        ConfigField("maxRiskPerTradePct", "number", 0.0, minimum=0.0, maximum=100.0),
        ConfigField("requireStop", "boolean", False),
        ConfigField("allowLong", "boolean", True),
        ConfigField("allowShort", "boolean", True),
    )
    return [
        NodeDef(
            type="trading.risk_check", version="1.0.0", label="Risk check",
            category="trading",
            inputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="price", name="Price", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="decision", name="Decision", type=PortType.OBJECT),
                PortDef(id="approved", name="Approved", type=PortType.BOOLEAN),
            ),
            config_fields=risk_fields,
            capabilities=("trading.risk",),
            side_effects=SideEffect.NONE,
            allowed_modes=_PAPER,
            executor=exec_risk_check,
            metadata={
                "docs": (
                    "Pure pre-trade gate over harness/quant/risk.py. A limit of 0 "
                    "disables that limit. A rejection is an outcome, not an error."
                ),
            },
        ),
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
            ),
            config_fields=(
                ConfigField("price", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
                ConfigField("commissionPct", "number", 0.0, minimum=0.0, maximum=10.0),
                ConfigField("slippagePct", "number", 0.0, minimum=0.0, maximum=10.0),
                ConfigField("accountId", "string", "paper", max_length=80),
                ConfigField("persist", "boolean", True),
                ConfigField("initialCash", "number", 100_000.0, minimum=0.0, maximum=1_000_000_000_000),
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
                    "Requires an explicit operator paper-trading grant."
                ),
            },
        ),
    ]


__all__ = [
    "build_trading_nodes",
    "set_paper_store",
    "exec_risk_check",
    "exec_paper_order",
]
