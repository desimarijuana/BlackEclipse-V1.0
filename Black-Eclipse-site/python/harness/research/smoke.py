"""Operator-triggered live smoke checks (Phase 6) — NOT part of the default suite.

These contact REAL external providers, so they are excluded from `npm run test`
(`pytest.ini` runs only `tests`, and this file lives here, not under `tests/`).
Run it deliberately:

    node scripts/test-python.js smoke            # (or:)
    cd Black-Eclipse-site && python -m harness.research.smoke

Each check is bounded, prints exactly which provider it contacted and the
structured diagnostic, and never fabricates a value. Exit code is non-zero when a
check that should be reachable is not, so an operator sees a real state.

What it contacts (all keyless, public, read-only):
  * DuckDuckGo HTML search endpoint            — web search route
  * https://www.sec.gov/files/company_tickers.json — web fetch route
  * https://data.sec.gov XBRL companyconcept   — SEC direct route
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


async def _health(bridge: Any) -> dict[str, Any]:
    return await bridge.fetch("research_health", {})


async def _sec_nvda(bridge: Any) -> dict[str, Any]:
    return await bridge.fetch("sec_filings", {"symbol": "NVDA", "market": "US"})


def _print(title: str, payload: dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str)[:4000])


async def main_async() -> int:
    """Build the real HTTP data bridge and probe each route once."""
    from ..service import _HttpDataBridge  # type: ignore[attr-defined]

    # The bridge needs the TS front door running. These env vars mirror the
    # runtime's own defaults; a running `npm run dev` satisfies them.
    import os

    base = os.environ.get("HARNESS_CALLBACK_URL") or os.environ.get("HARNESS_PY_URL") or "http://127.0.0.1:3000"
    token = os.environ.get("CRON_SECRET")
    bridge = _HttpDataBridge(base, token)

    failures: list[str] = []

    health = await _health(bridge)
    _print("research_health", health)
    if health.get("status") != "OK":
        failures.append("research_health probe failed")

    sec = await _sec_nvda(bridge)
    _print("sec_filings NVDA", {k: v for k, v in sec.items() if k != "periods"})
    periods = sec.get("periods") or []
    print(f"  periods returned: {len(periods)}")
    if sec.get("status") != "OK" or not periods:
        failures.append("SEC direct route returned no NVDA periods")

    if failures:
        print("\nSMOKE FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll smoke checks reachable.")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
