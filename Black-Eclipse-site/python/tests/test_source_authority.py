"""Phase 13 — source authority and freshness arbitration.

The labelled cases from the phase file's gate G1. The vault-vs-live disagreement
is UNREACHABLE on the pre-change code (the first success won and the live source
was never called), so case (c) fails before this phase. All fixtures are
synthetic and never touch JDdS.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from typing import Any

import pytest

from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
from harness.retrieval.authority import (
    AUTHORITY,
    SourceDecision,
    authority_for,
    decide_source,
)
from harness.retrieval.contract import NormalizedFinancialObject, SourceReference
from harness.retrieval.sources import SourceOutcome
from harness.tools import DataBridge

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "retrieval")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ── helpers ──────────────────────────────────────────────────────────────────


def _objects(specs: list[dict[str, Any]], tier: str) -> list[NormalizedFinancialObject]:
    source = SourceReference(source="X", sourceType=tier)
    out = []
    for spec in specs:
        out.append(
            NormalizedFinancialObject(
                name=spec["name"],
                value=spec["value"],
                source=source,
                observation_time=spec.get("observation_time"),
                observation_source=spec.get("observation_source", "unknown"),
            )
        )
    return out


def _outcome(spec: dict[str, Any]) -> SourceOutcome:
    return SourceOutcome(
        source=spec["source"],
        status="OK",
        objects=_objects(spec["objects"], spec.get("tier", "structured")),
        references=[SourceReference(source=spec["source"], sourceType=spec.get("tier", "structured"))],
    )


def _fixed_now() -> float:
    return dt.datetime(2026, 10, 2, 12, 0, 0, tzinfo=dt.timezone.utc).timestamp()


# ── table + pure decision function ──────────────────────────────────────────


def test_authority_has_one_row_per_data_type_and_expected_policies():
    assert AUTHORITY["current_quote"].policy == "arbitrated"
    assert AUTHORITY["historical_prices"].policy == "arbitrated"
    assert AUTHORITY["macro_series"].policy == "arbitrated"
    assert AUTHORITY["company_profile"].policy == "arbitrated"
    assert AUTHORITY["financial_statements"].policy == "single_best"
    # The vault is no longer first for a current price.
    assert AUTHORITY["current_quote"].candidates[0] == "LIVE_STRUCTURED"
    # A precise series never lists web.
    assert "WEB" not in AUTHORITY["historical_prices"].candidates
    assert "WEB" not in AUTHORITY["macro_series"].candidates


def test_decide_source_rejects_web_for_precise_types():
    authority = authority_for("historical_prices")
    web = SourceOutcome(source="WEB", status="OK", objects=_objects(
        [{"name": "close", "value": 1.0, "observation_time": now_iso()}], "secondary"
    ))
    decision = decide_source(authority, [web], FinancialRetrievalRequest(
        objective="h", dataType="historical_prices", freshnessRequirement="slow"
    ))
    assert decision.chosen is None
    assert any(name == "WEB" and "precise" in why for name, why in decision.rejected)


def test_decide_source_is_pure_and_has_no_side_effects():
    authority = authority_for("current_quote")
    outcomes = [
        SourceOutcome(source="JDDS", status="OK", objects=_objects(
            [{"name": "price", "value": 1.0, "observation_time": now_iso(), "observation_source": "snapshot_write"}],
            "structured",
        ))
    ]
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", freshnessRequirement="realtime")
    first = decide_source(authority, outcomes, request)
    second = decide_source(authority, outcomes, request)
    assert first == second
    assert isinstance(first, SourceDecision)


# ── G1(c): the vault-vs-live disagreement that is unreachable today ─────────


def test_sources_disagree_yields_no_chosen_value():
    authority = authority_for("current_quote")
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    vault = SourceOutcome(source="JDDS", status="OK", objects=_objects(
        [{"name": "price", "value": 100.0, "observation_time": stamp, "observation_source": "snapshot_write"}],
        "structured",
    ))
    live = SourceOutcome(source="LIVE_STRUCTURED", status="OK", objects=_objects(
        [{"name": "price", "value": 130.0, "observation_time": stamp, "observation_source": "provider_asof"}],
        "structured",
    ))
    decision = decide_source(authority, [vault, live], FinancialRetrievalRequest(
        objective="q", dataType="current_quote", freshnessRequirement="realtime"
    ))
    assert decision.chosen is None
    assert "CONFLICTING" in decision.reason


# ── fixtures-driven cases ────────────────────────────────────────────────────


def _load_cases() -> dict[str, Any]:
    with open(os.path.join(FIXTURES, "authority_cases.json"), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("case", _load_cases()["cases"], ids=lambda c: c["id"])
def test_labelled_authority_cases(case):
    authority = authority_for(case["dataType"])
    outcomes = [_outcome(spec) for spec in case["outcomes"]]
    request = FinancialRetrievalRequest(
        objective="x", dataType=case["dataType"], freshnessRequirement=case["freshness"]
    )
    decision = decide_source(authority, outcomes, request, now=_fixed_now())

    if case["expect"] == "chosen":
        assert decision.chosen is not None, decision
        if "expectChosen" in case:
            assert decision.chosen == case["expectChosen"]
        if "expectReason" in case:
            assert decision.reason == case["expectReason"]
    else:
        assert decision.chosen is None, decision
        if "expectCode" in case:
            haystack = decision.reason + " " + " ".join(why for _name, why in decision.rejected)
            assert case["expectCode"] in haystack, decision


# ── per-observation staleness (G1(f)) ────────────────────────────────────────


def test_three_stale_rows_in_a_fresh_payload_produce_warnings():
    from harness.retrieval.validate import validate_observations

    fresh = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = SourceReference(source="JDDS")
    objects = [
        NormalizedFinancialObject(name=f"m{i}", value=float(i), dataTimestamp=fresh, source=ref)
        for i in range(37)
    ]
    objects += [
        NormalizedFinancialObject(name=f"stale{i}", value=float(i), dataTimestamp=old, source=ref)
        for i in range(3)
    ]
    _objects_out, warnings = validate_observations(objects, "daily")
    stale_warnings = [w for w in warnings if w.startswith("stale")]
    assert len(stale_warnings) == 3
    # The dataset-level check alone would not have flagged these (newest is fresh).
    from harness.retrieval.validate import validate_objects

    _, dataset_warnings = validate_objects(list(objects), "daily")
    assert not [w for w in dataset_warnings if "stale" in w]


def test_a_saved_snapshot_is_never_worded_as_live():
    from harness.retrieval.validate import validate_observations

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    obj = NormalizedFinancialObject(
        name="price", value=1.0, dataTimestamp=now, source=SourceReference(source="JDDS"),
        observation_time=now, observation_source="snapshot_write",
    )
    _out, warnings = validate_observations([obj], "realtime")
    assert any("saved snapshot" in w and "not a live reading" in w for w in warnings)
    assert any("saved snapshot, not a live reading" in t for t in obj.transformations)
    assert obj.quality == "warning"


def test_old_payloads_without_observation_fields_still_load():
    obj = NormalizedFinancialObject(name="price", value=1.0, source=SourceReference(source="x"))
    assert obj.observation_time is None
    assert obj.observation_source == "unknown"


# ── layer integration: arbitration and the web prohibition ───────────────────


class _Bridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        value = self.responses.get(capability)
        if value is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        return value


def _fresh_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _quote(price: float, source: str, *, snapshot: bool = False, at: str | None = None) -> dict[str, Any]:
    now = at or _fresh_iso()
    return {
        "status": "OK", "symbol": "AAPL", "provider": source,
        "updatedAt": now,
        "observationTime": now,
        "observationSource": "snapshot_write" if snapshot else "provider_asof",
        "price": {"price": price, "changePct": 1.0},
    }


@pytest.mark.asyncio
async def test_layer_arbitrates_live_and_vault_and_shows_the_conflict():
    # Both a saved snapshot (vault) and a live reading answer, at the SAME instant,
    # 1.2% apart — the disagreement the first-success path could never surface.
    stamp = _fresh_iso()
    bridge = _Bridge({
        "market_snapshot": _quote(237.0, "scraper", snapshot=True, at=stamp),
        "live_quote": _quote(240.0, "yfinance", at=stamp),
    })
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(FinancialRetrievalRequest(
        objective="q", dataType="current_quote", instrument="AAPL", market="US",
        freshnessRequirement="realtime",
    ))
    # Both candidates were consulted (the live source is no longer skipped once
    # the vault would answer), and they disagree.
    assert result.status == "CONFLICTING", result.warnings
    assert result.conflicts and len(result.conflicts[0]["candidates"]) >= 2


@pytest.mark.asyncio
async def test_vault_only_answer_is_labelled_a_saved_snapshot_not_live():
    # Only the vault can answer (no live provider). A current vault row is
    # accepted, but its value is a SNAPSHOT — never worded as a live reading.
    bridge = _Bridge({"market_snapshot": _quote(240.0, "scraper", snapshot=True)})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(FinancialRetrievalRequest(
        objective="q", dataType="current_quote", instrument="AAPL",
        freshnessRequirement="realtime",
    ))
    assert result.status == "OK"
    assert any("not a live reading" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_with_no_bridge_no_source_can_run():
    layer = FinancialRetrievalLayer(None)
    result = await layer.retrieve(FinancialRetrievalRequest(
        objective="q", dataType="current_quote", instrument="AAPL",
    ))
    # No bridge ⇒ no source can run at all; UNAVAILABLE, never a fabricated quote.
    assert result.status == "UNAVAILABLE"
    assert result.data is None


@pytest.mark.asyncio
async def test_historical_prices_never_returns_a_web_result():
    bridge = _Bridge({"web_search": {"status": "OK", "results": [
        {"title": "prices", "url": "https://x.test/a", "snippet": "100"}
    ]}})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(FinancialRetrievalRequest(
        objective="h", dataType="historical_prices", instrument="AAPL",
        freshnessRequirement="slow", allowWeb=True,
    ))
    assert result.status != "OK"
    assert not any(cap == "web_search" for cap, _ in bridge.calls)


# ── The demo regression: get_market_snapshot must not return a stale cap ─────


class _SnapshotBridge(DataBridge):
    """The AMD demo, faithfully: JDdS has a MONTHS-OLD price/cap; a live provider
    (the retrieval-layer `live_quote` capability) has the current one."""

    def __init__(self, vault_ts: str, vault_cap: float, live_cap: float, live_ts: str | None = None) -> None:
        self.vault_ts = vault_ts
        self.live_ts = live_ts or _fresh_iso()
        self.vault_cap = vault_cap
        self.live_cap = live_cap
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        if capability == "source_health":
            return {"status": "UNAVAILABLE"}
        if capability == "market_snapshot":
            return {
                "status": "OK", "symbol": "AMD", "name": "Advanced Micro Devices",
                "exchange": "NASDAQ", "country": "US", "currency": "USD",
                "securityType": "Common Stock", "priceSource": "scraper",
                "instrumentId": "US:AMD",
                "updatedAt": self.vault_ts,
                "observationTime": self.vault_ts,
                "observationSource": "snapshot_write",
                "price": {"price": 150.0, "changePct": 1.0, "marketCap": self.vault_cap},
            }
        if capability == "live_quote":
            return {
                "status": "OK", "symbol": "AMD", "provider": "yfinance",
                "market": "US", "currency": "USD", "instrumentId": "US:AMD",
                "observationTime": self.live_ts, "observationSource": "provider_asof",
                "price": {"price": 170.0, "changePct": 2.0, "marketCap": self.live_cap},
            }
        return {"status": "UNAVAILABLE", "error": f"no fake for {capability}"}


def _months_ago() -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).strftime("%Y-%m-%dT00:00:00Z")


@pytest.mark.asyncio
async def test_demo_stale_market_cap_is_not_returned_as_current():
    # The vault says AMD's market cap is $243B (60 days old); the live provider
    # says $275B (now). The snapshot tool must consult BOTH and not present the
    # old cap as the answer.
    from harness.finance_tools import get_market_snapshot
    from harness.tools import ToolContext

    bridge = _SnapshotBridge(_months_ago(), vault_cap=243_000_000_000, live_cap=275_000_000_000)
    ctx = ToolContext(run_id="r", log=lambda *_: None, data_bridge=bridge)
    text, data = await get_market_snapshot({"symbol": "AMD"}, ctx)

    # Both routes ran: the vault snapshot AND the live provider.
    caps = [c for c, _ in bridge.calls]
    assert "market_snapshot" in caps and "live_quote" in caps

    # The months-old cap is NOT what the user is told is current.
    assert "243" not in text, text
    assert "275" in text, text
    assert data["verified"] is True
    assert data["marketCapOrigin"] == "live"
    # The answer states where it came from and how current it is.
    assert "observation" in text.lower(), text


@pytest.mark.asyncio
async def test_demo_live_price_but_no_live_cap_labels_the_cap_saved():
    # THE REAL US-EQUITY SHAPE: the live provider (yfinance fast_info) returns a
    # price but NO market cap, so the cap can only come from the saved snapshot.
    # The cap must be labelled a saved snapshot — never inherit the live badge.
    from harness.finance_tools import get_market_snapshot
    from harness.tools import ToolContext

    class _NoCapBridge(DataBridge):
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            if capability == "source_health":
                return {"status": "UNAVAILABLE"}
            if capability == "market_snapshot":
                return {
                    "status": "OK", "symbol": "AMD", "name": "Advanced Micro Devices",
                    "exchange": "NASDAQ", "country": "US", "currency": "USD",
                    "securityType": "Common Stock", "priceSource": "scraper",
                    "instrumentId": "US:AMD",
                    "updatedAt": _months_ago(), "observationTime": _months_ago(),
                    "observationSource": "snapshot_write",
                    "price": {"price": 150.0, "changePct": 1.0, "marketCap": 243_000_000_000.0},
                }
            if capability == "live_quote":
                # Exactly what the real yfinance fetcher returns: price, no cap.
                return {
                    "status": "OK", "symbol": "AMD", "provider": "yfinance",
                    "market": "US", "currency": "USD", "instrumentId": "US:AMD",
                    "observationTime": _fresh_iso(), "observationSource": "provider_asof",
                    "price": {"price": 170.0, "changePct": 2.0},
                }
            return {"status": "UNAVAILABLE"}

    ctx = ToolContext(run_id="r", log=lambda *_: None, data_bridge=_NoCapBridge())
    text, data = await get_market_snapshot({"symbol": "AMD"}, ctx)

    # The live price IS current and is used.
    assert "170" in text, text
    # The cap came from the saved snapshot and MUST say so — not "verified".
    assert data["priceOrigin"] == "live"
    assert data["marketCapOrigin"] == "saved"
    assert "saved snapshot" in text.lower(), text
    # A saved-only cap must not put a live badge on the whole payload.
    assert data["verified"] is True  # the PRICE is live...
    assert "243,000,000,000" in text  # ...and the cap is present, but labelled saved


@pytest.mark.asyncio
async def test_demo_disagreement_is_shown_when_sources_differ():
    from harness.finance_tools import get_market_snapshot
    from harness.tools import ToolContext

    # Same instant, 1.2% apart → CONFLICTING: both values must be shown, neither
    # silently asserted as the answer.
    same = _fresh_iso()
    bridge = _SnapshotBridge(same, vault_cap=150.0, live_cap=151.8, live_ts=same)
    ctx = ToolContext(run_id="r", log=lambda *_: None, data_bridge=bridge)
    text, data = await get_market_snapshot({"symbol": "AMD"}, ctx)

    assert "disagree" in text.lower() or "both" in text.lower(), text
    assert data.get("disagreement"), data


