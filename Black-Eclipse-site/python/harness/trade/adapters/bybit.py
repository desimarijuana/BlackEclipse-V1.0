"""Read-only Bybit v5 adapter (unified account).

Bybit signs a **prefix**, not the payload alone:

    signature = hex(HMAC-SHA256(secret, timestamp + api_key + recv_window + query))

The query string is the last component *for GET requests*, and the timestamp is
milliseconds. `sign_request` is pure so the exact input can be checked against an
independent computation — the usual mistakes are signature-comma prefixes copied
from v3 and signing the payload instead of the query.

Unlike a spot-only adapter, Bybit v5 reports **real positions** on the linear
category (size, average entry, mark price, unrealised PnL), so `positions()` is a
genuine position list rather than a balance list.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * `retCode != 0` is a refusal with Bybit's own message, never empty data.

Config: `baseUrl` (default https://api.bybit.com), `category` (default `linear`),
`credentialRef` naming an env var/secret holding `KEY:SECRET`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_BYBIT
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15
_RECV_WINDOW = "5000"


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, timestamp: str, api_key: str, query: str,
                 recv_window: str = _RECV_WINDOW) -> str:
    """Bybit v5 `X-BAPI-SIGN`: hex HMAC-SHA256 over ts+key+window+query."""
    message = f"{timestamp}{api_key}{recv_window}{query}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class BybitAdapter(BrokerAdapter):
    kind = KIND_BYBIT

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="BYBIT_CREDENTIALS",
            label="Bybit API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "BYBIT_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.bybit.com"),
            code="BYBIT_CONFIG",
            label="Bybit baseUrl",
        )

    def _category(self) -> str:
        return str(self.config.get("category") or "linear")

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json"}
        if signed:
            key, secret = self._credentials()
            timestamp = str(int(time.time() * 1000))
            headers.update({
                "X-BAPI-API-KEY": key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": _RECV_WINDOW,
                "X-BAPI-SIGN": sign_request(secret, timestamp, key, query),
            })
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("BYBIT_UNAUTHORIZED", "Bybit rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("BYBIT_RATE_LIMITED", "Bybit rate limit reached") from exc
            if exc.code == 451:
                raise AdapterUnavailable("BYBIT_RESTRICTED", "Bybit refused this jurisdiction (451)") from exc
            raise AdapterUnavailable("BYBIT_HTTP", f"Bybit returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("BYBIT_UNREACHABLE", "Bybit is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BYBIT_TIMEOUT", "Bybit timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("BYBIT_BAD_JSON", "Bybit returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BYBIT_BAD_SHAPE", "Bybit returned no envelope")
        if int(payload.get("retCode") or 0) != 0:
            raise AdapterUnavailable(
                "BYBIT_API_ERROR",
                f"Bybit error {payload.get('retCode')}: {payload.get('retMsg') or 'unknown'}",
            )
        return payload.get("result") or {}

    # -- BrokerAdapter ---------------------------------------------------

    def probe(self) -> dict[str, Any]:
        try:
            account = self.account()
        except AdapterUnavailable as exc:
            return {
                "available": True, "connected": False, "code": exc.code,
                "reason": exc.reason, "terminal": {"api": self._base()},
                "account": None, "warnings": [],
            }
        return {
            "available": True, "connected": True, "code": None, "reason": None,
            "terminal": {"api": self._base()}, "account": account, "warnings": [],
        }

    def account(self) -> dict[str, Any]:
        result = self._request("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        rows = result.get("list") if isinstance(result, dict) else None
        wallet = rows[0] if isinstance(rows, list) and rows else {}
        coins = wallet.get("coin") if isinstance(wallet, dict) else None
        equity = total = available = 0.0
        for coin in coins if isinstance(coins, list) else []:
            if not isinstance(coin, dict):
                continue
            equity += _num(coin.get("equity"))
            total += _num(coin.get("walletBalance"))
            available += _num(coin.get("availableToWithdraw"))
        return {
            "login": 0,
            "mode": "live",
            "server": "bybit",
            "company": "Bybit",
            "currency": "USD",
            "balance": total,
            "equity": equity,
            "margin": equity - available,
            "marginFree": available,
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": str(wallet.get("accountType") or "UNIFIED").lower()
            if isinstance(wallet, dict) else "unified",
            "tradeAllowed": False,   # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        result = self._request("/v5/position/list", {"category": self._category()})
        rows = result.get("list") if isinstance(result, dict) else None
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            size = _num(row.get("size"))
            if size == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("symbol") or "").upper(),
                "side": "buy" if str(row.get("side") or "").lower() == "buy" else "sell",
                "volume": size,
                "openPrice": _num(row.get("avgPrice")),
                "currentPrice": _num(row.get("markPrice")),
                "stopLoss": _num(row.get("stopLoss")) or None,
                "takeProfit": _num(row.get("takeProfit")) or None,
                "profit": _num(row.get("unrealisedPnl")),
                "swap": 0.0,
                "magic": 0,
                "comment": f"bybit {self._category()} position",
                "openedAt": int(_num(row.get("createdTime"))),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        result = self._request("/v5/order/realtime", {"category": self._category()})
        rows = result.get("list") if isinstance(result, dict) else None
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            out.append({
                "ticket": str(row.get("orderId") or ""),
                "symbol": str(row.get("symbol") or "").upper(),
                "type": str(row.get("orderType") or ""),
                "volumeCurrent": _num(row.get("qty")) - _num(row.get("cumExecQty")),
                "openPrice": _num(row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("orderStatus") or ""),
                "magic": 0,
                "comment": f"bybit {str(row.get('side') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("createdTime"))),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("BYBIT_SYMBOL", "a symbol is required")
        result = self._request(
            "/v5/market/tickers", {"category": "spot", "symbol": pair}, signed=False)
        rows = result.get("list") if isinstance(result, dict) else None
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, dict) or not row.get("lastPrice"):
            raise AdapterUnavailable("BYBIT_NO_QUOTE", f"Bybit has no ticker for {pair}")
        last = _num(row.get("lastPrice"))
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": _num(row.get("bid1Price")) or last,
            "ask": _num(row.get("ask1Price")) or last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "bybit",
        }


__all__ = ["BybitAdapter", "sign_request"]
