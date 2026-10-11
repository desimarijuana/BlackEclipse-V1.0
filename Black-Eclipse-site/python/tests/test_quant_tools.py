"""Tests for the quant agent tools (registration + end-to-end calls)."""

from __future__ import annotations

import json

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import fixtures as F
from harness.quant.store import QuantStore
from harness.quant.tools import register_quant_tools
from harness.tools import ToolContext, ToolRegistry

SPEC = {
    "strategy": {"id": "ema_cross", "name": "EMA Cross", "version": "1.0.0"},
    "universe": {"symbols": ["TESTUSDT"]},
    "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                   {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
                   {"id": "atr", "type": "atr", "params": {"period": 14}}],
    "rules": {"entry": {"long": {"conditions": [
        {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
        "exit": {"stop_loss": {"type": "atr", "value": 2}}},
    "position_sizing": {"type": "percent_equity", "value": 90},
}


class FakeGateway:
    """Returns a deterministic synthetic series through the gateway contract."""

    def __init__(self, rows):
        self.rows = rows

    async def get_historical_prices(self, symbol, market=None, *, start=None, end=None,
                                    interval="1d", adjusted=True, currency=None, freshness="slow"):
        from harness.market.models import HistoricalPriceSeries, MarketMeta, OHLCVBar

        return HistoricalPriceSeries(
            meta=MarketMeta(symbol=symbol, provider="synthetic", asset_type="crypto"),
            interval=interval, bars=[OHLCVBar(**{k: r[k] for k in
                     ("timestamp", "open", "high", "low", "close", "volume")}) for r in self.rows],
        )


@pytest.fixture()
def env(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)
    ctx.market_gateway = FakeGateway(F.bull_market("TESTUSDT", n=200))
    return registry, ctx, store


async def _call(registry, ctx, name, args):
    return await registry.execute(name, f"c_{name}", args, ctx)


async def test_create_validate_load(env):
    registry, ctx, store = env
    r = await _call(registry, ctx, "validate_strategy", {"strategy": SPEC})
    assert r.ok and r.data["status"] == "OK"
    r = await _call(registry, ctx, "create_strategy", {"strategy": SPEC})
    assert r.ok and r.data["status"] == "OK", r.text
    r = await _call(registry, ctx, "load_strategy", {"strategyId": "ema_cross"})
    assert r.ok and r.data["id"] == "ema_cross"
    r = await _call(registry, ctx, "list_strategies", {})
    assert any(s["id"] == "ema_cross" for s in r.data["strategies"])


async def test_invalid_strategy_reports_issues(env):
    registry, ctx, _ = env
    bad = json.loads(json.dumps(SPEC))
    bad["rules"]["entry"]["long"]["conditions"][0]["left"]["ref"] = "nope"
    r = await _call(registry, ctx, "create_strategy", {"strategy": bad})
    assert r.data["status"] == "INVALID"
    assert any(i["code"] == "UNKNOWN_REFERENCE" for i in r.data["issues"])


async def test_run_backtest_and_inspect(env):
    registry, ctx, store = env
    await _call(registry, ctx, "create_strategy", {"strategy": SPEC})
    r = await _call(registry, ctx, "run_backtest", {"strategyId": "ema_cross", "initialCapital": 100000})
    assert r.ok and r.data["status"] == "OK", r.text
    exp_id = r.data["experimentId"]
    assert exp_id and r.data["metrics"]["trade_count"] >= 0
    r2 = await _call(registry, ctx, "calculate_metrics", {"experimentId": exp_id})
    assert r2.ok and "sharpe" in r2.data["metrics"]
    r3 = await _call(registry, ctx, "inspect_trades", {"experimentId": exp_id})
    assert r3.ok
    r4 = await _call(registry, ctx, "plot_equity_curve", {"experimentId": exp_id})
    assert r4.ok and len(r4.data["points"]) == 200
    r5 = await _call(registry, ctx, "export_backtest", {"experimentId": exp_id})
    assert r5.ok and len(r5.data["files"]) >= 2
    r6 = await _call(registry, ctx, "compare_experiments", {"experimentIds": [exp_id]})
    assert r6.ok


async def test_research_tools_run_and_persist(env):
    registry, ctx, store = env
    ctx.market_gateway = FakeGateway(F.bull_market("TESTUSDT", n=600))
    await _call(registry, ctx, "create_strategy", {"strategy": SPEC})
    space = {"indicators.0.params.period": [5, 8], "indicators.1.params.period": [20, 30]}

    r = await _call(registry, ctx, "optimize_parameters", {
        "strategyId": "ema_cross", "paramSpace": space, "method": "random",
        "objective": "sharpe", "maxEvaluations": 4, "seed": 1})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["experimentId"] and r.data["best"] is not None

    r = await _call(registry, ctx, "run_walk_forward", {
        "strategyId": "ema_cross", "paramSpace": space, "trainBars": 250, "testBars": 100,
        "maxEvaluations": 4, "seed": 1})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["experimentId"]

    r = await _call(registry, ctx, "run_monte_carlo", {
        "strategyId": "ema_cross", "method": "trade_reshuffle", "simulations": 20, "seed": 1})
    assert r.ok and r.data["status"] == "OK", r.text
    assert "returnPercentiles" in r.data

    r = await _call(registry, ctx, "run_sensitivity_analysis", {
        "strategyId": "ema_cross", "paramRanges": {"indicators.0.params.period": [5, 8, 12]}})
    assert r.ok and r.data["status"] == "OK", r.text

    r = await _call(registry, ctx, "run_robustness_analysis", {
        "strategyId": "ema_cross",
        "paramRanges": {"indicators.0.params.period": [5, 8, 12]},
        "costMultipliers": [1, 2]})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["verdict"] in {"robust", "fragile", "insufficient_evidence"}

    kinds = {e["kind"] for e in store.list_experiments()}
    assert {"optimization", "walk_forward", "monte_carlo", "sensitivity", "robustness"} <= kinds


async def test_capability_advertises_research_engines(env):
    registry, ctx, _ = env
    r = await _call(registry, ctx, "quant_capabilities", {})
    cap = r.data["capability"]
    assert cap["optimization"] == cap["walkForward"] == cap["monteCarlo"] == cap["robustness"] == "available"
    # options analytics are available; options *backtesting* is what remains partial.
    assert cap["options"] == "partial"
    assert cap["optionAnalytics"] == "available"


def test_downsample_keeps_endpoints_and_bounds_size():
    from harness.quant.tools import _downsample

    points = [{"index": i, "value": i} for i in range(1000)]
    out = _downsample(points, 100)
    assert len(out) <= 100
    assert out[0] == points[0]
    assert out[-1] == points[-1]
    assert _downsample(points[:50], 100) == points[:50]


async def test_tools_without_store_report_unavailable(tmp_path):
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None)  # no quant_store
    r = await _call(registry, ctx, "list_strategies", {})
    assert "STORE_UNAVAILABLE" in r.text
    assert r.data["status"] == "ERROR"
