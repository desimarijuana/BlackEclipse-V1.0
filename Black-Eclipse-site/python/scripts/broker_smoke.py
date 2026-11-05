"""Live broker smoke test against a running Eclipse runtime.

It exercises the real broker: probe → account/positions/orders → a deals window
→ one reconciliation sync. Read-only against the broker; the only write is the
local mirror, exactly like a normal sync.

Examples:
  python scripts/broker_smoke.py
  python scripts/broker_smoke.py --connection brk_abc123 --days 30

Exit codes: 0 all checks passed, 1 a check failed, 2 the runtime was unreachable.
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
        with httpx.Client(base_url=_base_url(), timeout=120.0, headers=_headers()) as client:
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


def _pick(explicit: str) -> dict[str, Any]:
    connections = _request("GET", "/trading/connections").get("connections") or []
    if not connections:
        print("no broker connection is saved; add one in Settings › Broker connection", file=sys.stderr)
        raise SystemExit(1)
    if explicit:
        match = [row for row in connections if row.get("id") == explicit]
        if not match:
            print(f"no saved connection with id {explicit!r}", file=sys.stderr)
            raise SystemExit(1)
        return match[0]
    demo = [row for row in connections if row.get("mode") == "demo"]
    return demo[0] if demo else connections[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe, read and sync a broker once.")
    parser.add_argument("--connection", default="", help="connection id (default: first demo, else first)")
    parser.add_argument("--days", type=int, default=7, help="deal window in days (1-90)")
    args = parser.parse_args()

    connection = _pick(args.connection)
    days = max(1, min(int(args.days or 7), 90))
    report = _request(
        "POST",
        f"/trading/connections/{connection['id']}/smoke",
        {"days": days},
    )

    print(f"connection: {connection.get('label')} ({connection.get('kind')}, {connection.get('mode')})")
    for check in report.get("checks", []):
        mark = "PASS" if check.get("ok") else "FAIL"
        print(f"  [{mark}] {check.get('name'):10s} {check.get('detail', '')}")
    counts = report.get("counts") or {}
    if counts:
        print(
            f"  counts: {counts.get('positions', 0)} position(s), "
            f"{counts.get('orders', 0)} order(s), {counts.get('deals', 0)} deal leg(s)"
        )
    sync = report.get("sync") or {}
    if sync:
        print(
            f"  sync: ok={sync.get('ok')} fillsAdded={sync.get('fillsAdded')} "
            f"positions={sync.get('positions')}"
        )
    if not report.get("ok"):
        print(f"SMOKE FAILED: {report.get('error') or 'one or more checks failed'}", file=sys.stderr)
        return 1
    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
