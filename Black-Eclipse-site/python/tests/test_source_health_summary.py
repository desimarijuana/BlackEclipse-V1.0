"""Phase 2: the source-health summary partition (Python tool text).

The recorded ledger must be readable INSIDE the 24k tool-result bound. On a
sparse ledger the rendered text names at least one recorded route with its true
counts, and the declared list is withheld with a stated count.
"""

from __future__ import annotations

import pytest

from harness.finance_tools import get_source_health
from harness.tools import ToolContext, bound_tool_text, MAX_TOOL_RESULT_CHARS


class StubBridge:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def fetch(self, capability, params):
        self.calls.append((capability, params))
        return self.payload


def _ctx(bridge):
    return ToolContext(run_id="r", log=lambda *a: None, data_bridge=bridge)


@pytest.mark.asyncio
async def test_sparse_ledger_head_names_a_recorded_route_within_the_bound():
    # A ledger with 2 recorded routes, but the declared universe is huge. The
    # bridge partitions: recorded head + withheld count.
    payload = {
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
             "lastAttemptAt": "2026-09-30T00:00:00Z", "lastSuccessAt": "2026-09-30T00:00:00Z",
             "lastFailureAt": None, "sourceOfTruth": "live smoke/production"},
            {"source": "LIVE_STRUCTURED", "market": "PK", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "live", "health": "failing",
             "success": 0, "fail": 3, "total": 3, "successRate": 0.0,
             "lastAttemptAt": "2026-09-30T00:00:00Z", "lastSuccessAt": None,
             "lastFailureAt": "2026-09-30T00:00:00Z", "sourceOfTruth": "live smoke/production"},
        ],
        "withheld": 1194,
    }
    text, data = await get_source_health({}, _ctx(StubBridge(payload)))
    assert "US" in text and "PK" in text
    assert "10 ok" in text and "3 fail" in text
    assert "1194" in text  # the withheld count is stated
    # The whole rendered text stays under the execution bound.
    bounded, truncated, _shown, total = bound_tool_text(text)
    assert truncated is False or total <= len(text)
    assert len(text) <= MAX_TOOL_RESULT_CHARS
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_no_recorded_routes_is_no_data():
    payload = {"status": "OK", "summary": {"recordedRoutes": 0}, "rows": [], "withheld": 0}
    text, data = await get_source_health({}, _ctx(StubBridge(payload)))
    assert "no_data" in text.lower() or "No source health recorded" in text
    assert data["failureClass"] == "no_data"


@pytest.mark.asyncio
async def test_recorded_only_flag_is_forwarded_to_the_bridge():
    bridge = StubBridge({"status": "OK", "summary": {"recordedRoutes": 0}, "rows": [], "withheld": 0})
    await get_source_health({"recordedOnly": True}, _ctx(bridge))
    assert bridge.calls[-1][1].get("recordedOnly") is True


@pytest.mark.asyncio
async def test_fixture_rows_are_labelled_not_live():
    payload = {
        "status": "OK",
        "summary": {"recordedRoutes": 0, "fixtureRoutes": 1, "byHealth": {"healthy": 1}},
        "rows": [
            {"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "fixture", "health": "healthy",
             "success": 1, "fail": 0, "total": 1, "sourceOfTruth": "fixture"},
        ],
        "withheld": 0,
    }
    text, _data = await get_source_health({}, _ctx(StubBridge(payload)))
    assert "fixture" in text
    assert "via fixture" in text
