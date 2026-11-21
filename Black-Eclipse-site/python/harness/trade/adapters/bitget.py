"""Read-only Bitget v2 adapter (spot balances + USDT-margined positions).

Bitget signs `timestamp + method + requestPath + body` with **HMAC-SHA256 and then
base64-encodes** the digest (not hex), and needs the API **passphrase** as a
fourth header. `sign_request` is pure so the base64-vs-hex choice and the exact
preimage are checked against an independent computation.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * Bitget answers HTTP 200 with a non-`00000` `code`, so that code is the refusal
    check — an empty `data` list with a bad code is a failure, not "no positions".
  * Mix positions are reported per side exactly as Bitget returns them (size may
    be zero for a closed side and is skipped).

Config: `baseUrl` (default https://api.bitget.com), `productType` (default
`USDT-FUTURES`), `credentialRef` naming an env var/secret holding
`KEY:SECRET:PASSPHRASE`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_BITGET
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, timestamp: str, method: str, path: str, body: str = "") -> str:
    """Bitget's `ACCESS-SIGN`: base64(HMAC-SHA256(secret, ts + method + path + body))."""
    prehash = f"{timestamp}{method.upper()}{path}{body}"
    digest = hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class BitgetAdapter(BrokerAdapter):
    kind = KIND_BITGET

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="BITGET_CREDENTIALS",
            label="Bitget key/secret/passphrase",
        )
        if not raw:
            raise AdapterUnavailable(
                "BITGET_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding "
                "`KEY:SECRET:PASSPHRASE`",
            )
        parts = raw.split(":")
        if len(parts) != 3 or not all(parts):
            raise AdapterUnavailable(
                "BITGET_CREDENTIALS",
                "the credential must be `KEY:SECRET:PASSPHRASE` (three parts)",
            )
        return parts[0], parts[1], parts[2]

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.bitget.com"),
            code="BITGET_CONFIG",
            label="Bitget baseUrl",
        )

    def _product_type(self) -> str:
        return str(self.config.get("productType") or "USDT-FUTURES")

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        request_path = path + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "locale": "en-US"}
        if signed:
            key, secret, passphrase = self._credentials()
            timestamp = str(int(time.time() * 1000))
            headers.update({
                "ACCESS-KEY": key,
                "ACCESS-SIGN": sign_request(secret, timestamp, "GET", request_path),
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": passphrase,
            })
        request = urllib.request.Request(f"{self._base()}{request_path}",
                                         headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("BITGET_UNAUTHORIZED", "Bitget rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("BITGET_RATE_LIMITED", "Bitget rate limit reached") from exc
            raise AdapterUnavailable("BITGET_HTTP", f"Bitget returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("BITGET_UNREACHABLE", "Bitget is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BITGET_TIMEOUT", "Bitget timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("BITGET_BAD_JSON", "Bitget returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BITGET_BAD_SHAPE", "Bitget returned no envelope")
        if str(payload.get("code") or "") != "00000":
            raise AdapterUnavailable(
                "BITGET_API_ERROR",
                f"Bitget error {payload.get('code')}: {payload.get('msg') or 'unknown'}",
            )
        return payload.get("data")

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
        data = self._request("/api/v2/spot/account/assets")
        rows = data if isinstance(data, list) else []
        total = 0.0
        available = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            total += _num(row.get("balance"))
            available += _num(row.get("available"))
        return {
            "login": 0,
            "mode": "live",
            "server": "bitget",
            "company": "Bitget",
            "currency": "USD",
            "balance": total,
            "equity": total,
            "margin": total - available,
            "marginFree": available,
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": "spot",
            "tradeAllowed": False,   # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        data = self._request("/api/v2/mix/position/all-position",
                            {"productType": self._product_type()})
        rows = data if isinstance(data, list) else []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            size = _num(row.get("total"))
            if size == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("symbol") or "").upper(),
                "side": "buy" if str(row.get("holdSide") or "").lower() == "long" else "sell",
                "volume": size,
                "openPrice": _num(row.get("openPriceAvg")),
                "currentPrice": _num(row.get("markPrice")),
                "stopLoss": _num(row.get("stopLoss")) or None,
                "takeProfit": None,
                "profit": _num(row.get("unrealizedPL")),
                "swap": _num(row.get("totalFee")),
                "magic": 0,
                "comment": f"bitget {self._product_type()} {str(row.get('marginMode') or '').lower()}".strip(),
                "openedAt": int(_num(row.get("cTime"))),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        data = self._request("/api/v2/spot/trade/unfilled-orders")
        rows = data if isinstance(data, list) else []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append({
                "ticket": str(row.get("orderId") or ""),
                "symbol": str(row.get("symbol") or "").upper(),
                "type": str(row.get("orderType") or ""),
                "volumeCurrent": _num(row.get("size")) - _num(row.get("baseVolume")),
                "openPrice": _num(row.get("priceAvg") or row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": f"bitget {str(row.get('side') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("cTime"))),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("BITGET_SYMBOL", "a symbol is required")
        data = self._request("/api/v2/spot/market/tickers", {"symbol": pair}, signed=False)
        rows = data if isinstance(data, list) else []
        row = rows[0] if rows and isinstance(rows[0], dict) else None
        if row is None or not row.get("lastPr"):
            raise AdapterUnavailable("BITGET_NO_QUOTE", f"Bitget has no ticker for {pair}")
        last = _num(row.get("lastPr"))
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": _num(row.get("bidPr")) or last,
            "ask": _num(row.get("askPr")) or last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(_num(row.get("ts")) or time.time() * 1000),
            "provider": "bitget",
        }


__all__ = ["BitgetAdapter", "sign_request"]
