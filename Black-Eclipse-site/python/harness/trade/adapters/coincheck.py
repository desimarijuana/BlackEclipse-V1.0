"""Read-only Coincheck adapter.

Coincheck signs `nonce + url` — the **full request URL including scheme and
query** — with HMAC-SHA256 (hex) and sends `ACCESS-KEY`, `ACCESS-NONCE`,
`ACCESS-SIGN` as headers:

    sign = hex HMAC-SHA256(secret, nonce + "https://coincheck.com/api/accounts/balance")

`sign_request` is pure so the exact string (including the base and the query) is
checked against an independent computation; the usual mistake is signing the path
alone, which validates locally and fails remotely.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * Balances are per currency; `positions()` reports non-zero holdings and does not
    mark them to market (Coincheck's private surface carries no mark price).

Config: `baseUrl` (default https://coincheck.com), `credentialRef` naming an env
var/secret holding `KEY:SECRET`.
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
from ..model import KIND_COINCHECK
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, nonce: str, url: str) -> str:
    """Coincheck: hex HMAC-SHA256 over `nonce + full url`."""
    return hmac.new(secret.encode("utf-8"), f"{nonce}{url}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


class CoincheckAdapter(BrokerAdapter):
    kind = KIND_COINCHECK

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="COINCHECK_CREDENTIALS",
            label="Coincheck API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "COINCHECK_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://coincheck.com"),
            code="COINCHECK_CONFIG",
            label="Coincheck baseUrl",
        )

    def _nonce(self) -> str:
        candidate = int(time.time() * 1000)
        last = int(getattr(self, "_last_nonce", 0) or 0)
        if candidate <= last:
            candidate = last + 1
        self._last_nonce = candidate
        return str(candidate)

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json"}
        if signed:
            key, secret = self._credentials()
            nonce = self._nonce()
            headers.update({
                "ACCESS-KEY": key,
                "ACCESS-NONCE": nonce,
                "ACCESS-SIGN": sign_request(secret, nonce, url),
            })
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("COINCHECK_UNAUTHORIZED", "Coincheck rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("COINCHECK_RATE_LIMITED", "Coincheck rate limit reached") from exc
            raise AdapterUnavailable("COINCHECK_HTTP", f"Coincheck returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("COINCHECK_UNREACHABLE", "Coincheck is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("COINCHECK_TIMEOUT", "Coincheck timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("COINCHECK_BAD_JSON", "Coincheck returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("success") is False:
            raise AdapterUnavailable("COINCHECK_API_ERROR",
                                     str(payload.get("error") or "Coincheck refused the request")[:300])
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

    def _balances(self) -> dict[str, float]:
        payload = self._request("/api/accounts/balance")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("COINCHECK_BAD_RESPONSE", "Coincheck returned no balances")
        out: dict[str, float] = {}
        for name, value in payload.items():
            if name in ("success",):
                continue
            amount = _num(value, fallback=float("nan"))
            if amount != amount:      # not a number: not a balance field
                continue
            out[str(name).upper()] = amount
        return out

    def account(self) -> dict[str, Any]:
        balances = self._balances()
        total = sum(max(0.0, value) for value in balances.values())
        return {
            "login": 0,
            "mode": "live",
            "server": "coincheck",
            "company": "Coincheck",
            "currency": "JPY",
            "balance": total,
            "equity": total,
            "margin": 0.0,
            "marginFree": total,
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
        for currency, quantity in self._balances().items():
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
                "comment": "coincheck spot balance (not marked to market)",
                "openedAt": now_ms,
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        payload = self._request("/api/exchange/orders/opens")
        rows = payload.get("orders") if isinstance(payload, dict) else None
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            out.append({
                "ticket": str(row.get("id") or ""),
                "symbol": str(row.get("pair") or "").upper(),
                "type": str(row.get("order_type") or ""),
                "volumeCurrent": _num(row.get("amount")) - _num(row.get("executed_amount")),
                "openPrice": _num(row.get("rate")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": "open",
                "magic": 0,
                "comment": f"coincheck {str(row.get('order_type') or '').lower()}".strip(),
                "placedAt": 0,     # Coincheck's open-order payload carries no timestamp
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = "".join(ch for ch in str(symbol or "").lower() if ch.isalnum())
        if not pair:
            raise AdapterUnavailable("COINCHECK_SYMBOL", "a pair is required")
        row = self._request(f"/api/ticker?pair={pair}", signed=False)
        if not isinstance(row, dict) or row.get("last") in (None, ""):
            raise AdapterUnavailable("COINCHECK_NO_QUOTE", f"Coincheck has no ticker for {pair}")
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
            "serverTimeMs": int(time.time() * 1000),
            "provider": "coincheck",
        }


__all__ = ["CoincheckAdapter", "sign_request"]
