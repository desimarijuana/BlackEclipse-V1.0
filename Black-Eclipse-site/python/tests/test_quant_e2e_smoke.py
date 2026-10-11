"""End-to-end smoke: the chatbot's strategy flow through the real tool registry.

create → backtest → report → approve → deploy (paper) → paper shadow run.
Everything goes through `ToolRegistry.execute`, exactly as the agent would call
it; the market data comes from a deterministic fake gateway.
"""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import fixtures as F
from harness.quant.store import QuantStore
from harness.quant.tools import register_quant_tools
from harness.tools import ToolContext, ToolRegistry

SPEC = {
    "strategy": {"id": "e2e_cross", "name": "E2E Cross", "version": "1.0.0"},
    "universe": {"symbols": ["TESTUSDT"]},
    "indicators": [{"id": "ema_f", "type": "ema", "params": {"period": 5}},
                   {"id": "ema_s", "type": "ema", "params": {"period": 20}}],
    "rules": {"entry": {"long": {"conditions": [
        {"left": {"ref": "ema_f"}, "op": "cross_above", "right": {"ref": "ema_s"}}]}},
        "exit": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_below", "right": {"ref": "ema_s"}}]}}},
    "position_sizing": {"type": "percent_equity", "value": 90},
}


class FakeGateway:
    def __init__(self, rows):
        self.rows = rows

    async def get_historical_prices(self, symbol, market=None, *, start=None, end=None,
                                    interval="1d", adjusted=True, currency=None, freshness="slow"):
        from harness.market.models import HistoricalPriceSeries, MarketMeta, OHLCVBar

        return HistoricalPriceSeries(
            meta=MarketMeta(symbol=symbol, provider="synthetic", asset_type="crypto"),
            interval=interval,
            bars=[OHLCVBar(**{k: r[k] for k in
                  ("timestamp", "open", "high", "low", "close", "volume")}) for r in self.rows],
        )


@pytest.fixture()
def env(tmp_path):
    store = QuantStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "a"))
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="e2e", log=lambda *a, **k: None, quant_store=store)
    ctx.market_gateway = FakeGateway(F.bull_market("TESTUSDT", n=300))
    return registry, ctx, store


async def _call(registry, ctx, name, args):
    return await registry.execute(name, f"c_{name}", args, ctx)


async def test_full_strategy_flow(env):
    registry, ctx, store = env

    r = await _call(registry, ctx, "create_strategy", {"strategy": SPEC})
    assert r.ok and r.data["status"] == "OK", r.text

    r = await _call(registry, ctx, "validate_strategy", {"strategy": SPEC})
    assert r.ok and r.data["status"] == "OK", r.text

    r = await _call(registry, ctx, "run_backtest",
                    {"strategyId": "e2e_cross", "symbols": ["TESTUSDT"], "save": True})
    assert r.ok and r.data["status"] == "OK", r.text
    exp_id = r.data["experimentId"]
    assert exp_id

    r = await _call(registry, ctx, "generate_strategy_report", {"experimentId": exp_id})
    assert r.ok and r.data["status"] == "OK", r.text
    assert exp_id in r.data["report"]

    # Governance → paper deployment → shadow run.
    r = await _call(registry, ctx, "request_strategy_approval",
                    {"strategyId": "e2e_cross", "version": "1.0.0"})
    assert r.ok
    appr_id = r.data["approval"]["id"]
    r = await _call(registry, ctx, "decide_strategy_approval",
                    {"approvalId": appr_id, "approve": True})
    assert r.data["approval"]["status"] == "approved"

    r = await _call(registry, ctx, "create_strategy_deployment",
                    {"strategyId": "e2e_cross", "version": "1.0.0", "mode": "paper"})
    assert r.ok, r.text
    dep_id = r.data["deployment"]["id"]

    r = await _call(registry, ctx, "run_paper_session", {"deploymentId": dep_id})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["paperRun"]["liveExecution"] is False
    assert store.list_paper_runs(deployment_id=dep_id)
