"""Read-only OKX adapter (spot / perpetuals).

OKX authenticates every private call with four headers:

    OK-ACCESS-KEY        api key
    OK-ACCESS-TIMESTAMP  ISO-8601 UTC, millisecond precision
    OK-ACCESS-SIGN       base64(HMAC-SHA256(secret, timestamp + METHOD + requestPath + body))
    OK-ACCESS-PASSPHRASE the key's passphrase

`request_path` includes the query string, and the body is `""` for a GET — the
two details that break most implementations. `sign_request` is a pure function so
the exact signing input can be checked against an independently computed digest.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **Quotes are one ticker snapshot**, not a websocket stream.
  * **Positions are the account's reported rows**; nothing is derived.

Config (all non-secret): `baseUrl` (default https://www.okx.com),
`credentialRef` naming an env var/secret holding `API_KEY:SECRET:PASSPHRASE`,
and optional `accountType` (default `unified`).
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
from ..model import KIND_OKX
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _timestamp() -> str:
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int(now * 1000) % 1000:03d}Z"


def sign_request(secret: str, timestamp: str, method: str, request_path: str, body: str = "") -> str:
    """OKX's documented signature: base64(HMAC-SHA256(secret, ts + METHOD + path + body))."""
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class OkxAdapter(BrokerAdapter):
    kind = KIND_OKX

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="OKX_CREDENTIALS",
            label="OKX API key/secret/passphrase",
        )
        if not raw:
            raise AdapterUnavailable(
                "OKX_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing "
                "`API_KEY:SECRET:PASSPHRASE`",
            )
        parts = str(raw).split(":", 2)
        if len(parts) != 3 or not all(part.strip() for part in parts):
            raise AdapterUnavailable(
                "OKX_CREDENTIALS",
                "OKX needs `API_KEY:SECRET:PASSPHRASE` (three parts)",
            )
        return tuple(part.strip() for part in parts)  # type: ignore[return-value]

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://www.okx.com"),
            code="OKX_CONFIG",
            label="OKX baseUrl",
        )

    def _request(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Signed GET. `path` may carry a query string already."""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                path += "?" + urllib.parse.urlencode(clean)
        key, secret, passphrase = self._credentials()
        stamp = _timestamp()
        request = urllib.request.Request(
            self._base() + path,
            headers={
                "Accept": "application/json",
                "OK-ACCESS-KEY": key,
                "OK-ACCESS-SIGN": sign_request(secret, stamp, "GET", path),
                "OK-ACCESS-TIMESTAMP": stamp,
                "OK-ACCESS-PASSPHRASE": passphrase,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("OKX_UNAUTHORIZED", "OKX rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("OKX_RATE_LIMITED", "OKX rate limit reached") from exc
            raise AdapterUnavailable("OKX_HTTP", f"OKX returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("OKX_UNREACHABLE", "OKX is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("OKX_TIMEOUT", "OKX timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("OKX_BAD_JSON", "OKX returned invalid JSON") from exc
        if isinstance(payload, dict) and str(payload.get("code") or "0") != "0":
            raise AdapterUnavailable(
                "OKX_API_ERROR",
                f"OKX error {payload.get('code')}: {payload.get('msg') or 'unknown'}",
            )
        return payload.get("data") if isinstance(payload, dict) else payload

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
        rows = self._request("/api/v5/account/balance") or []
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, dict):
            raise AdapterUnavailable("OKX_BAD_RESPONSE", "OKX returned no account")
        return {
            "login": 0,
            "mode": "live",
            "server": "okx",
            "company": "OKX",
            "currency": "USD",
            "balance": _num(row.get("availBal") or row.get("availEq")),
            "equity": _num(row.get("totalEq")),
            "margin": _num(row.get("imr")),
            "marginFree": _num(row.get("availEq")),
            "marginLevel": 0.0,
            "profit": _num(row.get("upl")),
            "leverage": 1.0,
            "marginMode": "unified",
            "tradeAllowed": False,  # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._request(
            "/api/v5/account/positions",
            {"instType": str(self.config.get("instType") or "SWAP")},
        ) or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            size = _num(row.get("pos"))
            if size == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("instId") or "").upper(),
                "side": str(row.get("posSide") or ("long" if size >= 0 else "short")),
                "volume": abs(size),
                "openPrice": _num(row.get("avgPx")),
                "currentPrice": _num(row.get("markPx")),
                "stopLoss": None,
                "takeProfit": None,
                "profit": _num(row.get("upl")),
                "swap": 0.0,
                "magic": 0,
                "comment": "okx",
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._request(
            "/api/v5/trade/orders-pending",
            {"instType": str(self.config.get("instType") or "SWAP")},
        ) or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            out.append({
                "ticket": str(row.get("ordId") or ""),
                "symbol": str(row.get("instId") or "").upper(),
                "type": str(row.get("ordType") or ""),
                "volumeCurrent": _num(row.get("sz")),
                "openPrice": _num(row.get("px")),
                "currentPrice": _num(row.get("avgPx")),
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row.get("state") or ""),
                "magic": 0,
                "comment": f"okx {row.get('side') or ''}".strip(),
                "placedAt": 0,
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        inst = str(symbol or "").strip().upper()
        if not inst:
            raise AdapterUnavailable("OKX_SYMBOL", "an instrument id is required")
        rows = self._request("/api/v5/market/ticker", {"instId": inst}) or []
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, dict):
            raise AdapterUnavailable("OKX_NO_QUOTE", f"OKX has no ticker for {inst}")
        bid, ask = _num(row.get("bidPx")), _num(row.get("askPx"))
        last = _num(row.get("last")) or ((bid + ask) / 2 if bid and ask else 0.0)
        return {
            "symbol": inst,
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(_num(row.get("ts"), time.time() * 1000)),
            "provider": "okx",
        }


__all__ = ["OkxAdapter", "sign_request"]
