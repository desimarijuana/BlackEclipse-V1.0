"""Volatility-targeted trend: size each entry to a target annualized vol."""

from __future__ import annotations

import numpy as np

from ..sdk import BarData, Context, Strategy


class VolTargetTrend(Strategy):
    name = "vol_target_trend"
    version = "1.0.0"

    def initialize(self, ctx: Context) -> None:
        ctx.declare_indicator("ema", "ema", {"period": ctx.param("ema_period", 100)})
        ctx.declare_indicator("atr", "atr", {"period": 14})
        ctx.set_stop_loss("atr", ctx.param("atr_mult", 3.0), atr_indicator="atr")
        ctx.set_risk(max_leverage=ctx.param("max_leverage", 1.0))

    def on_data(self, ctx: Context, bar: BarData) -> None:
        ema, atr = ctx.indicator("ema"), ctx.indicator("atr")
        if ema is None or atr is None or atr <= 0 or bar.close <= 0:
            return
        pos = ctx.position(bar.symbol)
        target_vol = ctx.param("target_vol", 0.15)
        # Scale weight inversely with recent realized vol (a simple vol target).
        rets = np.diff(np.log(np.clip(ctx.history("close", 20, bar.symbol), 1e-9, None)))
        realized = float(np.std(rets, ddof=1)) * np.sqrt(252) if len(rets) > 1 else target_vol
        weight = min(ctx.param("max_weight", 0.9), target_vol / realized) if realized > 0 else 0.0
        if pos.is_flat and bar.close > ema and weight > 0:
            ctx.buy(bar.symbol, weight=weight, reason="trend up, vol-targeted")
        elif pos.quantity > 0 and bar.close < ema:
            ctx.close(bar.symbol, reason="trend broken")
