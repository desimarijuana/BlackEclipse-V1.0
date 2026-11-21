"""Read-only Gate.io v4 adapter (spot balances + USDT-settled perpetuals).

Gate.io v4 signs a five-part, newline-joined preimage with **HMAC-SHA512**, and
the body enters it as its own SHA-512 hex digest (the hex of the empty string for
a GET):

    payload_hash = sha512_hex(body)
    signature    = hex HMAC-SHA512(secret,
                     method + "\\n" + path + "\\n" + query + "\\n" +
                     payload_hash + "\\n" + timestamp)

Both details are the ones that go wrong: the digest is SHA-**512** (not 256), and
the *hash* of the body is signed rather than the body. `sign_request` is pure so
the exact preimage is checked against an independent computation.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * The perpetual positions carry `leverage` as a string and a signed `size` whose
    sign encodes the side; the adapter reads both rather than guessing a default.
  * Gate wraps refusals in `{"label": ..., "message": ...}` with a non-2xx status.

Config: `baseUrl` (default https://api.gateio.ws), `settle` (default `usdt`),
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
from ..model import KIND_GATEIO
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def payload_hash(body: str = "") -> str:
    """Gate's body digest: SHA-512 hex, of the empty string for a GET."""
    return hashlib.sha512(str(body or "").encode("utf-8")).hexdigest()


def sign_request(secret: str, timestamp: str, method: str, path: str,
                 query: str = "", body: str = "") -> str:
    """Gate.io v4 `SIGN`: hex HMAC-SHA512 over method/path/query/hash/ts."""
    preimage = "\n".join([
        method.upper(), path, str(query or ""), payload_hash(body), str(timestamp),
    ])
    return hmac.new(secret.encode("utf-8"), preimage.encode("utf-8"),
                    hashlib.sha512).hexdigest()


class GateioAdapter(BrokerAdapter):
    kind = KIND_GATEIO

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="GATEIO_CREDENTIALS",
            label="Gate.io API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "GATEIO_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.gateio.ws"),
            code="GATEIO_CONFIG",
            label="Gate.io baseUrl",
        )

    def _settle(self) -> str:
        return str(self.config.get("settle") or "usdt").lower()

    def _request(self, path: str, params: Optional[dict[str, Any]] = None, *,
                 signed: bool = True) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self._base()}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "application/json"}
        if signed:
            key, secret = self._credentials()
            timestamp = str(int(time.time()))
            headers.update({
                "KEY": key,
                "Timestamp": timestamp,
                "SIGN": sign_request(secret, timestamp, "GET", path, query),
            })
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("GATEIO_UNAUTHORIZED", "Gate.io rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("GATEIO_RATE_LIMITED", "Gate.io rate limit reached") from exc
            detail = ""
            try:
                detail = str((json.loads(exc.read() or b"{}") or {}).get("message") or "")
            except Exception:  # noqa: BLE001 - the body is advisory
                detail = ""
            raise AdapterUnavailable(
                "GATEIO_HTTP", f"Gate.io returned HTTP {exc.code}" + (f": {detail}" if detail else "")
            ) from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("GATEIO_UNREACHABLE", "Gate.io is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("GATEIO_TIMEOUT", "Gate.io timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("GATEIO_BAD_JSON", "Gate.io returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("label"):
            raise AdapterUnavailable("GATEIO_API_ERROR",
                                     str(payload.get("message") or payload["label"])[:300])
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
        rows = self._request("/api/v4/spot/accounts")
        total = available = 0.0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            total += _num(row.get("total"))
            available += _num(row.get("available"))
        frozen = total - available
        return {
            "login": 0,
            "mode": "live",
            "server": "gateio",
            "company": "Gate.io",
            "currency": "USD",
            "balance": total,
            "equity": total,
            "margin": frozen,
            "marginFree": available,
            "marginLevel": 0.0,
            "profit": 0.0,
            "leverage": 1.0,
            "marginMode": "spot",
            "tradeAllowed": False,   # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._request(f"/api/v4/futures/{self._settle()}/positions")
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            signed_size = _num(row.get("size"))
            if signed_size == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("contract") or "").upper(),
                "side": "buy" if signed_size > 0 else "sell",
                "volume": abs(signed_size),
                "openPrice": _num(row.get("entry_price")),
                "currentPrice": _num(row.get("mark_price")),
                "stopLoss": None,      # Gate keeps a separate price-triggered order list
                "takeProfit": None,
                "profit": _num(row.get("unrealised_pnl")),
                "swap": _num(row.get("funding_rate")),
                "magic": 0,
                "comment": f"gateio {self._settle()} futures (leverage {row.get('leverage') or '?'})",
                "openedAt": int(_num(row.get("open_time")) * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._request("/api/v4/spot/open_orders")
        out: list[dict[str, Any]] = []
        for bucket in rows if isinstance(rows, list) else []:
            for row in (bucket or {}).get("orders") or [] if isinstance(bucket, dict) else []:
                if not isinstance(row, dict):
                    continue
                amount = _num(row.get("amount"))
                left = _num(row.get("left"))
                out.append({
                    "ticket": str(row.get("id") or ""),
                    "symbol": str(row.get("currency_pair") or "").upper(),
                    "type": str(row.get("type") or ""),
                    "volumeCurrent": left or amount,
                    "openPrice": _num(row.get("price")),
                    "currentPrice": 0.0,
                    "stopLoss": None,
                    "takeProfit": None,
                    "state": str(row.get("status") or "open"),
                    "magic": 0,
                    "comment": f"gateio {str(row.get('side') or '').lower()}".strip(),
                    "placedAt": int(_num(row.get("create_time_ms")) or _num(row.get("create_time")) * 1000),
                })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("GATEIO_SYMBOL", "a currency pair is required")
        rows = self._request("/api/v4/spot/tickers", {"currency_pair": pair}, signed=False)
        row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
        if row is None or not row.get("last"):
            raise AdapterUnavailable("GATEIO_NO_QUOTE", f"Gate.io has no ticker for {pair}")
        last = _num(row.get("last"))
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": _num(row.get("highest_bid")) or last,
            "ask": _num(row.get("lowest_ask")) or last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "gateio",
        }


__all__ = ["GateioAdapter", "payload_hash", "sign_request"]
