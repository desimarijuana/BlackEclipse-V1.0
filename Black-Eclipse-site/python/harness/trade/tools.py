"""Read-only broker tools.

The agent may see which brokers are configured and read an account, positions,
working orders and a quote. It cannot create, edit or test a connection, and it
cannot place or cancel an order: those are operator routes (and, later, the
approval-gated execution phase).
"""

from __future__ import annotations

from typing import Any

from .analysis import bar_summary
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


def _known_connection(service: Any, connection_id: str) -> str:
    """Ignore a connection id that no longer exists.

    A remembered or copied id from another profile/DB is the classic cause of
    "no active mandate" on an account that has one: the id is stale, the mandate
    list for it is empty, and the user is told to create a mandate they already
    own. With a single saved connection the only honest interpretation is that
    id, so a stale one is dropped and resolved normally.
    """
    if not connection_id:
        return ""
    try:
        known = {str(item.get("id")) for item in service.list_connections()}
    except Exception:  # noqa: BLE001 - a read failure must not silently rewrite
        return connection_id
    return connection_id if connection_id in known else ""


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
            f"- #{row.get('ticket')} {row['symbol']} {row['side']} {row['volume']:g} "
            f"@ {row['openPrice']:g} (now {row['currentPrice']:g}, SL {stop}, "
            f"TP {target}, P&L {row['profit']:,.2f})"
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


def _select_mandate(service: Any, connection_id: str, symbol: str) -> str:
    """Resolve the one mandate that applies, without requiring an id from the user."""
    try:
        active = service.list_mandates(connection_id, active_only=True)
    except Exception:  # noqa: BLE001
        return ""
    if len(active) == 1:
        return str(active[0].get("id") or "")
    wanted = str(symbol or "").upper()
    matches = [
        mandate for mandate in active
        if any(str(item).strip().upper() in ("*", wanted) for item in (mandate.get("symbols") or []))
    ]
    if len(matches) == 1:
        return str(matches[0].get("id") or "")
    return ""


async def broker_bars(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """The broker's own OHLCV series, with ATR computed deterministically."""
    service = _service(ctx)
    symbol = str(args.get("symbol") or "").strip()
    if not symbol:
        return "A `symbol` is required (e.g. XAUUSD).", {"status": "INVALID_SYMBOL"}
    connection_id = _known_connection(
        service, str(args.get("connectionId") or "").strip()
    )
    try:
        if not connection_id:
            connection_id = _pick(service, {})
        timeframe = str(args.get("timeframe") or "H1").strip().upper()
        count = int(args.get("count") or 120)
        result = service.bars(connection_id, symbol, timeframe=timeframe, count=count)
    except ValueError as exc:
        return str(exc), {"status": "CONNECTION_REQUIRED"}
    if not result.get("available"):
        return _unavailable_text(result), result
    data = result.get("data") or {}
    bars = data.get("bars") or []
    summary = bar_summary(bars)
    if not bars or summary.get("atr") is None:
        return (
            f"{data.get('symbol') or symbol} {data.get('timeframe') or timeframe}: "
            f"{len(bars)} bars; not enough history for ATR(14).",
            {**result, "summary": summary},
        )
    contract = data.get("contractSize") or 0
    lines = [
        f"{data.get('symbol')} {data.get('timeframe')}: {len(bars)} bars from "
        "MetaTrader 5 (broker server time).",
        f"Last close {summary['lastClose']:g} "
        f"(high {summary['lastHigh']:g} / low {summary['lastLow']:g}), "
        f"change {summary['changePct'] if summary['changePct'] is not None else 'n/a'}%.",
        f"ATR({summary['atrPeriod']}) {summary['atr']:g} over the last "
        f"{summary['lookback']} bars; range "
        f"{summary['lookbackLow']:g}–{summary['lookbackHigh']:g}.",
    ]
    if contract:
        lines.append(
            f"Contract size {contract:g}; a 0.01 lot is {contract / 100:g} units."
        )
    return "\n".join(lines), {**result, "summary": summary}


async def order_submit(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Submit a demo order under the active mandate that covers its symbol."""
    service = _service(ctx)
    connection_id = str(args.get("connectionId") or "").strip()
    mandate_id = str(args.get("mandateId") or "").strip()
    intent = args.get("intent")
    if not isinstance(intent, dict):
        return "An `intent` object is required.", {"status": "INVALID_ORDER"}
    connection_id = _known_connection(service, connection_id)
    if not connection_id:
        try:
            connection_id = _pick(service, {})
        except ValueError as exc:
            return str(exc), {"status": "CONNECTION_REQUIRED"}
    if not mandate_id:
        mandate_id = _select_mandate(service, connection_id, str(intent.get("symbol") or ""))
    if not mandate_id:
        active = service.list_mandates(connection_id, active_only=True)
        return (
            "No single active demo mandate covers this symbol. Active mandates: "
            f"{', '.join(m['id'] for m in active) or 'none'}. Ask the operator to "
            "create one in Settings → Broker connection.",
            {"status": "MANDATE_REQUIRED", "mandates": active},
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
        detail = result.get("result") or {}
        verify = "" if detail.get("verified", True) else (
            " WARNING: the broker's stored bracket does not match the request — "
            f"{detail.get('verifyNote') or 'verify the position manually'}."
        )
        return (
            f"Order {status}. Ticket {ledger.get('ticket') or 'n/a'}, "
            f"order {ledger.get('id') or result.get('orderId') or 'n/a'}.{verify}",
            result,
        )
    reasons = "; ".join(result.get("reasons") or []) or status
    return f"Order not sent ({status}): {reasons}", result


async def position_close(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Close one position, or every open one, without an approval.

    Closing reduces exposure, so it follows the cancel rule: no mandate, no
    approval and no live arm. The service still requires the account mode to
    match the connection (demo/demo, live/real).
    """
    service = _service(ctx)
    connection_id = _known_connection(
        service, str(args.get("connectionId") or "").strip()
    )
    try:
        if not connection_id:
            connection_id = _pick(service, {})
        ticket = args.get("ticket")
        tickets = args.get("tickets")
        close_all = bool(args.get("all"))
        symbol = str(args.get("symbol") or "").strip().upper()
        volume = args.get("volume")
        if ticket is not None:
            result = service.close_position(
                connection_id, int(ticket),
                volume=float(volume) if volume is not None else None,
            )
            closed = bool(result.get("closed"))
            detail = result.get("result") or {}
            if closed:
                suffix = (
                    f" Partial close; {detail.get('remainingVolume'):g} still open."
                    if detail.get("partial") else ""
                )
                verify = "" if detail.get("verified") else (
                    " WARNING: the broker's position did not read back as expected."
                )
                return (
                    f"Closed position {ticket} ({detail.get('symbol', '?')} "
                    f"{detail.get('volume', '?')} at {detail.get('price', '?')})."
                    f"{suffix}{verify}",
                    result,
                )
            reasons = "; ".join(detail.get("reasons") or []) or detail.get("retcodeName")
            return f"Position {ticket} not closed: {reasons}", result
        if symbol:
            positions = service.positions(connection_id)
            rows = (positions.get("data") or []) if positions.get("available") else []
            wanted = [
                int(row.get("ticket") or 0)
                for row in rows
                if str(row.get("symbol") or "").upper() == symbol
            ]
            if not wanted:
                return f"No open {symbol} position to close.", {
                    "status": "NO_POSITION", "symbol": symbol
                }
            result = service.close_positions(connection_id, tickets=wanted)
        elif close_all or tickets:
            wanted = [int(item) for item in tickets] if isinstance(tickets, list) else None
            result = service.close_positions(connection_id, tickets=wanted)
        else:
            return (
                'Pass `ticket` to close one position, `symbol` to close that '
                'instrument, or `all: true` to close every open position.',
                {"status": "INVALID_ARGUMENTS"},
            )
    except ValueError as exc:
        return str(exc), {"status": "CONNECTION_REQUIRED"}
    except TradeRefused as exc:
        return f"Close refused ({exc.code}): {exc.message}", {
            "status": "REFUSED",
            "error": exc.to_dict(),
        }
    closed = int(result.get("closed") or 0)
    failed = int(result.get("failed") or 0)
    if not result.get("requested"):
        return "No open positions to close.", result
    summary = f"Closed {closed} of {result.get('requested')} position(s)"
    if failed:
        summary += f"; {failed} failed"
    return summary + ".", result


async def position_modify(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Move a position's stop and/or target (no mandate, approval or arm)."""
    service = _service(ctx)
    ticket = args.get("ticket")
    stop_loss = args.get("stopLoss")
    take_profit = args.get("takeProfit")
    if ticket is None:
        return "Pass `ticket` for the position to modify.", {"status": "INVALID_ARGUMENTS"}
    if stop_loss is None and take_profit is None:
        return (
            "Pass `stopLoss` and/or `takeProfit` (a number, or 0 to remove it).",
            {"status": "INVALID_STOPS"},
        )
    connection_id = _known_connection(
        service, str(args.get("connectionId") or "").strip()
    )
    try:
        if not connection_id:
            connection_id = _pick(service, {})
        result = service.modify_position(
            connection_id, int(ticket),
            stop_loss=float(stop_loss) if stop_loss is not None else None,
            take_profit=float(take_profit) if take_profit is not None else None,
        )
    except ValueError as exc:
        return str(exc), {"status": "CONNECTION_REQUIRED"}
    except TradeRefused as exc:
        return f"Modify refused ({exc.code}): {exc.message}", {
            "status": "REFUSED",
            "error": exc.to_dict(),
        }
    detail = result.get("result") or {}
    if result.get("modified"):
        verify = "" if detail.get("verified") else (
            " WARNING: the broker accepted the request but the stored bracket "
            "did not read back as requested."
        )
        return (
            f"Position {ticket} updated: stop loss "
            f"{detail.get('stopLoss', 'n/a')}, take profit "
            f"{detail.get('takeProfit', 'n/a')}.{verify}",
            result,
        )
    reasons = "; ".join(detail.get("reasons") or []) or detail.get("retcodeName")
    return f"Position {ticket} not modified: {reasons}", result


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
        "Validate an order (demo or live) against broker constraints, the "
        "connection's limits and the money guardrails, then request a single-use "
        "operator approval. On a live connection the operator confirms the "
        "approval card in chat and types the LIVE phrase; this tool NEVER sends "
        "an order.",
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
        "broker_bars",
        "Read the broker's OWN OHLCV bars for a symbol (server time) and the "
        "deterministic ATR(14) / 20-bar range computed from them. Use this for "
        "any instrument the stored market history does not cover (XAUUSD): it is "
        "the accurate series for a bracket, unlike a proxy ETF. Read-only.",
        broker_bars,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "symbol": {"type": "string"},
                "timeframe": {
                    "type": "string",
                    "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"],
                },
                "count": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            "required": ["symbol"],
        },
    )
    _def(
        "order_submit",
        "Submit ONE DEMO order under an active operator-created mandate. REQUIRED "
        "arguments: connectionId and intent {symbol, side, type, volume, stopLoss?, "
        "takeProfit?}. `connectionId` and `mandateId` are optional: the one saved "
        "connection and the one active mandate covering the symbol are resolved for "
        "you. Only an ambiguous multi-mandate symbol needs an id from broker_mandates. "
        "This call performs "
        "its own preview and submission; do not call order_preview first and never call "
        "it with empty arguments. It cannot create a mandate or arm live. LIVE orders "
        "are never submitted by this tool: call `order_preview` and the operator "
        "confirms the approval card in chat.",
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
            "required": ["intent"],
        },
        permission=READ,
        risk="high",
        effect="trading",
    )


    _def(
        "position_close",
        "Close an open position (risk-reducing, so no approval, mandate or live arm "
        "is needed). Pass `ticket` for one position, or `all: true` to step out of "
        "every open position; `connectionId` resolves on its own when there is one "
        "connection. Works on a demo or a live connection; the account mode must "
        "match the connection. Returns the broker's per-ticket result.",
        position_close,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "ticket": {"type": "integer"},
                "tickets": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Close these tickets instead of every position.",
                },
                "symbol": {
                    "type": "string",
                    "description": "Close every open position in this instrument.",
                },
                "volume": {
                    "type": "number",
                    "description": "Partial close size; omit to close the whole ticket.",
                },
                "all": {
                    "type": "boolean",
                    "description": "Close every open position on the connection.",
                },
                "deviation": {"type": "integer"},
            },
        },
        permission=READ,
        risk="medium",
        effect="trading",
    )
    _def(
        "position_modify",
        "Move a position's stop loss and/or take profit (risk-reducing; no "
        "approval, mandate or live arm). Pass `ticket` and `stopLoss`/`takeProfit`; "
        "0 removes a level. Works on a demo or a live connection; the account mode "
        "must match. The result is verified against the broker's stored bracket. A "
        "wider stop increases risk — say so when you do it.",
        position_modify,
        {
            "type": "object",
            "properties": {
                "connectionId": connection_id,
                "ticket": {"type": "integer"},
                "stopLoss": {"type": "number"},
                "takeProfit": {"type": "number"},
            },
            "required": ["ticket"],
        },
        permission=READ,
        risk="medium",
        effect="trading",
    )


__all__ = [
    "BROKER_TOOLS",
    "broker_account",
    "broker_bars",
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
    "position_close",
    "position_modify",
    "register_broker_tools",
]

#: The canonical broker allowlist (imported by `agents.py`). `order_submit` opens
#: exposure under an active demo mandate; `position_close` only reduces exposure.
BROKER_TOOLS = [
    "broker_connections",
    "broker_account",
    "broker_positions",
    "broker_orders",
    "broker_quote",
    "broker_bars",
    "order_preview",
    "order_submit",
    "position_close",
    "position_modify",
    "broker_mandates",
    "order_ledger",
    "broker_reconciliation",
    "broker_fills",
]
