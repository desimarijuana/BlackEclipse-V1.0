"""Read-only Tradier adapter (US equities and options).

Tradier's brokerage API authenticates with a single Bearer token and returns JSON
in a nested envelope (`{"balances": {...}}`, `{"positions": {"position": [...]}}`)
whose list fields collapse to a single object when there is exactly one row. The
adapter flattens that consistently so a caller never sees "sometimes a dict".

Declared limits, so nothing is invented:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **Quotes are snapshots**, not a stream.
  * **Balances are the broker's own figures**; this adapter does not mark
    positions to market itself.

Config (all non-secret):
  baseUrl       default https://api.tradier.com (sandbox: https://sandbox.tradier.com)
  accountId     the brokerage account id (required for account/positions/orders)
  credentialRef NAME of an env var / secret holding the access token
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_TRADIER
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _rows(value: Any) -> list[dict[str, Any]]:
    """Tradier's list fields: `None`, one object, or a list of objects."""
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _nested(payload: Any, outer: str, inner: str) -> Any:
    """`payload[outer][inner]` without assuming either level exists or is a dict.

    Tradier returns `{"quotes": null}` as readily as `{"quotes": {"quote": …}}`,
    and `.get(outer, {})` still yields `None` when the key is present with a null
    value — the exact bug this helper exists to prevent.
    """
    if not isinstance(payload, dict):
        return None
    block = payload.get(outer)
    return block.get(inner) if isinstance(block, dict) else None


class TradierAdapter(BrokerAdapter):
    kind = KIND_TRADIER

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- http ------------------------------------------------------------

    def _token(self) -> str:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="TRADIER_CREDENTIALS",
            label="Tradier access token",
        )
        if not raw:
            raise AdapterUnavailable(
                "TRADIER_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding the token",
            )
        return str(raw).strip()

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.tradier.com"),
            code="TRADIER_CONFIG",
            label="Tradier baseUrl",
        )

    def _account_id(self) -> str:
        value = str(self.config.get("accountId") or "").strip()
        if not value:
            raise AdapterUnavailable(
                "TRADIER_ACCOUNT", "accountId is required for account, positions and orders"
            )
        return value

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        token = self._token()
        url = self._base() + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable(
                    "TRADIER_UNAUTHORIZED", "Tradier rejected the access token"
                ) from exc
            if exc.code == 429:
                raise AdapterUnavailable("TRADIER_RATE_LIMITED", "Tradier rate limit reached") from exc
            if exc.code == 404:
                return None
            raise AdapterUnavailable("TRADIER_HTTP", f"Tradier returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable(
                "TRADIER_UNREACHABLE", f"Tradier at {self._base()} is unreachable"
            ) from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("TRADIER_TIMEOUT", "Tradier timed out") from exc
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("TRADIER_BAD_JSON", "Tradier returned invalid JSON") from exc

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
        payload = self._get(f"/v1/accounts/{self._account_id()}/balances")
        balances = (payload or {}).get("balances") if isinstance(payload, dict) else None
        if not isinstance(balances, dict):
            raise AdapterUnavailable("TRADIER_BAD_RESPONSE", "Tradier returned no balances")
        return {
            "login": 0,
            "mode": "sandbox" if "sandbox" in self._base() else "live",
            "server": "tradier",
            "company": "Tradier",
            "currency": "USD",
            "balance": _num(balances.get("total_cash")),
            "equity": _num(balances.get("total_equity")),
            "margin": _num(balances.get("margin", {}).get("stock_buying_power")
                           if isinstance(balances.get("margin"), dict) else 0),
            "marginFree": _num(balances.get("total_cash")),
            "marginLevel": 0.0,
            "profit": _num(balances.get("close_pl")),
            "leverage": 1.0,
            "marginMode": "cash",
            "tradeAllowed": False,  # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        payload = self._get(f"/v1/accounts/{self._account_id()}/positions")
        rows = _rows(_nested(payload, "positions", "position"))
        out: list[dict[str, Any]] = []
        for row in rows:
            quantity = _num(row.get("quantity"))
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("symbol") or "").upper(),
                "side": "buy" if quantity >= 0 else "sell",
                "volume": abs(quantity),
                "openPrice": _num(row.get("cost_basis")),
                "currentPrice": 0.0,  # the adapter does not mark to market itself
                "stopLoss": None,
                "takeProfit": None,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "tradier",
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        payload = self._get(f"/v1/accounts/{self._account_id()}/orders")
        rows = _rows(_nested(payload, "orders", "order"))
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append({
                "ticket": _num(row.get("id")),
                "symbol": str(row.get("symbol") or "").upper(),
                "type": str(row.get("type") or ""),
                "volumeCurrent": _num(row.get("remaining_quantity")),
                "openPrice": _num(row.get("price")),
                "currentPrice": _num(row.get("avg_fill_price")),
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": f"tradier {row.get('side') or ''}".strip(),
                "placedAt": 0,
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = str(symbol or "").strip().upper()
        if not requested:
            raise AdapterUnavailable("TRADIER_SYMBOL", "a symbol is required")
        payload = self._get("/v1/markets/quotes", {"symbols": requested})
        rows = _rows(_nested(payload, "quotes", "quote"))
        if not rows:
            raise AdapterUnavailable("TRADIER_NO_QUOTE", f"Tradier has no quote for {requested}")
        row = rows[0]
        bid, ask = _num(row.get("bid")), _num(row.get("ask"))
        return {
            "symbol": requested,
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": _num(row.get("last")) or (bid + ask) / 2 if (bid and ask) else _num(row.get("last")),
            "spreadPoints": None,
            "digits": 2,
            "point": 0.01,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "tradier",
        }


__all__ = ["TradierAdapter"]
