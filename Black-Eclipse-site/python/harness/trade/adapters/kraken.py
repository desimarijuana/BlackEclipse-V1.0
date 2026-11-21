"""Read-only Kraken adapter (spot).

Kraken's private API signs a **path + nonce + body** digest with HMAC-SHA512:

    postdata  = "nonce=<ms>"
    digest    = sha256(nonce + postdata).digest()
    signature = base64(HMAC-SHA512(base64decode(secret), path.encode() + digest))

`sign_request` is pure so the exact input can be checked against an independent
computation — this scheme is easy to get subtly wrong (the path is signed, the
body is hashed first, and the secret arrives base64-encoded).

Declared limits:

  * **Spot only.** `positions()` reports non-zero balances; nothing is priced.
  * **No order placement**, no websocket stream.
  * Kraken answers HTTP 200 with an `error` array on application failures, so that
    array is a refusal, not empty data.

Config: `baseUrl` (default https://api.kraken.com), `credentialRef` naming an env
var/secret holding `KEY:SECRET`, optional `assetPairs` for quote lookups.
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
from ..model import KIND_KRAKEN
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret_b64: str, path: str, nonce: str, postdata: str) -> str:
    """Kraken's documented API-Sign."""
    secret = base64.b64decode(secret_b64)
    digest = hashlib.sha256((nonce + postdata).encode("utf-8")).digest()
    return base64.b64encode(
        hmac.new(secret, path.encode("utf-8") + digest, hashlib.sha512).digest()
    ).decode("ascii")


class KrakenAdapter(BrokerAdapter):
    kind = KIND_KRAKEN

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- http ------------------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="KRAKEN_CREDENTIALS",
            label="Kraken API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "KRAKEN_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.kraken.com"),
            code="KRAKEN_CONFIG",
            label="Kraken baseUrl",
        )

    def _call(self, path: str, params: Optional[dict[str, Any]] = None, *, private: bool = True) -> Any:
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        url = self._base() + path
        if private:
            key, secret = self._credentials()
            nonce = str(int(time.time() * 1000))
            postdata = urllib.parse.urlencode(params or {})
            if postdata:
                postdata = f"nonce={nonce}&" + postdata
            else:
                postdata = f"nonce={nonce}"
            headers.update({
                "API-Key": key,
                "API-Sign": sign_request(secret, path, nonce, postdata),
                "Content-Type": "application/x-www-form-urlencoded",
            })
            data = postdata.encode("utf-8")
        elif params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=headers, data=data,
                                         method="POST" if private else "GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("KRAKEN_UNAUTHORIZED", "Kraken rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("KRAKEN_RATE_LIMITED", "Kraken rate limit reached") from exc
            raise AdapterUnavailable("KRAKEN_HTTP", f"Kraken returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("KRAKEN_UNREACHABLE", "Kraken is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("KRAKEN_TIMEOUT", "Kraken timed out") from exc
        try:
            payload = json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("KRAKEN_BAD_JSON", "Kraken returned invalid JSON") from exc
        errors = payload.get("error") if isinstance(payload, dict) else None
        if errors:
            raise AdapterUnavailable("KRAKEN_API_ERROR", "; ".join(str(e) for e in errors)[:300])
        return payload.get("result") if isinstance(payload, dict) else payload

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
        result = self._call("/0/private/Balance") or {}
        if not isinstance(result, dict):
            raise AdapterUnavailable("KRAKEN_BAD_RESPONSE", "Kraken returned no balances")
        return {str(asset): _num(amount) for asset, amount in result.items()}

    def account(self) -> dict[str, Any]:
        balances = self._balances()
        total = sum(max(0.0, value) for value in balances.values())
        return {
            "login": 0,
            "mode": "live",
            "server": "kraken",
            "company": "Kraken",
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
        for asset, quantity in self._balances().items():
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": asset.upper(),
                "side": "buy",
                "volume": quantity,
                "openPrice": 0.0,     # not derived: the adapter does not price assets
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "kraken spot balance (not marked to market)",
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        result = self._call("/0/private/OpenOrders") or {}
        open_orders = result.get("open") if isinstance(result, dict) else None
        out: list[dict[str, Any]] = []
        for ticket, row in (open_orders or {}).items():
            if not isinstance(row, dict):
                continue
            descr = row.get("descr") if isinstance(row.get("descr"), dict) else {}
            out.append({
                "ticket": str(ticket),
                "symbol": str(descr.get("pair") or "").upper(),
                "type": str(descr.get("ordertype") or ""),
                "volumeCurrent": _num(row.get("vol")) - _num(row.get("vol_exec")),
                "openPrice": _num(descr.get("price")),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": "open",
                "magic": 0,
                "comment": f"kraken {str(descr.get('type') or '').lower()}".strip(),
                "placedAt": int(_num(row.get("opentm")) * 1000),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = str(symbol or "").strip().upper()
        if not pair:
            raise AdapterUnavailable("KRAKEN_SYMBOL", "a pair is required")
        result = self._call("/0/public/Ticker", {"pair": pair}, private=False) or {}
        row = next(iter(result.values()), None) if isinstance(result, dict) else None
        if not isinstance(row, dict):
            raise AdapterUnavailable("KRAKEN_NO_QUOTE", f"Kraken has no ticker for {pair}")
        last = _num((row.get("c") or [0])[0])
        bid = _num((row.get("b") or [0])[0])
        ask = _num((row.get("a") or [0])[0])
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last or ((bid + ask) / 2 if bid and ask else 0.0),
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "kraken",
        }


__all__ = ["KrakenAdapter", "sign_request"]
