"""Read-only Coinbase Exchange adapter.

Coinbase's Exchange API signs `timestamp + method + requestPath + body` with
**HMAC-SHA256 over the base64-decoded secret** and sends the digest base64-encoded
alongside the key and passphrase:

    prehash   = <unix seconds> + "GET" + "/accounts" + ""
    signature = base64(HMAC-SHA256(base64decode(secret), prehash))

`sign_request` is pure so the exact prehash can be checked against an independent
computation — the two easy mistakes here are signing the *encoded* secret and
forgetting that the body is part of the message (even when empty).

Declared limits, so nothing is implied that is not true:

  * **Balances, not positions.** There are no margin positions in this surface;
    `positions()` reports non-zero balances with `currentPrice`/`profit` at 0
    because marking every asset would be one call each and a silent failure mode.
  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**

Config: `baseUrl` (default https://api.exchange.coinbase.com),
`credentialRef` naming an env var/secret holding `KEY:SECRET:PASSPHRASE`.
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
from ..model import KIND_COINBASE
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret_b64: str, timestamp: str, method: str, path: str, body: str = "") -> str:
    """Coinbase's `CB-ACCESS-SIGN`: base64(HMAC-SHA256(secret, ts+method+path+body))."""
    prehash = f"{timestamp}{method.upper()}{path}{body}"
    digest = hmac.new(
        base64.b64decode(secret_b64), prehash.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


class CoinbaseAdapter(BrokerAdapter):
    kind = KIND_COINBASE

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="COINBASE_CREDENTIALS",
            label="Coinbase key/secret/passphrase",
        )
        if not raw:
            raise AdapterUnavailable(
                "COINBASE_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding "
                "`KEY:SECRET:PASSPHRASE`",
            )
        parts = raw.split(":")
        if len(parts) != 3 or not all(parts):
            raise AdapterUnavailable(
                "COINBASE_CREDENTIALS",
                "the credential must be `KEY:SECRET:PASSPHRASE` (three parts)",
            )
        return parts[0], parts[1], parts[2]

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.exchange.coinbase.com"),
            code="COINBASE_CONFIG",
            label="Coinbase baseUrl",
        )

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        request_path = path + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "BlackEclipse/coinbase"}
        if signed:
            key, secret, passphrase = self._credentials()
            timestamp = str(int(time.time()))
            headers.update({
                "CB-ACCESS-KEY": key,
                "CB-ACCESS-PASSPHRASE": passphrase,
                "CB-ACCESS-TIMESTAMP": timestamp,
                "CB-ACCESS-SIGN": sign_request(secret, timestamp, "GET", request_path),
            })
        request = urllib.request.Request(
            f"{self._base()}{request_path}", headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("COINBASE_UNAUTHORIZED", "Coinbase rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("COINBASE_RATE_LIMITED", "Coinbase rate limit reached") from exc
            raise AdapterUnavailable("COINBASE_HTTP", f"Coinbase returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("COINBASE_UNREACHABLE", "Coinbase is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("COINBASE_TIMEOUT", "Coinbase timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("COINBASE_BAD_JSON", "Coinbase returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("message"):
            raise AdapterUnavailable("COINBASE_API_ERROR", str(payload["message"])[:300])
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

    def _accounts(self) -> list[dict[str, Any]]:
        payload = self._request("/accounts")
        if not isinstance(payload, list):
            raise AdapterUnavailable("COINBASE_BAD_RESPONSE", "Coinbase returned no accounts")
        return [row for row in payload if isinstance(row, dict)]

    def account(self) -> dict[str, Any]:
        total = 0.0
        for row in self._accounts():
            balance = row.get("balance")
            total += _num(balance)
        return {
            "login": 0,
            "mode": "live",
            "server": "coinbase",
            "company": "Coinbase Exchange",
            "currency": "USD",
            "balance": total,
            "equity": total,
            "margin": 0.0,
            "marginFree": total,
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": "spot",
            "tradeAllowed": False,  # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        now_ms = int(time.time() * 1000)
        for row in self._accounts():
            quantity = _num(row.get("balance"))
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("currency") or "").upper(),
                "side": "buy",
                "volume": quantity,
                "openPrice": 0.0,     # not derived: the adapter does not price assets
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "coinbase spot balance (not marked to market)",
                "openedAt": now_ms,
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        payload = self._request("/orders", {"status": "open"})
        out: list[dict[str, Any]] = []
        for row in payload if isinstance(payload, list) else []:
            if not isinstance(row, dict):
                continue
            out.append({
                "ticket": str(row.get("id") or ""),
                "symbol": str(row.get("product_id") or "").upper(),
                "type": str(row.get("type") or ""),
                "volumeCurrent": _num(row.get("size")) - _num(row.get("filled_size")),
                "openPrice": _num(row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": f"coinbase {str(row.get('side') or '').lower()}".strip(),
                "placedAt": _epoch_ms(row.get("created_at")),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("COINBASE_SYMBOL", "a product id is required")
        row = self._request(f"/products/{urllib.parse.quote(pair, safe='')}/ticker", signed=False)
        if not isinstance(row, dict) or row.get("price") in (None, ""):
            raise AdapterUnavailable("COINBASE_NO_QUOTE", f"Coinbase has no ticker for {pair}")
        last = _num(row.get("price"))
        bid = _num(row.get("bid")) or last
        ask = _num(row.get("ask")) or last
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "coinbase",
        }


def _epoch_ms(raw: Any) -> int:
    """Coinbase timestamps are ISO-8601 (e.g. `2026-11-01T12:00:00.000000Z`)."""
    text = str(raw or "").strip()
    if not text:
        return 0
    try:
        from datetime import datetime, timezone

        return int(datetime.fromisoformat(text.replace("Z", "+00:00"))
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    except ValueError:
        return 0


__all__ = ["CoinbaseAdapter", "sign_request"]
