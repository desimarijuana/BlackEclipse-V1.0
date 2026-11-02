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
from ..persistence import now_iso
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_PAPER = (ExecutionMode.PAPER,)
_BROKER = (ExecutionMode.PAPER, ExecutionMode.LIVE)
# A risk check has no side effect, so it is meaningful in a backtest too: the
# same limits that gate a live order should gate a simulated one.
_RISK = tuple(ExecutionMode)
_ALL_MODES = tuple(ExecutionMode)
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


def _claim_guard(context: NodeExecContext, scope: str) -> bool:
    """Claim this node's idempotency slot, or False when it was already used.

    `dedupe: none` (the default) sends every run. `key` uses the node's
    `idempotencyKey`; `day` uses the node id plus the UTC date. The claim happens
    BEFORE the send, so an ambiguous failure is never automatically repeated.
    """
    mode = str(context.config.get("dedupe") or "none").strip().lower()
    if mode == "none":
        return True
    if mode == "key":
        key = str(context.config.get("idempotencyKey") or "").strip()
        if not key:
            raise ValueError("dedupe 'key' needs a non-empty idempotencyKey")
        suffix = f"key:{key}"
    elif mode == "day":
        suffix = f"day:{now_iso()[:10]}:{context.node_id}"
    else:
        raise ValueError("dedupe must be none, key or day")
    return _require_paper_store().claim_guard(scope, suffix)


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


def _number_input(context: NodeExecContext, handle: str) -> float | None:
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


def _account_payload(raw: Any) -> dict[str, Any]:
    """Accept a service read envelope (`data`) or a bare account snapshot."""
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    body = data if isinstance(data, dict) else raw
    return body if isinstance(body, dict) else {}


def _position_rows(raw: Any) -> list[dict[str, Any]]:
    """Accept a list, a service envelope, or an object holding either."""
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        for key in ("data", "positions", "rows", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _first_number(source: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def exec_risk_check(context: NodeExecContext) -> dict[str, Any]:
    intent = _intent(context)
    price = _price(context, intent)
    config = context.config
    account = _account_payload(context.inputs.get("account"))
    positions_wired = context.inputs.get("positions") is not None
    positions = _position_rows(context.inputs.get("positions"))

    # Every figure the engine reads is either wired, derived from the broker's
    # own account/positions, or typed into config. The `state` map records which,
    # so a gate cannot silently run on a stale number.
    state: dict[str, dict[str, Any]] = {}

    def resolve(
        name: str,
        default: float,
        derived: tuple[str, float | None] | None = None,
    ) -> float:
        wired = _number_input(context, name)
        if wired is not None:
            state[name] = {"value": wired, "source": "input"}
            return wired
        if derived is not None and derived[1] is not None:
            state[name] = {"value": float(derived[1]), "source": derived[0]}
            return float(derived[1])
        value = float(config.get(name, default) or 0.0)
        state[name] = {"value": value, "source": "config"}
        return value

    equity = resolve(
        "equity", 100_000.0,
        ("account", _first_number(account, "equity", "balance", "bookValue")),
    )
    if equity <= 0:
        raise ValueError("equity must be greater than zero")
    open_positions = int(resolve(
        "openPositions", 0,
        ("positions", float(len(positions)) if positions_wired else None),
    ))
    gross_exposure = resolve("grossExposure", 0.0)
    current_symbol_value = resolve("currentSymbolValue", 0.0)
    daily_pnl = resolve("dailyPnl", 0.0)
    daily_start_equity = float(config.get("dailyStartEquity", 0.0) or 0.0) or None

    stop_distance = float(config.get("stopDistance", 0) or 0) or None
    try:
        decision = RiskEngine(_risk_rules(config)).evaluate(RiskContext(
            equity=equity,
            side=intent["side"],
            price=price,
            proposed_quantity=float(intent["quantity"]),
            is_opening=bool(config.get("isOpening", True)),
            current_symbol_value=current_symbol_value,
            gross_exposure=gross_exposure,
            open_positions=open_positions,
            stop_distance=stop_distance,
            has_stop=bool(config.get("hasStop", False)) or stop_distance is not None,
            daily_pnl=daily_pnl,
            daily_start_equity=daily_start_equity,
        ))
    except Exception as exc:  # noqa: BLE001 - a bad limit is a node data error
        raise ValueError(f"risk check failed: {exc}") from exc

    adjusted = dict(intent)
    adjusted["quantity"] = decision.quantity if decision.allowed else 0.0
    adjusted["price"] = price
    equity_source = state["equity"]["source"]
    context.emit(
        f"risk {intent['side']} {intent['symbol']}: "
        + ("approved" if decision.allowed else "rejected")
        + f" (equity {equity:g} from {equity_source})"
    )
    return {
        "intent": adjusted,
        "decision": decision.to_dict(),
        "approved": decision.allowed,
        "state": state,
    }


def exec_broker_order(context: NodeExecContext) -> dict[str, Any]:
    """Submit ONE demo order through the broker service under a bounded mandate.

    The graph is unattended, so there is no per-order approval card. The
    operator-created mandate is the authorization; the broker service still
    applies the connection's policy, the money guardrails and the demo-account
    check, and consumes one mandate use atomically.

    An optional `decision` wire is honored when present: a rejected risk check
    stops the order here, so wiring the gate to the intent alone can never send
    an order the gate refused.
    """
    intent = _intent(context)
    if bool(context.config.get("dryRun")):
        # A dry run is the preview path: broker order_check + policy +
        # guardrails, no send and no approval row.
        preview = exec_order_preview(context)
        return {
            "result": preview["result"],
            "status": "PREVIEW_ALLOWED" if preview["allowed"] else "PREVIEW_REFUSED",
            "orderId": "",
            "ok": preview["allowed"],
            "skipped": False,
            "reason": preview["reason"],
        }
    decision = context.inputs.get("decision")
    if isinstance(decision, dict) and decision.get("allowed") is False:
        reasons = [str(reason) for reason in (decision.get("reasons") or [])]
        context.emit(
            f"broker order rejected by risk: {'; '.join(reasons) or 'risk not allowed'}"
        )
        return {
            "result": {"status": "REJECTED", "sent": False, "reasons": reasons},
            "status": "REJECTED",
            "orderId": "",
            "ok": False,
            "skipped": False,
            "reason": "; ".join(reasons) or "risk decision not allowed",
        }
    connection_id = str(context.config.get("connectionId") or "").strip()
    mandate_id = str(context.config.get("mandateId") or "").strip()
    if not connection_id:
        raise ValueError("connectionId is required for a broker order")
    if not mandate_id:
        raise ValueError(
            "a mandateId is required for an unattended broker order; create one in "
            "Settings › Trading"
        )
    if not _claim_guard(context, f"broker:{connection_id}"):
        context.emit("broker order skipped: this idempotency key was already used")
        return {
            "result": {"status": "SKIPPED", "sent": False},
            "status": "SKIPPED",
            "orderId": "",
            "ok": False,
            "skipped": True,
            "reason": "this node already sent an order for the same key/period",
        }
    from ..trade.bootstrap import get_service  # noqa: PLC0415 - avoids an import cycle

    service = get_service()
    if service is None:
        raise ValueError("broker connectivity is unavailable in this runtime")

    payload = dict(intent)
    if "volume" not in payload:
        payload["volume"] = payload.get("quantity")
    if "type" not in payload and "orderType" not in payload:
        payload["type"] = "market"
    result = service.submit_order(
        connection_id,
        payload,
        mandate_id=mandate_id,
        run_id=context.run_id,
        workflow_id=getattr(context, "workflow_id", ""),
        node_id=context.node_id,
    )
    status = str(result.get("status") or "UNKNOWN")
    reasons = [str(reason) for reason in (result.get("reasons") or [])]
    ok = status in ("filled", "placed")
    if status in ("filled", "placed", "unknown"):
        context.emit(f"broker order {status} ({result.get('orderId')})")
    else:
        context.emit(f"broker order {status}: {'; '.join(reasons) or status}")
    return {
        "result": result,
        "status": status,
        "orderId": str(result.get("orderId") or ""),
        "ok": ok,
        "skipped": False,
        "reason": "" if ok else ("; ".join(reasons) or status),
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
            "skipped": False,
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
    if not _claim_guard(context, f"paper:{account_id}"):
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
        "skipped": False,
        "reasons": [],
    }


def _input_or_config(
    context: NodeExecContext, handle: str, config_key: str | None = None,
) -> Any:
    raw = context.inputs.get(handle)
    if raw is None or raw == "":
        raw = context.config.get(config_key or handle)
    return raw


def _positive_number(raw: Any, label: str) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return value


_ORDER_TYPES = ("market", "limit", "stop")
_TIME_IN_FORCE = ("gtc", "day")


def exec_order_intent(context: NodeExecContext) -> dict[str, Any]:
    """Build ONE validated order intent from ports/config.

    This is the canonical shape both execution adapters read, so a graph never
    has to hand-assemble a JSON object: the builder normalizes the symbol and
    side, checks that a pending order carries a price, and emits `quantity` and
    `volume` (the paper adapter reads the first, the broker adapter accepts
    either). Nothing is submitted.
    """
    symbol = str(_input_or_config(context, "symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("the order intent needs a symbol (wire the port or set it on the node)")
    side = str(_input_or_config(context, "side") or "").strip().lower()
    if side not in ("buy", "sell"):
        raise ValueError("the order intent side must be buy or sell")
    order_type = str(_input_or_config(context, "orderType") or "market").strip().lower()
    if order_type not in _ORDER_TYPES:
        raise ValueError("orderType must be market, limit or stop")
    time_in_force = str(_input_or_config(context, "timeInForce") or "gtc").strip().lower()
    if time_in_force not in _TIME_IN_FORCE:
        raise ValueError("timeInForce must be gtc or day")
    quantity = _positive_number(_input_or_config(context, "quantity"), "quantity")
    if quantity is None:
        raise ValueError("the order intent needs a positive quantity")
    if quantity > MAX_QUANTITY:
        raise ValueError(f"quantity must be at most {MAX_QUANTITY:g}")
    price = _positive_number(_input_or_config(context, "price"), "price")
    if order_type in ("limit", "stop") and price is None:
        raise ValueError(f"a {order_type} order needs a positive price")
    stop_loss = _positive_number(_input_or_config(context, "stopLoss"), "stopLoss")
    take_profit = _positive_number(_input_or_config(context, "takeProfit"), "takeProfit")

    intent: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "volume": quantity,
        "type": order_type,
        "orderType": order_type,
        "timeInForce": time_in_force,
    }
    if order_type != "market" and price is not None:
        intent["price"] = price
    if stop_loss is not None:
        intent["stopLoss"] = stop_loss
    if take_profit is not None:
        intent["takeProfit"] = take_profit
    context.emit(
        f"intent {side} {quantity:g} {symbol} ({order_type})"
        + (f" @ {price:g}" if price is not None else "")
    )
    return {"intent": intent, "ok": True, "reason": ""}


def exec_order_preview(context: NodeExecContext) -> dict[str, Any]:
    """Ask the broker + policy + guardrails whether an order would be allowed.

    Nothing is sent and NO approval is created: this is the safe way to dry-run a
    workflow. With a `mandateId` the mandate's scope is also checked (verify does
    not consume a use), so a graph can confirm it would fit before it arms.
    """
    try:
        intent = _intent(context)
    except ValueError as exc:
        # An unusable intent (missing symbol, zero quantity after a rejected risk
        # check) is an outcome here, not an exception: nothing was sent.
        return {
            "result": {"status": "INVALID_INTENT", "reasons": [str(exc)]},
            "allowed": False,
            "ok": False,
            "reason": str(exc),
        }
    connection_id = str(context.config.get("connectionId") or "").strip()
    if not connection_id:
        raise ValueError("connectionId is required for an order preview")
    mandate_id = str(context.config.get("mandateId") or "").strip()
    from ..trade.bootstrap import get_service  # noqa: PLC0415 - avoids an import cycle
    from ..trade.model import TradeRefused  # noqa: PLC0415 - avoids an import cycle

    service = get_service()
    if service is None:
        raise ValueError("broker connectivity is unavailable in this runtime")
    payload = dict(intent)
    if "volume" not in payload:
        payload["volume"] = payload.get("quantity")
    if "type" not in payload and "orderType" not in payload:
        payload["type"] = "market"
    try:
        result = service.preview_order(connection_id, payload, record_approval=False)
    except TradeRefused as exc:
        result = {
            "available": False,
            "allowed": False,
            "status": exc.code,
            "error": exc.to_dict(),
            "reasons": [exc.message],
        }

    allowed = bool(result.get("allowed"))
    reasons = [str(reason) for reason in (result.get("reasons") or [])]
    if mandate_id and result.get("available"):
        try:
            service.mandates.verify(
                mandate_id,
                connection_id=str(result.get("connectionId") or connection_id),
                symbol=str(intent["symbol"]),
                margin=float((result.get("preview") or {}).get("margin") or 0),
                mode=str(result.get("mode") or ""),
                workflow_id=getattr(context, "workflow_id", ""),
            )
        except TradeRefused as exc:
            allowed = False
            reasons.append(exc.message)

    ok = bool(result.get("available"))
    reason = "" if allowed else ("; ".join(reasons) or str(result.get("status") or ""))
    context.emit(
        f"preview {intent['side']} {intent['symbol']}: "
        + ("would be allowed" if allowed else f"would be refused ({reason})")
    )
    return {"result": result, "allowed": allowed, "ok": ok, "reason": reason}


def exec_paper_account(context: NodeExecContext) -> dict[str, Any]:
    """Read the durable PAPER account snapshot (cash, positions, realized PnL)."""
    account_id = str(context.config.get("accountId") or "paper").strip()[:80] or "paper"
    initial_cash = float(context.config.get("initialCash", 100_000.0) or 0)
    store = _require_paper_store()
    account = store.snapshot(account_id, initial_cash=initial_cash)
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
    store = _require_paper_store()
    account = store.snapshot(account_id, initial_cash=initial_cash)

    raw_prices = context.inputs.get("prices")
    prices: dict[str, float] = {}
    if isinstance(raw_prices, dict):
        for key, value in raw_prices.items():
            try:
                prices[str(key).strip().upper()] = float(value)
            except (TypeError, ValueError):
                continue
    single = _number_input(context, "price")
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
    nodes = [
        NodeDef(
            type="trading.risk_check", version="1.0.0", label="Risk check",
            category="trading",
            inputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="price", name="Price", type=PortType.NUMBER, optional=True),
                PortDef(id="account", name="Broker/paper account", type=PortType.OBJECT, optional=True),
                PortDef(id="positions", name="Open positions", type=PortType.ARRAY, optional=True),
                PortDef(id="equity", name="Equity", type=PortType.NUMBER, optional=True),
                PortDef(id="grossExposure", name="Gross exposure", type=PortType.NUMBER, optional=True),
                PortDef(id="openPositions", name="Open positions", type=PortType.NUMBER, optional=True),
                PortDef(id="dailyPnl", name="Daily P&L", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="decision", name="Decision", type=PortType.OBJECT),
                PortDef(id="approved", name="Approved", type=PortType.BOOLEAN),
                PortDef(id="state", name="Risk state & sources", type=PortType.OBJECT),
            ),
            config_fields=risk_fields,
            capabilities=("trading.risk",),
            side_effects=SideEffect.NONE,
            allowed_modes=_RISK,
            executor=exec_risk_check,
            metadata={
                "docs": (
                    "Pure pre-trade gate over harness/quant/risk.py. A limit of 0 "
                    "disables that limit. A rejection is an outcome, not an error. "
                    "Equity and open-position count are derived from a wired "
                    "account/positions when available, and the `state` output names "
                    "the source of every figure (input, account, positions, config). "
                    "Gross exposure and per-symbol value stay explicit because a "
                    "position list carries lots, not notional."
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
        NodeDef(
            type="trading.broker_order", version="1.0.0",
            label="Broker order",
            category="trading",
            inputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="decision", name="Risk decision", type=PortType.OBJECT, optional=True),
            ),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
                PortDef(id="orderId", name="Order id", type=PortType.STRING),
                PortDef(id="ok", name="Sent", type=PortType.BOOLEAN),
                PortDef(id="skipped", name="Skipped (already sent)", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("connectionId", "string", "", max_length=80),
                ConfigField("mandateId", "string", "", max_length=80),
                ConfigField("dryRun", "boolean", False),
                ConfigField("dedupe", "enum", "none", enum=("none", "key", "day")),
                ConfigField("idempotencyKey", "string", "", max_length=120),
            ),
            capabilities=("trading.broker",),
            side_effects=SideEffect.TRADING,
            allowed_modes=_BROKER,
            timeout_ms=45_000,
            executor=exec_broker_order,
            metadata={
                "docs": (
                    "Submits ONE order to a DEMO broker connection under an operator-"
                    "created, bounded, revocable mandate. No per-order approval card: "
                    "the mandate is the authorization. The connection must be demo; "
                    "live trading nodes are refused by the compiler. The broker service "
                    "still applies policy, money guardrails and the account-mode check, "
                    "and consumes one mandate use atomically. A rejected risk `decision` "
                    "wire stops the order before it reaches the broker; `ok` is true "
                    "only for a filled or placed order. With `dryRun` it runs the "
                    "preview instead: nothing is sent, no approval is created, and "
                    "`ok` means the order WOULD be allowed."
                ),
            },
        ),
        NodeDef(
            type="trading.order_intent", version="1.0.0", label="Order intent",
            category="trading",
            inputs=(
                PortDef(id="symbol", name="Symbol", type=PortType.STRING, optional=True),
                PortDef(id="side", name="Side", type=PortType.STRING, optional=True),
                PortDef(id="quantity", name="Quantity", type=PortType.NUMBER, optional=True),
                PortDef(id="price", name="Order price", type=PortType.NUMBER, optional=True),
                PortDef(id="stopLoss", name="Stop loss", type=PortType.NUMBER, optional=True),
                PortDef(id="takeProfit", name="Take profit", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("side", "enum", "buy", enum=("buy", "sell")),
                ConfigField("orderType", "enum", "market", enum=_ORDER_TYPES),
                ConfigField("quantity", "number", 0.0, minimum=0.0, maximum=MAX_QUANTITY),
                ConfigField("price", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
                ConfigField("stopLoss", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
                ConfigField("takeProfit", "number", 0.0, minimum=0.0, maximum=1_000_000_000),
                ConfigField("timeInForce", "enum", "gtc", enum=_TIME_IN_FORCE),
            ),
            capabilities=("trading.intent",),
            side_effects=SideEffect.NONE,
            allowed_modes=_RISK,
            executor=exec_order_intent,
            metadata={
                "docs": (
                    "Builds ONE validated order intent (symbol, side, quantity, "
                    "type, price, SL/TP, time-in-force) for the execution adapters. "
                    "A limit/stop order without a price is an error, never a market "
                    "order in disguise. Pure: nothing is submitted and no broker is "
                    "contacted."
                ),
            },
        ),
        NodeDef(
            type="trading.order_preview", version="1.0.0", label="Order preview",
            category="trading",
            inputs=(
                PortDef(id="intent", name="Order intent", type=PortType.ORDER_INTENT),
            ),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="allowed", name="Would be allowed", type=PortType.BOOLEAN),
                PortDef(id="ok", name="OK", type=PortType.BOOLEAN),
                PortDef(id="reason", name="Reason", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("connectionId", "string", "", max_length=80),
                ConfigField("mandateId", "string", "", max_length=80),
            ),
            capabilities=("trading.broker.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL_MODES,
            timeout_ms=45_000,
            executor=exec_order_preview,
            metadata={
                "docs": (
                    "The broker's order_check plus connection policy, money "
                    "guardrails and (optionally) mandate scope — nothing is sent and "
                    "no approval is created. `ok` means the check ran; `allowed` means "
                    "the order would pass. Use it as the dry run for a whole workflow."
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
    ]

    # Phase 9 primitives live in their own modules to keep this file small; the
    # trading category owns the aggregation so `nodes.py` needs no new import.
    from .trading_calc_nodes import build_calc_nodes  # noqa: PLC0415 - leaf modules
    from .trading_ops_nodes import build_ops_nodes  # noqa: PLC0415 - leaf modules

    return nodes + build_calc_nodes() + build_ops_nodes()

__all__ = [
    "build_trading_nodes",
    "set_paper_store",
    "exec_broker_order",
    "exec_risk_check",
    "exec_paper_order",
    "exec_order_intent",
    "exec_order_preview",
    "exec_paper_account",
]
