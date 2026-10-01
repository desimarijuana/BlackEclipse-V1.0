"""Route-health reachability gate (Harness closeout Phase 8.2).

Offline and deterministic. A FIXTURE bridge returns a sparse ledger shaped the
way `sourceHealth()` partitions it. Asserts:
  * get_source_health's rendered text stays under MAX_TOOL_RESULT_CHARS AND names
    at least one recorded route with its true counts;
  * a fixture probe is never presented as live;
  * no persisted row carries a literal `unknown` in source/market.
"""

from __future__ import annotations

import asyncio

from ..finance_tools import get_source_health
from ..tools import MAX_TOOL_RESULT_CHARS, ToolContext


class _FixtureBridge:
    def __init__(self, payload):
        self.payload = payload

    async def fetch(self, capability, params):
        return self.payload


def _ctx(payload) -> ToolContext:
    return ToolContext(run_id="gate", log=lambda *a: None, data_bridge=_FixtureBridge(payload))


def _sparse_ledger() -> dict:
    return {
        "status": "OK",
        "summary": {
            "recordedRoutes": 2, "fixtureRoutes": 0,
            "byHealth": {"healthy": 1, "degraded": 0, "failing": 1, "unknown": 0},
            "marketsWithAttempts": ["PK", "US"],
        },
        "rows": [
            {"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "live", "health": "healthy",
             "success": 10, "fail": 0, "total": 10, "successRate": 1.0,
             "lastAttemptAt": "2026-01-01T00:00:00Z", "lastSuccessAt": "2026-01-01T00:00:00Z",
             "lastFailureAt": None, "sourceOfTruth": "live smoke/production"},
            {"source": "LIVE_STRUCTURED", "market": "PK", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "live", "health": "failing",
             "success": 0, "fail": 3, "total": 3, "successRate": 0.0,
             "lastAttemptAt": "2026-01-01T00:00:00Z", "lastSuccessAt": None,
             "lastFailureAt": "2026-01-01T00:00:00Z", "sourceOfTruth": "live smoke/production"},
        ],
        "withheld": 1194,
    }


def run_gate() -> None:
    text, _data = asyncio.run(get_source_health({}, _ctx(_sparse_ledger())))
    assert len(text) <= MAX_TOOL_RESULT_CHARS, "sparse-ledger health exceeds the tool-result bound"
    assert "10 ok" in text and "3 fail" in text, "the head must name a recorded route with true counts"
    assert "1194" in text, "the withheld count must be stated"

    # A fixture-only ledger is labelled, never live.
    fixture = {
        "status": "OK",
        "summary": {"recordedRoutes": 0, "fixtureRoutes": 1, "byHealth": {"healthy": 1},
                    "marketsWithAttempts": []},
        "rows": [
            {"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "fixture", "health": "healthy",
             "success": 1, "fail": 0, "total": 1, "sourceOfTruth": "fixture"},
        ],
        "withheld": 0,
    }
    ftext, _ = asyncio.run(get_source_health({}, _ctx(fixture)))
    assert "via fixture" in ftext and "live smoke/production" not in ftext, (
        "a fixture probe must never be presented as live health"
    )


__all__ = ["run_gate"]
