"""Live DEMO smoke runner for the broker/trading surface.

Talks to a running Eclipse Python runtime (default http://127.0.0.1:8765).
Loopback is authorized without a token; for a remote runtime set CRON_SECRET.

This is the one check a unit test cannot make: it proves the terminal actually
answers, that the static symbol facts are read, and — when you ask for it — that
a WORKING order can be re-priced and the broker stores what you asked for.

Mutations are opt-in. Without `--modify-order` the script is read-only.

Examples:
  python scripts/trade_demo_smoke.py
  python scripts/trade_demo_smoke.py --symbol XAUUSD
  python scripts/trade_demo_smoke.py --connection brk_abc123
  python scripts/trade_demo_smoke.py --modify-order 123456789 --price 4025.10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def _base_url() -> str:
    return (os.environ.get("HARNESS_PY_URL") or "http://127.0.0.1:8765").rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("CRON_SECRET")
    return {"X-Harness-Operator": token} if token else {}


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    try:
        with httpx.Client(
            base_url=_base_url(), timeout=60.0, headers=_headers()
        ) as client:
            res = client.request(method, path, json=body)
    except httpx.HTTPError as exc:
        print(
            f"cannot reach the runtime at {_base_url()}: {exc}\n"
            "start it with `npm run dev` (or point HARNESS_PY_URL at it)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        payload = res.json()
    except ValueError:
        payload = res.text
    if res.status_code >= 300:
        print(
            f"HTTP {res.status_code} on {method} {path}: "
            f"{json.dumps(payload, indent=2, default=str)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return payload


def _pick_connection(explicit: str) -> dict[str, Any]:
    connections = _request("GET", "/trading/connections").get("connections") or []
    if not connections:
        print(
            "no broker connection is saved; add one in Settings › Broker connection",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if explicit:
        match = [row for row in connections if row.get("id") == explicit]
        if not match:
            print(f"no saved connection with id {explicit!r}", file=sys.stderr)
            raise SystemExit(1)
        return match[0]
    demo = [row for row in connections if row.get("mode") == "demo"]
    if len(demo) == 1:
        return demo[0]
    if not demo:
        print(
            "no DEMO connection is saved; this smoke run refuses a live account",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        "several demo connections are saved; pass --connection <id>: "
        + ", ".join(f"{row.get('id')} ({row.get('label')})" for row in demo),
        file=sys.stderr,
    )
    raise SystemExit(1)


def _check(label: str, condition: bool, detail: str = "") -> bool:
    print(f"[{'ok' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return condition


def main() -> None:
    parser = argparse.ArgumentParser(description="Eclipse trading DEMO smoke runner")
    parser.add_argument("--connection", default="", help="saved connection id (default: the only demo one)")
    parser.add_argument("--symbol", default="", help="symbol for the quote/symbol-facts checks")
    parser.add_argument("--modify-order", type=int, default=0, metavar="TICKET",
                        help="re-price this WORKING order (mutates the demo account)")
    parser.add_argument("--price", type=float, default=None, help="new price for --modify-order")
    parser.add_argument("--sl", type=float, default=None, help="new stop loss for --modify-order")
    parser.add_argument("--tp", type=float, default=None, help="new take profit for --modify-order")
    args = parser.parse_args()

    if args.modify_order and args.price is None and args.sl is None and args.tp is None:
        parser.error("--modify-order needs --price, --sl and/or --tp")

    failures = 0
    connection = _pick_connection(args.connection)
    connection_id = str(connection["id"])
    print(f"connection: {connection.get('label')} ({connection_id}, {connection.get('mode')})")

    probe = _request("POST", f"/trading/connections/{connection_id}/test")
    failures += not _check("terminal probe", bool(probe.get("available")),
                           str(probe.get("error") or probe.get("status") or ""))

    account = _request("GET", f"/trading/connections/{connection_id}/account")
    failures += not _check(
        "account read",
        bool(account.get("available")),
        f"{account.get('data', {}).get('currency', '?')} "
        f"equity {account.get('data', {}).get('equity', '?')}",
    )

    positions = _request("GET", f"/trading/connections/{connection_id}/positions")
    failures += not _check("positions read", bool(positions.get("available")),
                           f"{len(positions.get('data') or [])} open")

    orders = _request("GET", f"/trading/connections/{connection_id}/orders")
    failures += not _check("working orders read", bool(orders.get("available")),
                           f"{len(orders.get('data') or [])} working")

    symbol = (args.symbol or "").strip().upper()
    if symbol:
        quote = _request(
            "GET", f"/trading/connections/{connection_id}/quote?symbol={symbol}"
        )
        failures += not _check(
            "quote read",
            bool(quote.get("available")),
            f"bid {quote.get('data', {}).get('bid')} / ask {quote.get('data', {}).get('ask')}",
        )

        facts = _request("GET", f"/trading/connections/{connection_id}/symbols/{symbol}")
        data = facts.get("data") or {}
        failures += not _check(
            "static symbol facts (no tick needed)",
            bool(facts.get("available")),
            f"tradeMode {data.get('tradeMode')}, contract {data.get('contractSize')}, "
            f"step {data.get('volumeStep')}",
        )
        # Informational: the Python MT5 package does not reliably expose sessions.
        if data.get("sessionsAvailable"):
            print(f"       broker sessions: {len(data.get('sessionDeals') or [])} window(s) reported")
        else:
            print(f"       broker sessions unavailable: {data.get('sessionNote') or 'not reported'}")

    if args.modify_order:
        body = {
            key: value for key, value in
            (("price", args.price), ("stopLoss", args.sl), ("takeProfit", args.tp))
            if value is not None
        }
        result = _request(
            "POST",
            f"/trading/connections/{connection_id}/orders/{int(args.modify_order)}/modify",
            body,
        )
        detail = result.get("result") or {}
        failures += not _check(
            f"modify working order {args.modify_order}",
            bool(result.get("modified")),
            f"stored price {detail.get('price')}, SL {detail.get('stopLoss')}, "
            f"TP {detail.get('takeProfit')}",
        )
        failures += not _check("broker read-back verified", bool(detail.get("verified")),
                               str(detail.get("verifyNote") or ""))

    print()
    if failures:
        print(f"{failures} check(s) failed", file=sys.stderr)
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
