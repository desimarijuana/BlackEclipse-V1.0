"""MetaTrader 5 wire tables and pure row/record builders.

Split out of `mt5.py` to keep the adapter under its size budget. Nothing here
opens a session or touches the terminal: it is data plus the pure mapping from
MT5's named tuples to plain JSON-safe dicts. Behavior is unchanged — `mt5.py`
imports these names back, so every existing call site and test import still
works.
"""

from __future__ import annotations

import time
from datetime import datetime as _datetime, time as _clock_time
from typing import Any, Optional

_TRADE_MODE = {0: "demo", 1: "contest", 2: "real"}

_MARGIN_MODE = {0: "netting", 1: "exchange", 2: "hedging"}

_TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
}

_ORDER_TYPE = {
    0: "buy", 1: "sell", 2: "buy_limit", 3: "sell_limit",
    4: "buy_stop", 5: "sell_stop", 6: "buy_stop_limit", 7: "sell_stop_limit",
    8: "close_by",
}

_SYMBOL_TRADE_MODE = {
    0: "disabled", 1: "long_only", 2: "short_only", 3: "close_only", 4: "full",
}

_DEAL_TYPE = {
    0: "buy", 1: "sell", 2: "balance", 3: "credit", 4: "charge",
    5: "correction", 6: "bonus", 7: "commission", 8: "commission_daily",
    9: "commission_monthly", 10: "commission_agent", 11: "interest",
    12: "buy_canceled", 13: "sell_canceled", 14: "dividend", 15: "dividend_tax",
}

_DEAL_ENTRY = {0: "in", 1: "out", 2: "inout", 3: "out_by"}

_ORDER_STATE = {
    0: "started", 1: "placed", 2: "cancelled", 3: "partial", 4: "filled",
    5: "rejected", 6: "expired", 7: "request_add", 8: "request_modify",
    9: "request_cancel",
}

_RETCODE = {
    10004: ("REQUOTE", "the broker requoted; no order was placed"),
    10006: ("REJECTED", "the broker rejected the order"),
    10007: ("CANCELLED", "the order was cancelled"),
    10008: ("PLACED", "the order was placed"),
    10009: ("DONE", "the order was executed"),
    10010: ("PARTIAL", "the order was partially filled"),
    10011: ("ERROR", "the broker returned a generic error"),
    10012: ("TIMEOUT", "the request timed out; the order state is unknown"),
    10013: ("INVALID", "the request is invalid"),
    10014: ("INVALID_VOLUME", "the volume is invalid for this symbol"),
    10015: ("INVALID_PRICE", "the price is invalid"),
    10016: ("INVALID_STOPS", "the stop loss or take profit is too close"),
    10017: ("TRADE_DISABLED", "trading is disabled for this account"),
    10018: ("MARKET_CLOSED", "the market is closed"),
    10019: ("NO_MONEY", "there is not enough free margin"),
    10020: ("PRICE_CHANGED", "the price changed; no order was placed"),
    10021: ("PRICE_OFF", "there are no quotes to execute against"),
    10022: ("INVALID_EXPIRATION", "the expiration is invalid"),
    10023: ("ORDER_CHANGED", "the order changed"),
    10024: ("TOO_MANY_REQUESTS", "the broker is rate-limiting requests"),
    10025: ("NO_CHANGES", "the request made no changes"),
    10026: ("SERVER_DISABLES_AT", "the server disabled trading for this request"),
    10027: ("CLIENT_DISABLES_AT", "Algo Trading is disabled in the terminal"),
    10028: ("LOCKED", "the order is locked by the broker"),
    10029: ("FROZEN", "the order is frozen by the broker"),
    10030: ("INVALID_FILL", "the requested filling mode is not allowed"),
    10031: ("CONNECTION", "there is no connection to the broker"),
    10032: ("ONLY_REAL", "this operation is only allowed on a real account"),
    10033: ("LIMIT_ORDERS", "the working-order limit was reached"),
    10034: ("LIMIT_VOLUME", "the volume limit was reached"),
    10035: ("INVALID_ORDER", "the order is invalid"),
    10036: ("POSITION_CLOSED", "the position is already closed"),
}

_FILLED_RETCODES = {10008, 10009, 10010}

_OK_CHECK_RETCODES = {0, 10009}

_IPC_ERRORS = {
    -2: ("INVALID_PARAMS", "MetaTrader 5 rejected the initialize parameters."),
    -3: ("NO_MEMORY", "MetaTrader 5 ran out of memory while initializing."),
    -4: ("NOT_FOUND", "The MetaTrader 5 terminal executable was not found."),
    -5: ("NO_IPC", "No IPC connection to the MetaTrader 5 terminal."),
    -6: ("NOT_INITIALIZED", "The MetaTrader 5 terminal is not initialized."),
    -7: ("INVALID_HANDLE", "The MetaTrader 5 terminal handle is invalid."),
    -8: ("INTERNAL_ERROR", "The MetaTrader 5 terminal reported an internal error."),
    -9: ("TIMEOUT", "The MetaTrader 5 terminal did not answer in time."),
    -10: ("NO_CONNECTION", "The MetaTrader 5 terminal has no connection to its broker."),
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _account_dict(info: Any) -> dict[str, Any]:
    trade_mode = _int(getattr(info, "trade_mode", -1), -1)
    margin_mode = _int(getattr(info, "margin_mode", -1), -1)
    return {
        "login": _int(getattr(info, "login", 0)),
        "mode": _TRADE_MODE.get(trade_mode, "unknown"),
        "tradeModeCode": trade_mode,
        "server": str(getattr(info, "server", "") or ""),
        "company": str(getattr(info, "company", "") or ""),
        "currency": str(getattr(info, "currency", "") or ""),
        "balance": _num(getattr(info, "balance", 0)),
        "equity": _num(getattr(info, "equity", 0)),
        "margin": _num(getattr(info, "margin", 0)),
        "marginFree": _num(getattr(info, "margin_free", 0)),
        "marginLevel": _num(getattr(info, "margin_level", 0)),
        "profit": _num(getattr(info, "profit", 0)),
        "leverage": _int(getattr(info, "leverage", 0)),
        "marginMode": _MARGIN_MODE.get(margin_mode, "unknown"),
        "tradeAllowed": bool(getattr(info, "trade_allowed", False)),
        "expertAllowed": bool(getattr(info, "trade_expert", False)),
    }


def _terminal_dict(info: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(info, "name", "") or ""),
        "company": str(getattr(info, "company", "") or ""),
        "path": str(getattr(info, "path", "") or ""),
        "build": _int(getattr(info, "build", 0)),
        "connected": bool(getattr(info, "connected", False)),
        "tradeAllowed": bool(getattr(info, "trade_allowed", False)),
        "communityAccount": bool(getattr(info, "community_account", False)),
        "maxBars": _int(getattr(info, "maxbars", 0)),
    }


def _position_dict(row: Any) -> dict[str, Any]:
    return {
        "ticket": _int(getattr(row, "ticket", 0)),
        "symbol": str(getattr(row, "symbol", "") or ""),
        "side": "buy" if _int(getattr(row, "type", -1)) == 0 else "sell",
        "volume": _num(getattr(row, "volume", 0)),
        "openPrice": _num(getattr(row, "price_open", 0)),
        "currentPrice": _num(getattr(row, "price_current", 0)),
        "stopLoss": _num(getattr(row, "sl", 0)) or None,
        "takeProfit": _num(getattr(row, "tp", 0)) or None,
        "profit": _num(getattr(row, "profit", 0)),
        "swap": _num(getattr(row, "swap", 0)),
        "commission": _num(getattr(row, "commission", 0)),
        "magic": _int(getattr(row, "magic", 0)),
        "comment": str(getattr(row, "comment", "") or ""),
        "openedAt": _int(getattr(row, "time", 0)),
        "identifier": _int(getattr(row, "identifier", 0)),
    }


def _order_dict(row: Any) -> dict[str, Any]:
    order_type = _int(getattr(row, "type", -1), -1)
    return {
        "ticket": _int(getattr(row, "ticket", 0)),
        "symbol": str(getattr(row, "symbol", "") or ""),
        "type": _ORDER_TYPE.get(order_type, "unknown"),
        "volumeInitial": _num(getattr(row, "volume_initial", 0)),
        "volumeCurrent": _num(getattr(row, "volume_current", 0)),
        "openPrice": _num(getattr(row, "price_open", 0)),
        "currentPrice": _num(getattr(row, "price_current", 0)),
        "stopLoss": _num(getattr(row, "sl", 0)) or None,
        "takeProfit": _num(getattr(row, "tp", 0)) or None,
        "state": str(getattr(row, "state", "") or ""),
        "magic": _int(getattr(row, "magic", 0)),
        "comment": str(getattr(row, "comment", "") or ""),
        "placedAt": _int(getattr(row, "time_setup", 0)),
        "expiresAt": _int(getattr(row, "time_expiration", 0)),
    }


def _retcode(code: int) -> tuple[str, str]:
    return _RETCODE.get(int(code), ("UNKNOWN", f"the broker returned retcode {code}"))


def _symbol_trade_mode(info: Any) -> str:
    return _SYMBOL_TRADE_MODE.get(_int(getattr(info, "trade_mode", -1), -1), "unknown")


def _notional(volume: float, info: Any, price: float) -> float:
    contract = _num(getattr(info, "trade_contract_size", 1), 1) or 1.0
    return round(float(volume) * contract * float(price), 6)


def _own_margin(account_margin: Any, check_margin: Any) -> float:
    """The margin THIS order adds, not the account total after it.

    `order_check().margin` is reported as the account's margin once the order
    fills. Comparing that total with a mandate's cap refuses a valid small order
    whenever other positions are already open (on this demo: 113.74 total for a
    0.01 XAUUSD lot that only needed 40.00). A reducing order adds nothing, so
    the increment is floored at zero and can never turn negative.
    """
    before = _num(account_margin, 0)
    after = _num(check_margin, 0)
    return round(max(after - before, 0.0), 2)


def _symbol_quote_dict(symbol: str, info: Any, tick: Any) -> dict[str, Any]:
    bid = _num(getattr(tick, "bid", 0))
    ask = _num(getattr(tick, "ask", 0))
    point = _num(getattr(info, "point", 0))
    spread = (ask - bid) / point if point > 0 and ask > 0 and bid > 0 else None
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "last": _num(getattr(tick, "last", 0)),
        "spreadPoints": round(spread, 2) if spread is not None else None,
        "digits": _int(getattr(info, "digits", 0)),
        "point": point,
        "volumeMin": _num(getattr(info, "volume_min", 0)),
        "volumeMax": _num(getattr(info, "volume_max", 0)),
        "volumeStep": _num(getattr(info, "volume_step", 0)),
        "stopsLevelPoints": _int(getattr(info, "trade_stops_level", 0)),
        "tradeMode": _symbol_trade_mode(info),
        "contractSize": _num(getattr(info, "trade_contract_size", 0)),
        "tickSize": _num(getattr(info, "trade_tick_size", 0)),
        "serverTimeMs": _int(getattr(tick, "time_msc", 0)),
        "retrievedAt": time.time(),
        "provider": "metatrader5",
    }


def _row_value(row: Any, key: str, default: Any = 0) -> Any:
    """Read a `copy_rates_*` field from a numpy record, dict or object."""
    try:
        return row[key]
    except Exception:  # noqa: BLE001
        return getattr(row, key, default)


def _bars_from_rates(rates: Any) -> list[dict[str, Any]]:
    """Normalize MT5's structured OHLCV rows into plain JSON-safe bars."""
    bars: list[dict[str, Any]] = []
    if rates is None:
        return bars
    for row in rates:
        bars.append({
            "time": _int(_row_value(row, "time")),
            "open": _num(_row_value(row, "open")),
            "high": _num(_row_value(row, "high")),
            "low": _num(_row_value(row, "low")),
            "close": _num(_row_value(row, "close")),
            "tickVolume": _int(_row_value(row, "tick_volume")),
            "spreadPoints": _int(_row_value(row, "spread")),
        })
    return bars


_SESSION_START_ATTRS = ("from", "session_from", "date_from", "start")
_SESSION_END_ATTRS = ("to", "session_to", "date_to", "end")


def _first_clock(row: Any, names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        value = getattr(row, name, None)
        if isinstance(value, _datetime):
            return value.strftime("%H:%M")
        if isinstance(value, _clock_time):
            return value.strftime("%H:%M")
    return None


def _session_rows(mt5: Any, symbol: str) -> tuple[list[dict[str, Any]], str]:
    """Best-effort broker TRADE session table, or ([], reason).

    The MetaTrader5 Python package does not reliably expose session windows: the
    functions exist in some builds and return nothing for many symbols (reported
    to MetaQuotes). This never guesses — a boundary that is not a clock value is
    skipped, and an empty table is reported with its reason so the caller falls
    back to its explicit UTC window. Days are normalized to 0=Monday.
    """
    fetch = getattr(mt5, "symbol_info_session_trade", None)
    if not callable(fetch):
        return [], "this MetaTrader5 build does not expose symbol sessions"
    rows: list[dict[str, Any]] = []
    for day in range(7):
        for index in range(8):
            try:
                row = fetch(symbol, day, index)
            except Exception:  # noqa: BLE001 - an unsupported call is not a broker fact
                row = None
            if row is None:
                break
            start = _first_clock(row, _SESSION_START_ATTRS)
            end = _first_clock(row, _SESSION_END_ATTRS)
            if start is None or end is None:
                continue
            rows.append({
                "day": (int(day) + 6) % 7,  # MT5: 0=Sunday -> ours: 0=Monday
                "from": start,
                "to": end,
            })
    return rows, "" if rows else "the terminal reported no trade sessions for this symbol"
