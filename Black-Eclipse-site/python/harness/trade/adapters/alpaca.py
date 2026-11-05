"""Read-only Alpaca adapter (US equities/ETFs/crypto).

Alpaca has no position-id on its execution stream. Filled orders are therefore
normalized with FIFO into round-trip deals (`fifo.normalize_fifo`), so the journal
gets correct entry/exit and P&L instead of a guessed pairing. That P&L is
Eclipse-computed FIFO, not a broker-reported figure.

Config (all non-secret):
  baseUrl       default https://paper-api.alpaca.markets
  dataUrl       default https://data.alpaca.markets
  accountId     optional label/display id
  credentialRef NAME of the secret (env var or secret://…) containing
                `KEY:SECRET` or {"key": "...", "secret": "..."}

This adapter is read-only: it is a `BrokerAdapter`, not a `TradingAdapter`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_ALPACA
from .credentials import parse_key_pair, resolve_secret_value, validate_http_url
from .fifo import Execution, normalize_fifo

_TIMEOUT = 15
_MAX_ORDERS = 5000


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number and number not in (float("inf"), float("-inf")) else fallback


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _ms(iso: Any) -> int:
    text = str(iso or "").strip()
    if not text:
        return 0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return 0


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


class AlpacaAdapter(BrokerAdapter):
    kind = KIND_ALPACA

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # ── HTTP ─────────────────────────────────────────────────────────────────
    def _credentials(self) -> tuple[str, str]:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="ALPACA_CREDENTIALS",
            label="Alpaca API key",
        )
        if not raw:
            raise AdapterUnavailable(
                "ALPACA_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing `KEY:SECRET`",
            )
        return parse_key_pair(raw)

    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://paper-api.alpaca.markets"),
            code="ALPACA_CONFIG",
            label="Alpaca baseUrl",
        )

    def _data_base(self) -> str:
        return validate_http_url(
            str(self.config.get("dataUrl") or "https://data.alpaca.markets"),
            code="ALPACA_CONFIG",
            label="Alpaca dataUrl",
        )

    def _get(self, path: str, params: Optional[dict[str, Any]] = None, *, base: Optional[str] = None) -> Any:
        key, secret = self._credentials()
        url = (base or self._base()) + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
            },
            method="GET",
        )
        body: bytes | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    body = response.read(4_000_000)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = (exc.headers.get("Retry-After") if exc.headers else None) or ""
                    try:
                        delay = float(retry)
                    except ValueError:
                        delay = 2**attempt
                    time.sleep(min(max(delay, 0.5), 5.0))
                    continue
                if exc.code in (401, 403):
                    raise AdapterUnavailable(
                        "ALPACA_UNAUTHORIZED",
                        "Alpaca rejected the API key/secret",
                    ) from exc
                if exc.code == 404:
                    return None
                raise AdapterUnavailable(
                    "ALPACA_HTTP",
                    f"Alpaca returned HTTP {exc.code}",
                ) from exc
            except urllib.error.URLError as exc:
                raise AdapterUnavailable(
                    "ALPACA_UNREACHABLE",
                    f"Alpaca at {base or self._base()} is unreachable",
                ) from exc
            except TimeoutError as exc:
                raise AdapterUnavailable("ALPACA_TIMEOUT", "Alpaca timed out") from exc
        if body is None:
            raise AdapterUnavailable("ALPACA_RETRY_EXHAUSTED", "Alpaca did not answer after retries")
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("ALPACA_BAD_JSON", "Alpaca returned invalid JSON") from exc

    # ── BrokerAdapter ────────────────────────────────────────────────────────
    def probe(self) -> dict[str, Any]:
        try:
            account = self.account()
        except AdapterUnavailable as exc:
            return {
                "available": True,
                "connected": False,
                "code": exc.code,
                "reason": exc.reason,
                "terminal": {"api": self._base()},
                "account": None,
                "warnings": [],
            }
        return {
            "available": True,
            "connected": True,
            "code": None,
            "reason": None,
            "terminal": {"api": self._base()},
            "account": account,
            "warnings": [],
        }

    def account(self) -> dict[str, Any]:
        row = self._get("/v2/account")
        if not isinstance(row, dict):
            raise AdapterUnavailable("ALPACA_BAD_RESPONSE", "Alpaca returned no account")
        last_equity = _num(row.get("last_equity"), _num(row.get("equity")))
        return {
            "login": _int(row.get("account_number"), 0),
            "mode": "demo" if "paper" in self._base() else "live",
            "server": "alpaca",
            "company": "Alpaca",
            "currency": str(row.get("currency") or "USD"),
            "balance": _num(row.get("cash")),
            "equity": _num(row.get("equity")),
            "margin": _num(row.get("initial_margin")),
            "marginFree": _num(row.get("buying_power")),
            "marginLevel": 0.0,
            "profit": _num(row.get("equity")) - last_equity,
            "leverage": _num(row.get("multiplier")),
            "marginMode": "unknown",
            "tradeAllowed": not bool(row.get("trading_blocked")),
            "expertAllowed": True,
        }

    def positions(self) -> list[dict[str, Any]]:
        rows = self._get("/v2/positions") or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            qty = _num(row.get("qty"))
            side = "buy" if qty >= 0 else "sell"
            out.append(
                {
                    "ticket": 0,
                    "symbol": str(row.get("symbol") or "").upper(),
                    "side": side,
                    "volume": abs(qty),
                    "openPrice": _num(row.get("avg_entry_price")),
                    "currentPrice": _num(row.get("current_price")),
                    "stopLoss": None,
                    "takeProfit": None,
                    "profit": _num(row.get("unrealized_pl")),
                    "swap": 0.0,
                    "magic": 0,
                    "comment": "alpaca (openedAt is first seen)",
                    # Alpaca's position payload has no open time. The opening
                    # order is in the deal window, so the journal normally uses
                    # that; when it is absent, "first seen" is honest and never
                    # silently dated 1970.
                    "openedAt": int(time.time() * 1000),
                }
            )
        return out

    def orders(self) -> list[dict[str, Any]]:
        rows = self._get("/v2/orders", {"status": "open", "limit": 500, "direction": "asc"}) or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            out.append(
                {
                    "ticket": _int(str(row.get("id") or "")[:8], 0),
                    "symbol": str(row.get("symbol") or "").upper(),
                    "type": str(row.get("type") or ""),
                    "volumeCurrent": _num(row.get("qty")) - _num(row.get("filled_qty")),
                    "openPrice": _num(row.get("limit_price")) or _num(row.get("stop_price")),
                    "currentPrice": 0.0,
                    "stopLoss": _num(row.get("stop_loss")) or None,
                    "takeProfit": _num(row.get("take_profit")) or None,
                    "state": str(row.get("status") or ""),
                    "magic": 0,
                    "comment": "alpaca",
                    "placedAt": _ms(row.get("submitted_at")),
                }
            )
        return out

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = str(symbol or "").strip()
        row = self._get(
            f"/v2/stocks/{urllib.parse.quote(requested.upper())}/quotes/latest",
            {"feed": "iex"},
            base=self._data_base(),
        )
        if isinstance(row, dict) and isinstance(row.get("quote"), dict):
            q = row["quote"]
        else:
            # Crypto pairs (BTC/USD) use the beta crypto endpoint.
            row = self._get(
                "/v1beta3/crypto/us/latest/quotes",
                {"symbols": requested.upper()},
                base=self._data_base(),
            )
            quotes = row.get("quotes") if isinstance(row, dict) else None
            q = quotes.get(requested.upper()) if isinstance(quotes, dict) else None
        if not isinstance(q, dict):
            raise AdapterUnavailable("ALPACA_NO_QUOTE", f"Alpaca has no quote for {requested}")
        bid = _num(q.get("bp"))
        ask = _num(q.get("ap"))
        return {
            "symbol": requested.upper(),
            "requestedSymbol": requested,
            "bid": bid,
            "ask": ask,
            "last": (bid + ask) / 2 if bid and ask else bid or ask,
            "spreadPoints": None,
            "digits": 4,
            "point": 0.0001,
            "stopsLevelPoints": 0,
            "serverTimeMs": _ms(q.get("t")) or int(time.time() * 1000),
            "provider": "alpaca",
        }

    def order_status(self, ticket: int) -> dict[str, Any]:
        return {"found": False, "ticket": int(ticket)}

    # ── reconciliation ───────────────────────────────────────────────────────
    def _executions(self, after_ms: int, until_ms: int) -> list[Execution]:
        executions: list[Execution] = []
        after = _iso(after_ms)
        until = _iso(until_ms)
        seen = 0
        for _ in range(10):
            rows = self._get(
                "/v2/orders",
                {
                    "status": "closed",
                    "after": after,
                    "until": until,
                    "limit": 500,
                    "direction": "asc",
                    "nested": "false",
                },
            )
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                filled = _num(row.get("filled_qty"))
                price = _num(row.get("filled_avg_price"))
                when = _ms(row.get("filled_at") or row.get("submitted_at"))
                if filled <= 0 or price <= 0 or when <= 0:
                    continue
                executions.append(
                    Execution(
                        id=str(row.get("id") or f"{when}-{len(executions)}"),
                        symbol=str(row.get("symbol") or ""),
                        side="buy" if str(row.get("side") or "").lower() == "buy" else "sell",
                        qty=filled,
                        price=price,
                        time_ms=when,
                        fee=0.0,
                    )
                )
                seen += 1
            if len(rows) < 500 or seen >= _MAX_ORDERS:
                break
            after = _iso(_ms(rows[-1].get("filled_at") or rows[-1].get("submitted_at")) + 1)
        return executions

    def deals_since(self, since_ms: int) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        from_ms = int(since_ms or 0) or (now - 7 * 86_400_000)
        return normalize_fifo(self._executions(from_ms, now))

    def deals_window(self, days: int) -> list[dict[str, Any]]:
        safe = max(1, min(int(days or 7), 3650))
        now = int(time.time() * 1000)
        return normalize_fifo(self._executions(now - safe * 86_400_000, now))


__all__ = ["AlpacaAdapter"]
