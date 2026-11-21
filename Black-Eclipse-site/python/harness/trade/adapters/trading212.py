"""Read-only Trading212 adapter (equities / ETFs).

Trading212's public API is a clean REST surface with no order placement in the
read path we use: cash, portfolio and open orders. This adapter is therefore a
`BrokerAdapter`, not a `TradingAdapter` — it cannot send an order.

Two honest limitations, stated rather than papered over:

  * **No quote endpoint.** `quote()` raises `TRADING212_QUOTE_UNSUPPORTED`; the
    BrokerKind omits the `quote` capability, so the capability matrix shows it as
    absent instead of pretending a price came from the broker.
  * **No execution history.** The public API exposes open orders, not fills, so
    `deals_since` stays unsupported. The journal will not fabricate trades.

Auth: Trading212 issues an API key used as the HTTP Basic *username* with an
empty password. `authStyle` may be set to `"key"` for a deployment whose gateway
expects the raw key instead (the two forms are base64(`KEY:`) vs base64(`KEY`)).

Config (all non-secret):
  baseUrl        default https://live.trading212.com/api/v0
                 demo:  https://demo.trading212.com/api/v0
  credentialRef  NAME of an env var / secret holding the API key
  currency       account currency label (default GBP); Trading212's cash payload
                 does not carry it, so it is declared, never guessed
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_TRADING212
from .credentials import resolve_secret_value, validate_http_url

_TIMEOUT = 15
_MAX_RETRIES = 2


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


class Trading212Adapter(BrokerAdapter):
    kind = KIND_TRADING212

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        # stdlib only: nothing to install, nothing to probe over the network here.
        return True, None

    # -- http ------------------------------------------------------------

    def _credentials(self) -> str:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="TRADING212_CREDENTIALS",
            label="Trading212 API key",
        )
        if not raw:
            raise AdapterUnavailable(
                "TRADING212_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret holding the API key",
            )
        return raw.strip()

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://live.trading212.com/api/v0"),
            code="TRADING212_CONFIG",
            label="Trading212 baseUrl",
        )

    def _auth_header(self) -> str:
        key = self._credentials()
        style = str(self.config.get("authStyle") or "colon").strip().lower()
        token = base64.b64encode((key if style == "key" else key + ":").encode("utf-8"))
        return "Basic " + token.decode("ascii")

    def _get(self, path: str) -> Any:
        url = self._base() + path
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "Authorization": self._auth_header()},
            method="GET",
        )
        body: bytes | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    body = response.read(4_000_000)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES:
                    time.sleep(min(max(2**attempt, 0.5), 5.0))
                    continue
                if exc.code in (401, 403):
                    raise AdapterUnavailable(
                        "TRADING212_UNAUTHORIZED",
                        "Trading212 rejected the API key",
                    ) from exc
                if exc.code == 404:
                    return None
                raise AdapterUnavailable(
                    "TRADING212_HTTP", f"Trading212 returned HTTP {exc.code}"
                ) from exc
            except urllib.error.URLError as exc:
                raise AdapterUnavailable(
                    "TRADING212_UNREACHABLE", f"Trading212 at {self._base()} is unreachable"
                ) from exc
            except TimeoutError as exc:
                raise AdapterUnavailable("TRADING212_TIMEOUT", "Trading212 timed out") from exc
        if body is None:
            raise AdapterUnavailable(
                "TRADING212_RETRY_EXHAUSTED", "Trading212 did not answer after retries"
            )
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable(
                "TRADING212_BAD_JSON", "Trading212 returned invalid JSON"
            ) from exc

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
        row = self._get("/equity/account/cash")
        if not isinstance(row, dict):
            raise AdapterUnavailable(
                "TRADING212_BAD_RESPONSE", "Trading212 returned no account"
            )
        currency = str(self.config.get("currency") or "GBP")
        return {
            "login": 0,
            "mode": "demo" if "demo" in self._base() else "live",
            "server": "trading212",
            "company": "Trading212",
            "currency": currency,
            "balance": _num(row.get("free")),
            "equity": _num(row.get("total")),
            "margin": _num(row.get("invested")),
            "marginFree": _num(row.get("free")),
            "marginLevel": 0.0,
            "profit": _num(row.get("ppl")),
            "leverage": 1.0,
            "marginMode": "cash",
            "tradeAllowed": False,  # read-only adapter by construction
            "expertAllowed": False,
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._get("/equity/portfolio") or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            quantity = _num(row.get("quantity"))
            if quantity == 0:
                continue
            out.append({
                "ticket": 0,
                "symbol": str(row.get("ticker") or "").upper(),
                "side": "buy" if quantity >= 0 else "sell",
                "volume": abs(quantity),
                "openPrice": _num(row.get("averagePrice")),
                "currentPrice": _num(row.get("currentPrice")),
                "stopLoss": None,
                "takeProfit": None,
                "profit": _num(row.get("ppl")),
                "swap": _num(row.get("fxPpl")),
                "magic": 0,
                "comment": "trading212",
                # The payload has no open timestamp; "first seen" is honest.
                "openedAt": int(time.time() * 1000),
            })
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._get("/equity/orders") or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            quantity = _num(row.get("quantity"))
            out.append({
                "ticket": _int(row.get("id"), 0),
                "symbol": str(row.get("ticker") or "").upper(),
                "type": str(row.get("type") or ""),
                "volumeCurrent": abs(quantity),
                "openPrice": _num(row.get("limitPrice")) or _num(row.get("stopPrice")),
                "currentPrice": 0.0,
                "stopLoss": _num(row.get("stopLoss")) or None,
                "takeProfit": _num(row.get("takeProfit")) or None,
                "state": str(row.get("status") or ""),
                "magic": 0,
                "comment": "trading212",
                "placedAt": 0,
            })
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        raise AdapterUnavailable(
            "TRADING212_QUOTE_UNSUPPORTED",
            "Trading212's public API has no quote endpoint; use a market-data provider",
        )


__all__ = ["Trading212Adapter"]
