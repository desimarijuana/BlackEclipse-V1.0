"""Tests for the vectorized engine, parity with the event engine, and the
advanced agent tools (engine selection, cost diagnostics, OOS, bootstrap, compare).
"""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import fixtures as F
from harness.quant.data import BarSeries, MarketDataset
from harness.quant.engine import BacktestConfig, run_backtest
from harness.quant.strategy import StrategySpec
from harness.quant.store import QuantStore
from harness.quant.tools import QUANT_TOOLS, register_quant_tools
from harness.quant.advanced_tools import ADVANCED_TOOLS
from harness.quant.vector_engine import (
    VectorUnsupported,
    run_vectorized_backtest,
    vector_capability,
)
from harness.tools import ToolContext, ToolRegistry


SUPPORTED = {
    "id": "vec_cross", "name": "Vector Cross", "version": "1.0.0", "asset_class": "crypto",
    "universe": {"symbols": ["TESTUSDT"]},
    "timeframes": {"primary": "1d"},
    "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                   {"id": "ema_slow", "type": "ema", "params": {"period": 20}}],
    "rules": {
        "entry": {"long": {"conditions": [
            {"type": "condition", "left": {"ref": "ema_fast"}, "op": "cross_above",
             "right": {"ref": "ema_slow"}}]}},
        "exit": {"long": {"conditions": [
            {"type": "condition", "left": {"ref": "ema_fast"}, "op": "cross_below",
             "right": {"ref": "ema_slow"}}]}},
    },
    "position_sizing": {"type": "fixed_quantity", "value": 10},
    "execution": {"commission": {"type": "percentage", "value": 0.1}, "fill_at": "next_open"},
}


def _spec(overrides=None):
    import copy

    from harness.quant.strategy import parse_strategy

    data = copy.deepcopy(SUPPORTED)
    if overrides:
        for path, value in overrides.items():
            keys = path.split(".")
            node = data
            for k in keys[:-1]:
                node = node[k]
            node[keys[-1]] = value
    return parse_strategy(data)


def _dataset(rows, symbol="TESTUSDT", interval="1d"):
    return MarketDataset(series={symbol: BarSeries(
        symbol=symbol, interval=interval, timestamps=[r["timestamp"] for r in rows],
        open=[r["open"] for r in rows], high=[r["high"] for r in rows],
        low=[r["low"] for r in rows], close=[r["close"] for r in rows],
        volume=[r["volume"] for r in rows], source="synthetic",
    )})


# ── Capability boundaries ────────────────────────────────────────────────────

def test_capability_rejects_protective_legs():
    spec = _spec({"rules.exit.stop_loss": {"type": "atr", "value": 2}})
    cap = vector_capability(spec)
    assert cap["supported"] is False
    assert any("stop-loss" in r for r in cap["reasons"])


def test_capability_rejects_multi_symbol():
    spec = _spec({"universe.symbols": ["AAAUSDT", "BBBUSDT"]})
    assert vector_capability(spec)["supported"] is False


def test_capability_accepts_supported_spec():
    assert vector_capability(_spec())["supported"] is True


def test_vector_backtest_refuses_unsupported():
    spec = _spec({"rules.exit.stop_loss": {"type": "atr", "value": 2}})
    with pytest.raises(VectorUnsupported):
        run_vectorized_backtest(spec, _dataset(F.bull_market(n=120)))


# ── Vectorized run + parity ──────────────────────────────────────────────────

def test_vector_backtest_produces_full_result():
    spec = _spec()
    rows = F.bull_market("TESTUSDT", n=200)
    result = run_vectorized_backtest(spec, _dataset(rows), BacktestConfig(initial_capital=100_000))
    assert result.status == "OK"
    assert result.metadata["engine"] == "vectorized"
    assert len(result.equity_curve) == len(rows)
    assert "total_return" in result.metrics
    assert result.metrics["trade_count"] is not None
    # Trades must reconcile with fills: every trade has an entry and exit.
    for t in result.trades:
        assert t["entryPrice"] > 0 and t["exitPrice"] > 0


def test_vector_event_parity_fixed_quantity():
    """For the representable subset the two engines must agree on equity."""
    spec = _spec()
    dataset = _dataset(F.bull_market("TESTUSDT", n=250))
    cfg = BacktestConfig(initial_capital=100_000)
    ev = run_backtest(spec, dataset, cfg, symbols=["TESTUSDT"])
    vec = run_vectorized_backtest(spec, dataset, cfg, symbols=["TESTUSDT"])
    ev_eq = [p["equity"] for p in ev.equity_curve]
    vec_eq = [p["equity"] for p in vec.equity_curve]
    assert len(ev_eq) == len(vec_eq)
    for a, b in zip(ev_eq, vec_eq):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-6), (a, b)
    assert ev.metrics["trade_count"] == vec.metrics["trade_count"]


def test_vector_does_not_look_ahead():
    """A monotone-rising series with a lagged cross cannot trade before warm-up."""
    spec = _spec()
    rows = F.bull_market("TESTUSDT", n=80)
    result = run_vectorized_backtest(spec, _dataset(rows), BacktestConfig())
    # No fill (and hence no trade) may occur in the indicator warm-up region.
    for f in result.fills:
        assert f["index"] >= result.metadata["minBars"] - 1


# ── Advanced tool registration ───────────────────────────────────────────────

def test_advanced_tools_registered_and_allowlisted():
    registry = ToolRegistry()
    register_quant_tools(registry)
    registered = set(registry.names())
    assert set(ADVANCED_TOOLS) <= registered
    assert set(ADVANCED_TOOLS) <= set(QUANT_TOOLS)
    # No drift between the literal allowlist and the registered names.
    assert registered == set(QUANT_TOOLS)


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
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)
    ctx.market_gateway = FakeGateway(F.bull_market("TESTUSDT", n=600))
    return registry, ctx, store


async def _call(registry, ctx, name, args):
    return await registry.execute(name, f"c_{name}", args, ctx)


async def test_cost_tools_via_registry(env):
    registry, ctx, _ = env
    args = {"orders": [{"side": "buy", "quantity": 10, "price": 100.0}],
            "execution": {"commission": {"type": "percentage", "value": 0.1}}}
    r = await _call(registry, ctx, "simulate_transaction_costs", args)
    assert r.ok and r.data["status"] == "OK"
    assert r.data["simulation"]["total"] == pytest.approx(1.0)
    r = await _call(registry, ctx, "simulate_slippage",
                    {**args, "execution": {"slippage": {"type": "fixed", "value": 0.2}}})
    assert r.ok and r.data["simulation"]["total"] == pytest.approx(2.0)


async def test_vectorized_tool_refuses_and_runs(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    r = await _call(registry, ctx, "run_vectorized_backtest", {"strategyId": "vec_cross"})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["experimentId"]

    # A stop-loss strategy must be refused, not silently approximated.
    stopped = _spec({"rules.exit.stop_loss": {"type": "atr", "value": 2},
                     "version": "2.0.0"})
    await _call(registry, ctx, "create_strategy", {"strategy": stopped.to_dict()})
    r = await _call(registry, ctx, "run_vectorized_backtest", {"strategyId": "vec_cross",
                                                               "version": stopped.version})
    assert r.data["status"] == "ERROR"
    assert r.data["error"]["code"] == "VECTOR_UNSUPPORTED"


async def test_event_driven_tool(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    r = await _call(registry, ctx, "run_event_driven_backtest", {"strategyId": "vec_cross"})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["experimentId"]


async def test_bootstrap_tool_from_experiment(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    r = await _call(registry, ctx, "run_backtest", {"strategyId": "vec_cross"})
    exp_id = r.data["experimentId"]
    b = await _call(registry, ctx, "run_bootstrap_test",
                    {"experimentId": exp_id, "method": "block", "iterations": 200, "seed": 5})
    assert b.ok and b.data["status"] == "OK"
    assert b.data["bootstrap"]["available"] is True


async def test_out_of_sample_tool(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    r = await _call(registry, ctx, "run_out_of_sample_test",
                    {"strategyId": "vec_cross", "oosFraction": 0.3})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["split"]["overlapBars"] == 0
    assert r.data["split"]["isBars"] > 0 and r.data["split"]["oosBars"] > 0
    assert r.data["experimentId"]


async def test_compare_backtests_tool(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    a = await _call(registry, ctx, "run_backtest",
                    {"strategyId": "vec_cross", "initialCapital": 100000})
    b = await _call(registry, ctx, "run_backtest",
                    {"strategyId": "vec_cross", "initialCapital": 50000})
    r = await _call(registry, ctx, "compare_backtests",
                    {"experimentIds": [a.data["experimentId"], b.data["experimentId"]]})
    assert r.ok and r.data["status"] == "OK"
    # differing initialCapital must raise a comparability caution
    assert any(w["code"] == "COMPARABILITY_DIFFERENT_INITIALCAPITAL"
               for w in r.data["comparability"])


async def test_multiple_testing_tool_runs_real_sweep(env):
    registry, ctx, _ = env
    await _call(registry, ctx, "create_strategy", {"strategy": SUPPORTED})
    r = await _call(registry, ctx, "run_multiple_testing_diagnostics", {
        "strategyId": "vec_cross",
        "paramSpace": {"indicators.0.params.period": [4, 6, 8, 10, 12, 14]}})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["sweep"]["trials"] >= 2
    assert r.data["deflatedSharpe"]["available"] is True
    assert r.data["pbo"]["available"] is True


async def test_capability_advertises_new_engines(env):
    registry, ctx, _ = env
    r = await _call(registry, ctx, "quant_capabilities", {})
    cap = r.data["capability"]
    for key in ("vectorizedBacktest", "costDiagnostics", "outOfSample", "bootstrap",
                "multipleTesting"):
        assert cap[key] == "available"


def test_oos_contamination_detects_overlapping_selection_experiments():
    from harness.quant.advanced_tools import _oos_contamination

    class _StubStore:
        def __init__(self, exps):
            self._exps = exps

        def list_experiments(self, strategy_id=None, limit=50):
            return self._exps

    store = _StubStore([
        {"id": "e1", "kind": "optimization", "start": "2023-05-01", "end": "2023-09-01"},
        {"id": "e2", "kind": "backtest", "start": "2023-06-01", "end": "2023-08-01"},
        {"id": "e3", "kind": "optimization", "start": "2020-01-01", "end": "2020-06-01"},
    ])
    hits = _oos_contamination(store, "s", "2023-07-01", "2023-12-31")
    assert [h["id"] for h in hits] == ["e1"]
    assert _oos_contamination(store, "s", "2024-01-01", "2024-06-01") == []
