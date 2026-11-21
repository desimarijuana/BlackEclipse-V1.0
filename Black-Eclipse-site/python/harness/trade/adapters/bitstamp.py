"""Read-only Bitstamp v2 adapter.

Bitstamp is the odd one out here: it does **not** use auth headers. The key,
signature and nonce travel in the **form body**, and the signature covers the
credential itself:

    nonce     = unix seconds (monotonic per call)
    signature = hex HMAC-SHA256(secret, nonce + customer_id + api_key)

`sign_request` is pure so that preimage — including the customer id, which is the
one people forget — is checked against an independent computation. The nonce must
strictly increase, so it is derived from a monotonic clock and bumped on repeat.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * Bitstamp's balance is per currency with `available` and `balance`; `positions`
    reports non-zero balances and does not mark them to market.

Config: `baseUrl` (default https://www.bitstamp.net), `credentialRef` naming an
env var/secret holding `KEY:SECRET:CUSTOMER_ID`.
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
from ..model import KIND_BITSTAMP
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, nonce: str, customer_id: str, api_key: str) -> str:
    """Bitstamp v2: hex HMAC-SHA256 over `nonce + customer_id + api_key`."""
    message = f"{nonce}{customer_id}{api_key}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"),
                    hashlib.sha256).hexdigest()


class BitstampAdapter(BrokerAdapter):
    kind = KIND_BITSTAMP

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="BITSTAMP_CREDENTIALS",
            label="Bitstamp key/secret/customer id",
        )
        if not raw:
            raise AdapterUnavailable(
                "BITSTAMP_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding "
                "`KEY:SECRET:CUSTOMER_ID`",
            )
        parts = raw.split(":")
        if len(parts) != 3 or not all(parts):
            raise AdapterUnavailable(
                "BITSTAMP_CREDENTIALS",
                "the credential must be `KEY:SECRET:CUSTOMER_ID` (three parts)",
            )
        return parts[0], parts[1], parts[2]

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://www.bitstamp.net"),
            code="BITSTAMP_CONFIG",
            label="Bitstamp baseUrl",
        )

    def _nonce(self) -> str:
        """Strictly increasing seconds: a repeated nonce is rejected by Bitstamp."""
        candidate = int(time.time())
        last = int(getattr(self, "_last_nonce", 0) or 0)
        if candidate <= last:
            candidate = last + 1
        self._last_nonce = candidate
        return str(candidate)

    def _call(self, path: str, *, private: bool = True) -> Any:
        data: Optional[bytes] = None
        headers = {"Accept": "application/json"}
        if private:
            key, secret, customer_id = self._credentials()
            nonce = self._nonce()
            data = urllib.parse.urlencode({
                "key": key,
                "nonce": nonce,
                "signature": sign_request(secret, nonce, customer_id, key),
            }).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        url = f"{self._base()}{path}"
        request = urllib.request.Request(url, headers=headers, data=data,
                                         method="POST" if private else "GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("BITSTAMP_UNAUTHORIZED", "Bitstamp rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("BITSTAMP_RATE_LIMITED", "Bitstamp rate limit reached") from exc
            raise AdapterUnavailable("BITSTAMP_HTTP", f"Bitstamp returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("BITSTAMP_UNREACHABLE", "Bitstamp is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BITSTAMP_TIMEOUT", "Bitstamp timed out") from exc
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("BITSTAMP_BAD_JSON", "Bitstamp returned invalid JSON") from exc

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

    def _balances(self) -> dict[str, dict[str, float]]:
        payload = self._call("/api/v2/balance/")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("BITSTAMP_BAD_RESPONSE", "Bitstamp returned no balances")
        out: dict[str, dict[str, float]] = {}
        for key, value in payload.items():
            name = str(key)
            if name.endswith("_balance"):
                currency = name[: -len("_balance")].upper()
                out.setdefault(currency, {})["balance"] = _num(value)
            elif name.endswith("_available"):
                currency = name[: -len("_available")].upper()
                out.setdefault(currency, {})["available"] = _num(value)
            elif name.endswith("_fee"):
                continue
        return out

    def account(self) -> dict[str, Any]:
        balances = self._balances()
        total = sum(row.get("balance", 0.0) for row in balances.values())
        available = sum(row.get("available", 0.0) for row in balances.values())
        fees = {
            row.get("fee") for row in balances.values() if row.get("fee")
        }
        del fees
        return {
            "login": 0,
            "mode": "live",
            "server": "bitstamp",
            "company": "Bitstamp",
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
        now_ms = int(time.time() * 1000)
        out: list[dict[str, Any]] = []
        for currency, row in self._balances().items():
            quantity = row.get("balance", 0.0)
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": currency,
                "side": "buy",
                "volume": quantity,
                "openPrice": 0.0,     # not derived: the adapter does not price assets
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "bitstamp spot balance (not marked to market)",
                "openedAt": now_ms,
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        payload = self._call("/api/v2/open_orders/all/")
        out: list[dict[str, Any]] = []
        for row in payload if isinstance(payload, list) else []:
            if not isinstance(row, dict):
                continue
            amount = _num(row.get("amount"))
            out.append({
                "ticket": str(row.get("id") or ""),
                "symbol": str(row.get("currency_pair") or "").upper(),
                "type": str(row.get("type") or ""),
                "volumeCurrent": amount,
                "openPrice": _num(row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": "open",
                "magic": 0,
                "comment": f"bitstamp {str(row.get('type') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("datetime")) * 1000),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = "".join(ch for ch in str(symbol or "").lower() if ch.isalnum())
        if not pair:
            raise AdapterUnavailable("BITSTAMP_SYMBOL", "a currency pair is required")
        row = self._call(f"/api/v2/ticker/{pair}/", private=False)
        if not isinstance(row, dict) or row.get("last") in (None, ""):
            raise AdapterUnavailable("BITSTAMP_NO_QUOTE", f"Bitstamp has no ticker for {pair}")
        last = _num(row.get("last"))
        bid = _num(row.get("bid")) or last
        ask = _num(row.get("ask")) or last
        return {
            "symbol": pair.upper(),
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            # Bitstamp's ticker timestamp is in SECONDS; the contract is ms.
            "serverTimeMs": int((_num(row.get("timestamp")) or time.time()) * 1000),
            "provider": "bitstamp",
        }


__all__ = ["BitstampAdapter", "sign_request"]
