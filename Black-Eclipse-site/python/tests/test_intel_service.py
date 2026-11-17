"""End-to-end intel pipeline over fixtures — no sockets, no clock, no model."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from harness.intel import service as service_module
from harness.intel.service import IntelService
from harness.intel.store import IntelStore
from harness.persistence import AgentMemoryStore

AS_OF = "2026-11-17"
LAST = date(2026, 11, 17)


FORM4_BUYER_A = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Ada Officer</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>true</isOfficer><isDirector>false</isDirector>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>false</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-11-10</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>200</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

FORM4_BUYER_B = FORM4_BUYER_A.replace("Ada Officer", "Bo Director").replace(
    "<isOfficer>true</isOfficer><isDirector>false</isDirector>",
    "<isOfficer>false</isOfficer><isDirector>true</isDirector>",
).replace("2026-11-10", "2026-11-12").replace("<value>1000</value>", "<value>500</value>")


def _pageviews_json(days: int = 97) -> str:
    items = []
    for index in range(days):
        day = LAST - timedelta(days=days - 1 - index)
        views = 100 if index < days - 5 else 320
        items.append({"timestamp": day.strftime("%Y%m%d00"), "views": views})
    return json.dumps({"items": items})


def _make_fetch() -> service_module.sec.Fetch:
    tickers = {"0": {"cik_str": 123, "ticker": "TEST", "title": "Test Corp"}}
    submissions = {"filings": {"recent": {
        "form": ["4", "4", "13D", "8-K"],
        "filingDate": ["2026-11-12", "2026-11-13", "2026-10-20", "2026-11-01"],
        "accessionNumber": ["0000-1", "0000-2", "0000-3", "0000-4"],
        "primaryDocument": ["form4.xml", "form4.xml", "d13d.htm", "8k.htm"],
    }}}

    def fetch(url: str) -> str:
        if "company_tickers.json" in url:
            return json.dumps(tickers)
        if "submissions/CIK0000000123.json" in url:
            return json.dumps(submissions)
        if "00001/index.json" in url or "00002/index.json" in url:
            return json.dumps({"directory": {"item": [{"name": "form4.xml"}]}})
        if "00001/form4.xml" in url:
            return FORM4_BUYER_A
        if "00002/form4.xml" in url:
            return FORM4_BUYER_B
        if "pageviews/per-article" in url:
            return _pageviews_json()
        raise OSError(f"unexpected url {url}")

    return fetch


@pytest.fixture()
def intel(tmp_path):
    service_module._tickers_cache["map"] = {}
    service_module._tickers_cache["at"] = 0.0
    store = AgentMemoryStore(os.path.join(str(tmp_path), "intel-test.db"))
    return IntelService(store, fetch=_make_fetch(), today=lambda: LAST)


def _scan(intel: IntelService, tickers, **kwargs):
    return asyncio.run(intel.scan("local", tickers, as_of=AS_OF, deadline_seconds=15, **kwargs))


def test_scan_measures_every_signal_and_produces_a_bullish_card(intel):
    result = _scan(intel, ["TEST"])

    assert result["scanned"] == 1
    assert result["partial"] is False
    entity = result["entities"][0]
    assert entity["status"] == "ok"
    assert entity["missing"] == {}

    signals = {row["signal"] for row in entity["observations"]}
    assert signals == {"insider_conviction", "activist_stake", "filing_heat", "attention_velocity"}

    insider = next(o for o in entity["observations"] if o["signal"] == "insider_conviction")
    assert insider["value"] == pytest.approx(300_000)  # 1000*200 + 500*200
    assert len(insider["detail"]["buyers"]) == 2
    assert insider["detail"]["cluster"] is True

    card = result["cards"][0]
    assert card["entity"] == "TEST"
    assert card["direction"] == "bullish"
    assert "insider" in card["thesis"].lower()
    assert set(card["sources"]) == {"sec-edgar", "wikipedia"}


def test_observations_persist_and_a_rescan_does_not_duplicate(intel):
    first = _scan(intel, ["TEST"])
    assert first["scanned"] == 1
    rows_before = intel.store.list_observations("local", entity="TEST")
    assert len(rows_before) == 4

    _scan(intel, ["TEST"])
    rows_after = intel.store.list_observations("local", entity="TEST")
    assert len(rows_after) == 4  # deterministic ids, INSERT OR REPLACE

    series = intel.store.series("local", "TEST", "insider_conviction")
    assert [row["value"] for row in series] == [pytest.approx(300_000)]


def test_cards_are_retrievable_and_scoped_to_the_owner(intel):
    _scan(intel, ["TEST"])
    cards = intel.cards("local")
    assert len(cards) == 1
    assert cards[0]["entity"] == "TEST"
    assert intel.cards("someone-else") == []


def test_an_unknown_ticker_is_unavailable_not_a_zero(intel):
    result = _scan(intel, ["ZZZZ"])
    assert result["scanned"] == 0
    entity = result["entities"][0]
    assert entity["status"] == "unavailable"
    assert "ticker→CIK" in entity["reason"]
    assert result["cards"] == []


def test_a_failed_source_reports_the_reason_and_still_returns_the_rest(monkeypatch):
    service_module._tickers_cache["map"] = {}
    service_module._tickers_cache["at"] = 0.0

    def broken(url: str) -> str:
        if "company_tickers" in url:
            return json.dumps({"0": {"cik_str": 123, "ticker": "TEST", "title": "Test Corp"}})
        if "pageviews" in url:
            raise OSError("network down")
        if "submissions" in url:
            return json.dumps({"filings": {"recent": {
                "form": ["4"], "filingDate": ["2026-11-12"],
                "accessionNumber": ["0000-1"], "primaryDocument": ["form4.xml"],
            }}})
        if "index.json" in url:
            return json.dumps({"directory": {"item": [{"name": "form4.xml"}]}})
        if "form4.xml" in url:
            return FORM4_BUYER_A
        raise OSError(url)

    from harness.persistence import AgentMemoryStore as Store
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "x.db")
    intel = IntelService(Store(path), fetch=broken, today=lambda: LAST)
    result = _scan(intel, ["TEST"])
    entity = result["entities"][0]
    assert entity["status"] == "ok"
    assert "attention_velocity" in entity["missing"]
    assert "pageview fetch failed" in entity["missing"]["attention_velocity"]


def test_watchlist_round_trip(intel):
    intel.store.add_watch("local", ["test", "aapl"])
    assert intel.store.list_watch("local") == ["AAPL", "TEST"]
    intel.store.remove_watch("local", ["aapl"])
    assert intel.store.list_watch("local") == ["TEST"]


def test_tool_scan_renders_measured_and_unmeasured(intel):
    from harness.intel import tools

    ctx = SimpleNamespace(user_id="local")
    text, payload = asyncio.run(tools.intel_scan({"tickers": ["TEST"]}, ctx, intel))
    assert "priority" in text
    assert "not a probability" in text
    assert payload["status"] in ("OK", "PARTIAL")
    assert payload["scanned"] == 1


def test_tool_reports_unavailable_without_inventing_numbers(intel):
    from harness.intel import tools

    ctx = SimpleNamespace(user_id="local")
    text, payload = asyncio.run(tools.intel_entity({"ticker": "TEST"}, ctx, intel))
    assert payload["status"] == "UNAVAILABLE"
    assert "not evidence of calm" in text


def test_boot_wiring_registers_every_intel_tool_on_the_shared_registry(tmp_path):
    from harness.intel.bootstrap import install_intel_layer
    from harness.tools import ToolRegistry

    store = AgentMemoryStore(os.path.join(str(tmp_path), "boot.db"))
    host = SimpleNamespace(store=store, registry=ToolRegistry())
    install_intel_layer(host)
    assert host.intel is not None
    for name in ("intel_scan", "intel_entity", "intel_series",
                 "intel_cards", "intel_watch", "intel_catalog"):
        definition = host.registry.get(name)
        assert definition is not None, name
        assert definition.permission == "read"
        assert definition.risk == "low"
    # The agent can only call a tool it advertises.
    from harness.agents import INTEL_TOOLS, ECLIPSE_AGENT

    assert set(INTEL_TOOLS) <= set(ECLIPSE_AGENT.tools)
