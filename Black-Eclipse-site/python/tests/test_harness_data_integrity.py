"""Regression tests for the harness data-integrity defects (D1-D12).

Offline and deterministic: every provider call goes through a fake bridge, but
each assertion exercises the REAL tool/registry/layer entry point.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import pytest

from harness.finance_tools import get_market_snapshot, get_news
from harness.market.cache import MarketCache
from harness.market.gateway import MarketDataGateway
from harness.market.models import MarketMeta, Quote
from harness.market.quality_contract import (
    DataQualityEnvelope,
    compare_values,
    envelope_from_record,
    evaluate_envelope_invariants,
)
from harness.market.research_tools import get_provider_health
from harness.market.research_tools_ext import get_currency_conversion
from harness.market.router import ProviderRouter
from harness.market.tools import get_fx_rate, register_market_tools
from harness.retrieval.freshness import cadence_tolerance_seconds
from harness.retrieval.fetch_quality import FetchQuality
from harness.retrieval.layer import FinancialRetrievalLayer
from harness.retrieval_tools import (
    fundamentals_get_financials,
    market_get_quote,
    register_retrieval_tools,
    research_retrieve_source,
)
from harness.tools import DataBridge, ToolContext, ToolRegistry


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Bridge(DataBridge):
    def __init__(self, *, prices: dict[str, float] | None = None,
                 source_health: list[dict[str, Any]] | None = None,
                 news_items: list[dict[str, Any]] | None = None,
                 statements: list[dict[str, Any]] | None = None,
                 web_fetch: dict[str, Any] | None = None) -> None:
        self.prices = prices or {"yahoo": 386.16, "stooq": 4.18}
        self.source_health = source_health or []
        self.news_items = news_items
        self.statements = statements
        self.web_fetch = web_fetch
        self.fx_asof = _now()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, dict(params)))
        provider = str(params.get("provider") or "yahoo")
        if capability == "market_snapshot":
            market = str(params.get("market") or "US")
            if market == "FX":
                return {"status": "UNAVAILABLE", "failureClass": "invalid_request",
                        "error": 'Unknown venue "FX"'}
            return {"status": "OK", "symbol": params.get("symbol"), "market": market,
                    "exchange": "NASDAQ", "currency": "USD", "assetClass": "equity",
                    "instrumentId": f"{market}:{params.get('symbol')}",
                    "updatedAt": _now(), "observationTime": _now(),
                    "observationSource": "snapshot_write",
                    "price": {"price": 386.16, "changePct": 1.0, "volume": 10}}
        if capability == "market_data":
            cap = params.get("capability")
            if cap == "fx":
                return {"status": "OK", "provider": provider, "base": "USD", "quote": "PKR",
                        "mid": 276.51, "rate": 276.51, "asOf": self.fx_asof}
            base = self.prices.get(provider, 100.0)
            rows = [
                {"timestamp": f"2026-10-{day:02d}T00:00:00Z", "open": base,
                 "high": base * 1.02, "low": base * 0.98, "close": base + i * 0.01,
                 "volume": 1000}
                for i, day in enumerate(range(1, 39))
            ]
            return {"status": "OK", "provider": provider, "interval": "1d",
                    "adjusted": True, "series": rows, "asOf": rows[-1]["timestamp"]}
        if capability == "live_quote":
            return {"status": "OK", "provider": "livedata", "symbol": params.get("symbol"),
                    "market": params.get("market") or "US", "currency": "USD",
                    "assetClass": "equity", "asOf": _now(),
                    "observationTime": _now(),
                    "price": {"price": 4.18, "changePct": -1.2, "volume": 1000}}
        if capability == "price_history":
            base = self.prices.get(provider, 4.18)
            rows = [{"date": f"2026-10-{day:02d}", "open": base, "high": base,
                     "low": base, "close": base, "volume": 1} for day in range(1, 11)]
            return {"status": "OK", "symbol": params.get("symbol"), "currency": "USD",
                    "interval": "1d", "series": rows, "asOf": rows[-1]["date"]}
        if capability in ("fundamentals", "financial_statements"):
            return {"status": "OK", "symbol": params.get("symbol"), "currency": "USD",
                    "provider": "legacy-cache", "retrievedAt": _now(),
                    "periods": self.statements or [
                        {"endDate": "2018-09-29", "fiscalYear": 2018,
                         "revenue": 1000, "netIncome": 100, "eps": 1.0}]}
        if capability == "source_health":
            return {"status": "OK", "rows": self.source_health,
                    "summary": {"recordedRoutes": len(self.source_health)}}
        if capability == "news":
            return {"status": "OK", "sourceKind": "vault",
                    "items": self.news_items if self.news_items is not None else []}
        if capability == "web_fetch":
            return self.web_fetch or {"status": "UNAVAILABLE", "error": "no fixture"}
        return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "no fixture"}


def ctx(bridge: DataBridge) -> ToolContext:
    return ToolContext(run_id="integrity", log=lambda *_: None, data_bridge=bridge)


def gateway(bridge: DataBridge) -> MarketDataGateway:
    return MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())


def _run(coro):
    return asyncio.run(coro)


# ── D1 ────────────────────────────────────────────────────────────────────────

def test_d1_ohlcv_cross_source_is_divergent_not_valid():
    g = gateway(Bridge(prices={"yahoo": 386.16, "stooq": 4.18}))
    series = _run(g.get_ohlcv("LUCK", "PSX", interval="1d"))
    assert getattr(series, "conflict", None) is not None
    assert series.meta.quality != "valid"
    assert series.meta.data_status == "CONFLICTING"
    candidates = series.conflict["candidates"]
    assert {c["provider"] for c in candidates} == {"yahoo", "stooq"}
    assert all(c["timestamp"] for c in candidates)
    assert series.conflict["verdict"] in ("DIVERGENT", "SCALE_MISMATCH")


def test_d1_snapshot_never_returns_a_valid_blend():
    text, data = _run(get_market_snapshot({"symbol": "LUCK", "market": "PSX"}, ctx(Bridge())))
    assert data["qualityVerdict"] in ("DIVERGENT", "SCALE_MISMATCH")
    assert data["qualityVerdict"] != "VALID"
    assert data["conflict"]
    assert data["envelope"]["value"] is None  # no single blended price
    assert "CONFLICT" in text.upper() or "DISAGREE" in text.upper()


def test_d1_scale_mismatch_names_the_factor():
    verdict, gap, factor = compare_values(418.0, 4.18, tolerance=0.01)
    assert verdict == "SCALE_MISMATCH"
    assert factor == 100.0
    assert gap > 0.9


# ── D2 ────────────────────────────────────────────────────────────────────────

def test_d2_old_statement_period_is_named_stale():
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    res = _run(reg.execute("fundamentals_get_financials", "c", {"symbol": "AAPL"}, ctx(Bridge())))
    assert res.data["status"] == "STALE"
    assert res.data["stale"] is True
    assert res.data["reasonCode"] == "DATA_STALE"
    assert any("2018-09-29" in w for w in res.data.get("warnings", []))


def test_d2_recent_statement_is_not_stale():
    recent = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    bridge = Bridge(statements=[{"endDate": recent, "fiscalYear": dt.date.today().year,
                                 "revenue": 1000, "netIncome": 100, "eps": 1.0}])
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    res = _run(reg.execute("fundamentals_get_financials", "c", {"symbol": "AAPL"}, ctx(bridge)))
    assert res.data["status"] == "OK"
    assert res.data["stale"] is False


# ── D3 ────────────────────────────────────────────────────────────────────────

def test_d3_all_fx_entry_points_agree_or_refuse_identically():
    bridge = Bridge()
    c = ctx(bridge)
    _, fx = _run(get_fx_rate({"base": "USD", "quote": "PKR"}, c))
    _, conv = _run(get_currency_conversion({"base": "USD", "quote": "PKR"}, c))
    _, quote = _run(market_get_quote({"symbol": "USDPKR=X"}, c))
    assert fx["status"] == conv["status"] == quote["status"] == "OK"
    assert fx["rate"] == conv["rate"] == quote["rate"] == 276.51
    assert fx["timestamp"] == conv["timestamp"] == quote["timestamp"]


@pytest.mark.parametrize("symbol", ["USD/PKR", "USDPKR", "USDPKR=X", "USD-PKR"])
def test_d3_pair_spellings_normalise_to_one_instrument(symbol):
    from harness.market.instruments import normalize_fx_pair

    assert normalize_fx_pair(symbol) == ("USD", "PKR")


def test_d3_fx_has_no_venue_requirement():
    bridge = Bridge()
    _, fx = _run(get_fx_rate({"base": "USD", "quote": "PKR"}, ctx(bridge)))
    assert fx["status"] == "OK"


# ── D4 ────────────────────────────────────────────────────────────────────────

def test_d4_daily_series_is_valid_one_business_day_later_and_stale_after_five():
    friday = dt.datetime(2026, 10, 23, 12, tzinfo=dt.timezone.utc)
    daily = cadence_tolerance_seconds("treasury", "DGS10", "daily", now=friday)
    thursday_age = 24 * 3600
    five_business_days = 5 * 24 * 3600
    assert thursday_age <= daily < five_business_days


def test_d4_weekend_is_not_staleness():
    monday = dt.datetime(2026, 10, 26, 12, tzinfo=dt.timezone.utc)
    daily = cadence_tolerance_seconds("treasury", "DGS10", "daily", now=monday)
    assert 72 * 3600 <= daily


def test_d4_intraday_keeps_a_tight_window():
    assert cadence_tolerance_seconds("binance", "BTCUSDT", "intraday") <= 15 * 60


# ── D5 ────────────────────────────────────────────────────────────────────────

def test_d5_provider_health_reads_the_recorded_run_ledger():
    rows = [
        {"source": "JDDS", "market": "US", "assetClass": "equity",
         "capability": "live_quote", "success": 0, "fail": 423, "health": "failing"},
        {"source": "yfinance", "market": "US", "assetClass": "equity",
         "capability": "live_quote", "success": 634, "fail": 0, "health": "healthy"},
    ]
    _, data = _run(get_provider_health({}, ctx(Bridge(source_health=rows))))
    health = {h["provider"]: h for h in data["health"]}
    assert health["JDDS"]["failures"] == 423
    assert health["yfinance"]["successes"] == 634
    assert health["JDDS"]["state"] == "FAILING"


def test_d5_zero_runs_is_unknown_not_healthy():
    rows = [{"source": "never-run", "market": "US", "assetClass": "equity",
             "capability": "live_quote", "success": 0, "fail": 0}]
    _, data = _run(get_provider_health({}, ctx(Bridge(source_health=rows))))
    assert data["health"][0]["state"] == "UNKNOWN"


def test_d5_the_two_health_surfaces_agree_on_every_shared_route():
    from harness.finance_tools import get_source_health

    rows = [
        {"source": "JDDS", "market": "US", "assetClass": "equity",
         "capability": "live_quote", "success": 0, "fail": 423, "health": "failing"},
        {"source": "yfinance", "market": "US", "assetClass": "equity",
         "capability": "live_quote", "success": 634, "fail": 0, "health": "healthy"},
    ]
    bridge = Bridge(source_health=rows)
    _, source_surface = _run(get_source_health({}, ctx(bridge)))
    _, provider_surface = _run(get_provider_health({}, ctx(bridge)))
    source_rows = {(r["source"], r["capability"]): r for r in source_surface["rows"]}
    provider_rows = {(r["provider"], r["capability"]): r for r in provider_surface["health"]}
    assert source_rows.keys() == provider_rows.keys()
    for key, row in source_rows.items():
        assert (row["success"], row["fail"]) == (
            provider_rows[key]["successes"], provider_rows[key]["failures"])


# ── D6 ────────────────────────────────────────────────────────────────────────

def test_d6_dead_route_is_skipped_and_named():
    rows = [{"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
             "capability": "price_history", "success": 0, "fail": 111,
             "lastFailureAt": _now()}]
    bridge = Bridge(source_health=rows)
    layer = FinancialRetrievalLayer(bridge)
    from harness.retrieval.contract import FinancialRetrievalRequest

    result = _run(layer.retrieve(FinancialRetrievalRequest(
        objective="history", dataType="historical_prices", instrument="AAPL",
        market="US", freshnessRequirement="slow",
    )))
    assert not any(c[0] == "price_history" for c in bridge.calls)
    skipped = [d for d in result.diagnostics
               if d.get("normalizedStatus") in ("skipped_by_breaker", "probe")]
    assert skipped
    assert "skipped-by-breaker" in skipped[0]["detail"]


# ── D7 ────────────────────────────────────────────────────────────────────────

def _capability_check(*args: str):
    import os
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script = os.path.join(root, "scripts", "capability-matrix-check.ts")
    tsx = os.path.join(root, "node_modules", ".bin", "tsx.cmd")
    cmd = [tsx, script, *args] if os.path.exists(tsx) else ["npx", "tsx", script, *args]
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                          timeout=180, shell=False)


def test_d7_ci_check_passes_on_the_real_matrix():
    proc = _capability_check()
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-800:]


def test_d7_ci_check_fails_on_an_injected_contradiction():
    proc = _capability_check("--inject=UK:quote")
    assert proc.returncode != 0
    assert "unexplained mismatch" in (proc.stdout + proc.stderr)


# ── D8 ────────────────────────────────────────────────────────────────────────

def test_d8_undated_news_is_flagged_and_excluded_from_latest():
    items = [{"source": "wire", "headline": f"undated {i}", "url": f"https://x/{i}"}
             for i in range(8)]
    _, data = _run(get_news({"query": "latest news"}, ctx(Bridge(news_items=items))))
    assert data["count"] == 0
    assert data["excludedUndated"] == 8
    assert data["undated"] == 8


def test_d8_dated_news_preserves_timestamp_and_timezone():
    items = [{"source": "wire", "headline": "dated", "url": "https://x/1",
              "publishedAt": "2026-10-23T14:05:00+05:00"}]
    _, data = _run(get_news({"query": "latest news"}, ctx(Bridge(news_items=items))))
    assert data["count"] == 1
    assert data["items"][0]["publishedAt"] == "2026-10-23T14:05:00+05:00"
    assert data["items"][0]["undated"] is False


def test_d8_undated_items_are_returned_in_a_non_time_sensitive_query():
    items = [{"source": "wire", "headline": "undated", "url": "https://x/1"}]
    _, data = _run(get_news({"query": "company history"}, ctx(Bridge(news_items=items))))
    assert data["count"] == 1
    assert data["items"][0]["undated"] is True


# ── D9 ────────────────────────────────────────────────────────────────────────

def test_d9_retries_transients_and_reaches_the_success_floor():
    q = FetchQuality(url_window_s=3600)
    attempts: dict[str, int] = {}

    async def fetch(url: str) -> dict[str, Any]:
        attempts[url] = attempts.get(url, 0) + 1
        if url.endswith(("4", "9", "14", "19")) and attempts[url] == 1:
            return {"status": "UNAVAILABLE", "error": "timeout",
                    "diagnostics": [{"category": "timeout"}]}
        return {"status": "OK", "url": url, "text": "body"}

    for i in range(20):
        _run(q.fetch(f"https://fixture/{i}", fetch))
    stats = q.stats()
    assert stats["successRate"] >= 0.85
    assert stats["successes"] == 20
    assert stats["retries"] == 4


def test_d9_definitive_4xx_is_never_retried():
    q = FetchQuality()
    attempts = {"n": 0}

    async def fetch(url: str) -> dict[str, Any]:
        attempts["n"] += 1
        return {"status": "UNAVAILABLE", "error": "403 forbidden",
                "diagnostics": [{"category": "http_error", "httpStatus": 403}]}

    payload = _run(q.fetch("https://fixture/forbidden", fetch))
    assert payload["status"] == "UNAVAILABLE"
    assert attempts["n"] == 1


def test_d9_cache_hits_are_reported_distinctly():
    q = FetchQuality()
    calls = {"n": 0}

    async def fetch(url: str) -> dict[str, Any]:
        calls["n"] += 1
        return {"status": "OK", "url": url, "text": "body"}

    first = _run(q.fetch("https://fixture/1", fetch))
    second = _run(q.fetch("https://fixture/1", fetch))
    assert first["cacheHit"] is False
    assert second["cacheHit"] is True
    assert q.stats()["cacheHits"] == 1
    assert calls["n"] == 1


# ── D10 ───────────────────────────────────────────────────────────────────────

def test_d10_typo_returns_suggestions_without_auto_executing():
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    register_market_tools(reg)
    res = _run(reg.execute("get_historial_prices", "c", {}, ctx(Bridge())))
    assert res.ok is False
    assert res.error is not None and res.error.code == "TOOL_NOT_FOUND"
    assert "get_historical_prices" in (res.data or {}).get("suggestions", [])
    assert (res.data or {}).get("autoExecuted") is False


# ── D11 ───────────────────────────────────────────────────────────────────────

def test_d11_empty_extraction_is_image_only_or_ocr_unavailable():
    bridge = Bridge(web_fetch={"status": "OK", "url": "https://psx/filing.pdf",
                               "title": "scanned filing", "text": ""})
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    res = _run(reg.execute("research_retrieve_source", "c",
                           {"url": "https://psx/filing.pdf"}, ctx(bridge)))
    assert res.data["status"] in ("IMAGE_ONLY", "OCR_UNAVAILABLE")
    assert res.data["status"] != "OK"
    assert res.data.get("reasonCode") in ("IMAGE_ONLY", "OCR_UNAVAILABLE")


# ── D12 ───────────────────────────────────────────────────────────────────────

def test_d12_valid_with_conflict_is_rejected_by_the_invariant():
    record = Quote(
        meta=MarketMeta(symbol="LUCK", quality="valid", provider="yahoo"),
        price=386.16,
        conflict={"metric": "price", "scaleFactor": 100,
                  "candidates": [{"provider": "yahoo", "value": 386.16},
                                 {"provider": "stooq", "value": 4.18}]},
    )
    env = envelope_from_record(record)
    assert env.qualityVerdict == "SCALE_MISMATCH"
    assert evaluate_envelope_invariants(env) == []


def test_d12_valid_with_zero_providers_is_rejected():
    env = DataQualityEnvelope(qualityVerdict="VALID", provider=None)
    problems = evaluate_envelope_invariants(env)
    assert any("provider" in p for p in problems)


def test_d12_valid_with_stale_observation_is_rejected():
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    env = DataQualityEnvelope(qualityVerdict="VALID", provider="yahoo",
                              observationTimestamp=old)
    problems = evaluate_envelope_invariants(env, cadence_tolerance_s=3600)
    assert any("old" in p for p in problems)


def test_d12_market_and_retrieval_tools_emit_the_envelope():
    g = gateway(Bridge())
    from harness.market.tools import get_quote

    _, quote = _run(get_quote({"symbol": "AAPL"}, ctx(Bridge())))
    # market tool (via the lazy gateway on ctx)
    market_reg = ToolRegistry()
    register_market_tools(market_reg)
    market_ctx = ctx(Bridge())
    market_ctx.market_gateway = g
    market_res = _run(market_reg.execute("get_quote", "c", {"symbol": "AAPL"}, market_ctx))
    market_data = market_res.data
    assert "envelope" in market_data
    assert market_data["envelope"]["qualityVerdict"] in (
        "VALID", "STALE", "DIVERGENT", "SCALE_MISMATCH", "UNAVAILABLE", "UNVERIFIED")

    retrieval_reg = ToolRegistry()
    register_retrieval_tools(retrieval_reg)
    retrieval_res = _run(retrieval_reg.execute(
        "market_get_ohlcv", "c", {"symbol": "AAPL"}, ctx(Bridge())))
    assert "envelope" in retrieval_res.data

