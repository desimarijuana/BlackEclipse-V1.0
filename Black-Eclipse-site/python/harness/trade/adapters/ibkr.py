"""Read-only Interactive Brokers (Client Portal Web API) adapter.

IBKR runs a local Client Portal Gateway that owns the SSO session. Eclipse reads
it over HTTPS; it never logs in, never places an order and never stores a
password. The connection config carries:

    baseUrl     default https://localhost:5000/v1/api
    accountId   the IBKR account (e.g. DU1234567)
    credentialRef NAME of an env var / secret:// containing the gateway cookie
                (`SESSION=...`) or JSON {"cookie": "..."}

The gateway uses a self-signed certificate on loopback, so TLS verification is
relaxed ONLY for a loopback host. A remote baseUrl keeps normal verification.

Executions are normalized with FIFO into round-trip deals (IBKR's execution
stream has no position id). P&L is therefore Eclipse-computed, not a
broker-reported figure, until the CPAPI exposes a reliable per-execution P&L.

This adapter is read-only: it is a `BrokerAdapter`, not a `TradingAdapter`.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from ..adapter import AdapterUnavailable, BrokerAdapter
from ..model import KIND_IBKR
from .credentials import resolve_secret_value, validate_http_url
from .fifo import Execution, normalize_fifo

_TIMEOUT = 20
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return fallback
    return number if number == number and number not in (float("inf"), float("-inf")) else fallback


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return fallback


def _ms(value: Any) -> int:
    if isinstance(value, (int, float)) and value > 0:
        number = float(value)
        return int(number if number > 10_000_000_000 else number * 1000)
    text = str(value or "").strip()
    if not text:
        return 0
    for fmt in ("%Y%m%d-%H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return 0


class IBKRAdapter(BrokerAdapter):
    kind = KIND_IBKR

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._conids: dict[str, int] = {}

    @classmethod
    def availability(cls) -> tuple[bool, Optional[str]]:
        return True, None

    # ── HTTP ─────────────────────────────────────────────────────────────────
    def _base(self) -> str:
        return validate_http_url(
            str(self.config.get("baseUrl") or "https://localhost:5000/v1/api"),
            code="IBKR_CONFIG",
            label="IBKR gateway baseUrl",
        )

    def _cookie(self) -> str:
        raw = resolve_secret_value(
            str(self.config.get("credentialRef") or ""),
            code="IBKR_CREDENTIALS",
            label="IBKR gateway cookie",
        )
        if not raw:
            raise AdapterUnavailable(
                "IBKR_CREDENTIALS",
                "set credentialRef to the NAME of an env var or secret containing the gateway cookie",
            )
        text = raw.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError as exc:
                raise AdapterUnavailable("IBKR_CREDENTIALS", "the cookie JSON is invalid") from exc
            text = str(data.get("cookie") or data.get("session") or "")
        if not text:
            raise AdapterUnavailable("IBKR_CREDENTIALS", "the gateway cookie is empty")
        return text if "=" in text else f"SESSION={text}"

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = self._base() + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Cookie": self._cookie(),
                "X-Requested-With": "XMLHttpRequest",
            },
            method="GET",
        )
        parsed = urllib.parse.urlparse(self._base())
        host = parsed.hostname or ""
        kwargs: dict[str, Any] = {}
        if parsed.scheme == "https" and host in _LOOPBACK:
            # The local gateway's certificate is self-signed; only loopback is
            # allowed to skip verification.
            kwargs["context"] = ssl._create_unverified_context()  # noqa: SLF001
        body: bytes | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT, **kwargs) as response:
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
                        "IBKR_UNAUTHORIZED",
                        "IBKR rejected the gateway cookie (re-authenticate the Client Portal)",
                    ) from exc
                if exc.code == 404:
                    return None
                raise AdapterUnavailable("IBKR_HTTP", f"IBKR gateway returned HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise AdapterUnavailable(
                    "IBKR_UNREACHABLE",
                    "the IBKR Client Portal Gateway is not reachable; start it and log in",
                ) from exc
            except TimeoutError as exc:
                raise AdapterUnavailable("IBKR_TIMEOUT", "the IBKR gateway timed out") from exc
        if body is None:
            raise AdapterUnavailable("IBKR_RETRY_EXHAUSTED", "the IBKR gateway did not answer after retries")
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise AdapterUnavailable("IBKR_BAD_JSON", "the IBKR gateway returned invalid JSON") from exc

    def _account_id(self) -> str:
        configured = str(self.config.get("accountId") or "").strip()
        if configured:
            return configured
        data = self._get("/iserver/accounts") or {}
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if isinstance(accounts, list) and accounts:
            return str(accounts[0])
        raise AdapterUnavailable("IBKR_NO_ACCOUNT", "no IBKR account is available in this gateway")

    # ── BrokerAdapter ────────────────────────────────────────────────────────
    def probe(self) -> dict[str, Any]:
        try:
            status = self._get("/iserver/auth/status") or {}
            if isinstance(status, dict) and status.get("authenticated") is False:
                raise AdapterUnavailable(
                    "IBKR_AUTH_EXPIRED",
                    "the IBKR Client Portal session is not authenticated; log in to the gateway again",
                )
            account = self.account()
        except AdapterUnavailable as exc:
            return {
                "available": True,
                "connected": False,
                "code": exc.code,
                "reason": exc.reason,
                "terminal": {"gateway": self._base()},
                "account": None,
                "warnings": [],
            }
        return {
            "available": True,
            "connected": True,
            "code": None,
            "reason": None,
            "terminal": {"gateway": self._base()},
            "account": account,
            "warnings": [],
        }

    def account(self) -> dict[str, Any]:
        account_id = self._account_id()
        row = self._get(f"/portfolio/{urllib.parse.quote(account_id)}/summary") or {}
        if not isinstance(row, dict):
            raise AdapterUnavailable("IBKR_BAD_RESPONSE", "IBKR returned no account summary")
        return {
            "login": 0,
            "mode": "demo" if account_id.upper().startswith("DU") else "live",
            "server": "ibkr",
            "company": "Interactive Brokers",
            "currency": str(row.get("currency") or "USD"),
            "balance": _num(row.get("availablefunds")),
            "equity": _num(row.get("netliquidation")),
            "margin": _num(row.get("initialmargin")),
            "marginFree": _num(row.get("availablefunds")),
            "marginLevel": 0.0,
            "profit": _num(row.get("unrealizedpnl")),
            "leverage": 0.0,
            "marginMode": "unknown",
            "tradeAllowed": True,
            "expertAllowed": True,
        }

    def positions(self) -> list[dict[str, Any]]:
        account_id = self._account_id()
        rows = self._get(f"/portfolio/{urllib.parse.quote(account_id)}/positions/0") or []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            qty = _num(row.get("position"))
            out.append(
                {
                    "ticket": _int(row.get("conid")),
                    "symbol": str(row.get("contractDesc") or row.get("ticker") or "").upper(),
                    "side": "buy" if qty >= 0 else "sell",
                    "volume": abs(qty),
                    "openPrice": _num(row.get("avgCost") or row.get("avgPrice")),
                    "currentPrice": _num(row.get("mktPrice")),
                    "stopLoss": None,
                    "takeProfit": None,
                    "profit": _num(row.get("unrealizedPnl")),
                    "swap": 0.0,
                    "magic": 0,
                    "comment": "ibkr (openedAt is first seen)",
                    # The CPAPI position row has no open time; the execution is
                    # in the deal window. Never date an unknown as 1970.
                    "openedAt": int(time.time() * 1000),
                }
            )
        return out

    def orders(self) -> list[dict[str, Any]]:
        data = self._get("/iserver/account/orders") or {}
        rows = data.get("orders") if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            out.append(
                {
                    "ticket": _int(row.get("orderId")),
                    "symbol": str(row.get("ticker") or "").upper(),
                    "type": str(row.get("orderType") or ""),
                    "volumeCurrent": _num(row.get("remainingQuantity")),
                    "openPrice": _num(row.get("price")),
                    "currentPrice": 0.0,
                    "stopLoss": _num(row.get("stop_price")) or None,
                    "takeProfit": None,
                    "state": str(row.get("status") or ""),
                    "magic": 0,
                    "comment": "ibkr",
                    "placedAt": _ms(row.get("lastExecutionTime_r") or row.get("orderTime")),
                }
            )
        return out

    def _conid(self, symbol: str) -> int:
        key = symbol.upper()
        if key in self._conids:
            return self._conids[key]
        rows = self._get("/iserver/secdef/search", {"symbol": key}) or []
        for row in rows if isinstance(rows, list) else []:
            conid = _int(row.get("conid"))
            if conid:
                self._conids[key] = conid
                return conid
        raise AdapterUnavailable("IBKR_NO_SYMBOL", f"IBKR has no contract for {symbol}")

    def quote(self, symbol: str) -> dict[str, Any]:
        requested = str(symbol or "").strip()
        conid = self._conid(requested)
        rows = self._get(
            "/iserver/marketdata/snapshot",
            {"conids": conid, "fields": "31,84,86"},
        ) or []
        row = rows[0] if isinstance(rows, list) and rows else {}
        bid = _num(row.get("84"))
        ask = _num(row.get("86"))
        last = _num(row.get("31"))
        return {
            "symbol": requested.upper(),
            "requestedSymbol": requested,
            "bid": bid,
            "ask": ask,
            "last": last or bid or ask,
            "spreadPoints": None,
            "digits": 4,
            "point": 0.0001,
            "stopsLevelPoints": 0,
            "serverTimeMs": int(time.time() * 1000),
            "provider": "ibkr",
        }

    def order_status(self, ticket: int) -> dict[str, Any]:
        return {"found": False, "ticket": int(ticket)}

    # ── reconciliation ───────────────────────────────────────────────────────
    def _executions(self) -> list[Execution]:
        rows = self._get("/iserver/account/trades") or []
        out: list[Execution] = []
        for row in rows if isinstance(rows, list) else []:
            qty = abs(_num(row.get("size")))
            price = _num(row.get("price"))
            when = _ms(row.get("trade_time_r") or row.get("trade_time"))
            symbol = str(row.get("symbol") or row.get("contractDesc") or "").upper()
            if qty <= 0 or price <= 0 or not symbol:
                continue
            side_raw = str(row.get("side") or "").upper()
            side = "buy" if side_raw in ("B", "BUY", "BOT") else "sell"
            fee = abs(_num(row.get("commission")))
            out.append(
                Execution(
                    id=str(row.get("execution_id") or row.get("id") or f"{symbol}-{when}-{len(out)}"),
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    price=price,
                    time_ms=when or int(time.time() * 1000),
                    fee=fee,
                )
            )
        return out

    def deals_since(self, since_ms: int) -> list[dict[str, Any]]:
        since = int(since_ms or 0)
        executions = self._executions()
        if since > 0:
            executions = [e for e in executions if e.time_ms >= since]
        return normalize_fifo(executions)

    def deals_window(self, days: int) -> list[dict[str, Any]]:
        # The CPAPI executions endpoint is a recent-window read; filter locally
        # so the caller still gets an honest `days` contract.
        since = int(time.time() * 1000) - max(1, min(int(days or 7), 3650)) * 86_400_000
        return self.deals_since(since)


__all__ = ["IBKRAdapter"]
