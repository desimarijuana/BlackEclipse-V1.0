"""Vectorized backtest engine — a fast research path for *representable* strategies.

This is deliberately a **restricted** engine, not a second general backtester. It
is only correct for strategy semantics that reduce to a causal signal → target
position → mark-to-market pipeline. It reuses the SAME:

  * indicator computation (`engine.build_context`) — causal, identical warm-up;
  * rule evaluation (`rules.evaluate`);
  * position sizing (`sizing.compute_quantity`);
  * execution-cost models (`ExecutionSimulator`);
  * metric set (`MetricsEngine`).

so a supported strategy cannot silently change meaning between engines. What it
does **not** support (protective legs, path-dependent risk rules, multi-timeframe
confirmation, latency, intrabar fills) is *refused with a structured capability
error* and routed to the event-driven engine — never silently approximated.

Supported subset (all must hold):
  * single primary timeframe, no confirmation timeframes;
  * no stop-loss / take-profit / trailing-stop / time-stop legs;
  * position sizing in {fixed_quantity, fixed_dollar, percent_equity};
  * no path-dependent risk rules (only allow_long / allow_short);
  * execution fill_at == next_open and latency_bars == 0;
  * a single symbol.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

from . import rules as rule_eval
from .data import MarketDataset
from .engine import (
    ENGINE_VERSION,
    BacktestConfig,
    BacktestResult,
    build_context,
)
from .errors import QuantError
from .execution import ExecutionSimulator
from .metrics import MetricInputs, MetricsEngine
from .models import EquityPoint, Fill, Order, TradeRecord, Warning_
from .sizing import SizingContext, compute_quantity
from .strategy import StrategySpec

_SUPPORTED_SIZING = {"fixed_quantity", "fixed_dollar", "percent_equity"}


class VectorUnsupported(QuantError):
    """The strategy uses semantics the vectorized engine cannot represent."""

    code = "VECTOR_UNSUPPORTED"
    http_status = 422


def vector_capability(strategy: StrategySpec, *, symbols: Optional[list[str]] = None) -> dict[str, Any]:
    """Return whether `strategy` is representable by the vector engine, with reasons."""
    reasons: list[str] = []
    ex = strategy.rules.exit
    if strategy.timeframes.confirmation:
        reasons.append("confirmation timeframes require the event engine")
    if ex.stop_loss is not None:
        reasons.append("stop-loss legs are path-dependent")
    if ex.take_profit is not None:
        reasons.append("take-profit legs are path-dependent")
    if ex.trailing_stop is not None:
        reasons.append("trailing stops are path-dependent")
    if ex.time_stop_bars is not None:
        reasons.append("time stops are path-dependent")
    if strategy.position_sizing.type not in _SUPPORTED_SIZING:
        reasons.append(f"position sizing {strategy.position_sizing.type!r} is not vector-representable")
    risk = strategy.risk
    for field in ("max_position_pct", "max_gross_exposure", "max_leverage",
                  "max_open_positions", "max_daily_loss_pct", "max_risk_per_trade_pct"):
        if getattr(risk, field) is not None:
            reasons.append(f"risk rule {field!r} is not vector-representable")
    if risk.require_stop:
        reasons.append("require_stop is not vector-representable")
    if strategy.execution.fill_at != "next_open":
        reasons.append("only fill_at='next_open' is supported")
    if strategy.execution.latency_bars:
        reasons.append("execution latency is not supported")
    selected = symbols or strategy.universe.symbols
    if len(selected) != 1:
        reasons.append("the vectorized engine runs one symbol at a time")
    return {"supported": not reasons, "reasons": reasons, "engine": "vectorized"}


def _min_bars(ctx: dict[str, np.ndarray]) -> int:
    min_bars = 2
    for key, arr in ctx.items():
        if key in ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"):
            continue
        if arr.ndim == 1 and len(arr):
            first_valid = int(np.argmax(~np.isnan(arr)))
            min_bars = max(min_bars, first_valid + 1)
    return min_bars


def run_vectorized_backtest(
    strategy: StrategySpec,
    dataset: MarketDataset,
    config: Optional[BacktestConfig] = None,
    *,
    symbols: Optional[list[str]] = None,
) -> BacktestResult:
    cap = vector_capability(strategy, symbols=symbols)
    if not cap["supported"]:
        raise VectorUnsupported(
            "strategy is not representable by the vectorized engine: "
            + "; ".join(cap["reasons"]),
            detail=cap,
        )
    return _VectorEngine(strategy, dataset, config or BacktestConfig(),
                         symbols=symbols).run()


class _VectorEngine:
    def __init__(self, strategy: StrategySpec, dataset: MarketDataset,
                 config: BacktestConfig, *, symbols: Optional[list[str]] = None) -> None:
        self.strategy = strategy
        self.dataset = dataset
        self.config = config
        self.symbol = (symbols or strategy.universe.symbols)[0].upper()
        self.warnings: list[Warning_] = []

    def run(self) -> BacktestResult:
        started = time.monotonic()
        strat = self.strategy
        series = self.dataset.series.get(self.symbol)
        if series is None:
            raise VectorUnsupported(f"no data for {self.symbol}",
                                    detail={"symbol": self.symbol})
        ctx, warns = build_context(strat, self.symbol, series, {})
        self.warnings.extend(warns)
        min_bars = _min_bars(ctx)

        open_ = np.asarray(series.open, dtype=float)
        close = np.asarray(series.close, dtype=float)
        ts = list(series.timestamps)
        n = series.length

        sim = ExecutionSimulator(strat.execution, seed=self.config.random_seed)
        if strat.execution.spread.type == "historical" and series.spread is None:
            self.warnings.append(Warning_(
                "HISTORICAL_SPREAD_UNAVAILABLE",
                "spread model is 'historical' but the dataset carries no per-bar bid/ask; "
                "spread cost is treated as zero",
            ))

        entry = strat.rules.entry
        ex = strat.rules.exit
        sizing = strat.position_sizing
        risk = strat.risk

        cash = float(self.config.initial_capital)
        pos = 0.0
        entry_price = 0.0
        entry_index: Optional[int] = None
        entry_commission = 0.0
        pending: Optional[dict[str, Any]] = None

        equity_values: list[float] = []
        equity_curve: list[dict[str, Any]] = []
        drawdown_curve: list[dict[str, Any]] = []
        exposure: list[EquityPoint] = []
        orders: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        commission_paid = 0.0
        order_seq = 0

        def _do_trade(dq: float, i: int, reason: str) -> None:
            nonlocal cash, pos, entry_price, entry_index, entry_commission, order_seq, commission_paid
            if dq == 0:
                return
            bar = _barctx(self.symbol, i, ts, open_, close, series)
            side = "buy" if dq > 0 else "sell"
            qty = abs(dq)
            base = float(open_[i])
            adverse = (sim.spread_adjustment(base, bar.spread)
                       + sim.slippage_adjustment(base, qty, bar)
                       + sim.impact_adjustment(base, qty, bar))
            fill_price = base + adverse if side == "buy" else base - adverse
            commission = sim.commission(qty, fill_price)
            order_seq += 1
            oid = f"vorder_{order_seq}"
            orders.append(Order(
                id=oid, symbol=self.symbol, side=side, type="market", quantity=qty,
                status="filled", created_index=i - 1 if i > 0 else i,
                created_ts=ts[i - 1] if i > 0 else ts[i], submitted_index=i,
                filled_quantity=qty, avg_fill_price=fill_price, commission=commission,
                tag="entry" if (pos == 0 or pos * dq < 0) else "exit", reason=reason,
            ).to_dict())
            fills.append(Fill(
                id=f"vfill_{order_seq}", order_id=oid, symbol=self.symbol, side=side,
                quantity=qty, price=fill_price, commission=commission,
                slippage=sim.slippage_adjustment(base, qty, bar) * qty,
                spread_cost=sim.spread_adjustment(base, bar.spread) * qty,
                impact=sim.impact_adjustment(base, qty, bar) * qty,
                index=i, ts=ts[i], reason=reason,
            ).to_dict())
            cash -= dq * base + qty * adverse + commission
            commission_paid += commission

            was_flat = pos == 0.0
            closing = (pos > 0 and dq < 0) or (pos < 0 and dq > 0)
            if closing:
                # realize the round trip
                qty_closed = min(abs(dq), abs(pos))
                direction = "long" if pos > 0 else "short"
                gross = (fill_price - entry_price) * qty_closed * (1 if pos > 0 else -1)
                comm = entry_commission + commission * (qty_closed / qty)
                net = gross - comm
                basis = abs(entry_price) * qty_closed
                trades.append(TradeRecord(
                    id=f"vtrade_{len(trades) + 1}", symbol=self.symbol, direction=direction,
                    entry_ts=ts[entry_index] if entry_index is not None else None, exit_ts=ts[i],
                    entry_price=entry_price, exit_price=fill_price, quantity=qty_closed,
                    gross_pnl=gross, net_pnl=net, commission=comm,
                    bars_held=(i - entry_index) if entry_index is not None else 0,
                    pnl_pct=(net / basis * 100.0) if basis else 0.0, exit_reason=reason,
                ).to_dict())
            pos += dq
            if pos != 0.0:
                entry_price = fill_price
                entry_index = i
                entry_commission = commission
            else:
                entry_price = 0.0
                entry_index = None
                entry_commission = 0.0
            del was_flat

        for i in range(n):
            if pending is not None:
                _do_trade(pending["target"] - pos, i, pending["reason"])
                pending = None

            eq_market = pos * float(close[i])
            equity = cash + eq_market
            equity_values.append(equity)
            equity_curve.append({"index": i, "ts": ts[i], "equity": equity})
            peak = max(equity_values) if equity_values else 0.0
            drawdown_curve.append({"index": i, "ts": ts[i],
                                   "drawdown": (equity / peak - 1.0) * 100.0 if peak else 0.0})
            exposure.append(EquityPoint(
                index=i, ts=ts[i], equity=equity, cash=cash, positions_value=eq_market,
                gross_exposure=abs(eq_market), net_exposure=eq_market,
                leverage=(abs(eq_market) / equity) if equity else 0.0,
            ))

            if i < min_bars or i + 1 >= n:
                continue
            # signal evaluation at close of bar i (executed at open of i+1)
            if pos == 0.0:
                if risk.allow_long and entry.long is not None and rule_eval.evaluate(entry.long, ctx, i):
                    qty, _ = compute_quantity(sizing, SizingContext(
                        equity=cash, price=float(close[i]), weight=1.0))
                    if qty:
                        pending = {"target": qty, "reason": "long entry"}
                elif risk.allow_short and entry.short is not None and rule_eval.evaluate(entry.short, ctx, i):
                    qty, _ = compute_quantity(sizing, SizingContext(
                        equity=cash, price=float(close[i]), weight=1.0))
                    if qty:
                        pending = {"target": -qty, "reason": "short entry"}
            else:
                exit_rule = ex.long if pos > 0 else ex.short
                if exit_rule is not None and rule_eval.evaluate(exit_rule, ctx, i):
                    pending = {"target": 0.0, "reason": "exit signal"}

        duration_ms = int((time.monotonic() - started) * 1000)
        return self._build_result(
            equity_values, ts, exposure, equity_curve, drawdown_curve,
            orders, fills, trades, min_bars, duration_ms)

    def _build_result(self, equity_values, ts, exposure, equity_curve, drawdown_curve,
                      orders, fills, trades, min_bars, duration_ms) -> BacktestResult:
        strat = self.strategy
        asset_class = getattr(strat, "asset_class", None)
        metric_inputs = MetricInputs(
            equity=equity_values, timestamps=list(ts),
            trades=[], exposure=exposure, interval=strat.timeframes.primary,
            initial_capital=self.config.initial_capital,
            risk_free_rate=self.config.risk_free_rate,
        )
        # Trade stats need TradeRecord objects; rebuild them from the dicts.
        metric_inputs.trades = _records_from_dicts(trades)
        engine = MetricsEngine(metric_inputs, asset_class=asset_class)
        metric_map = engine.compute()
        metrics = {name: mv.value for name, mv in metric_map.items()}
        definitions = {name: mv.to_dict() for name, mv in metric_map.items()}

        sim = ExecutionSimulator(strat.execution, seed=self.config.random_seed)
        metadata = {
            "engineVersion": ENGINE_VERSION,
            "engine": "vectorized",
            "strategyId": strat.id,
            "strategyVersion": strat.version,
            "symbols": [self.symbol],
            "timeframes": [strat.timeframes.primary],
            "bars": len(equity_values),
            "minBars": min_bars,
        }
        configuration = {
            "initialCapital": self.config.initial_capital,
            "start": ts[0] if ts else None,
            "end": ts[-1] if ts else None,
            "riskFreeRate": self.config.risk_free_rate,
            "randomSeed": self.config.random_seed,
            "interval": strat.timeframes.primary,
            "execution": sim.assumptions_summary(),
            "engine": "vectorized",
        }
        capability = {
            "vectorized": "available", "singleSymbol": "available",
            "protectiveLegs": "unsupported", "multiTimeframe": "unsupported",
        }
        monthly = _monthly_returns(equity_curve)
        return BacktestResult(
            metadata=metadata, configuration=configuration, metrics=metrics,
            metric_definitions=definitions, trades=trades, orders=orders, fills=fills,
            positions=[], equity_curve=equity_curve, drawdown_curve=drawdown_curve,
            exposure=[e.to_dict() for e in exposure], monthly_returns=monthly,
            warnings=[w.to_dict() for w in self.warnings], errors=[], artifacts={},
            observability={"barsProcessed": len(equity_values), "fills": len(fills),
                           "trades": len(trades),
                           "durationMs": duration_ms},
            capability=capability,
        )


def _barctx(symbol, i, ts, open_, close, series):
    from .execution import BarContext

    return BarContext(
        symbol=symbol, index=i, ts=ts[i], open=float(open_[i]),
        high=float(series.high[i]), low=float(series.low[i]), close=float(close[i]),
        volume=float(series.volume[i]) if series.volume is not None else 0.0,
        spread=(float(series.spread[i]) if getattr(series, "spread", None) is not None else None),
    )


def _records_from_dicts(trades: list[dict[str, Any]]) -> list[TradeRecord]:
    out: list[TradeRecord] = []
    for t in trades:
        out.append(TradeRecord(
            id=t["id"], symbol=t["symbol"], direction=t["direction"],
            entry_ts=t.get("entryTs"), exit_ts=t.get("exitTs"),
            entry_price=t["entryPrice"], exit_price=t["exitPrice"],
            quantity=t["quantity"], gross_pnl=t["grossPnl"], net_pnl=t["netPnl"],
            commission=t["commission"], bars_held=t["barsHeld"],
            pnl_pct=t["pnlPct"], exit_reason=t.get("exitReason", ""),
        ))
    return out


def _monthly_returns(equity_curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {}
    order: list[str] = []
    for point in equity_curve:
        t = point.get("ts")
        if not t:
            continue
        month = t[:7]
        if month not in buckets:
            buckets[month] = []
            order.append(month)
        buckets[month].append(point["equity"])
    out: list[dict[str, Any]] = []
    prev_close: Optional[float] = None
    for month in order:
        vals = buckets[month]
        base = prev_close if prev_close is not None else vals[0]
        out.append({"month": month,
                    "return": ((vals[-1] / base - 1.0) * 100.0) if base else 0.0,
                    "endEquity": vals[-1]})
        prev_close = vals[-1]
    return out


__all__ = [
    "VectorUnsupported",
    "run_vectorized_backtest",
    "vector_capability",
]
