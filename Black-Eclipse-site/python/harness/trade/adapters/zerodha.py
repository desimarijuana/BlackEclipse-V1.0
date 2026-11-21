"""Read-only Zerodha Kite adapter (NSE/BSE equities, F&O, currency).

Kite's REST API authenticates with two static headers (`Authorization: token
<api_key>:<access_token>` and `X-Kite-Version: 3`) — no request signing — which
makes the adapter small and the tests able to run entirely on recorded shapes.

What it does NOT do, stated so nothing is invented:

  * **No order placement.** This is a `BrokerAdapter`, not a `TradingAdapter`.
  * **Quotes are per instrument, not a stream.** `quote()` returns one snapshot
    from `/quote`; the WebSocket ticker is not implemented.
  * **Positions are the broker's net + day split.** `positions()` returns the
    `net` book only; intraday `day` rows are not merged, because merging them
    would fabricate a position the broker does not report as net.

Config (all non-secret):
  baseUrl        default https://api.kite.trade
  credentialRef  NAME of an env var / secret holding `API_KEY:ACCESS_TOKEN`

Symbol convention: `EXCHANGE:TRADINGSYMBOL` (e.g. `NSE:RELIANCE`). A bare ticker
is refused rather than guessed at — the exchange changes the instrument.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_ZERODHA
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15
_API_VERSION = "3"


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


class ZerodhaAdapter(BrokerAdapter):
    kind = KIND_ZERODHA

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- http ------------------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="ZERODHA_CREDENTIALS",
            label="Zerodha API key/access token",
        )
        if not raw:
            raise AdapterUnavailable(
                "ZERODHA_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing "
                "`API_KEY:ACCESS_TOKEN`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.kite.trade"),
            code="ZERODHA_CONFIG",
            label="Zerodha baseUrl",
        )

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        key, token = self._credentials()
        url = self._base() + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Kite-Version": _API_VERSION,
                "Authorization": f"token {key}:{token}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable(
                    "ZERODHA_UNAUTHORIZED", "Kite rejected the API key/access token"
                ) from exc
            if exc.code == 429:
                raise AdapterUnavailable(
                    "ZERODHA_RATE_LIMITED", "Kite rate limit reached"
                ) from exc
            if exc.code == 404:
                return None
            raise AdapterUnavailable("ZERODHA_HTTP", f"Kite returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable(
                "ZERODHA_UNREACHABLE", f"Kite at {self._base()} is unreachable"
            ) from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("ZERODHA_TIMEOUT", "Kite timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("ZERODHA_BAD_JSON", "Kite returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise AdapterUnavailable(
                "ZERODHA_API_ERROR",
                str(payload.get("message") or "Kite returned an error"),
            )
        return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload

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
        profile = self._get("/user/profile") or {}
        margins = self._get("/user/margins") or {}
        equity = margins.get("equity") if isinstance(margins, dict) else {}
        if not isinstance(equity, dict):
            equity = {}
        return {
            "login": _int(profile.get("user_id"), 0) if str(profile.get("user_id", "")).isdigit() else 0,
            "mode": "live",
            "server": "zerodha",
            "company": str(profile.get("broker") or "Zerodha"),
            "currency": "INR",
            "balance": _num(equity.get("available", {}).get("cash") if isinstance(equity.get("available"), dict) else 0),
            "equity": _num(equity.get("net")),
            "margin": _num(equity.get("utilised", {}).get("debits") if isinstance(equity.get("utilised"), dict) else 0),
            "marginFree": _num(equity.get("available", {}).get("cash") if isinstance(equity.get("available"), dict) else 0),
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": "cash",
            "tradeAllowed": False,  # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        payload = self._get("/portfolio/positions") or {}
        rows = payload.get("net") if isinstance(payload, dict) else None
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            quantity = _num(row.get("quantity"))
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("tradingsymbol") or "").upper(),
                "side": "buy" if quantity >= 0 else "sell",
                "volume": abs(quantity),
                "openPrice": _num(row.get("average_price")),
                "currentPrice": _num(row.get("last_price")),
                "stopLoss": None,
                "takeProfit": None,
                "profit": _num(row.get("pnl")),
                "swap": 0.0,
                "magic": 0,
                "comment": "zerodha (net book)",
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._get("/orders") or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            out.append({
                "ticket": _int(row.get("order_id"), 0),
                "symbol": str(row.get("tradingsymbol") or "").upper(),
                "type": str(row.get("order_type") or ""),
                "volumeCurrent": _num(row.get("pending_quantity")),
                "openPrice": _num(row.get("price")),
                "currentPrice": _num(row.get("average_price")),
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": f"zerodha {row.get('transaction_type') or ''}".strip(),
                "placedAt": 0,
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = str(symbol or "").strip().upper()
        if ":" not in requested:
            raise AdapterUnavailable(
                "ZERODHA_SYMBOL_AMBIGUOUS",
                f"quote {requested!r} needs an exchange, e.g. NSE:{requested}",
            )
        row = self._get("/quote", {"i": requested})
        if not isinstance(row, dict) or not row:
            raise AdapterUnavailable("ZERODHA_NO_QUOTE", f"Kite has no quote for {requested}")
        data = next(iter(row.values()))
        if not isinstance(data, dict):
            raise AdapterUnavailable("ZERODHA_NO_QUOTE", f"Kite has no quote for {requested}")
        last = _num(data.get("last_price"))
        return {
            "symbol": requested,
            "requestedSymbol": symbol,
            "bid": _num(data.get("depth", {}).get("buy", [{}])[0].get("price")) if isinstance(data.get("depth"), dict) else 0.0,
            "ask": _num(data.get("depth", {}).get("sell", [{}])[0].get("price")) if isinstance(data.get("depth"), dict) else 0.0,
            "last": last,
            "spreadPoints": None,
            "digits": 2,
            "point": 0.01,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "zerodha",
        }


__all__ = ["ZerodhaAdapter"]
