"""Python Strategy SDK (in-process): hooks, orders, stops, determinism, errors."""

from __future__ import annotations

import pytest

from harness.quant import fixtures as F
from harness.quant.data import build_dataset, series_from_rows
from harness.quant.engine import BacktestConfig
from harness.quant.sdk import SdkError, Strategy, run_user_strategy


def _dataset(n=260):
    rows = F.bull_market("TESTUSDT", n=n)
    return build_dataset({"TESTUSDT": series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


class EmaCross(Strategy):
    name = "ema_cross_sdk"

    def __init__(self):
        self.fills = 0
        self.stopped = False

    def initialize(self, ctx):
        ctx.declare_indicator("fast", "ema", {"period": 5})
        ctx.declare_indicator("slow", "ema", {"period": 20})
        ctx.declare_indicator("atr", "atr", {"period": 14})
        ctx.set_stop_loss("atr", 2.0, atr_indicator="atr")
        ctx.set_take_profit("risk_reward", 2.0)

    def on_data(self, ctx, bar):
        fast, slow = ctx.indicator("fast"), ctx.indicator("slow")
        if fast is None or slow is None:
            return
        if ctx.position().is_flat and fast > slow:
            ctx.buy(weight=0.9, reason="cross up")
        elif not ctx.position().is_flat and fast < slow:
            ctx.close(reason="cross down")

    def on_fill(self, ctx, fill):
        self.fills += 1

    def on_stop(self, ctx):
        self.stopped = True


def test_sdk_runs_and_hooks_fire():
    user = EmaCross()
    res = run_user_strategy(user, _dataset(), BacktestConfig(initial_capital=100_000))
    assert res.status == "OK"
    assert res.metrics["trade_count"] is not None
    assert user.fills > 0
    assert user.stopped is True
    assert res.metadata["strategyId"] == "ema_cross_sdk"
    assert res.observability["barsProcessed"] > 0


def test_sdk_is_deterministic():
    a = run_user_strategy(EmaCross(), _dataset(), BacktestConfig(initial_capital=100_000))
    b = run_user_strategy(EmaCross(), _dataset(), BacktestConfig(initial_capital=100_000))
    assert a.metrics == b.metrics
    assert a.equity_curve == b.equity_curve


def test_sdk_uses_shared_accounting_and_risk():
    user = EmaCross()
    res = run_user_strategy(user, _dataset(), BacktestConfig(initial_capital=50_000))
    # Fills carry commission/slippage structure identical to the declarative engine.
    assert res.fills and all("commission" in f for f in res.fills)
    assert res.configuration["initialCapital"] == 50_000


class Boom(Strategy):
    name = "boom"

    def on_data(self, ctx, bar):
        raise RuntimeError("kaboom")


def test_sdk_user_error_is_reported_not_hidden():
    res = run_user_strategy(Boom(), _dataset(), BacktestConfig())
    assert res.status == "FAILED"
    assert res.errors and res.errors[0]["type"] == "RuntimeError"
    assert any(w["code"] == "SDK_STRATEGY_ERROR" for w in res.warnings)


class BadInit(Strategy):
    name = "bad_init"

    def initialize(self, ctx):
        raise ValueError("no params")


def test_sdk_initialize_error_raises_sdkerror():
    with pytest.raises(SdkError):
        run_user_strategy(BadInit(), _dataset(), BacktestConfig())


class Sizer(Strategy):
    name = "sizer"

    def initialize(self, ctx):
        ctx.declare_indicator("atr", "atr", {"period": 14})
        ctx.set_risk(max_open_positions=1)

    def on_data(self, ctx, bar):
        if ctx.position().is_flat:
            ctx.buy(weight=0.5, reason="fixed")


def test_sdk_weight_sizing_and_params():
    res = run_user_strategy(Sizer(), _dataset(), BacktestConfig(initial_capital=100_000),
                            params={"unused": 1})
    assert res.status == "OK"
    assert res.metadata["strategyId"] == "sizer"


# ── Tool end-to-end (registry → isolated runtime) ────────────────────────────

class _FakeGateway:
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


async def test_tool_run_python_strategy(tmp_path):
    from harness.persistence import AgentMemoryStore
    from harness.quant.store import QuantStore
    from harness.quant.tools import QUANT_TOOLS, register_quant_tools
    from harness.tools import ToolContext, ToolRegistry

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    registry = ToolRegistry()
    register_quant_tools(registry)
    assert "run_python_strategy" in QUANT_TOOLS
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)
    ctx.market_gateway = _FakeGateway(F.bull_market("TESTUSDT", n=200))

    src = (
        "from harness.quant.sdk import Strategy\n"
        "class S(Strategy):\n"
        "    name='tool_sdk'\n"
        "    def initialize(self, ctx):\n"
        "        ctx.declare_indicator('ema','ema',{'period':10})\n"
        "    def on_data(self, ctx, bar):\n"
        "        e=ctx.indicator('ema')\n"
        "        if e is None: return\n"
        "        if ctx.position().is_flat and bar.close>e: ctx.buy(weight=0.5)\n"
        "        elif not ctx.position().is_flat and bar.close<e: ctx.close()\n"
    )
    r = await registry.execute("run_python_strategy", "c1",
                               {"strategyCode": src, "symbols": ["TESTUSDT"]}, ctx)
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["experimentId"]
