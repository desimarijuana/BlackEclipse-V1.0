"""Mean reversion: buy oversold RSI, exit on reversion to the mean band."""

from __future__ import annotations

from ..sdk import BarData, Context, Strategy


class MeanReversion(Strategy):
    name = "mean_reversion"
    version = "1.0.0"

    def initialize(self, ctx: Context) -> None:
        ctx.declare_indicator("rsi", "rsi", {"period": ctx.param("rsi_period", 14)})
        ctx.declare_indicator("sma", "sma", {"period": ctx.param("sma_period", 20)})
        ctx.set_stop_loss("percent", ctx.param("stop_pct", 5.0))
        ctx.set_sizing("percent_equity", ctx.param("size_pct", 50))

    def on_data(self, ctx: Context, bar: BarData) -> None:
        rsi = ctx.indicator("rsi")
        sma = ctx.indicator("sma")
        if rsi is None or sma is None:
            return
        pos = ctx.position(bar.symbol)
        if pos.is_flat and rsi < ctx.param("oversold", 30):
            ctx.buy(bar.symbol, weight=ctx.param("weight", 0.5), reason="rsi oversold")
        elif pos.quantity > 0 and (rsi > ctx.param("overbought", 55) or bar.close > sma):
            ctx.close(bar.symbol, reason="reverted")
