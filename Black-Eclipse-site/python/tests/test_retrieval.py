"""Phase 2 — Financial Retrieval Layer tests (Milestones 2A–2L).

Covers the unified contract, planner, structured/web retrieval, normalization,
cache, parallel retrieval, validation, conflicts and aggregation. Everything is
driven through fakes — no network, no JDdS, no provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
from harness.retrieval.aggregate import aggregate, derive_evidence
from harness.retrieval.cache import RetrievalCache
from harness.retrieval.conflicts import resolve_group
from harness.retrieval.contract import NormalizedFinancialObject, SourceReference
from harness.retrieval.normalize import normalize_history, normalize_quote
from harness.retrieval.parallel import run_parallel
from harness.retrieval.planner import plan_retrieval
from harness.retrieval.sources import SourceOutcome
from harness.retrieval.validate import validate_object, validate_objects
from harness.tools import DataBridge


class FakeBridge(DataBridge):
    """Answers by capability from a table; records every call for assertions."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        value = self.responses.get(capability)
        if value is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        if callable(value):
            result = value(params)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        return value


def quote_payload(price: float = 237.42, source: str = "scraper") -> dict[str, Any]:
    return {
        "status": "OK",
        "symbol": "AAPL",
        "priceSource": source,
        "updatedAt": "2026-09-20T12:00:00.000Z",
        "price": {"price": price, "changePct": 1.23, "volume": 1000, "marketCap": None, "peRatio": None},
    }


def research_payload() -> dict[str, Any]:
    return {
        "status": "OK",
        "query": "why did NVDA move",
        "results": [
            {"title": "SEC filing", "url": "https://www.sec.gov/x", "snippet": "8-K", "publishedAt": None},
            {"title": "NVDA jumps", "url": "https://www.reuters.com/a", "snippet": "rally", "publishedAt": "2026-09-20"},
        ],
    }


# ── 2A contract ─────────────────────────────────────────────────────────────


def test_contract_defaults_and_provenance():
    request = FinancialRetrievalRequest(objective="price", dataType="current_quote", instrument="aapl")
    assert request.freshnessRequirement == "any"
    assert request.allowWeb is True

    obj = NormalizedFinancialObject(
        name="price", value=1.0, source=SourceReference(source="x")
    )
    assert obj.source.publishedAt is None  # never fabricated


# ── 2C planner ──────────────────────────────────────────────────────────────


def test_planner_selects_structured_for_quotes_and_history():
    quote = plan_retrieval(FinancialRetrievalRequest(objective="q", dataType="current_quote"))
    assert quote.sources[0] == "JDDS"
    assert quote.requires_precise_data is True

    history = plan_retrieval(FinancialRetrievalRequest(objective="h", dataType="historical_prices"))
    assert "WEB" not in history.sources  # a series is never web-sourced


def test_planner_selects_web_for_research_and_earnings():
    research = plan_retrieval(FinancialRetrievalRequest(objective="r", dataType="web_research"))
    assert research.sources == ["WEB"]

    earnings = plan_retrieval(FinancialRetrievalRequest(objective="e", dataType="earnings"))
    assert earnings.sources[0] == "WEB"


def test_planner_respects_allow_web_false():
    plan = plan_retrieval(FinancialRetrievalRequest(objective="r", dataType="web_research", allowWeb=False))
    assert "WEB" not in plan.sources
    assert plan.warnings  # explicit that nothing is available


# ── 2D/2F structured + normalization ────────────────────────────────────────


def test_normalize_quote_keeps_value_and_timestamp():
    ref = SourceReference(source="JDDS")
    objects = normalize_quote(quote_payload(), ref)
    names = {o.name for o in objects}
    assert {"price", "changePct", "volume"} <= names
    price = next(o for o in objects if o.name == "price")
    assert price.value == 237.42
    assert price.dataTimestamp == "2026-09-20T12:00:00.000Z"


def test_normalize_history_one_object_per_bar_field():
    payload = {
        "symbol": "AAPL",
        "currency": "USD",
        "interval": "1d",
        "series": [
            {"date": "2026-09-18", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"date": "2026-09-19", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 20},
        ],
    }
    objects = normalize_history(payload, SourceReference(source="yfinance"))
    closes = [o for o in objects if o.name == "close"]
    assert [o.value for o in closes] == [1.5, 2.5]
    assert closes[0].period == "1d"


def test_params_for_does_not_confuse_range_with_interval():
    """Regression: passing a range ("6mo") as an interval silently disabled the
    whole historical path — the bridge ran the quote path, not history."""
    from harness.retrieval.structured import _params_for

    history = _params_for(
        FinancialRetrievalRequest(
            objective="h", dataType="historical_prices", instrument="AAPL", quantity="6mo"
        )
    )
    assert history["range"] == "6mo"
    assert "interval" not in history  # 6mo is a range, never an interval
    assert "period" not in history

    intraday = _params_for(
        FinancialRetrievalRequest(
            objective="h", dataType="historical_prices", instrument="AAPL", quantity="5m"
        )
    )
    assert intraday["interval"] == "5m"
    assert "range" not in intraday


def test_params_for_maps_macro_series_and_source():
    from harness.retrieval.structured import _params_for

    params = _params_for(
        FinancialRetrievalRequest(
            objective="m",
            dataType="macro_series",
            quantity="CPIAUCSL",
            metadata={"source": "bls"},
        )
    )
    assert params["series"] == "CPIAUCSL"
    assert params["source"] == "bls"


@pytest.mark.asyncio
async def test_company_profile_keeps_non_numeric_fields():
    """Regression: non-numeric facts were dropped by numeric-only conflict
    resolution, so company_profile returned five valid objects as an empty body."""
    bridge = FakeBridge(
        {
            "fundamentals": {
                "status": "OK",
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "securityType": "Stock",
                "country": "US",
                "price": 338.96,
            }
        }
    )
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="p", dataType="company_profile", instrument="AAPL")
    )
    assert result.status == "OK"
    assert result.data["name"] == "Apple Inc."
    assert result.data["sector"] == "Technology"
    assert result.data["country"] == "US"


@pytest.mark.asyncio
async def test_structured_source_returns_unavailable_without_inventing():
    bridge = FakeBridge({"market_snapshot": {"status": "UNAVAILABLE"}})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="ZZZZ")
    )
    assert result.status == "UNAVAILABLE"
    assert result.data is None


@pytest.mark.asyncio
async def test_structured_quote_via_layer():
    bridge = FakeBridge({"market_snapshot": quote_payload()})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    )
    assert result.status == "OK"
    assert result.data["price"] == 237.42
    assert result.strategy[0] == "JDDS"


# ── 2E web research ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_research_prefers_primary_and_marks_unverified_snippets():
    bridge = FakeBridge(
        {
            "web_search": research_payload(),
            "web_fetch": lambda params: (
                {"status": "OK", "url": params["url"], "title": "SEC filing", "text": "full text", "bytes": 9}
                if "sec.gov" in params["url"]
                else {"status": "UNAVAILABLE", "error": "blocked"}
            ),
        }
    )
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="why NVDA moved", dataType="web_research", query="NVDA")
    )
    assert result.status == "OK"
    primary = [e for e in result.evidence if e.source.sourceType == "primary"]
    assert primary, "primary source should rank first"
    assert primary[0].kind == "filing"
    # The reuters page failed to fetch → snippet-only, explicitly unverified.
    unverified = [e for e in result.evidence if e.source.validationStatus == "unverified"]
    assert unverified
    assert all(e.source.url for e in result.evidence)


@pytest.mark.asyncio
async def test_web_research_does_not_invent_when_search_empty():
    bridge = FakeBridge({"web_search": {"status": "UNAVAILABLE", "error": "rate limited"}})
    layer = FinancialRetrievalLayer(bridge)
    result = await layer.retrieve(
        FinancialRetrievalRequest(objective="x", dataType="web_research", query="x")
    )
    assert result.status == "UNAVAILABLE"
    assert not result.evidence


# ── 2G cache + 2H parallel + dedup ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_reuses_recent_retrieval():
    bridge = FakeBridge({"market_snapshot": quote_payload()})
    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    first = await layer.retrieve(request)
    second = await layer.retrieve(request)
    assert first.cached is False
    assert second.cached is True
    # Only one provider call despite two retrievals.
    assert len([c for c in bridge.calls if c[0] == "market_snapshot"]) == 1


@pytest.mark.asyncio
async def test_cache_does_not_serve_realtime_stale_quote():
    bridge = FakeBridge({"market_snapshot": quote_payload()})
    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    await layer.retrieve(request)
    # Force the cache entry to look old; a realtime request must not reuse it.
    for entry in layer.cache._entries.values():
        entry.cachedAt -= 3600
    result = await layer.retrieve(request)
    assert result.cached is False
    assert len([c for c in bridge.calls if c[0] == "market_snapshot"]) == 2


@pytest.mark.asyncio
async def test_inflight_deduplication_shares_one_retrieval():
    calls = {"n": 0}

    async def slow_quote(params: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return quote_payload()

    bridge = FakeBridge({"market_snapshot": slow_quote})
    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    results = await asyncio.gather(*(layer.retrieve(request) for _ in range(5)))
    assert all(r.status == "OK" for r in results)
    assert calls["n"] == 1, "concurrent identical retrievals must share one call"


@pytest.mark.asyncio
async def test_parallel_error_isolation():
    async def boom() -> SourceOutcome:
        raise RuntimeError("provider exploded")

    async def ok() -> SourceOutcome:
        await asyncio.sleep(0.01)
        return SourceOutcome(source="ok", status="OK", references=[SourceReference(source="ok")])

    results = await run_parallel([("bad", boom), ("good", ok)], concurrency=4)
    by_name = {r.name: r for r in results}
    assert by_name["good"].ok
    assert not by_name["bad"].ok and "exploded" in (by_name["bad"].error or "")


@pytest.mark.asyncio
async def test_parallel_timeout_is_isolated():
    async def slow() -> SourceOutcome:
        await asyncio.sleep(0.5)
        return SourceOutcome(source="slow", status="OK")

    async def fast() -> SourceOutcome:
        return SourceOutcome(source="fast", status="OK", references=[SourceReference(source="fast")])

    results = await run_parallel([("slow", slow), ("fast", fast)], timeout_s=0.05)
    by_name = {r.name: r for r in results}
    assert by_name["slow"].timed_out
    assert by_name["fast"].ok


# ── 2J validation ───────────────────────────────────────────────────────────


def test_validation_allows_negative_earnings():
    ref = SourceReference(source="JDDS")
    negative = NormalizedFinancialObject(name="netIncome", value=-500_000, source=ref)
    assert validate_object(negative) == "valid"


def test_validation_flags_negative_price_as_warning():
    ref = SourceReference(source="JDDS")
    bad = NormalizedFinancialObject(name="price", value=-1.0, source=ref)
    assert validate_object(bad) == "warning"


def test_validation_flags_missing_value():
    ref = SourceReference(source="JDDS")
    assert validate_object(NormalizedFinancialObject(name="price", value=None, source=ref)) == "warning"


def test_validation_flags_stale_dataset_once_not_per_row():
    """Staleness is a dataset property. Flagging every historical bar as a
    'quality issue' was noise — the per-row check must not fire."""
    ref = SourceReference(source="JDDS")
    series = [
        NormalizedFinancialObject(name="close", value=1.0, source=ref, dataTimestamp="2000-01-01T00:00:00"),
        NormalizedFinancialObject(name="close", value=2.0, source=ref, dataTimestamp="2000-01-02T00:00:00"),
    ]
    # Per-object: no stale warning (a historical bar is valid).
    assert validate_object(series[0]) == "valid"
    # Dataset-level: exactly one stale warning, naming the reason.
    _, warnings = validate_objects(series, "daily")
    assert len([w for w in warnings if "stale" in w]) == 1
    assert all("close" not in w for w in warnings), "no per-row noise"


def test_validation_warning_names_the_reason():
    ref = SourceReference(source="JDDS")
    _, warnings = validate_objects(
        [NormalizedFinancialObject(name="price", value=-1.0, source=ref)], "any"
    )
    assert len(warnings) == 1
    assert "price" in warnings[0] and "non-negative" in warnings[0]


# ── 2K conflicts ────────────────────────────────────────────────────────────


def test_conflict_preserved_when_unresolvable():
    import time

    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    a = NormalizedFinancialObject(name="price", value=185.20, dataTimestamp=now, source=SourceReference(source="A", sourceType="secondary"))
    b = NormalizedFinancialObject(name="price", value=184.95, dataTimestamp=now, source=SourceReference(source="B", sourceType="secondary"))
    resolution = resolve_group("price", [a, b], rel_tolerance=0.001)
    assert resolution.status == "conflicting"
    assert "184.95" in resolution.reason or "185.2" in resolution.reason


def test_conflict_resolved_by_tier():
    import time

    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    low = NormalizedFinancialObject(name="price", value=185.20, dataTimestamp=now, source=SourceReference(source="A", sourceType="secondary"))
    high = NormalizedFinancialObject(name="price", value=184.95, dataTimestamp=now, source=SourceReference(source="B", sourceType="primary"))
    resolution = resolve_group("price", [low, high], rel_tolerance=0.001)
    assert resolution.status == "resolved"
    assert resolution.chosen.source.source == "B"


def test_conflict_consistent_within_tolerance():
    import time

    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    a = NormalizedFinancialObject(name="price", value=185.20, dataTimestamp=now, source=SourceReference(source="A"))
    b = NormalizedFinancialObject(name="price", value=185.205, dataTimestamp=now, source=SourceReference(source="B"))
    assert resolve_group("price", [a, b]).status == "consistent"


# ── 2I aggregation ──────────────────────────────────────────────────────────


def test_aggregate_keeps_evidence_kinds_distinct():
    ref = SourceReference(source="JDDS")
    from harness.retrieval.contract import EvidenceItem, FinancialRetrievalResult

    structured = FinancialRetrievalResult(
        status="OK", objective="x", dataType="current_quote",
        evidence=[EvidenceItem(id="e1", kind="structured", summary="s", source=ref, objects=[
            NormalizedFinancialObject(name="price", value=1.0, source=ref)
        ])],
    )
    derived = derive_evidence("sharpe", 1.2, ref, "Sharpe over 5y")
    web_result = FinancialRetrievalResult(
        status="OK", objective="x", dataType="web_research",
        evidence=[EvidenceItem(id="e2", kind="web", summary="news", source=ref)],
    )
    evidence = aggregate("x", [structured, web_result])
    evidence.items.append(derived)
    kinds = {i.kind for i in evidence.items}
    assert {"structured", "web", "derived"} <= kinds
    assert evidence.by_kind("derived")[0].data["value"] == 1.2
