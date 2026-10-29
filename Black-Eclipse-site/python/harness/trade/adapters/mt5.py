"""MetaTrader 5 read-only adapter (Windows, local IPC).

The official `MetaTrader5` package talks to a running `terminal64.exe`; it is not
a REST API and there is no API key. In the preferred ATTACH mode the operator has
already logged the terminal into a demo (or live) account, and Eclipse passes no
credentials at all.

P0 implements only reads. `order_send` is deliberately absent: live execution is a
separate, approval-gated phase. A missing package, terminal, login or broker
connection is reported with a distinct code, never as an empty account.
"""

from __future__ import annotations

import os
import math
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

from ..adapter import AdapterUnavailable, TradingAdapter
from ..model import KIND_MT5

_MODULE: Any = None
_IMPORT_ERROR: Optional[str] = None
# MT5's Python API is not safe to initialize concurrently from several threads.
# The agent can issue parallel broker tool calls, so every session/probe is
# serialized. This lock is process-wide (one terminal connection per process).
_MT5_LOCK = threading.Lock()

_TERMINAL_CANDIDATES = (
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\MetaTrader 5 IC Markets\terminal64.exe",
    r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
)

_TRADE_MODE = {0: "demo", 1: "contest", 2: "real"}
_MARGIN_MODE = {0: "netting", 1: "exchange", 2: "hedging"}
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

#: MetaTrader's `order_send` retcodes. Only 10008/10009/10010 are fills.
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

#: `mt5.last_error()` codes that name an actionable cause.
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


def _import_mt5() -> Any:
    global _MODULE, _IMPORT_ERROR
    if _MODULE is not None:
        return _MODULE
    if sys.platform != "win32":
        raise AdapterUnavailable(
            "PLATFORM_UNSUPPORTED",
            "the MetaTrader5 Python API is Windows-only; run the runtime on Windows",
        )
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - a missing package is a supported state
        _IMPORT_ERROR = str(exc)
        raise AdapterUnavailable(
            "PACKAGE_MISSING",
            "the MetaTrader5 package is not installed; run "
            "`pip install MetaTrader5` in the Eclipse Python environment",
        ) from exc
    _MODULE = mt5
    return mt5


def _last_error(mt5: Any) -> tuple[Optional[int], str]:
    try:
        code, description = mt5.last_error()
        return int(code), str(description or "")
    except Exception:  # noqa: BLE001 - diagnostics must never mask the real failure
        return None, ""


def _ipc_error(mt5: Any, fallback: str) -> AdapterUnavailable:
    code, description = _last_error(mt5)
    name, reason = _IPC_ERRORS.get(code, ("MT5_UNAVAILABLE", description or fallback))
    return AdapterUnavailable(name, reason, detail={"mt5Code": code})


def _terminal_path(config: dict[str, Any]) -> Optional[str]:
    explicit = str(config.get("terminalPath") or os.environ.get("MT5_TERMINAL_PATH") or "").strip()
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for candidate in _TERMINAL_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("terminal64.exe")
    return found or None


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


def _filling_mode(mt5: Any, info: Any, order_type: str = "market") -> tuple[int, list[str]]:
    """Pick an allowed filling mode; never guess one blindly.

    MT5 exposes the *symbol's* allowed modes as a bitmask (`1=FOK, 2=IOC,
    4=BOC`). BOC is book-only and is not a market-execution mode.
    """
    flags = _int(getattr(info, "filling_mode", 0), 0)
    fok = _int(getattr(mt5, "ORDER_FILLING_FOK", 0), 0)
    ioc = _int(getattr(mt5, "ORDER_FILLING_IOC", 1), 1)
    ret = _int(getattr(mt5, "ORDER_FILLING_RETURN", 2), 2)
    boc = _int(getattr(mt5, "ORDER_FILLING_BOC", 3), 3)
    if flags & 1:
        return fok, []
    if flags & 2:
        return ioc, []
    if flags & 4:
        if order_type in ("limit", "stop"):
            return boc, []
        return ret, [
            "this symbol only advertises book-only filling; market orders are not available"
        ]
    return ret, ["the symbol reports no permitted filling mode"]


def _normalise_volume(info: Any, volume: float) -> tuple[float, list[str]]:
    """Volume must already be a valid step. Resizing silently would break the approval."""
    reasons: list[str] = []
    try:
        requested = float(volume)
    except (TypeError, ValueError):
        return 0.0, ["volume must be a number"]
    step = _num(getattr(info, "volume_step", 0), 0) or 0.01
    minimum = _num(getattr(info, "volume_min", 0), 0) or step
    maximum = _num(getattr(info, "volume_max", 0), 0)
    steps = math.floor(requested / step + 1e-9)
    normalised = round(steps * step, 8)
    if abs(normalised - requested) > 1e-8:
        reasons.append(
            f"volume {requested:g} is not a multiple of this symbol's step {step:g}"
        )
    if normalised < minimum - 1e-9:
        reasons.append(f"volume {requested:g} is below this symbol's minimum {minimum:g}")
    if maximum > 0 and normalised > maximum + 1e-9:
        reasons.append(f"volume {requested:g} is above this symbol's maximum {maximum:g}")
    return normalised, reasons


def _stops_reasons(
    side: str, price: float, point: float, stops_level: int,
    stop_loss: Optional[float], take_profit: Optional[float],
) -> list[str]:
    reasons: list[str] = []
    distance = max(0.0, float(stops_level or 0) * (point or 0))
    if side == "buy":
        if stop_loss is not None and stop_loss > price - distance + 1e-12:
            reasons.append(
                f"stop loss must be at least {distance:g} below the entry price"
            )
        if take_profit is not None and take_profit < price + distance - 1e-12:
            reasons.append(
                f"take profit must be at least {distance:g} above the entry price"
            )
    else:
        if stop_loss is not None and stop_loss < price + distance - 1e-12:
            reasons.append(
                f"stop loss must be at least {distance:g} above the entry price"
            )
        if take_profit is not None and take_profit > price - distance + 1e-12:
            reasons.append(
                f"take profit must be at least {distance:g} below the entry price"
            )
    return reasons


def _build_request(
    mt5: Any, intent: Any, info: Any, tick: Any, filling: int,
) -> tuple[Optional[dict[str, Any]], list[str], float]:
    """Build the exact `order_send` request and validate what the broker forbids."""
    reasons: list[str] = []
    side = str(intent.side)
    order_type = str(intent.order_type)
    bid = _num(getattr(tick, "bid", 0))
    ask = _num(getattr(tick, "ask", 0))
    if bid <= 0 or ask <= 0:
        return None, ["the broker returned no usable bid/ask"], 0.0
    price_ref = ask if side == "buy" else bid

    trade_mode = _symbol_trade_mode(info)
    if trade_mode == "disabled":
        reasons.append("this symbol is disabled for trading")
    elif trade_mode == "close_only":
        reasons.append("this symbol only allows closing positions")
    elif trade_mode == "long_only" and side == "sell":
        reasons.append("this symbol only allows buy orders")
    elif trade_mode == "short_only" and side == "buy":
        reasons.append("this symbol only allows sell orders")

    request: dict[str, Any] = {
        "symbol": str(getattr(info, "name", "") or ""),
        "volume": float(intent.volume),
        "deviation": int(intent.deviation_points),
        "magic": int(intent.magic),
        "comment": str(intent.comment)[:31],
        "type_time": (
            _int(getattr(mt5, "ORDER_TIME_DAY", 1), 1)
            if intent.time_in_force == "day"
            else _int(getattr(mt5, "ORDER_TIME_GTC", 0), 0)
        ),
        "type_filling": filling,
    }
    if intent.stop_loss is not None:
        request["sl"] = float(intent.stop_loss)
    if intent.take_profit is not None:
        request["tp"] = float(intent.take_profit)

    if order_type == "market":
        request["action"] = _int(getattr(mt5, "TRADE_ACTION_DEAL", 1), 1)
        request["type"] = (
            _int(getattr(mt5, "ORDER_TYPE_BUY", 0), 0)
            if side == "buy"
            else _int(getattr(mt5, "ORDER_TYPE_SELL", 1), 1)
        )
        request["price"] = price_ref
    else:
        request["action"] = _int(getattr(mt5, "TRADE_ACTION_PENDING", 5), 5)
        if order_type == "limit":
            request["type"] = (
                _int(getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2), 2)
                if side == "buy"
                else _int(getattr(mt5, "ORDER_TYPE_SELL_LIMIT", 3), 3)
            )
        else:
            request["type"] = (
                _int(getattr(mt5, "ORDER_TYPE_BUY_STOP", 4), 4)
                if side == "buy"
                else _int(getattr(mt5, "ORDER_TYPE_SELL_STOP", 5), 5)
            )
        request["price"] = float(intent.price or 0)
        if order_type == "limit":
            if side == "buy" and request["price"] >= ask:
                reasons.append("a buy limit must be below the current ask")
            if side == "sell" and request["price"] <= bid:
                reasons.append("a sell limit must be above the current bid")
        else:
            if side == "buy" and request["price"] <= ask:
                reasons.append("a buy stop must be above the current ask")
            if side == "sell" and request["price"] >= bid:
                reasons.append("a sell stop must be below the current bid")

    reasons.extend(_stops_reasons(
        side,
        float(request["price"]),
        _num(getattr(info, "point", 0)),
        _int(getattr(info, "trade_stops_level", 0)),
        intent.stop_loss,
        intent.take_profit,
    ))
    return request, reasons, float(request["price"])


def _notional(volume: float, info: Any, price: float) -> float:
    contract = _num(getattr(info, "trade_contract_size", 1), 1) or 1.0
    return round(float(volume) * contract * float(price), 6)


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
        "serverTimeMs": _int(getattr(tick, "time_msc", 0)),
        "retrievedAt": time.time(),
        "provider": "metatrader5",
    }


class MT5Adapter(TradingAdapter):
    kind = KIND_MT5

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        if sys.platform != "win32":
            return False, "the MetaTrader5 Python API is Windows-only"
        try:
            _import_mt5()
        except AdapterUnavailable as exc:
            return False, exc.reason
        return True, None

    # ── session ──────────────────────────────────────────────────────────────
    @contextmanager
    def _session(self) -> Iterator[Any]:
        mt5 = _import_mt5()
        path = _terminal_path(self.config)
        if path is None:
            raise AdapterUnavailable(
                "TERMINAL_NOT_FOUND",
                "no terminal64.exe was found; set the terminal path in Settings › "
                "Trading (or MT5_TERMINAL_PATH)",
            )
        kwargs: dict[str, Any] = {"path": path, "timeout": 10_000}
        if bool(self.config.get("portable")):
            kwargs["portable"] = True
        _MT5_LOCK.acquire()
        try:
            try:
                initialized = mt5.initialize(**kwargs)
            except Exception as exc:  # noqa: BLE001 - the package raises on some builds
                raise AdapterUnavailable(
                    "IPC_FAILED", f"MetaTrader 5 initialization failed: {exc}"
                ) from exc
            if not initialized:
                raise _ipc_error(mt5, "MetaTrader 5 initialization failed")
            try:
                yield mt5
            finally:
                try:
                    mt5.shutdown()
                except Exception:  # noqa: BLE001 - shutdown is best-effort
                    pass
        finally:
            _MT5_LOCK.release()

    def _require_account(self, mt5: Any) -> Any:
        info = mt5.account_info()
        if info is None:
            raise AdapterUnavailable(
                "NOT_LOGGED_IN",
                "the MetaTrader 5 terminal is running but not logged in to an account",
                detail={"mt5Code": _last_error(mt5)[0]},
            )
        return info

    def _resolve_symbol(self, mt5: Any, symbol: str) -> str:
        requested = str(symbol or "").strip()
        if not requested:
            raise AdapterUnavailable("SYMBOL_REQUIRED", "a symbol is required")
        mapping = self.config.get("symbolMap") or {}
        if isinstance(mapping, dict) and mapping.get(requested):
            return str(mapping[requested])
        symbols = mt5.symbols_get() or ()
        names = [str(getattr(item, "name", "") or "") for item in symbols]
        for name in names:
            if name == requested:
                return name
        lowered = requested.upper()
        for name in names:
            if name.upper() == lowered:
                return name
        for name in names:
            if name.upper().startswith(lowered) or name.upper().endswith(lowered):
                return name
        raise AdapterUnavailable(
            "SYMBOL_NOT_FOUND",
            f"{requested!r} is not offered by this broker; set a symbol mapping",
            detail={"candidates": [n for n in names if lowered[:3] in n.upper()][:10]},
        )

    # ── contract ─────────────────────────────────────────────────────────────
    def probe(self) -> dict[str, Any]:
        """Test the connection with the MT5 IPC lock held (never concurrent)."""
        with _MT5_LOCK:
            return self._probe_locked()

    def _probe_locked(self) -> dict[str, Any]:
        mt5 = _import_mt5()
        path = _terminal_path(self.config)
        if path is None:
            return {
                "available": False,
                "connected": False,
                "code": "TERMINAL_NOT_FOUND",
                "reason": "no terminal64.exe was found on this machine",
                "terminalPath": None,
                "terminal": None,
                "account": None,
                "warnings": [],
            }
        kwargs: dict[str, Any] = {"path": path, "timeout": 10_000}
        if bool(self.config.get("portable")):
            kwargs["portable"] = True
        try:
            initialized = mt5.initialize(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return {
                "available": False,
                "connected": False,
                "code": "IPC_FAILED",
                "reason": f"MetaTrader 5 initialization failed: {exc}",
                "terminalPath": path,
                "terminal": None,
                "account": None,
                "warnings": [],
            }
        if not initialized:
            failure = _ipc_error(mt5, "MetaTrader 5 initialization failed")
            return {
                "available": False,
                "connected": False,
                "code": failure.code,
                "reason": failure.reason,
                "terminalPath": path,
                "terminal": None,
                "account": None,
                "warnings": [],
                **failure.detail,
            }
        try:
            terminal_info = mt5.terminal_info()
            terminal = _terminal_dict(terminal_info) if terminal_info is not None else None
            account_info = mt5.account_info()
            account = _account_dict(account_info) if account_info is not None else None
            warnings: list[str] = []
            if terminal is not None and not terminal["connected"]:
                warnings.append("the terminal is not connected to its broker")
            if terminal is not None and not terminal["tradeAllowed"]:
                warnings.append("Algo Trading is disabled in the terminal")
            if account is not None and not account["tradeAllowed"]:
                warnings.append("trading is disabled for this account")
            payload: dict[str, Any] = {
                "available": account is not None,
                "connected": bool(terminal and terminal["connected"]),
                "code": None if account is not None else "NOT_LOGGED_IN",
                "reason": None if account is not None else (
                    "the terminal is running but no account is logged in"
                ),
                "terminalPath": path,
                "terminal": terminal,
                "account": account,
                "warnings": warnings,
            }
            return payload
        finally:
            try:
                mt5.shutdown()
            except Exception:  # noqa: BLE001
                pass

    def account(self) -> dict[str, Any]:
        with self._session() as mt5:
            return _account_dict(self._require_account(mt5))

    def positions(self) -> list[dict[str, Any]]:
        with self._session() as mt5:
            self._require_account(mt5)
            rows = mt5.positions_get()
            if rows is None:
                code, description = _last_error(mt5)
                if code:
                    raise _ipc_error(mt5, "positions_get returned no rows")
                return []
            return [_position_dict(row) for row in rows]

    def orders(self) -> list[dict[str, Any]]:
        with self._session() as mt5:
            self._require_account(mt5)
            rows = mt5.orders_get()
            if rows is None:
                code, description = _last_error(mt5)
                if code:
                    raise _ipc_error(mt5, "orders_get returned no rows")
                return []
            return [_order_dict(row) for row in rows]

    def quote(self, symbol: str) -> dict[str, Any]:
        with self._session() as mt5:
            self._require_account(mt5)
            resolved = self._resolve_symbol(mt5, symbol)
            info = mt5.symbol_info(resolved)
            tick = mt5.symbol_info_tick(resolved)
            if info is None or tick is None:
                raise AdapterUnavailable(
                    "SYMBOL_NOT_FOUND",
                    f"no live tick for {resolved!r}",
                )
            payload = _symbol_quote_dict(resolved, info, tick)
            payload["requestedSymbol"] = symbol
            return payload

    # ── P1 demo execution ────────────────────────────────────────────────────
    def order_preview(self, intent: Any) -> dict[str, Any]:
        """Normalize, validate and run the broker's own `order_check` (no send)."""
        with self._session() as mt5:
            account = _account_dict(self._require_account(mt5))
            resolved = self._resolve_symbol(mt5, intent.symbol)
            info = mt5.symbol_info(resolved)
            tick = mt5.symbol_info_tick(resolved)
            if info is None or tick is None:
                raise AdapterUnavailable(
                    "SYMBOL_NOT_FOUND", f"no live tick for {resolved!r}"
                )
            volume, reasons = _normalise_volume(info, intent.volume)
            normalised_intent = intent
            if abs(volume - float(intent.volume)) > 1e-8:
                normalised_intent = type(intent)(
                    **{**intent.__dict__, "volume": volume}
                )
            filling, fill_reasons = _filling_mode(mt5, info, intent.order_type)
            request, build_reasons, price = _build_request(
                mt5, normalised_intent, info, tick, filling
            )
            reasons = reasons + fill_reasons + build_reasons
            quote = _symbol_quote_dict(resolved, info, tick)
            positions = mt5.positions_get() or ()
            terminal = mt5.terminal_info()
            preview: dict[str, Any] = {
                "ok": False,
                "symbol": resolved,
                "requestedSymbol": intent.symbol,
                "side": intent.side,
                "type": intent.order_type,
                "volume": volume,
                "price": price,
                "notional": _notional(volume, info, price),
                "margin": None,
                "marginFree": account.get("marginFree"),
                "spreadPoints": quote.get("spreadPoints"),
                "openPositions": len(positions),
                "account": account,
                "terminalTradeAllowed": bool(getattr(terminal, "trade_allowed", False)),
                "quote": quote,
                "request": request,
                "retcode": None,
                "retcodeName": None,
                "reasons": reasons,
            }
            if reasons or request is None:
                preview["reasons"] = reasons or ["the order could not be built"]
                return preview
            check = mt5.order_check(request)
            if check is None:
                raise _ipc_error(mt5, "order_send check returned no result")
            code = _int(getattr(check, "retcode", -1), -1)
            name, message = _retcode(code)
            ok = code in _OK_CHECK_RETCODES
            if not ok:
                reasons.append(message)
            preview.update({
                "ok": ok,
                "retcode": code,
                "retcodeName": name,
                "margin": _num(getattr(check, "margin", 0)),
                "marginFree": _num(getattr(check, "margin_free", account.get("marginFree", 0))),
                "balance": _num(getattr(check, "balance", account.get("balance", 0))),
                "equity": _num(getattr(check, "equity", account.get("equity", 0))),
                "checkComment": str(getattr(check, "comment", "") or ""),
                "reasons": reasons,
            })
            return preview

    def submit_order(self, intent: Any) -> dict[str, Any]:
        """Send exactly one order. An ambiguous result is never retried here."""
        with self._session() as mt5:
            account = _account_dict(self._require_account(mt5))
            resolved = self._resolve_symbol(mt5, intent.symbol)
            info = mt5.symbol_info(resolved)
            tick = mt5.symbol_info_tick(resolved)
            if info is None or tick is None:
                raise AdapterUnavailable(
                    "SYMBOL_NOT_FOUND", f"no live tick for {resolved!r}"
                )
            volume, reasons = _normalise_volume(info, intent.volume)
            if abs(volume - float(intent.volume)) > 1e-8:
                raise AdapterUnavailable(
                    "INVALID_VOLUME",
                    f"volume {intent.volume:g} is not a multiple of the symbol's step",
                )
            filling, fill_reasons = _filling_mode(mt5, info, intent.order_type)
            request, build_reasons, _price = _build_request(
                mt5, intent, info, tick, filling
            )
            reasons = reasons + fill_reasons + build_reasons
            if reasons or request is None:
                return {
                    "ok": False,
                    "status": "REFUSED",
                    "symbol": resolved,
                    "retcode": None,
                    "retcodeName": "PREVIEW_REJECTED",
                    "reasons": reasons,
                    "account": account,
                }
            result = mt5.order_send(request)
            if result is None:
                raise _ipc_error(mt5, "order_send returned no result")
            code = _int(getattr(result, "retcode", -1), -1)
            name, message = _retcode(code)
            return {
                "ok": code in _FILLED_RETCODES,
                "status": "FILLED" if code in _FILLED_RETCODES else "REJECTED",
                "symbol": resolved,
                "side": intent.side,
                "type": intent.order_type,
                "volume": _num(getattr(result, "volume", volume)),
                "price": _num(getattr(result, "price", 0)),
                "ticket": _int(getattr(result, "order", 0)),
                "deal": _int(getattr(result, "deal", 0)),
                "retcode": code,
                "retcodeName": name,
                "comment": str(getattr(result, "comment", "") or ""),
                "requestId": _int(getattr(result, "request_id", 0)),
                "reasons": [] if code in _FILLED_RETCODES else [message],
                "account": account,
            }

    def cancel_order(self, ticket: int) -> dict[str, Any]:
        with self._session() as mt5:
            self._require_account(mt5)
            request = {
                "action": _int(getattr(mt5, "TRADE_ACTION_REMOVE", 8), 8),
                "order": int(ticket),
            }
            result = mt5.order_send(request)
            if result is None:
                raise _ipc_error(mt5, "cancel returned no result")
            code = _int(getattr(result, "retcode", -1), -1)
            name, message = _retcode(code)
            ok = code in (10008, 10009)
            return {
                "ok": ok,
                "ticket": int(ticket),
                "retcode": code,
                "retcodeName": name,
                "reasons": [] if ok else [message],
            }

    def cancel_all(self, magic: int) -> dict[str, Any]:
        """Kill switch: cancel only orders Eclipse owns (by magic), never all."""
        if int(magic) <= 0:
            raise AdapterUnavailable(
                "MAGIC_REQUIRED",
                "a non-zero magic is required to cancel Eclipse's orders safely",
            )
        with self._session() as mt5:
            self._require_account(mt5)
            rows = mt5.orders_get() or ()
            targets = [
                row for row in rows
                if _int(getattr(row, "magic", 0), 0) == int(magic)
            ]
            results: list[dict[str, Any]] = []
            cancelled = 0
            for row in targets:
                ticket = _int(getattr(row, "ticket", 0))
                result = mt5.order_send({
                    "action": _int(getattr(mt5, "TRADE_ACTION_REMOVE", 8), 8),
                    "order": ticket,
                })
                code = _int(getattr(result, "retcode", -1), -1) if result else -1
                name, message = _retcode(code)
                ok = code in (10008, 10009)
                cancelled += 1 if ok else 0
                results.append({
                    "ticket": ticket,
                    "retcode": code,
                    "retcodeName": name,
                    "ok": ok,
                    "reason": None if ok else message,
                })
            return {
                "ok": cancelled == len(targets),
                "magic": int(magic),
                "matched": len(targets),
                "cancelled": cancelled,
                "failed": len(targets) - cancelled,
                "results": results,
            }

    # ── reconciliation reads ─────────────────────────────────────────────────
    def deals_since(self, since_ms: int) -> list[dict[str, Any]]:
        """Deals from a wide, server-time-safe window.

        `history_deals_get` expects SERVER time. The Python process clock can be
        hours off (this demo is +2h), so a tight local-time cursor silently drops
        the newest deals. Query a 7-day window with a 2-day future margin and let
        `(connectionId, dealTicket)` dedupe; the cursor is advisory only.
        """
        with self._session() as mt5:
            self._require_account(mt5)
            since = datetime.now() - timedelta(days=7)
            until = datetime.now() + timedelta(days=2)
            rows = mt5.history_deals_get(since, until)
            if rows is None:
                code, _ = _last_error(mt5)
                if code:
                    raise _ipc_error(mt5, "history_deals_get returned no rows")
                return []
            magic = int(self.config.get("magic") or 0)
            out: list[dict[str, Any]] = []
            for row in rows:
                symbol = str(getattr(row, "symbol", "") or "")
                if not symbol:
                    continue
                deal_type = _int(getattr(row, "type", -1), -1)
                entry = _int(getattr(row, "entry", -1), -1)
                deal_magic = _int(getattr(row, "magic", 0), 0)
                out.append({
                    "dealTicket": _int(getattr(row, "ticket", 0)),
                    "orderTicket": _int(getattr(row, "order", 0)),
                    "positionTicket": _int(getattr(row, "position_id", 0)),
                    "symbol": symbol,
                    "side": _DEAL_TYPE.get(deal_type, "other"),
                    "entry": _DEAL_ENTRY.get(entry, "unknown"),
                    "volume": _num(getattr(row, "volume", 0)),
                    "price": _num(getattr(row, "price", 0)),
                    "commission": _num(getattr(row, "commission", 0)),
                    "swap": _num(getattr(row, "swap", 0)),
                    "profit": _num(getattr(row, "profit", 0)),
                    "magic": deal_magic,
                    "comment": str(getattr(row, "comment", "") or ""),
                    "dealtAt": _int(getattr(row, "time_msc", 0)) or (
                        _int(getattr(row, "time", 0)) * 1000
                    ),
                    "eclipseOwned": bool(magic and deal_magic == magic),
                })
            return out

    def order_status(self, ticket: int) -> dict[str, Any]:
        """The broker's latest state for an order ticket (history first)."""
        with self._session() as mt5:
            self._require_account(mt5)
            rows = None
            try:
                rows = mt5.history_orders_get(ticket=int(ticket))
            except Exception:  # noqa: BLE001 - older builds only accept a range
                rows = None
            if not rows:
                try:
                    rows = mt5.orders_get(ticket=int(ticket))
                except Exception:  # noqa: BLE001
                    rows = None
            if not rows:
                return {"found": False, "ticket": int(ticket)}
            row = rows[0]
            state = _int(getattr(row, "state", -1), -1)
            return {
                "found": True,
                "ticket": int(ticket),
                "state": state,
                "stateName": _ORDER_STATE.get(state, "unknown"),
                "symbol": str(getattr(row, "symbol", "") or ""),
                "volumeInitial": _num(getattr(row, "volume_initial", 0)),
                "priceOpen": _num(getattr(row, "price_open", 0)),
            }


__all__ = ["MT5Adapter"]
