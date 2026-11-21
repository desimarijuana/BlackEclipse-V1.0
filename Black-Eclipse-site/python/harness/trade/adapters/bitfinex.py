"""Read-only Bitfinex v2 adapter.

Bitfinex v2 is the only connector here that signs with **HMAC-SHA384**, and its
preimage is the *signed* path (the public one with `auth` replaced by `r`), the
nonce and the body:

    signature = hex HMAC-SHA384(secret,
                  "/api/v2/r/wallets" + nonce + body)

Three consequences the tests pin:

  * a **96-hex** digest (SHA-384), not 64 — the mistake a copy-paste from the
    SHA-256 adapters produces;
  * the path is signed **as sent** (`/api/v2/r/...`), not the `/auth/` path the
    caller wrote;
  * v2 answers with **positional arrays**, not objects, so every field is read by
    index with the schema documented next to it.

Declared limits:

  * **No order placement.** A `BrokerAdapter`, not a `TradingAdapter`.
  * **No websocket stream.**
  * Wallet balances are not marked to market; a position's `currentPrice` is only
    filled when Bitfinex's own position payload carries a mark (it does not), so it
    stays 0 and the comment says so.

Config: `baseUrl` (default https://api.bitfinex.com), `credentialRef` naming an
env var/secret holding `KEY:SECRET`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_BITFINEX
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url

_TIMEOUT = 15


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def sign_request(secret: str, path: str, nonce: str, body: str = "") -> str:
    """Bitfinex v2: hex HMAC-SHA384 over signed path + nonce + body."""
    message = f"{path}{nonce}{body}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"),
                    hashlib.sha384).hexdigest()


def symbol_for(raw: Any) -> str:
    """`tBTCUSD` / `fUSD` -> `BTCUSD` / `USD` (the `t`/`f` prefix is a class tag)."""
    text = str(raw or "").strip()
    return text[1:].upper() if text[:1] in ("t", "f") else text.upper()


class BitfinexAdapter(BrokerAdapter):
    kind = KIND_BITFINEX

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # -- credentials / http ----------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="BITFINEX_CREDENTIALS",
            label="Bitfinex API key/secret",
        )
        if not raw:
            raise AdapterUnavailable(
                "BITFINEX_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://api.bitfinex.com"),
            code="BITFINEX_CONFIG",
            label="Bitfinex baseUrl",
        )

    def _nonce(self) -> str:
        candidate = int(time.time() * 1000)
        last = int(getattr(self, "_last_nonce", 0) or 0)
        if candidate <= last:
            candidate = last + 1
        self._last_nonce = candidate
        return str(candidate)

    def _request(self, path: str, *, signed: bool = False, body: str = "") -> Any:
        headers = {"Accept": "application/json"}
        url = f"{self._base()}{path}"
        data: Optional[bytes] = None
        if signed:
            key, secret = self._credentials()
            nonce = self._nonce()
            # The preimage uses the SIGNED path (`/api/v2/r/...`), i.e. the one sent.
            headers.update({
                "bfx-apikey": key,
                "bfx-nonce": nonce,
                "bfx-signature": sign_request(secret, path, nonce, body),
            })
            if body:
                data = body.encode("utf-8")
                headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, headers=headers, data=data, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                payload = response.read(4_000_000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdapterUnavailable("BITFINEX_UNAUTHORIZED", "Bitfinex rejected the API key") from exc
            if exc.code == 429:
                raise AdapterUnavailable("BITFINEX_RATE_LIMITED", "Bitfinex rate limit reached") from exc
            raise AdapterUnavailable("BITFINEX_HTTP", f"Bitfinex returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable("BITFINEX_UNREACHABLE", "Bitfinex is unreachable") from exc
        except TimeoutError as exc:
            raise AdapterUnavailable("BITFINEX_TIMEOUT", "Bitfinex timed out") from exc
        try:
            parsed = json.loads(payload or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("BITFINEX_BAD_JSON", "Bitfinex returned invalid JSON") from exc
        if isinstance(parsed, dict) and parsed.get("error"):
            raise AdapterUnavailable("BITFINEX_API_ERROR", str(parsed["error"])[:300])
        return parsed

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
        rows = self._request("/api/v2/r/wallets", signed=True)
        # [TYPE, CURRENCY, BALANCE, UNSETTLED_INTEREST, AVAILABLE_BALANCE, ...]
        total = available = 0.0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list) or len(row) < 5:
                continue
            total += _num(row[2])
            available += _num(row[4])
        return {
            "login": 0,
            "mode": "live",
            "server": "bitfinex",
            "company": "Bitfinex",
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
        rows = self._request("/api/v2/r/positions", signed=True)
        # [SYMBOL, STATUS, AMOUNT, BASE_PRICE, FUNDING_COST, FUNDING_VALUE,
        #  COLLATERAL, PL, PL_PERC, PRICE_LIQ, LEVERAGE, _PLACEHOLDER, POSITION_ID,
        #  MTIME, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, PRICE]
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list) or len(row) < 4:
                continue
            amount = _num(row[2])
            if amount == 0:
                continue
            out.append({
                "ticket": int(_num(row[12])) if len(row) > 12 else 0,
                "symbol": symbol_for(row[0]),
                "side": "buy" if amount > 0 else "sell",
                "volume": abs(amount),
                "openPrice": _num(row[3]),
                "currentPrice": _num(row[17]) if len(row) > 17 else 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "profit": _num(row[7]),
                "swap": _num(row[4]),
                "magic": 0,
                "comment": f"bitfinex {str(row[1] or '').lower()}".strip(),
                "openedAt": int(_num(row[13])) if len(row) > 13 else 0,
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._request("/api/v2/r/orders", signed=True)
        # [ID, GID, CID, SYMBOL, MTIME, AMOUNT, PRICE, _PLACEHOLDER, _PLACEHOLDER,
        #  TYPE, _PLACEHOLDER, _PLACEHOLDER, STATUS, ...]
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list) or len(row) < 7:
                continue
            amount = _num(row[5])
            out.append({
                "ticket": str(int(_num(row[0]))),
                "symbol": symbol_for(row[3]),
                "type": str(row[9] or "") if len(row) > 9 else "",
                "volumeCurrent": abs(amount),
                "openPrice": _num(row[6]),
                "currentPrice": 0.0,
                "stopLoss": None,
                "takeProfit": None,
                "state": str(row[12] or "ACTIVE") if len(row) > 12 else "ACTIVE",
                "magic": 0,
                "comment": f"bitfinex {'buy' if amount > 0 else 'sell'}".strip(),
                "placedAt": int(_num(row[4])),
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        pair = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
        if not pair:
            raise AdapterUnavailable("BITFINEX_SYMBOL", "a pair is required")
        row = self._request(f"/api/v2/ticker/t{pair}")
        # [BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE, DAILY_CHANGE_REL,
        #  LAST_PRICE, VOLUME, HIGH, LOW]
        if not isinstance(row, list) or len(row) < 7:
            raise AdapterUnavailable("BITFINEX_NO_QUOTE", f"Bitfinex has no ticker for {pair}")
        last = _num(row[6])
        return {
            "symbol": pair,
            "requestedSymbol": symbol,
            "bid": _num(row[0]) or last,
            "ask": _num(row[2]) or last,
            "last": last,
            "spreadPoints": None,
            "digits": 8,
            "point": 0.00000001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "bitfinex",
        }


__all__ = ["BitfinexAdapter", "sign_request", "symbol_for"]
