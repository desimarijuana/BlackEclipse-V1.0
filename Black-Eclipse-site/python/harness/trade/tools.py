"""Read-only broker tools.

The agent may see which brokers are configured and read an account, positions,
working orders and a quote. It cannot create, edit or test a connection, and it
cannot place or cancel an order: those are operator routes (and, later, the
approval-gated execution phase).
"""

from __future__ import annotations

from typing import Any

from .model import TradeRefused

READ = "read"


def _service(ctx: Any) -> Any:
    service = getattr(ctx, "brokers", None)
    if service is None:
        from .bootstrap import get_service  # noqa: PLC0415

        service = get_service()
    if service is None:
        raise RuntimeError("broker connectivity is not available in this run")
    return service


def _pick(service: Any, args: dict[str, Any]) -> str:
    explicit = str(args.get("connectionId") or args.get("connection_id") or "").strip()
    if explicit:
        return explicit
    connections = service.connections.list()
    if not connections:
        raise ValueError(
            "no broker connection is configured; add one in Settings › Trading"
        )
    if len(connections) > 1:
        raise ValueError(
            "more than one broker connection exists; pass connectionId "
            f"({', '.join(c.id for c in connections)})"
        )
    return connections[0].id


def _unavailable_text(result: dict[str, Any]) -> str:
    error = result.get("error") or {}
    return (
        f"Broker unavailable ({error.get('code') or 'UNAVAILABLE'}): "
        f"{error.get('message') or 'the broker did not answer'}"
    )


async def broker_connections(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    kinds = service.kinds()
    connections = service.list_connections()
    lines = ["Broker adapters:"]
    for kind in kinds:
        state = "available" if kind.get("available") else f"unavailable — {kind.get('unavailableReason')}"
        execution = (
            f"execution={','.join(kind.get('executionModes') or [])}"
            if kind.get("execution") else "execution=no"
        )
        lines.append(
            f"- {kind['label']} ({kind['id']}): {state}; "
            f"auth={kind['auth']}; {execution}"
        )
    lines.append("")
    if connections:
        lines.append("Saved connections:")
        for connection in connections:
            lines.append(
                f"- {connection['label']} [{connection['id']}] "
                f"{connection['kind']}/{connection['mode']} — {connection['status']}"
                + (f" ({connection['statusReason']})" if connection.get("statusReason") else "")
            )
    else:
        lines.append("No broker connection is configured yet.")
    return "\n".join(lines), {"kinds": kinds, "connections": connections}


async def broker_account(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    result = service.account(_pick(service, args))
    if not result.get("available"):
        return _unavailable_text(result), result
    account = result["data"]
    return (
        f"{account['company']} · {account['server']} · {account['mode'].upper()} "
        f"account {account['login']}\n"
        f"Balance {account['balance']:,.2f} {account['currency']} · "
        f"Equity {account['equity']:,.2f} · Free margin {account['marginFree']:,.2f} · "
        f"Leverage 1:{account['leverage']}\n"
        f"Margin mode {account['marginMode']} · "
        f"trading {'allowed' if account['tradeAllowed'] else 'disabled'} · "
        f"expert {'allowed' if account['expertAllowed'] else 'disabled'}",
        result,
    )


async def broker_positions(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    result = service.positions(_pick(service, args))
    if not result.get("available"):
        return _unavailable_text(result), result
    rows = result["data"]
    if not rows:
        return "No open positions.", result
    lines = [f"{len(rows)} open position(s):"]
    for row in rows:
        stop = f"{row['stopLoss']:g}" if row.get("stopLoss") is not None else "—"
        target = f"{row['takeProfit']:g}" if row.get("takeProfit") is not None else "—"
        lines.append(
            f"- {row['symbol']} {row['side']} {row['volume']:g} @ {row['openPrice']:g} "
            f"(now {row['currentPrice']:g}, SL {stop}, TP {target}, "
            f"P&L {row['profit']:,.2f})"
        )
    return "\n".join(lines), result


async def broker_orders(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    result = service.orders(_pick(service, args))
    if not result.get("available"):
        return _unavailable_text(result), result
    rows = result["data"]
    if not rows:
        return "No working orders.", result
    lines = [f"{len(rows)} working order(s):"]
    for row in rows:
        lines.append(
            f"- #{row['ticket']} {row['symbol']} {row['type']} "
            f"{row['volumeCurrent']:g} @ {row['openPrice']:g} ({row['state']})"
        )
    return "\n".join(lines), result


async def broker_quote(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    symbol = str(args.get("symbol") or "").strip()
    if not symbol:
        return "A symbol is required (for example EURUSD).", {"status": "SYMBOL_REQUIRED"}
    result = service.quote(_pick(service, args), symbol)
    if not result.get("available"):
        return _unavailable_text(result), result
    quote = result["data"]
    spread = (
        f"{quote['spreadPoints']:g} pts" if quote.get("spreadPoints") is not None else "unknown"
    )
    digits = int(quote.get("digits") or 5)
    bid = f"{quote['bid']:.{digits}f}"
    ask = f"{quote['ask']:.{digits}f}"
    volume_max = quote.get("volumeMax") or 0
    volume = (
        f"{quote.get('volumeMin', 0):g}–{volume_max:g} (step {quote.get('volumeStep', 0):g})"
        if volume_max
        else "unavailable"
    )
    return (
        f"{quote['symbol']}: bid {bid} / ask {ask} (spread {spread}) from MetaTrader 5\n"
        f"digits {digits} · point {quote.get('point', 0):g} · volume {volume} · "
        f"stops level {quote.get('stopsLevelPoints', 0)} pts · "
        f"server time {quote.get('serverTimeMs', 0)} ms",
        result,
    )


async def order_preview(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    connection_id = str(args.get("connectionId") or "").strip()
    if not connection_id:
        connection_id = _pick(service, args)
    intent = args.get("intent")
    if not isinstance(intent, dict):
        return "An `intent` object is required (symbol, side, type, volume, …).", {
            "status": "INVALID_ORDER"
        }
    result = service.preview_order(connection_id, intent)
    if result.get("allowed"):
        approval = result.get("approval") or {}
        return (
            "Order preview is valid and awaits an operator decision. "
            f"Approval {approval.get('id')} ({approval.get('status')}).\n"
            f"{approval.get('actionSummary') or ''}\n"
            "No order was sent. Submission is an operator action.",
            result,
        )
    reasons = "; ".join(result.get("reasons") or []) or "the order was refused"
    error = result.get("error") or {}
    code = error.get("code") or "REFUSED"
    return f"Order preview refused ({code}): {reasons}", result


async def broker_reconciliation(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    result = service.reconciliation(_pick(service, args), limit=int(args.get("limit") or 50))
    state = result.get("state") or {}
    positions = result.get("positions") or []
    fills = result.get("fills") or []
    if not state:
        return "No reconciliation has run for this connection yet.", result
    lines = [
        f"Last sync: {state.get('lastSyncedAt')} ({state.get('status')})",
        f"Positions: {len(positions)} · fills stored: {len(fills)} · "
        f"last deal: {state.get('lastDealAt') or 'none'}",
    ]
    if state.get("error"):
        lines.append(f"Error: {state['error']}")
    return "\n".join(lines), result


async def broker_fills(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    fills = service.list_fills(
        _pick(service, args), limit=int(args.get("limit") or 20)
    )
    if not fills:
        return "No broker fills are recorded.", {"fills": []}
    lines = [f"{len(fills)} fill(s), newest first:"]
    for fill in fills:
        lines.append(
            f"- {fill['symbol']} {fill['side']} {fill['entry']} {fill['volume']:g} "
            f"@ {fill['price']:g} (profit {fill['profit']:,.2f}, "
            f"deal {fill['dealTicket']})"
        )
    return "\n".join(lines), {"fills": fills}


async def broker_mandates(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    connection_id = str(args.get("connectionId") or "").strip() or None
    mandates = service.list_mandates(connection_id, active_only=True)
    if not mandates:
        return (
            "No active demo mandate. An operator must create one in "
            "Settings → Broker connection before unattended orders are allowed.",
            {"mandates": []},
        )
    lines = [f"{len(mandates)} active demo mandate(s):"]
    for mandate in mandates:
        lines.append(
            f"- {mandate['id']} · connection {mandate['connectionId']} · "
            f"symbols {', '.join(mandate['symbols'])} · "
            f"{mandate['remainingOrders']}/{mandate['maxOrders']} orders left · "
            f"max margin {mandate['maxMargin']:g} · expires {mandate['expiresAt']}"
        )
    return "\n".join(lines), {"mandates": mandates}


async def order_submit(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Submit a demo order under an active mandate (the only agent write path)."""
    service = _service(ctx)
    connection_id = str(args.get("connectionId") or "").strip()
    mandate_id = str(args.get("mandateId") or "").strip()
    intent = args.get("intent")
    if not isinstance(intent, dict):
        return "An `intent` object is required.", {"status": "INVALID_ORDER"}
    if not connection_id:
        connection_id = _pick(service, args)
    if not mandate_id:
        active = service.list_mandates(connection_id, active_only=True)
        if len(active) == 1:
            mandate_id = active[0]["id"]
        else:
            return (
                "A mandateId is required when zero or multiple active mandates exist. "
                "Call broker_mandates first.",
                {"status": "MANDATE_REQUIRED"},
            )
    try:
        result = service.submit_order(
            connection_id,
            intent,
            mandate_id=mandate_id,
            run_id=str(getattr(ctx, "run_id", "") or ""),
        )
    except TradeRefused as exc:
        return f"Order refused ({exc.code}): {exc.message}", {
            "status": "REFUSED",
            "error": exc.to_dict(),
        }
    status = str(result.get("status") or "UNKNOWN")
    ledger = result.get("ledger") or {}
    if status in ("filled", "placed"):
        return (
            f"Order {status}. Ticket {ledger.get('ticket') or 'n/a'}, "
            f"order {ledger.get('id') or result.get('orderId') or 'n/a'}.",
            result,
        )
    reasons = "; ".join(result.get("reasons") or []) or status
    return f"Order not sent ({status}): {reasons}", result


async def order_ledger(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    connection_id = str(args.get("connectionId") or "").strip() or None
    orders = service.ledger_orders(connection_id, limit=int(args.get("limit") or 20))
    if not orders:
        return "No submitted broker orders are recorded.", {"orders": []}
    lines = [f"{len(orders)} submitted order(s), newest first:"]
    for order in orders:
        intent = order.get("intent") or {}
        lines.append(
            f"- {order['id']} {intent.get('side', '?')} {intent.get('volume', '?')} "
            f"{intent.get('symbol', '?')} {order['status']}"
            + (f" ticket {order['ticket']}" if order.get("ticket") else "")
        )
    return "\n".join(lines), {"orders": orders}


def register_broker_tools(registry: Any) -> None:
    from ..tools import ToolDefinition

    def _def(
        name: str,
        description: str,
        handler: Any,
        schema: dict[str, Any],
        *,
        permission: str = READ,
        risk: str = "none",
        effect: str | None = None,
    ) -> None:
        registry.register(ToolDefinition(
            name=name,
            description=description,
            input_schema=schema,
            handler=handler,
            permission=permission,
            risk=risk,
            effect=effect,
        ))

    connection_id = {"type": "string", "description": "Saved connection id (optional when there is exactly one)."}
    _def(
        "broker_connections",
        "List the broker adapters Eclipse knows and the saved connections with "
        "their last known status. Read-only.",
        broker_connections,
        {"type": "object", "properties": {}},
    )
    _def(
        "broker_account",
        "Read the connected broker account (balance, equity, margin, leverage, "
        "demo/real mode). Read-only.",
        broker_account,
        {"type": "object", "properties": {"connectionId": connection_id}},
    )
    _def(
        "broker_positions",
        "Read open broker positions. Read-only; never invents a position.",
        broker_positions,
        {"type": "object", "properties": {"connectionId": connection_id}},
    )
    _def(
        "broker_orders",
        "Read working (pending) broker orders. Read-only.",
        broker_orders,
        {"type": "object", "properties": {"connectionId": connection_id}},
    )
    _def(
        "broker_quote",
        "Read a live bid/ask quote from the connected broker feed.",
        broker_quote,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "symbol": {"type": "string"},
            },
            "required": ["symbol"],
        },
    )
    _def(
        "order_preview",
        "Validate a demo order against broker constraints, the connection's limits "
        "and the money guardrails, then request a single-use operator approval. "
        "This NEVER sends an order; submission is an operator action.",
        order_preview,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "intent": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "type": {"type": "string", "enum": ["market", "limit", "stop"]},
                        "volume": {"type": "number"},
                        "price": {"type": "number"},
                        "stopLoss": {"type": "number"},
                        "takeProfit": {"type": "number"},
                        "deviationPoints": {"type": "integer"},
                        "timeInForce": {"type": "string", "enum": ["gtc", "day"]},
                        "comment": {"type": "string"},
                        "magic": {"type": "integer"},
                    },
                    "required": ["symbol", "side", "type", "volume"],
                },
            },
            "required": ["intent"],
        },
    )
    _def(
        "order_ledger",
        "Read the local ledger of orders Eclipse submitted to a broker. This is an "
        "audit record; the broker remains the source of truth for fills.",
        order_ledger,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "limit": {"type": "integer"},
            },
        },
    )
    _def(
        "broker_reconciliation",
        "Read the last reconciled fills, positions snapshot and sync state for a "
        "broker connection. Read-only.",
        broker_reconciliation,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "limit": {"type": "integer"},
            },
        },
    )
    _def(
        "broker_fills",
        "Read the broker deals Eclipse has durably recorded (deduped by deal ticket). "
        "Read-only; the broker remains the source of truth.",
        broker_fills,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "limit": {"type": "integer"},
            },
        },
    )
    _def(
        "broker_mandates",
        "List active demo mandates (symbols, remaining orders, margin cap, expiry). "
        "A mandate is the operator's authorization for unattended demo orders.",
        broker_mandates,
        {"type": "object", "properties": {"connectionId": connection_id}},
    )
    _def(
        "order_submit",
        "Submit ONE demo order under an active operator-created mandate. REQUIRED "
        "arguments: connectionId, mandateId, and intent {symbol, side, type, volume, "
        "stopLoss?, takeProfit?}. This call performs its own preview and submission; "
        "do not call order_preview first and never call it with empty arguments. It "
        "cannot create a mandate, arm live, or submit live. The broker service still "
        "enforces policy, money guardrails, the demo account check, the mandate margin "
        "cap and the mandate order count.",
        order_submit,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "mandateId": {
                    "type": "string",
                    "description": "Active demo mandate id from broker_mandates.",
                },
                "intent": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "type": {"type": "string", "enum": ["market", "limit", "stop"]},
                        "volume": {"type": "number"},
                        "price": {"type": "number"},
                        "stopLoss": {"type": "number"},
                        "takeProfit": {"type": "number"},
                        "deviationPoints": {"type": "integer"},
                        "timeInForce": {"type": "string", "enum": ["gtc", "day"]},
                        "comment": {"type": "string"},
                        "magic": {"type": "integer"},
                    },
                    "required": ["symbol", "side", "type", "volume"],
                },
            },
            "required": ["connectionId", "mandateId", "intent"],
        },
        permission=READ,
        risk="high",
        effect="trading",
    )


__all__ = [
    "BROKER_TOOLS",
    "broker_account",
    "broker_connections",
    "broker_fills",
    "broker_mandates",
    "broker_orders",
    "broker_positions",
    "broker_quote",
    "broker_reconciliation",
    "order_ledger",
    "order_preview",
    "order_submit",
    "register_broker_tools",
]

#: The canonical broker allowlist (imported by `agents.py`). `order_submit` is the
#: ONE effectful entry; its authorizer requires an active demo mandate.
BROKER_TOOLS = [
    "broker_connections",
    "broker_account",
    "broker_positions",
    "broker_orders",
    "broker_quote",
    "order_preview",
    "order_submit",
    "broker_mandates",
    "order_ledger",
    "broker_reconciliation",
    "broker_fills",
]
