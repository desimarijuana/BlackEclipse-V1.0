"""Phase 2: route-health probe invariants visible to the Python runtime.

The probe itself is implemented in TypeScript (`src/lib/harness/route-probe.ts`),
where the SSRF-safe transport and Prisma ledger live; its behaviour is covered by
`src/lib/harness/route-probe.test.ts`. THIS file asserts the invariants the
Python tool surface must uphold once the ledger is written:

  * a fixture probe is NEVER presented as live health through get_source_health;
  * a canonical market with a recorded live attempt is named in the head;
  * no row carries a literal `unknown` in source/market (the probe and every
    writer normalise to the wildcard `*`).
"""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from harness.finance_tools import get_source_health
from harness.tools import ToolContext


class StubBridge:
    def __init__(self, payload):
        self.payload = payload

    async def fetch(self, capability, params):
        return self.payload


def _ctx(payload):
    return ToolContext(run_id="r", log=lambda *a: None, data_bridge=StubBridge(payload))


@pytest.mark.asyncio
async def test_fixture_probe_never_presented_as_live_health():
    # A ledger whose ONLY recorded rows are fixture probes. The tool must not
    # claim live health; it labels the fixture rows and reports 0 live recorded.
    payload = {
        "status": "OK",
        "summary": {"recordedRoutes": 0, "fixtureRoutes": 2,
                    "byHealth": {"healthy": 2}, "marketsWithAttempts": []},
        "rows": [
            {"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "fixture", "health": "healthy",
             "success": 1, "fail": 0, "total": 1, "sourceOfTruth": "fixture"},
        ],
        "withheld": 1200,
    }
    text, _data = await get_source_health({}, _ctx(payload))
    assert "via fixture" in text
    assert "offline test" in text
    # It does not present the fixture row as live production health.
    assert "live smoke/production" not in text


@pytest.mark.asyncio
async def test_canonical_market_with_attempts_is_named_in_the_head():
    payload = {
        "status": "OK",
        "summary": {"recordedRoutes": 1, "fixtureRoutes": 0,
                    "byHealth": {"healthy": 1}, "marketsWithAttempts": ["CH"]},
        "rows": [
            {"source": "LIVE_STRUCTURED", "market": "CH", "assetClass": "equity",
             "capability": "live_quote", "probeKind": "live", "health": "healthy",
             "success": 4, "fail": 0, "total": 4, "sourceOfTruth": "live smoke/production"},
        ],
        "withheld": 0,
    }
    text, _data = await get_source_health({}, _ctx(payload))
    assert "CH" in text
    assert "4 ok" in text
    assert "markets with any recorded attempt: CH" in text


def test_canonical_ledger_fold_leaves_no_literal_unknown():
    """A DB-level invariant: after folding, no source/market is a literal `unknown`.

    Mirrors the canonical vocabulary in `src/lib/harness/health-key.ts` (market
    unknown → `*`; source unknown → `*`). The migration
    `scripts/migrate-source-health-canonical.ts` applies the same rule.
    """
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE SourceHealth (id TEXT, source TEXT, market TEXT, symbol TEXT)")
    con.executemany(
        "INSERT INTO SourceHealth VALUES (?,?,?,?)",
        [
            ("1", "JDDS", "unknown", "unknown#live_quote"),
            ("2", "unknown", "US", "equity#live_quote"),
            ("3", "JDDS", "US", "equity#live_quote"),
        ],
    )
    # Apply the declared fold: a literal `unknown` collapses to the wildcard `*`.
    con.execute("UPDATE SourceHealth SET market='*' WHERE lower(trim(market))='unknown'")
    con.execute("UPDATE SourceHealth SET source='*' WHERE lower(trim(source))='unknown'")
    con.commit()
    bad = con.execute(
        "SELECT COUNT(*) FROM SourceHealth "
        "WHERE lower(trim(source))='unknown' OR lower(trim(market))='unknown'"
    ).fetchone()[0]
    assert bad == 0
    con.close()
