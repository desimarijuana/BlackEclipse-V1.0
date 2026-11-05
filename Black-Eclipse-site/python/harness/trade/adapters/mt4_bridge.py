"""Read-only MetaTrader 4 (and generic) HTTP bridge adapter.

MT4 has no supported local Python IPC, so the supported shape is a small bridge
the operator already runs next to the terminal. The bridge owns credentials and
the terminal connection; Eclipse only speaks this read-only JSON contract:

    GET {bridgeUrl}/account
    GET {bridgeUrl}/positions
    GET {bridgeUrl}/orders
    GET {bridgeUrl}/orders/{ticket}
    GET {bridgeUrl}/quote?symbol=EURUSD
    GET {bridgeUrl}/deals?from=<epoch_ms>&to=<epoch_ms>

Every response is JSON. Lists may be a bare array or wrapped as
`{"positions": [...]}`, `{"orders": [...]}` or `{"deals": [...]}`. The account
and quote shapes mirror `BrokerAccount`/`BrokerQuote` in the rest of the trade
layer. `bridgeSecretRef` is a NAME (an environment variable, or a
`secret://...` vault reference), never a value; when set it is sent as
`Authorization: Bearer <value>`.

This adapter is deliberately NOT a `TradingAdapter`: there is no order path.
Adding execution to a bridge would be a separate, separately-authorized feature.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_MT4_BRIDGE

_TIMEOUT_SECONDS = 10
_MAX_BODY_BYTES = 2_000_000


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number and number not in (float("inf"), float("-inf")) else fallback


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_secret(config: dict[str, Any]) -> Optional[str]:
    ref = _text(config.get("bridgeSecretRef"))
    if not ref:
        return None
    if ref.startswith("secret://"):
        try:
            from ...security.secrets import build_default_secrets_manager

            return build_default_secrets_manager().resolve(
                ref,
                consumer="trade",
                action="read",
                resource="broker_bridge",
                require_grant=False,
            )
        except Exception as exc:  # noqa: BLE001 - a missing secret is a named refusal
            raise AdapterUnavailable(
                "BRIDGE_SECRET",
                f"the bridge secret reference {ref!r} could not be resolved",
            ) from exc
    # A bare name is an environment variable name. The value is never stored in
    # the connection config.
    value = os.environ.get(ref)
    if value is None:
        raise AdapterUnavailable(
            "BRIDGE_SECRET",
            f"environment variable {ref!r} for the bridge secret is not set",
        )
    return value


def _base_url(config: dict[str, Any]) -> str:
    raw = _text(config.get("bridgeUrl")).rstrip("/")
    if not raw:
        raise AdapterUnavailable(
            "BRIDGE_CONFIG",
            "bridgeUrl is required (for example http://127.0.0.1:8090)",
        )
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AdapterUnavailable("BRIDGE_CONFIG", "bridgeUrl must be an http(s) URL")
    return raw


class MT4BridgeAdapter(BrokerAdapter):
    kind = KIND_MT4_BRIDGE

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        # The adapter itself is stdlib-only. Whether a bridge answers is a
        # connection-level fact, reported by `probe()`.
        return True, None

    # ── HTTP ─────────────────────────────────────────────────────────────────
    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = _base_url(self.config) + path
        if params:
            clean = {key: value for key, value in params.items() if value is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        headers = {"Accept": "application/json"}
        secret = _resolve_secret(self.config)
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = response.read(_MAX_BODY_BYTES)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise AdapterUnavailable(
                "BRIDGE_HTTP",
                f"the MT4 bridge returned HTTP {exc.code}",
            ) from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable(
                "BRIDGE_UNREACHABLE",
                f"the MT4 bridge at {_base_url(self.config)} is unreachable",
            ) from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BRIDGE_TIMEOUT", "the MT4 bridge timed out") from exc
        try:
            return json.loads(body or b"{}")
        except ValueError as exc:
            raise AdapterUnavailable(
                "BRIDGE_BAD_JSON",
                "the MT4 bridge did not return valid JSON",
            ) from exc

    @staticmethod
    def _list(payload: Any, key: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    # ── BrokerAdapter ────────────────────────────────────────────────────────
    def probe(self) -> dict[str, Any]:
        try:
            account = self.account()
        except AdapterUnavailable as exc:
            return {
                "available": True,
                "connected": False,
                "code": exc.code,
                "reason": exc.reason,
                "terminal": {"bridge": _text(self.config.get("bridgeUrl"))},
                "account": None,
                "warnings": [],
            }
        return {
            "available": True,
            "connected": True,
            "code": None,
            "reason": None,
            "terminal": {"bridge": _text(self.config.get("bridgeUrl"))},
            "account": account,
            "warnings": [],
        }

    def account(self) -> dict[str, Any]:
        payload = self._get("/account")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BRIDGE_BAD_RESPONSE", "the bridge returned no account object")
        row = payload.get("account") if isinstance(payload.get("account"), dict) else payload
        return {
            "login": _int(row.get("login")),
            "mode": _text(row.get("mode") or "unknown"),
            "server": _text(row.get("server")),
            "company": _text(row.get("company") or "MT4 bridge"),
            "currency": _text(row.get("currency") or "USD"),
            "balance": _num(row.get("balance")),
            "equity": _num(row.get("equity")),
            "margin": _num(row.get("margin")),
            "marginFree": _num(row.get("marginFree")),
            "marginLevel": _num(row.get("marginLevel")),
            "profit": _num(row.get("profit")),
            "leverage": _num(row.get("leverage")),
            "marginMode": _text(row.get("marginMode") or "unknown"),
            "tradeAllowed": bool(row.get("tradeAllowed", False)),
            "expertAllowed": bool(row.get("expertAllowed", False)),
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._list(self._get("/positions"), "positions")
        return [
            {
                "ticket": _int(row.get("ticket")),
                "symbol": _text(row.get("symbol")).upper(),
                "side": _text(row.get("side")).lower(),
                "volume": _num(row.get("volume")),
                "openPrice": _num(row.get("openPrice")),
                "currentPrice": _num(row.get("currentPrice")),
                "stopLoss": None if row.get("stopLoss") in (None, "", 0) else _num(row.get("stopLoss")),
                "takeProfit": None if row.get("takeProfit") in (None, "", 0) else _num(row.get("takeProfit")),
                "profit": _num(row.get("profit")),
                "swap": _num(row.get("swap")),
                "magic": _int(row.get("magic")),
                "comment": _text(row.get("comment")),
                "openedAt": _int(row.get("openedAt")),
            }
            for row in rows
        ]

    def orders(self) -> list[dict[str, Any]]:
        rows = self._list(self._get("/orders"), "orders")
        return [
            {
                "ticket": _int(row.get("ticket")),
                "symbol": _text(row.get("symbol")).upper(),
                "type": _text(row.get("type")),
                "volumeCurrent": _num(row.get("volumeCurrent")),
                "openPrice": _num(row.get("openPrice")),
                "currentPrice": _num(row.get("currentPrice")),
                "stopLoss": None if row.get("stopLoss") in (None, "", 0) else _num(row.get("stopLoss")),
                "takeProfit": None if row.get("takeProfit") in (None, "", 0) else _num(row.get("takeProfit")),
                "state": _text(row.get("state")),
                "magic": _int(row.get("magic")),
                "comment": _text(row.get("comment")),
                "placedAt": _int(row.get("placedAt")),
            }
            for row in rows
        ]

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = _text(symbol)
        payload = self._get("/quote", {"symbol": requested})
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BRIDGE_BAD_RESPONSE", "the bridge returned no quote object")
        row = payload.get("quote") if isinstance(payload.get("quote"), dict) else payload
        return {
            "symbol": _text(row.get("symbol") or requested).upper(),
            "requestedSymbol": requested,
            "bid": _num(row.get("bid")),
            "ask": _num(row.get("ask")),
            "last": _num(row.get("last")),
            "spreadPoints": None if row.get("spreadPoints") is None else _num(row.get("spreadPoints")),
            "digits": _int(row.get("digits")),
            "point": _num(row.get("point")),
            "stopsLevelPoints": _int(row.get("stopsLevelPoints")),
            "serverTimeMs": _int(row.get("serverTimeMs")) or int(time.time() * 1000),
            "provider": "mt4_bridge",
        }

    def order_status(self, ticket: int) -> dict[str, Any]:
        payload = self._get(f"/orders/{int(ticket)}")
        if not isinstance(payload, dict):
            return {"found": False, "ticket": int(ticket)}
        row = payload.get("order") if isinstance(payload.get("order"), dict) else payload
        if not row:
            return {"found": False, "ticket": int(ticket)}
        return {
            "found": True,
            "ticket": _int(row.get("ticket"), int(ticket)),
            "state": _int(row.get("state")),
            "stateName": _text(row.get("stateName")),
        }

    # ── reconciliation ───────────────────────────────────────────────────────
    def _deals(self, from_ms: int, to_ms: int) -> list[dict[str, Any]]:
        payload = self._get("/deals", {"from": int(from_ms), "to": int(to_ms)})
        rows = self._list(payload, "deals")
        magic = _int(self.config.get("magic"))
        out: list[dict[str, Any]] = []
        for row in rows:
            symbol = _text(row.get("symbol")).upper()
            if not symbol:
                continue
            deal_magic = _int(row.get("magic"))
            out.append(
                {
                    "dealTicket": _int(row.get("dealTicket")),
                    "orderTicket": _int(row.get("orderTicket")) or None,
                    "positionTicket": _int(row.get("positionTicket")) or None,
                    "symbol": symbol,
                    "side": _text(row.get("side")).lower(),
                    "entry": _text(row.get("entry")).lower() or "unknown",
                    "volume": _num(row.get("volume")),
                    "price": _num(row.get("price")),
                    "commission": _num(row.get("commission")),
                    "swap": _num(row.get("swap")),
                    "profit": _num(row.get("profit")),
                    "magic": deal_magic,
                    "comment": _text(row.get("comment")),
                    "dealtAt": _int(row.get("dealtAt")),
                    "eclipseOwned": bool(magic and deal_magic == magic),
                }
            )
        return out

    def deals_since(self, since_ms: int) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        from_ms = int(since_ms or 0)
        if from_ms <= 0:
            # No cursor means an incremental read, not "everything since 1970".
            from_ms = now - 7 * 86_400_000
        return self._deals(from_ms, now + 2 * 86_400_000)

    def deals_window(self, days: int) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days or 7), 3650))
        now = int(time.time() * 1000)
        return self._deals(now - safe_days * 86_400_000, now + 2 * 86_400_000)


__all__ = ["MT4BridgeAdapter"]
