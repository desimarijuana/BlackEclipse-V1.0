"""Read-only OANDA v20 adapter (FX and CFD).

OANDA is the first **fx** connector here, and its auth is the simplest of any
broker in the tree: a bearer token, no request signing. That is not a reason to
be careless about the two things that actually go wrong:

  * **the account id is data, not a guess.** v20 addresses every call by
    `accountID`, so it is either configured or discovered once from
    `GET /v3/accounts`; a missing id is a named refusal, never a default.
  * **positions are two-sided.** v20 reports `long` and `short` halves on the same
    instrument. A row is emitted per non-zero half, with its own units and PnL,
    rather than netting them into a number the exchange never reported.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No streaming.** v20's prices normally arrive over HTTP streaming; this
    adapter polls `/pricing` once per `quote()` call.
  * `NAV`/`marginAvailable` are v20's own account fields; `balance` is not
    recomputed from positions.

Config: `baseUrl` (default the v20 practice host), `accountId` (optional — it is
discovered when absent), `credentialRef` naming an env var/secret holding the
token.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_OANDA
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15
_PRACTICE = "https://api-fxpractice.oanda.com"


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def instrument_symbol(name: str) -> str:
    """`EUR_USD` -> `EURUSD` (OANDA spells pairs with an underscore)."""
    return str(name or "").replace("_", "").upper()


class OandaAdapter(BrokerAdapter):
    kind = KIND_OANDA

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _token(self) -> str:
        token = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="OANDA_CREDENTIALS",
            label="OANDA v20 access token",
        )
        if not token:
            raise AdapterUnavailable(
                "OANDA_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding the token",
            )
        return token

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or _PRACTICE),
            code="OANDA_CONFIG",
            label="OANDA baseUrl",
        )

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
        }, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("OANDA_UNAUTHORIZED", "OANDA rejected the token") from exc
            if exc.code == 404:
                raise AdapterUnavailable("OANDA_NOT_FOUND", "OANDA has no such account or instrument") from exc
            if exc.code == 429:
                raise AdapterUnavailable("OANDA_RATE_LIMITED", "OANDA rate limit reached") from exc
            raise AdapterUnavailable("OANDA_HTTP", f"OANDA returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("OANDA_UNREACHABLE", "OANDA is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("OANDA_TIMEOUT", "OANDA timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("OANDA_BAD_JSON", "OANDA returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("errorMessage"):
            raise AdapterUnavailable("OANDA_API_ERROR", str(payload["errorMessage"])[:300])
        return payload

    def _account_id(self) -> str:
        configured = str(self.config.get("accountId") or "").strip()
        if configured:
            return configured
        payload = self._get("/v3/accounts")
        accounts = payload.get("accounts") if isinstance(payload, dict) else None
        first = accounts[0] if isinstance(accounts, list) and accounts else None
        if not isinstance(first, dict) or not first.get("id"):
            raise AdapterUnavailable("OANDA_NO_ACCOUNT", "OANDA returned no account id")
        return str(first["id"])

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
        payload = self._get(f"/v3/accounts/{self._account_id()}/summary")
        summary = payload.get("account") if isinstance(payload, dict) else None
        if not isinstance(summary, dict):
            raise AdapterUnavailable("OANDA_BAD_RESPONSE", "OANDA returned no account summary")
        nav = _num(summary.get("NAV"))
        margin_available = _num(summary.get("marginAvailable"))
        return {
            "login": 0,
            "mode": "live",
            "server": "oanda",
            "company": "OANDA",
            "currency": str(summary.get("currency") or "USD"),
            "balance": _num(summary.get("balance")),
            "equity": nav,
            "margin": _num(summary.get("marginUsed")) or (nav - margin_available),
            "marginFree": margin_available,
            "marginLevel": _num(summary.get("marginCloseoutPercent")) * 100.0,
            "profit": _num(summary.get("unrealizedPL")),
            "leverage": _num(summary.get("marginRate")) and round(1.0 / _num(summary.get("marginRate")), 2),
            "marginMode": "cfd",
            "tradeAllowed": False,   # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        payload = self._get(f"/v3/accounts/{self._account_id()}/openPositions")
        rows = payload.get("positions") if isinstance(payload, dict) else None
        out: list[dict[str, Any]] = []
        for position in rows if isinstance(rows, list) else []:
            if not isinstance(position, dict):
                continue
            instrument = str(position.get("instrument") or "")
            for side in ("long", "short"):
                half = position.get(side)
                if not isinstance(half, dict):
                    continue
                units = abs(_num(half.get("units")))
                if units == 0:
                    continue
                out.append({
                    "ticket": 0,
                    "symbol": instrument_symbol(instrument),
                    "side": "buy" if side == "long" else "sell",
                    "volume": units,
                    "openPrice": _num(half.get("averagePrice")),
                    "currentPrice": 0.0,   # not marked: that needs a price per instrument
                    "stopLoss": None,
                    "takeProfit": None,
                    "profit": _num(half.get("unrealizedPL")),
                    "swap": _num(half.get("financing")),
                    "magic": 0,
                    "comment": f"oanda {side} ({instrument})",
                    "openedAt": int(time.time() * 1000),
                })
        return out

    def orders(self) -> list[dict[str, Any]]:
        payload = self._get(f"/v3/accounts/{self._account_id()}/pendingOrders")
        rows = payload.get("orders") if isinstance(payload, dict) else None
        out: list[dict[str, Any]] = []
        for order in rows if isinstance(rows, list) else []:
            if not isinstance(order, dict):
                continue
            units = _num(order.get("units"))
            out.append({
                "ticket": str(order.get("id") or ""),
                "symbol": instrument_symbol(order.get("instrument") or ""),
                "type": str(order.get("type") or ""),
                "volumeCurrent": abs(units),
                "openPrice": _num(order.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(order.get("state") or ""),
                "magic": 0,
                "comment": f"oanda {'buy' if units > 0 else 'sell'}".strip(),
                "placedAt": int(_num(order.get("createTime")) / 1e6) if order.get("createTime") else 0,
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        raw = str(symbol or "").strip().upper()
        if not raw:
            raise AdapterUnavailable("OANDA_SYMBOL", "an instrument is required")
        instrument = raw if "_" in raw else f"{raw[:3]}_{raw[3:]}" if len(raw) == 6 else raw
        payload = self._get(f"/v3/accounts/{self._account_id()}/pricing",
                            {"instruments": instrument})
        prices = payload.get("prices") if isinstance(payload, dict) else None
        row = prices[0] if isinstance(prices, list) and prices else None
        if not isinstance(row, dict) or not row.get("bids"):
            raise AdapterUnavailable("OANDA_NO_QUOTE", f"OANDA has no price for {instrument}")
        bid = _num((row.get("bids") or [{}])[0].get("price"))
        ask = _num((row.get("asks") or [{}])[0].get("price"))
        return {
            "symbol": instrument_symbol(instrument),
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": (bid + ask) / 2 if bid and ask else bid or ask,
            "spreadPoints": round((ask - bid) * 100_000, 1) if bid and ask else None,
            "digits": 5,
            "point": 0.00001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "oanda",
        }


__all__ = ["OandaAdapter", "instrument_symbol"]
