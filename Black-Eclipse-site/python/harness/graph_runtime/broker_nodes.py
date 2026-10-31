"""Broker read and risk-reducing nodes (Phase 6).

These are thin adapters over the EXISTING `BrokerService` (the same paths the
chat tools and REST surface use). Reads are honest envelopes: a missing or
logged-out terminal is a named failure, never a fabricated account or price.

Live ORDER submission stays in `trading.broker_order`; it requires an armed live
connection plus a workflow-pinned live mandate. Close/modify/cancel only reduce
or re-scope exposure, so they remain arm-free and mandate-free — an expired arm
must never trap a position.
"""

from __future__ import annotations

from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1")


def _service() -> Any:
    from ..trade.bootstrap import get_service  # noqa: PLC0415 - avoids an import cycle

    service = get_service()
    if service is None:
        raise ValueError("broker connectivity is unavailable in this runtime")
    return service


def _connection(context: NodeExecContext) -> str:
    connection_id = str(context.config.get("connectionId") or "").strip()
    if not connection_id:
        raise ValueError("connectionId is required")
    return connection_id


def _symbol(context: NodeExecContext) -> str:
    raw = context.inputs.get("symbol") or context.config.get("symbol") or ""
    symbol = str(raw).strip().upper()
    if not symbol:
        raise ValueError("a symbol is required")
    return symbol


def _number(context: NodeExecContext, handle: str, config_key: str | None = None) -> float | None:
    raw = context.inputs.get(handle)
    if raw is None and config_key:
        raw = context.config.get(config_key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{handle} must be a number") from exc


def exec_broker_account(context: NodeExecContext) -> dict[str, Any]:
    result = _service().account(_connection(context))
    return {"account": result, "status": "connected" if result.get("available") else "unavailable"}


def exec_broker_quote(context: NodeExecContext) -> dict[str, Any]:
    result = _service().quote(_connection(context), _symbol(context))
    return {"quote": result, "status": "ok" if result.get("available") else "unavailable"}


def exec_broker_bars(context: NodeExecContext) -> dict[str, Any]:
    timeframe = str(context.config.get("timeframe") or "H1")
    try:
        count = int(context.config.get("count", 120))
    except (TypeError, ValueError) as exc:
        raise ValueError("count must be a whole number") from exc
    result = _service().bars(
        _connection(context), _symbol(context), timeframe=timeframe, count=count,
    )
    return {"bars": result, "status": "ok" if result.get("available") else "unavailable"}


def exec_broker_close(context: NodeExecContext) -> dict[str, Any]:
    service = _service()
    connection_id = _connection(context)
    ticket = _number(context, "ticket")
    volume = _number(context, "volume")
    if bool(context.config.get("closeAll")):
        result = service.close_positions(connection_id)
    elif ticket is not None:
        result = service.close_position(
            connection_id, int(ticket), volume=volume,
            deviation=int(context.config.get("deviation", 20) or 20),
        )
    else:
        raise ValueError("broker close needs a ticket input or closeAll = true")
    return {"result": result, "status": "closed" if result.get("closed") else "rejected"}


def exec_broker_modify(context: NodeExecContext) -> dict[str, Any]:
    ticket = _number(context, "ticket")
    if ticket is None:
        raise ValueError("broker modify needs a ticket input")
    result = _service().modify_position(
        _connection(context), int(ticket),
        stop_loss=_number(context, "stopLoss"),
        take_profit=_number(context, "takeProfit"),
    )
    return {"result": result, "status": "modified" if result.get("modified") else "rejected"}


def exec_broker_cancel(context: NodeExecContext) -> dict[str, Any]:
    ticket = _number(context, "ticket")
    if ticket is None:
        raise ValueError("broker cancel needs a ticket input")
    result = _service().cancel_order(_connection(context), int(ticket))
    return {"result": result, "status": "cancelled" if result.get("cancelled") else "rejected"}


def build_broker_nodes() -> list[NodeDef]:
    connection = ConfigField("connectionId", "string", "", max_length=80)
    return [
        NodeDef(
            type="trading.broker_account", version="1.0.0", label="Broker account",
            category="trading",
            outputs=(
                PortDef(id="account", name="Account", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(connection,),
            capabilities=("trading.broker.read",), side_effects=SideEffect.READ,
            allowed_modes=_ALL, executor=exec_broker_account,
            metadata={"docs": "Reads the broker account/positions envelope. Honest UNAVAILABLE, never a fake balance."},
        ),
        NodeDef(
            type="trading.broker_quote", version="1.0.0", label="Broker quote",
            category="trading",
            inputs=(PortDef(id="symbol", name="Symbol", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="quote", name="Quote", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(connection, ConfigField("symbol", "string", "", max_length=40)),
            capabilities=("trading.broker.read",), side_effects=SideEffect.READ,
            allowed_modes=_ALL, executor=exec_broker_quote,
            metadata={"docs": "Bid/ask/spread from the broker (including symbols JDDS may not carry)."},
        ),
        NodeDef(
            type="trading.broker_bars", version="1.0.0", label="Broker bars",
            category="trading",
            inputs=(PortDef(id="symbol", name="Symbol", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="bars", name="Bars", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(
                connection,
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("timeframe", "enum", "H1", enum=_TIMEFRAMES),
                ConfigField("count", "integer", 120, minimum=1, maximum=500),
            ),
            capabilities=("trading.broker.read",), side_effects=SideEffect.READ,
            allowed_modes=_ALL, executor=exec_broker_bars,
            metadata={"docs": "The broker's own OHLCV series (server time), for symbols JDDS cannot proxy."},
        ),
        NodeDef(
            type="trading.broker_close", version="1.0.0", label="Close position",
            category="trading",
            inputs=(
                PortDef(id="ticket", name="Ticket", type=PortType.NUMBER, optional=True),
                PortDef(id="volume", name="Volume", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(
                connection,
                ConfigField("closeAll", "boolean", False),
                ConfigField("deviation", "integer", 20, minimum=0, maximum=1_000),
            ),
            capabilities=("trading.broker",), side_effects=SideEffect.TRADING,
            allowed_modes=(ExecutionMode.PAPER, ExecutionMode.LIVE),
            executor=exec_broker_close,
            metadata={"docs": "Risk-reducing: closes one ticket (full/partial) or all positions; no arm/approval/mandate."},
        ),
        NodeDef(
            type="trading.broker_modify", version="1.0.0", label="Modify position",
            category="trading",
            inputs=(
                PortDef(id="ticket", name="Ticket", type=PortType.NUMBER),
                PortDef(id="stopLoss", name="Stop loss", type=PortType.NUMBER, optional=True),
                PortDef(id="takeProfit", name="Take profit", type=PortType.NUMBER, optional=True),
            ),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(connection,),
            capabilities=("trading.broker",), side_effects=SideEffect.TRADING,
            allowed_modes=(ExecutionMode.PAPER, ExecutionMode.LIVE),
            executor=exec_broker_modify,
            metadata={"docs": "Moves SL/TP on one position. Risk-reducing: no arm/approval/mandate."},
        ),
        NodeDef(
            type="trading.broker_cancel", version="1.0.0", label="Cancel order",
            category="trading",
            inputs=(PortDef(id="ticket", name="Ticket", type=PortType.NUMBER),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(connection,),
            capabilities=("trading.broker",), side_effects=SideEffect.TRADING,
            allowed_modes=(ExecutionMode.PAPER, ExecutionMode.LIVE),
            executor=exec_broker_cancel,
            metadata={"docs": "Cancels one working order. Risk-reducing: no arm/approval/mandate."},
        ),
    ]


__all__ = [
    "build_broker_nodes",
    "exec_broker_account",
    "exec_broker_quote",
    "exec_broker_bars",
    "exec_broker_close",
    "exec_broker_modify",
    "exec_broker_cancel",
]
