"""Read-only Binance adapter (spot).

Binance signs a query string, not a canonical request: the payload is
`<query>&signature=<hmac_sha256(secret, query)>`, sent with `X-MBX-APIKEY`. Public
endpoints (ticker price) take no signature at all, so `_request(signed=False)` is
a first-class path rather than a special case.

Declared limits, so nothing is invented:

  * **Spot only.** There are no margin or futures *positions*; `positions()`
    reports non-zero **balances**, with `currentPrice`/`profit` left at 0 because
    the adapter does not fetch a price per asset to mark them (that would be
    N calls per snapshot and a silent failure mode).
  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**

Config (all non-secret): `baseUrl` (default https://api.binance.com),
`credentialRef` naming an env var/secret holding `API_KEY:SECRET`.
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
from ..model import KIND_BINANCE
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_query(secret: str, query: str) -> str:
    """Binance's signature: hex HMAC-SHA256 over the query string."""
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


class BinanceAdapter(BrokerAdapter):
    kind = KIND_BINANCE

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="BINANCE_CREDENTIALS",
            label="Binance API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "BINANCE_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.binance.com"),
            code="BINANCE_CONFIG",
            label="Binance baseUrl",
        )

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *, signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        headers = {"Accept": "application/json"}
        if signed:
            key, secret = self._credentials()
            if query:
                query += "&"
            query += f"timestamp={int(time.time() * 1000)}"
            query += f"&signature={sign_query(secret, query)}"
            headers["X-MBX-APIKEY"] = key
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("BINANCE_UNAUTHORIZED", "Binance rejected the API key") from exc
            if exc.code == 418:
                raise AdapterUnavailable("BINANCE_IP_BANNED", "Binance banned this IP") from exc
            if exc.code == 429:
                raise AdapterUnavailable("BINANCE_RATE_LIMITED", "Binance rate limit reached") from exc
            if exc.code == 451:
                raise AdapterUnavailable(
                    "BINANCE_RESTRICTED",
                    "Binance refused the request from this jurisdiction (HTTP 451)",
                ) from exc
            raise AdapterUnavailable("BINANCE_HTTP", f"Binance returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("BINANCE_UNREACHABLE", "Binance is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BINANCE_TIMEOUT", "Binance timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("BINANCE_BAD_JSON", "Binance returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise AdapterUnavailable(
                "BINANCE_API_ERROR",
                f"Binance error {payload.get('code')}: {payload.get('msg') or 'unknown'}",
            )
        return payload

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
        payload = self._request("/api/v3/account")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BINANCE_BAD_RESPONSE", "Binance returned no account")
        balances = [row for row in payload.get("balances") or [] if isinstance(row, dict)]
        total = 0.0
        for row in balances:
            total += _num(row.get("free")) + _num(row.get("locked"))
        return {
            "login": 0,
            "mode": "live",
            "server": "binance",
            "company": "Binance",
            "currency": "USD",
            "balance": total,
            "equity": total,
            "margin": 0.0,
            "marginFree": total,
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": "spot",
            "tradeAllowed": bool(payload.get("canTrade")),
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        payload = self._request("/api/v3/account")
        rows = payload.get("balances") if isinstance(payload, dict) else None
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            quantity = _num(row.get("free")) + _num(row.get("locked"))
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("asset") or "").upper(),
                "side": "buy",
                "volume": quantity,
                "openPrice": 0.0,     # not derived: the adapter does not price assets
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "binance spot balance (not marked to market)",
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._request("/api/v3/openOrders")
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            out.append({
                "ticket": str(row.get("orderId") or ""),
                "symbol": str(row.get("symbol") or "").upper(),
                "type": str(row.get("type") or ""),
                "volumeCurrent": _num(row.get("origQty")) - _num(row.get("executedQty")),
                "openPrice": _num(row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": f"binance {str(row.get('side') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("time"))),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("BINANCE_SYMBOL", "a symbol is required")
        row = self._request("/api/v3/ticker/price", {"symbol": pair}, signed=False)
        if not isinstance(row, dict) or not row.get("price"):
            raise AdapterUnavailable("BINANCE_NO_QUOTE", f"Binance has no price for {pair}")
        last = _num(row.get("price"))
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": last,
            "ask": last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "binance",
        }


__all__ = ["BinanceAdapter", "sign_query"]
