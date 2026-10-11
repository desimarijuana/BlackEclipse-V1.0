"""Research-data HTTP route tests.

Calls the route coroutines directly with a patched `service` (the ONE process
singleton), so no FastAPI app lifecycle or auth overhead is needed. Provider
calls go through a fake bridge.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.tools import DataBridge


def _rows(base: float) -> list[dict[str, Any]]:
    return [
        {"timestamp": "2026-01-02T00:00:00Z", "open": base, "high": base + 2, "low": base - 1, "close": base, "volume": 10},
        {"timestamp": "2026-01-03T00:00:00Z", "open": base, "high": base + 3, "low": base - 1, "close": base + 1, "volume": 20},
    ]


class FakeBridge(DataBridge):
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "market_snapshot":
            symbol = params.get("symbol", "AAPL")
            market = params.get("market") or "US"
            return {"status": "OK", "symbol": symbol, "market": market, "exchange": "NASDAQ",
                    "currency": "USD", "assetClass": "equity", "instrumentId": f"{market}:{symbol}"}
        if capability == "market_data":
            provider = params.get("provider") or "yahoo"
            return {"status": "OK", "provider": provider,
                    "interval": params.get("interval") or "1d", "adjusted": True,
                    "series": _rows(100.0)}
        if capability == "fundamentals":
            return {"status": "OK", "symbol": params.get("symbol"), "pe": 12.5, "marketCap": 1_000_000}
        if capability == "macro_series":
            return {"status": "OK", "seriesId": params.get("seriesId"),
                    "observations": [{"date": "2026-01-01", "value": 3.1}]}
        return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "unknown"}


@pytest.fixture()
def patched(tmp_path):
    from harness import deps
    from harness.market.store import MarketStore
    from harness.persistence import AgentMemoryStore
    from harness.quant.dataset_store import DatasetStore

    mem = AgentMemoryStore(path=str(tmp_path / "am.db"))
    deps.service.server_bridge = lambda: FakeBridge()  # type: ignore[method-assign]
    deps.service.market_store = MarketStore(mem)
    deps.service.dataset_store = DatasetStore(mem, artifact_root=str(tmp_path / "art"))
    deps.service.market_cache = None
    deps.service.market_router = None
    yield deps.service


def _run(coro):
    return asyncio.run(coro)


def test_policies_route(patched):
    from harness.routers import research_data as rd

    data = _run(rd.policies(_=True))
    assert data["available"] is True
    assert {p["name"] for p in data["policies"]} >= {"cross_verified", "strict_research"}


def test_providers_route(patched):
    from harness.routers import research_data as rd

    data = _run(rd.providers(_=True))
    assert data["status"] == "OK"
    assert any(p["id"] == "yahoo" for p in data["providers"])


def test_calendar_route(patched):
    from harness.routers import research_data as rd

    data = _run(rd.calendar(market="us_equity", year=2026, _=True))
    assert data["status"] == "OK"
    assert len(data["holidays"]) >= 8


def test_build_and_list_dataset_route(patched):
    from harness.routers import research_data as rd

    built = _run(rd.build_dataset(rd.BuildBody(symbols=["AAPL"], dataset_id="ds_api"), _=True))
    assert built["status"] == "OK"
    assert built["manifest"]["version"] == "v1"

    listing = _run(rd.list_datasets(_=True))
    assert any(d["id"] == "ds_api" for d in listing["datasets"])

    manifest = _run(rd.get_dataset("ds_api", None, _=True))
    assert manifest["manifest"]["coverage"]["symbolCount"] == 1


def test_analyze_dataset_route(patched):
    from harness.routers import research_data as rd

    _run(rd.build_dataset(rd.BuildBody(symbols=["AAPL"], dataset_id="ds_api2"), _=True))
    result = _run(rd.analyze_dataset("ds_api2", rd.AnalyzeBody(operations=["summary"]), _=True))
    assert result["status"] == "OK"
    assert result["results"]["summary"]["AAPL"]["count"] == 2


def test_fundamentals_and_macro_routes(patched):
    from harness.routers import research_data as rd

    fundamentals = _run(rd.fundamentals(rd.SymbolBody(symbol="AAPL"), _=True))
    assert fundamentals["status"] == "OK"
    assert fundamentals["fundamentals"]["pe"] == 12.5

    macro = _run(rd.macro(rd.MacroBody(series_id="UNRATE", quantity=12), _=True))
    assert macro["status"] == "OK"
    assert macro["macro"]["seriesId"] == "UNRATE"


def test_execute_dataset_route(patched, tmp_path):
    from harness.routers import research_data as rd

    _run(rd.build_dataset(rd.BuildBody(symbols=["AAPL"], dataset_id="ds_nb"), _=True))
    code = (
        "import os, csv\n"
        "rows = list(csv.DictReader(open(os.environ['ECLIPSE_DATASET_PATH'])))\n"
        "print('ROWS', len(rows))\n"
    )
    result = _run(rd.execute_dataset("ds_nb", rd.NotebookBody(code=code, timeout_seconds=20), _=True))
    assert result["status"] == "OK", result
    assert "ROWS 2" in result["output"]
