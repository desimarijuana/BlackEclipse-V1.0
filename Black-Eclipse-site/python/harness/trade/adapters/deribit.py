"""Read-only Deribit adapter (crypto derivatives).

Deribit's private API is JSON-RPC over **GET**, and its signature is a
newline-joined preimage rather than a concatenation:

    sig = hex HMAC-SHA256(client_secret, ts + "\\n" + nonce + "\\n" + data + "\\n" + query)
    Authorization: deri-hmac-sha256 id=<client_id>,ts=<ts>,nonce=<nonce>,sig=<sig>

`data` is the empty string for GET, and the query string is signed **verbatim** —
`sign_request` is pure so both facts can be checked against an independent
computation instead of hoped for.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * The account summary is per **currency** (Deribit keeps them separate), so
    `account()` marks the returned `currency` rather than inventing a total
    across currencies it did not query.
  * A JSON-RPC `error` object is a refusal, never empty data.

Config: `baseUrl` (default https://www.deribit.com), `currency` (default `BTC`),
`credentialRef` naming an env var/secret holding `CLIENT_ID:CLIENT_SECRET`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_DERIBIT
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, timestamp: str, nonce: str, query: str,
                 data: str = "") -> str:
    """Deribit's `deri-hmac-sha256` signature over ts/nonce/data/query."""
    preimage = f"{timestamp}\n{nonce}\n{data}\n{query}"
    return hmac.new(secret.encode("utf-8"), preimage.encode("utf-8"),
                    hashlib.sha256).hexdigest()


class DeribitAdapter(BrokerAdapter):
    kind = KIND_DERIBIT

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="DERIBIT_CREDENTIALS",
            label="Deribit client id/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "DERIBIT_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing "
                "`CLIENT_ID:CLIENT_SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://www.deribit.com"),
            code="DERIBIT_CONFIG",
            label="Deribit baseUrl",
        )

    def _currency(self) -> str:
        return str(self.config.get("currency") or "BTC").upper()

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json"}
        if signed:
            client_id, secret = self._credentials()
            timestamp = str(int(time.time() * 1000))
            nonce = str(uuid.uuid4())
            signature = sign_request(secret, timestamp, nonce, query)
            headers["Authorization"] = (
                f"deri-hmac-sha256 id={client_id},ts={timestamp},"
                f"nonce={nonce},sig={signature}"
            )
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("DERIBIT_UNAUTHORIZED", "Deribit rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("DERIBIT_RATE_LIMITED", "Deribit rate limit reached") from exc
            raise AdapterUnavailable("DERIBIT_HTTP", f"Deribit returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("DERIBIT_UNREACHABLE", "Deribit is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("DERIBIT_TIMEOUT", "Deribit timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("DERIBIT_BAD_JSON", "Deribit returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AdapterUnavailable("DERIBIT_BAD_SHAPE", "Deribit returned no envelope")
        error = payload.get("error")
        if isinstance(error, dict) and error:
            raise AdapterUnavailable(
                "DERIBIT_API_ERROR",
                f"Deribit error {error.get('code')}: {error.get('message') or 'unknown'}",
            )
        return payload.get("result")

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
        result = self._request("/api/v2/private/get_account_summary",
                              {"currency": self._currency()})
        if not isinstance(result, dict):
            raise AdapterUnavailable("DERIBIT_BAD_RESPONSE", "Deribit returned no account summary")
        equity = _num(result.get("equity"))
        return {
            "login": 0,
            "mode": "live",
            "server": "deribit",
            "company": "Deribit",
            "currency": str(result.get("currency") or self._currency()),
            "balance": _num(result.get("balance")),
            "equity": equity,
            "margin": equity - _num(result.get("available_funds")),
            "marginFree": _num(result.get("available_funds")),
            "marginLevel": 0.0,
            "profit": _num(result.get("session_upl")),
            "leverage": 1.0,
            "marginMode": "derivatives",
            "tradeAllowed": False,   # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._request("/api/v2/private/get_positions", {"currency": self._currency()})
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            size = abs(_num(row.get("size")))
            if size == 0:
                continue
            direction = str(row.get("direction") or "")
            out.append({
                "ticket": 0,
                "symbol": str(row.get("instrument_name") or "").upper(),
                "side": "buy" if direction == "buy" else "sell",
                "volume": size,
                "openPrice": _num(row.get("average_price")),
                "currentPrice": _num(row.get("mark_price")),
                "stopLoss": None,
                "takeProfit": None,
                "profit": _num(row.get("floating_profit_loss")),
                "swap": 0.0,
                "magic": 0,
                "comment": f"deribit {row.get('kind') or 'position'} ({self._currency()})",
                "openedAt": int(_num(row.get("timestamp"))),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._request("/api/v2/private/get_open_orders_by_currency",
                             {"currency": self._currency()})
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            amount = abs(_num(row.get("amount")))
            filled = abs(_num(row.get("filled_amount")))
            out.append({
                "ticket": str(row.get("order_id") or ""),
                "symbol": str(row.get("instrument_name") or "").upper(),
                "type": str(row.get("order_type") or ""),
                "volumeCurrent": max(0.0, amount - filled),
                "openPrice": _num(row.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("order_state") or ""),
                "magic": 0,
                "comment": f"deribit {str(row.get('direction') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("creation_timestamp"))),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        instrument = str(symbol or "").strip().upper()
        if not instrument:
            raise AdapterUnavailable("DERIBIT_SYMBOL", "an instrument name is required")
        row = self._request("/api/v2/public/ticker", {"instrument_name": instrument},
                            signed=False)
        if not isinstance(row, dict) or row.get("last_price") in (None, ""):
            raise AdapterUnavailable("DERIBIT_NO_QUOTE", f"Deribit has no ticker for {instrument}")
        last = _num(row.get("last_price"))
        return {
            "symbol": instrument,
            "requestedSymbol": symbol,
            "bid": _num(row.get("best_bid_price")) or last,
            "ask": _num(row.get("best_ask_price")) or last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(_num(row.get("timestamp")) or time.time() * 1000),
            "provider": "deribit",
        }


__all__ = ["DeribitAdapter", "sign_request"]
