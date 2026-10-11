"""Trend following: a fast/slow EMA crossover with an ATR stop and 2R target."""

from __future__ import annotations

from ..sdk import BarData, Context, Strategy


class MaCrossover(Strategy):
    name = "ma_crossover"
    version = "1.0.0"

    def initialize(self, ctx: Context) -> None:
        ctx.declare_indicator("fast", "ema", {"period": ctx.param("fast", 12)})
        ctx.declare_indicator("slow", "ema", {"period": ctx.param("slow", 50)})
        ctx.declare_indicator("atr", "atr", {"period": ctx.param("atr_period", 14)})
        ctx.set_stop_loss("atr", ctx.param("atr_mult", 2.0), atr_indicator="atr")
        ctx.set_take_profit("risk_reward", ctx.param("reward", 2.0))
        ctx.set_sizing("percent_equity", ctx.param("size_pct", 90))

    def on_data(self, ctx: Context, bar: BarData) -> None:
        fast, slow = ctx.indicator("fast"), ctx.indicator("slow")
        if fast is None or slow is None:
            return
        pos = ctx.position(bar.symbol)
        if pos.is_flat and fast > slow:
            ctx.buy(bar.symbol, weight=ctx.param("weight", 0.9), reason="ema cross up")
        elif pos.quantity > 0 and fast < slow:
            ctx.close(bar.symbol, reason="ema cross down")
