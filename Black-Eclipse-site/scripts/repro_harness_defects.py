"""Reproduce the twelve observed harness data-integrity defects (D1-D10 surface).

Run from `Black-Eclipse-site/`:

    python scripts/repro_harness_defects.py

Every check goes through a REAL tool/registry/layer entry point with a
deterministic offline bridge. It prints PASS/FAIL per defect and exits non-zero
when any defect is still present. D11/D12 are covered by pytest, not here.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "python")
if PY not in sys.path:
    sys.path.insert(0, PY)

from harness.finance_tools import get_news, get_market_snapshot  # noqa: E402
from harness.market.cache import MarketCache  # noqa: E402
from harness.market.gateway import MarketDataGateway  # noqa: E402
from harness.market.research_tools import get_provider_health  # noqa: E402
from harness.market.research_tools_ext import get_currency_conversion  # noqa: E402
from harness.market.router import ProviderRouter  # noqa: E402
from harness.market.tools import get_fx_rate, register_market_tools  # noqa: E402
from harness.retrieval.authority import DataTypeAuthority, _is_stale  # noqa: E402
from harness.retrieval.contract import FinancialRetrievalRequest, NormalizedFinancialObject, SourceReference  # noqa: E402
from harness.retrieval.layer import FinancialRetrievalLayer  # noqa: E402
from harness.retrieval.sources import SourceOutcome  # noqa: E402
from harness.retrieval_tools import market_get_quote, register_retrieval_tools  # noqa: E402
from harness.tools import DataBridge, ToolContext, ToolRegistry  # noqa: E402


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeBridge(DataBridge):
    """Deterministic offline provider surface used by every check."""

    def __init__(self, *, prices: dict[str, float] | None = None,
                 source_health: list[dict[str, Any]] | None = None,
                 news_items: list[dict[str, Any]] | None = None) -> None:
        self.prices = prices or {"yahoo": 386.16, "stooq": 4.18}
        self.source_health = source_health or []
        self.news_items = news_items
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, dict(params)))
        provider = str(params.get("provider") or "yahoo")
        if capability == "market_snapshot":
            market = str(params.get("market") or "US")
            if market == "FX":
                return {"status": "UNAVAILABLE", "failureClass": "invalid_request",
                        "error": 'Unknown venue "FX"'}
            return {"status": "OK", "symbol": params.get("symbol"), "market": market, "updatedAt": _now(), "observationTime": _now(), "observationSource": "snapshot_write", "price": {"price": 386.16, "changePct": 1.0, "volume": 10},
                    "exchange": "PSX" if market == "PSX" else "NASDAQ",
                    "currency": "PKR" if market == "PSX" else "USD",
                    "assetClass": "equity",
                    "instrumentId": f"{market}:{params.get('symbol')}"}
        if capability == "market_snapshot_price":
            return {"status": "OK"}
        if capability == "market_data":
            cap = params.get("capability")
            if cap == "fx":
                return {"status": "OK", "provider": provider, "base": "USD", "quote": "PKR",
                        "mid": 276.51, "rate": 276.51,
                        "timestamp": "2026-10-23T10:00:00Z", "asOf": "2026-10-23T10:00:00Z"}
            base = self.prices.get(provider, 100.0)
            rows = [
                {"timestamp": f"2026-10-{day:02d}T00:00:00Z", "open": base,
                 "high": base * 1.02, "low": base * 0.98, "close": base + i * 0.01,
                 "volume": 1000 + i}
                for i, day in enumerate(range(1, 39))
            ]
            return {"status": "OK", "provider": provider, "interval": "1d",
                    "adjusted": True, "series": rows, "asOf": rows[-1]["timestamp"]}
        if capability == "live_quote":
            return {"status": "OK", "provider": "livedata", "symbol": params.get("symbol"),
                    "market": params.get("market") or "PSX", "currency": "PKR",
                    "assetClass": "equity", "asOf": _now(),
                    "observationTime": _now(),
                    "price": {"price": 4.18, "changePct": -1.2, "volume": 1000}}
        if capability == "price_history":
            base = self.prices.get(provider, 4.18)
            rows = [{"date": f"2026-10-{day:02d}", "open": base, "high": base,
                     "low": base, "close": base, "volume": 1}
                    for day in range(1, 11)]
            return {"status": "OK", "symbol": params.get("symbol"), "currency": "PKR",
                    "interval": "1d", "series": rows, "asOf": rows[-1]["date"]}
        if capability == "fundamentals" or capability == "financial_statements":
            return {"status": "OK", "symbol": params.get("symbol"), "currency": "USD",
                    "provider": "legacy-cache",
                    "retrievedAt": "2026-10-23T00:00:00Z",
                    "periods": [{"endDate": "2018-09-29", "fiscalYear": 2018,
                                 "revenue": 1000, "netIncome": 100, "eps": 1.0}]}
        if capability == "macro_series":
            return {"status": "OK", "series": "DGS10", "provider": "treasury",
                    "observations": [{"date": "2026-10-22", "value": 4.1}]}
        if capability == "source_health":
            return {"status": "OK", "rows": self.source_health,
                    "summary": {"recordedRoutes": len(self.source_health)}}
        if capability == "news":
            if self.news_items is not None:
                return {"status": "OK", "sourceKind": "vault", "items": self.news_items}
            return {"status": "OK", "sourceKind": "vault", "items": [
                {"source": "newswire", "headline": f"undated {i}", "url": f"https://x/{i}",
                 "sentiment": "neutral"} for i in range(8)]}
        return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "no fixture"}


def ctx_with(bridge: DataBridge) -> ToolContext:
    return ToolContext(run_id="repro", log=lambda *_: None, data_bridge=bridge)


def gateway_with(bridge: DataBridge) -> MarketDataGateway:
    return MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())


def _result(ok: bool, detail: str) -> dict[str, Any]:
    return {"pass": ok, "detail": detail}


async def d1_cross_source() -> dict[str, Any]:
    bridge = FakeBridge(prices={"yahoo": 386.16, "stooq": 4.18})
    gateway = gateway_with(bridge)
    series = await gateway.get_ohlcv("LUCK", "PSX", interval="1d")
    if isinstance(series, Exception) or not hasattr(series, "bars"):
        return _result(False, f"series unavailable: {series}")
    conflict = getattr(series, "conflict", None)
    verdict = str(getattr(series.meta, "quality", "")).lower()
    close = series.bars[-1].close if series.bars else None
    ok = bool(conflict) and verdict != "valid" and verdict in ("divergent", "scale_mismatch", "warning")
    # get_market_snapshot must surface the same disagreement (vault 386.16 vs live 4.18)
    snap_bridge = FakeBridge()
    snap_text, snap = await get_market_snapshot({"symbol": "LUCK", "market": "PSX"}, ctx_with(snap_bridge))
    snap_verdict = str(snap.get("qualityVerdict") or snap.get("quality") or "").lower()
    snap_ok = snap_verdict not in ("valid", "ok", "") and bool(snap.get("conflict") or snap.get("disagreement"))
    return _result(ok and snap_ok,
                   f"ohlcv quality={verdict} conflict={'yes' if conflict else 'no'} close={close}; "
                   f"snapshot quality={snap_verdict} sides={snap.get('sources')}")


async def d2_statement_age() -> dict[str, Any]:
    bridge = FakeBridge()
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    res = await reg.execute("fundamentals_get_financials", "c", {"symbol": "AAPL"}, ctx_with(bridge))
    data = res.data or {}
    periods = data.get("data") or []
    end = None
    if isinstance(periods, list):
        stamps = [row.get("endDate") or row.get("dataTimestamp")
                  for row in periods if isinstance(row, dict)]
        stamps = [s for s in stamps if s]
        end = max(stamps) if stamps else None
    status = str(data.get("status"))
    stale = bool(data.get("stale"))
    ok = status in ("STALE", "UNAVAILABLE") and (stale or end is None or str(end) >= "2024")
    return _result(ok, f"status={status} stale={stale} periodEnd={end}")


async def d3_fx_resolver() -> dict[str, Any]:
    bridge = FakeBridge()
    ctx = ctx_with(bridge)
    _, fx = await get_fx_rate({"base": "USD", "quote": "PKR"}, ctx)
    _, conv = await get_currency_conversion({"base": "USD", "quote": "PKR"}, ctx)
    _, quote = await market_get_quote({"symbol": "USDPKR=X"}, ctx)
    evidence = []
    for name, payload in (("fx", fx), ("conversion", conv), ("quote", quote)):
        status = str((payload or {}).get("status"))
        rate = (payload or {}).get("rate") or (payload or {}).get("converted")
        as_of = (payload or {}).get("timestamp") or (payload or {}).get("asOf") or (payload or {}).get("observationTime")
        evidence.append(f"{name}={status}/{rate}/{as_of}")
    ok = all(str((p or {}).get("status")) == "OK" for p in (fx, conv, quote))
    if ok:
        rates = {(p or {}).get("rate") for p in (fx, conv, quote)}
        ok = len(rates) == 1 and None not in rates
    return _result(ok, "; ".join(evidence))


async def d4_cadence_freshness() -> dict[str, Any]:
    from harness.retrieval.freshness import cadence_tolerance_seconds

    ref = dt.datetime(2026, 10, 23, 12, 0, tzinfo=dt.timezone.utc)  # Friday
    thursday = int((ref - dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)).total_seconds())
    five_bd_old = int((ref - dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc)).total_seconds())
    daily = cadence_tolerance_seconds("treasury", "DGS10", "daily", now=ref)
    ok = thursday <= daily < five_bd_old
    return _result(ok, f"tolerance={daily}s (Thursday {thursday}s, 5 business days {five_bd_old}s)")


async def d5_health_agreement() -> dict[str, Any]:
    rows = [
        {"source": "JDDS", "market": "US", "assetClass": "equity", "capability": "live_quote",
         "success": 0, "fail": 423, "health": "failing"},
        {"source": "yfinance", "market": "US", "assetClass": "equity", "capability": "live_quote",
         "success": 634, "fail": 0, "health": "healthy"},
    ]
    bridge = FakeBridge(source_health=rows)
    _, data = await get_provider_health({}, ctx_with(bridge))
    health = {str(h.get("provider")): h for h in (data.get("health") or [])}
    reported = {k: (v.get("successes"), v.get("failures")) for k, v in health.items()}
    ok = any(v.get("capability") == "live_quote" for v in health.values()) and all(
        not (v.get("successes") == 0 and v.get("failures") == 0 and v.get("state") == "unknown")
        for v in health.values() if v.get("records", 0) > 0
    )
    jdds = next((v for v in health.values() if str(v.get("provider")) in ("JDDS", "jdds")), {})
    ok = ok and jdds.get("failures") == 423
    return _result(ok, f"provider health={json.dumps(reported)[:300]}")


async def d6_dead_route_skipped() -> dict[str, Any]:
    rows = [
        {"source": "LIVE_STRUCTURED", "market": "US", "assetClass": "equity",
         "capability": "price_history", "success": 0, "fail": 111, "health": "failing"},
    ]
    bridge = FakeBridge(source_health=rows)
    layer = FinancialRetrievalLayer(bridge)
    req = FinancialRetrievalRequest(
        objective="history", dataType="historical_prices", instrument="AAPL", market="US",
        freshnessRequirement="slow",
    )
    result = await layer.retrieve(req)
    called = any(c[0] == "price_history" for c in bridge.calls)
    skipped = [d for d in (result.diagnostics or [])
               if "skipped" in str(d.get("normalizedStatus")) or "breaker" in str(d).lower()]
    ok = not called and bool(skipped)
    return _result(ok, f"price_history called={called} diagnostics={json.dumps(skipped)[:300]}")


def d7_capability_ci() -> dict[str, Any]:
    script = os.path.join(ROOT, "scripts", "capability-matrix-check.ts")
    if not os.path.exists(script):
        return _result(False, "capability-matrix-check.ts missing")
    try:
        proc = subprocess.run(
            ["npx", "tsx", script], cwd=ROOT, capture_output=True, text=True, timeout=120,
            shell=os.name == "nt",
        )
    except Exception as exc:  # noqa: BLE001
        return _result(False, f"runner error: {exc}")
    out = (proc.stdout or "") + (proc.stderr or "")
    return _result(proc.returncode == 0, out.strip()[:400])


async def d8_news_undated() -> dict[str, Any]:
    bridge = FakeBridge(news_items=[
        {"source": "wire", "headline": f"undated {i}", "url": f"https://x/{i}", "sentiment": "neutral"}
        for i in range(8)
    ])
    _, data = await get_news({"query": "latest news"}, ctx_with(bridge))
    items = data.get("items") or []
    flagged = all(i.get("undated") is True for i in items)
    ok = flagged and data.get("excludedUndated") == 8 and data.get("count") == 0
    return _result(ok, f"count={data.get('count')} excluded={data.get('excludedUndated')} flagged={flagged}")


async def d9_research_fetch() -> dict[str, Any]:
    from harness.retrieval.fetch_quality import FetchQuality

    q = FetchQuality(url_window_s=3600, max_retries=2)
    attempts: dict[str, int] = {}

    async def fetch(url: str) -> dict[str, Any]:
        attempts[url] = attempts.get(url, 0) + 1
        # 4 of 20 URLs timeout on the first attempt then succeed; 16 succeed first time.
        if url.endswith(("4", "9", "14", "19")) and attempts[url] == 1:
            return {"status": "UNAVAILABLE", "error": "timeout",
                    "diagnostics": [{"category": "timeout", "httpStatus": None}]}
        return {"status": "OK", "url": url, "text": "body"}

    for i in range(20):
        await q.fetch(f"https://fixture/{i}", fetch)
        await q.fetch(f"https://fixture/{i}", fetch)  # immediate cache hit
    stats = q.stats()
    ok = stats["successRate"] >= 0.85 and stats["cacheHits"] >= 20 and stats["successes"] >= 20
    return _result(ok, json.dumps(stats))


async def d10_tool_typo() -> dict[str, Any]:
    reg = ToolRegistry()
    register_retrieval_tools(reg)
    register_market_tools(reg)
    res = await reg.execute("get_historial_prices", "c", {}, ctx_with(FakeBridge()))
    data = res.data or {}
    suggestions = data.get("suggestions") or []
    ok = (not res.ok) and str((res.error.code if res.error else "")) == "TOOL_NOT_FOUND" and \
        "get_historical_prices" in suggestions
    return _result(ok, f"code={res.error.code if res.error else None} suggestions={suggestions}")


CHECKS = {
    "D1": d1_cross_source,
    "D2": d2_statement_age,
    "D3": d3_fx_resolver,
    "D4": d4_cadence_freshness,
    "D5": d5_health_agreement,
    "D6": d6_dead_route_skipped,
    "D7": d7_capability_ci,
    "D8": d8_news_undated,
    "D9": d9_research_fetch,
    "D10": d10_tool_typo,
}


async def main() -> int:
    failures = 0
    for defect, check in CHECKS.items():
        try:
            outcome = check()
            if asyncio.iscoroutine(outcome):
                outcome = await outcome
        except Exception as exc:  # noqa: BLE001 - a crash is a failing reproduction
            outcome = _result(False, f"{type(exc).__name__}: {exc}")
        status = "PASS" if outcome["pass"] else "FAIL"
        if not outcome["pass"]:
            failures += 1
        print(f"{defect} {status} - {outcome['detail']}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} defect reproductions pass")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

