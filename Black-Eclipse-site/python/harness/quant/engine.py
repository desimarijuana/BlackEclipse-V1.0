"""Event-driven backtest engine.

The pipeline is explicit:

    data → indicator context → signal (rules) → risk → order → fill
         → portfolio → equity/positions → metrics

Bar-processing order within each bar (this ordering is the anti-lookahead
contract, and is tested):

  1. fill orders that were submitted on an earlier bar (at this bar's open /
     range; `latency_bars` is honoured);
  2. advance trailing stops using the bar's favourable extreme;
  3. trigger protective legs (stop-loss / take-profit) on the bar's range, and
     time stops, closing the position;
  4. evaluate exit-signal rules and submit exit orders;
  5. evaluate entry-signal rules at the bar close and submit entry orders
     (which fill on a later bar);
  6. mark-to-market at the close and record the equity/exposure snapshot.

Nothing computed from bar `i` is used to fill an order on bar `i`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from . import indicators as ind
from . import rules as rule_eval
from .carry import (
    borrow_available,
    borrow_cost,
    elapsed_days,
    financing_cost,
    locate_fee,
    margin_status,
)
from .corporate_actions import CorporateAction, events_for, parse_actions
from .data import BarSeries, MarketDataset, align_higher_to_primary
from .errors import CorruptDataset, InsufficientHistory, MissingData, QuantError
from .execution import BarContext, ExecutionSimulator
from .manifest import build_run_manifest
from .metrics import MetricInputs, MetricsEngine
from .models import EquityPoint, Fill, Order, TradeRecord, Warning_
from .orders import OrderEngine
from .portfolio import Portfolio
from .risk import RiskContext, RiskEngine
from .sizing import SizingContext, compute_quantity
from .strategy import StrategySpec, StopSpec, TakeProfitSpec, TrailingStopSpec

ENGINE_VERSION = "0.2.0"


@dataclass
class StrategyBinding:
    """A strategy + the symbols it trades over the shared portfolio."""

    strategy: StrategySpec
    symbols: list[str]


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    start: Optional[str] = None
    end: Optional[str] = None
    risk_free_rate: float = 0.0
    random_seed: int = 42
    # Optional execution overrides (else the strategy's own assumptions apply).
    execution_override: Optional[dict[str, Any]] = None
    # Cap on how many bars to process (safety for very large datasets).
    max_bars: Optional[int] = None
    # Corporate actions for UNADJUSTED series. Empty by default because the
    # normal research path uses adjusted prices; applying both would double count.
    corporate_actions: list[Any] = field(default_factory=list)
    # Optional label for the code/build that produced the run (run manifest).
    code_version: Optional[str] = None


@dataclass
class BacktestResult:
    metadata: dict[str, Any]
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    metric_definitions: dict[str, Any]
    trades: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]
    drawdown_curve: list[dict[str, Any]]
    exposure: list[dict[str, Any]]
    monthly_returns: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    artifacts: dict[str, Any]
    observability: dict[str, Any]
    capability: dict[str, str]
    # Convenience flat metric map (same values as `metrics`).
    status: str = "OK"
    # Content-hashed reproducibility record (see `manifest.py`).
    manifest: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status, "metadata": self.metadata,
            "configuration": self.configuration, "metrics": self.metrics,
            "warnings": self.warnings, "errors": self.errors,
            "observability": self.observability, "capability": self.capability,
            "manifest": self.manifest,
        }

    def to_dict(self, *, include_series: bool = True) -> dict[str, Any]:
        data = self.summary()
        data.update({
            "metricDefinitions": self.metric_definitions,
            "trades": self.trades, "orders": self.orders, "fills": self.fills,
            "positions": self.positions, "artifacts": self.artifacts,
        })
        if include_series:
            data.update({
                "equityCurve": self.equity_curve, "drawdownCurve": self.drawdown_curve,
                "exposure": self.exposure, "monthlyReturns": self.monthly_returns,
            })
        return data


# ── Indicator context ────────────────────────────────────────────────────────

def _price_arrays(series: BarSeries) -> dict[str, np.ndarray]:
    ohlcv = series.ohlcv()
    ohlcv["hl2"] = (series.high + series.low) / 2.0
    ohlcv["hlc3"] = (series.high + series.low + series.close) / 3.0
    ohlcv["ohlc4"] = (series.open + series.high + series.low + series.close) / 4.0
    return ohlcv


def build_context(
    strategy: StrategySpec,
    symbol: str,
    series: BarSeries,
    higher: dict[str, BarSeries],
) -> tuple[dict[str, np.ndarray], list[Warning_]]:
    """Compute the array context for one symbol (primary + aligned confirmation)."""
    warnings: list[Warning_]= []
    ctx: dict[str, np.ndarray] = dict(_price_arrays(series))
    primary_tf = strategy.timeframes.primary

    primary_specs: list[ind.IndicatorSpec] = []
    tf_specs: dict[str, list[ind.IndicatorSpec]] = {tf: [] for tf in strategy.timeframes.confirmation}
    for decl in strategy.indicators:
        spec = decl.to_spec()
        tf = decl.timeframe or primary_tf
        if tf == primary_tf:
            primary_specs.append(spec)
        elif tf in tf_specs:
            tf_specs[tf].append(spec)
        else:
            warnings.append(Warning_(
                "INDICATOR_TF_IGNORED",
                f"indicator timeframe {tf!r} for {symbol} is not the primary or a "
                f"declared confirmation timeframe; ignored",
                {"symbol": symbol, "timeframe": tf},
            ))

    for key, arr in ind.compute_indicators(primary_specs, series.ohlcv()).items():
        ctx[key] = arr

    for tf in strategy.timeframes.confirmation:
        hseries = higher.get(tf)
        if hseries is None:
            warnings.append(Warning_(
                "MISSING_CONFIRMATION_DATA",
                f"no {tf} data for {symbol}; confirmation indicators unavailable",
                {"symbol": symbol, "timeframe": tf},
            ))
            for spec in tf_specs.get(tf, []):
                for key in ind.output_keys(spec):
                    ctx[f"{key}@{tf}"] = np.full(series.length, np.nan)
            continue
        align = align_higher_to_primary(hseries, series.timestamps, primary_tf)
        computed = ind.compute_indicators(tf_specs.get(tf, []), hseries.ohlcv())
        for key, arr in computed.items():
            aligned = np.full(series.length, np.nan)
            for i, hi in enumerate(align):
                if hi >= 0:
                    aligned[i] = arr[hi]
            ctx[f"{key}@{tf}"] = aligned
        # Aligned higher-TF price fields.
        for fld in ("open", "high", "low", "close"):
            src = getattr(hseries, fld)
            aligned = np.full(series.length, np.nan)
            for i, hi in enumerate(align):
                if hi >= 0:
                    aligned[i] = src[hi]
            ctx[f"{fld}@{tf}"] = aligned
    return ctx, warnings


# ── The engine ───────────────────────────────────────────────────────────────

class BacktestEngine:
    def __init__(
        self,
        bindings: list[StrategyBinding],
        dataset: MarketDataset,
        config: BacktestConfig,
    ) -> None:
        if not bindings:
            raise MissingData("at least one strategy binding is required")
        self.bindings = bindings
        self.dataset = dataset
        self.config = config
        self.primary_tf = dataset.primary_interval()
        self.timeline = dataset.timeline()
        if config.max_bars:
            self.timeline = self.timeline[: config.max_bars]

        self.portfolio = Portfolio(
            config.initial_capital,
            allow_short=any(b.strategy.risk.allow_short for b in bindings),
        )
        self.orders = OrderEngine()
        # One execution simulator + risk engine PER strategy binding, so a
        # portfolio run honours each strategy's own costs and risk limits rather
        # than inheriting the first binding's. A symbol maps to exactly one
        # binding (conflicting symbols are rejected before construction).
        self._sims: dict[str, ExecutionSimulator] = {}
        self._risks: dict[str, RiskEngine] = {}
        for binding in bindings:
            key = binding.strategy.id
            self._sims[key] = ExecutionSimulator(binding.strategy.execution, seed=config.random_seed)
            self._risks[key] = RiskEngine(binding.strategy.risk)

        self.warnings: list[Warning_] = []
        self.errors: list[dict[str, Any]] = []
        self.fills: list[Fill] = []
        self.ctx: dict[str, dict[str, np.ndarray]] = {}
        self.bindings_by_symbol: dict[str, StrategyBinding] = {}
        # symbol → index in its series timestamp list
        self._bar_index: dict[str, dict[str, int]] = {}
        self._series: dict[str, BarSeries] = {}
        # symbol → protective order ids
        self._protective: dict[str, dict[str, str]] = {}
        self._observability = {
            "barsProcessed": 0, "signals": 0, "ordersCreated": 0,
            "ordersRejectedByRisk": 0, "ordersCancelled": 0,
            "fills": 0, "trades": 0,
            "partialFills": 0, "marginCalls": 0, "corporateActions": 0,
            "borrowRejections": 0,
        }
        self._corporate_actions: list[CorporateAction] = parse_actions(config.corporate_actions)
        self._actions_by_date = events_for(self._corporate_actions)
        self._last_carry_ts: Optional[str] = None
        self._financing_paid = 0.0
        self._borrow_paid = 0.0
        self._locate_paid = 0.0

    # ── setup ────────────────────────────────────────────────────────────────
    def _prepare(self) -> None:
        for binding in self.bindings:
            strat = binding.strategy
            for symbol in binding.symbols:
                series = self.dataset.series.get(symbol)
                if series is None:
                    raise MissingData(f"no data for {symbol}", detail={"symbol": symbol})
                if series.length < 2:
                    raise InsufficientHistory(f"{symbol} has fewer than 2 bars",
                                              detail={"symbol": symbol})
                self._series[symbol] = series
                self._bar_index[symbol] = {ts: i for i, ts in enumerate(series.timestamps)}
                higher = {tf: self.dataset.higher[(symbol, tf)]
                          for tf in strat.timeframes.confirmation
                          if (symbol, tf) in self.dataset.higher}
                ctx, warns = build_context(strat, symbol, series, higher)
                self.ctx[symbol] = ctx
                self.warnings.extend(warns)
                self.bindings_by_symbol[symbol] = binding
        # A `historical` spread needs a per-bar spread series; warn honestly when
        # the dataset does not carry one (the cost is then zero, never silent).
        for binding in self.bindings:
            if binding.strategy.execution.spread.type != "historical":
                continue
            missing = [sym for sym in binding.symbols
                       if self._series.get(sym) is not None and self._series[sym].spread is None]
            if missing:
                self.warnings.append(Warning_(
                    "HISTORICAL_SPREAD_UNAVAILABLE",
                    "spread model is 'historical' but the dataset carries no per-bar "
                    f"bid/ask for {', '.join(missing)}; spread cost is treated as zero",
                    {"symbols": missing},
                ))
        # Surface the dataset's own quality findings (gaps / duplicates /
        # out-of-order / incomplete bars) — never hidden from the user.
        for finding in self.dataset.findings():
            self.warnings.append(Warning_(
                f"DATA_{finding.kind.upper()}",
                f"dataset quality: {finding.kind}"
                + (f" ({', '.join(f'{k}={v}' for k, v in finding.detail.items())})"
                   if finding.detail else ""),
                dict(finding.detail),
            ))
        # require at least the longest indicator warm-up before trading.
        min_bars = 2
        for symbol, ctx in self.ctx.items():
            for key, arr in ctx.items():
                if key in ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"):
                    continue
                if arr.ndim == 1 and len(arr):
                    first_valid = int(np.argmax(~np.isnan(arr)))
                    min_bars = max(min_bars, first_valid + 1)
        self._min_bars = min_bars
        if self.primary_tf not in ("1mo",) and any(
            self._series[s].length < self._min_bars for s in self._series
        ):
            self.warnings.append(Warning_(
                "SHORT_HISTORY",
                "some series are shorter than the indicator warm-up; no trades may occur",
                {"minBars": self._min_bars},
            ))

    # ── helpers ──────────────────────────────────────────────────────────────
    def _sim(self, binding: StrategyBinding) -> ExecutionSimulator:
        return self._sims[binding.strategy.id]

    def _risk(self, binding: StrategyBinding) -> RiskEngine:
        return self._risks[binding.strategy.id]

    def _bar_ctx(self, symbol: str, i: int) -> BarContext:
        s = self._series[symbol]
        atr_key = self._atr_key(symbol, None)
        atr_val = float(self.ctx[symbol][atr_key][i]) if atr_key and not np.isnan(
            self.ctx[symbol][atr_key][i]) else None
        bar_spread = None
        if s.spread is not None and not np.isnan(s.spread[i]):
            bar_spread = float(s.spread[i])
        return BarContext(
            symbol=symbol, index=i, ts=s.timestamps[i],
            open=float(s.open[i]), high=float(s.high[i]), low=float(s.low[i]),
            close=float(s.close[i]), volume=float(s.volume[i]), atr=atr_val,
            spread=bar_spread,
        )

    def _atr_key(self, symbol: str, spec: Optional[str]) -> Optional[str]:
        ctx = self.ctx[symbol]
        if spec:
            return spec if spec in ctx else None
        if "atr" in ctx:
            return "atr"
        return next((k for k in ctx if k.startswith("atr_")), None)

    def _atr_value(self, symbol: str, i: int, spec: Optional[str]) -> Optional[float]:
        key = self._atr_key(symbol, spec)
        if not key:
            return None
        v = float(self.ctx[symbol][key][i])
        return None if np.isnan(v) else v

    def _stop_distance(self, binding: StrategyBinding, symbol: str, i: int,
                       price: float) -> tuple[Optional[float], Optional[float]]:
        """Return (stop_distance, stop_price) for the long/short entry."""
        stop: Optional[StopSpec] = binding.strategy.rules.exit.stop_loss
        if stop is None:
            trail = binding.strategy.rules.exit.trailing_stop
            if trail is None:
                return None, None
            return self._trail_distance(trail, symbol, i, price), None
        if stop.type == "atr":
            atr = self._atr_value(symbol, i, stop.atr_indicator)
            if atr is None:
                return None, None
            return atr * stop.value, None
        if stop.type == "percent":
            return price * stop.value / 100.0, None
        return abs(stop.value), None

    def _trail_distance(self, trail: TrailingStopSpec, symbol: str, i: int,
                        price: float) -> Optional[float]:
        if trail.type == "atr":
            atr = self._atr_value(symbol, i, trail.atr_indicator)
            return atr * trail.value if atr is not None else None
        if trail.type == "percent":
            return price * trail.value / 100.0
        return abs(trail.value)

    def _realized_vol(self, symbol: str, lookback: int, i: int) -> Optional[float]:
        """Trailing realized volatility of log returns over `lookback` bars.

        Only bars up to and including the decision bar `i` are used — a causal
        window. Using a fixed tail of the whole series would leak future prices
        into the position size.
        """
        s = self._series[symbol]
        end = i + 1
        start = max(0, end - lookback - 1)
        window = np.clip(s.close[start:end], 1e-9, None)
        if len(window) < 2:
            return None
        rets = np.diff(np.log(window))
        if len(rets) < 2:
            return None
        return float(np.std(rets, ddof=1))

    def _kelly_stats(self) -> tuple[Optional[float], Optional[float]]:
        trades = [t for t in self.portfolio.trades]
        if len(trades) < 10:
            return None, None
        wins = [t.net_pnl for t in trades if t.net_pnl > 0]
        losses = [t.net_pnl for t in trades if t.net_pnl < 0]
        if not wins or not losses:
            return None, None
        win_rate = len(wins) / len(trades)
        payoff = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
        return win_rate, payoff

    # ── order submission ─────────────────────────────────────────────────────
    def _make_protective(self, binding: StrategyBinding, symbol: str, i: int,
                         entry_side: str, quantity: float, entry_price: float,
                         stop_distance: Optional[float],
                         atr_index: Optional[int] = None) -> None:
        """Create the live protective legs (stop-loss + take-profit + trailing).

        Created at the entry fill (position size known), so quantity is exact and
        the legs are submitted/accepted immediately. Called only from a fill.

        `atr_index` is the bar whose ATR is safe to use for sizing the protective
        distance — the *decision* bar, not the (later) fill bar, so the fill bar's
        range cannot leak into the stop distance.
        """
        ref = atr_index if atr_index is not None else i
        exit_rules = binding.strategy.rules.exit
        ids: dict[str, str] = {}
        qty = abs(quantity)
        if qty <= 0:
            self._protective[symbol] = ids
            return
        long_entry = entry_side == "buy"
        protect_side = "sell" if long_entry else "buy"
        if stop_distance is not None and stop_distance > 0:
            stop_price = entry_price - stop_distance if long_entry else entry_price + stop_distance
            order = self.orders.create(
                symbol, protect_side, "stop_loss", qty, index=i, stop_price=stop_price,
                tag="stop_loss", reason="stop loss", parent_id=None,
            )
            self.orders.submit(order, i)
            self.orders.accept(order, i)
            self._observability["ordersCreated"] += 1
            ids["stop_loss"] = order.id
        tp: Optional[TakeProfitSpec] = exit_rules.take_profit
        if tp is not None and stop_distance is not None:
            if tp.type == "risk_reward":
                dist = stop_distance * tp.value
            elif tp.type == "percent":
                dist = entry_price * tp.value / 100.0
            else:
                dist = abs(tp.value)
            tp_price = entry_price + dist if long_entry else entry_price - dist
            order = self.orders.create(
                symbol, protect_side, "take_profit", qty, index=i, stop_price=tp_price,
                tag="take_profit", reason="take profit",
            )
            self.orders.submit(order, i)
            self.orders.accept(order, i)
            self._observability["ordersCreated"] += 1
            ids["take_profit"] = order.id
        trail: Optional[TrailingStopSpec] = exit_rules.trailing_stop
        if trail is not None:
            dist = self._trail_distance(trail, symbol, ref, entry_price)
            if dist and dist > 0:
                stop_price = entry_price - dist if long_entry else entry_price + dist
                order = self.orders.create(
                    symbol, protect_side, "trailing_stop", qty, index=i,
                    trail_amount=dist, stop_price=stop_price,
                    tag="trailing_stop", reason="trailing stop",
                )
                order.current_stop = stop_price
                self.orders.submit(order, i)
                self.orders.accept(order, i)
                self._observability["ordersCreated"] += 1
                ids["trailing_stop"] = order.id
        self._protective[symbol] = ids

    def _cancel_protective(self, symbol: str, index: int, *, except_id: Optional[str] = None) -> None:
        for oid in list(self._protective.get(symbol, {}).values()):
            if oid == except_id:
                continue
            order = self.orders.get(oid)
            if order is not None and order.is_open:
                try:
                    self.orders.cancel(order, index, "oco sibling filled")
                    self._observability["ordersCancelled"] += 1
                except Exception:  # noqa: BLE001
                    pass

    def _submit_entry(self, binding: StrategyBinding, symbol: str, i: int,
                      side: str, ctx_arrays: dict[str, np.ndarray]) -> None:
        strat = binding.strategy
        s = self._series[symbol]
        price = float(s.close[i])
        stop_distance, _ = self._stop_distance(binding, symbol, i, price)
        sizing_ctx = SizingContext(
            equity=self.portfolio.equity, price=price, stop_distance=stop_distance,
            atr=self._atr_value(symbol, i, strat.position_sizing.atr_indicator),
            realized_vol=self._realized_vol(symbol, strat.position_sizing.lookback or 20, i),
            kelly_win_rate=self._kelly_stats()[0], kelly_payoff=self._kelly_stats()[1],
            weight=1.0 / max(1, len(binding.symbols)),
        )
        qty, detail = compute_quantity(strat.position_sizing, sizing_ctx)
        if qty is None or qty <= 0:
            self.warnings.append(Warning_(
                "SIZE_NOT_COMPUTED",
                f"no size for {symbol} entry at {s.timestamps[i]}: {detail.get('reason', '')}",
                {"symbol": symbol, "detail": detail},
            ))
            return
        pos = self.portfolio.position(symbol)
        has_stop = strat.rules.exit.stop_loss is not None or \
            strat.rules.exit.trailing_stop is not None
        risk_ctx = RiskContext(
            equity=self.portfolio.equity, side=side, price=price,
            proposed_quantity=qty, is_opening=True,
            current_symbol_value=pos.quantity * price,
            gross_exposure=self.portfolio.gross_exposure(),
            open_positions=len(self.portfolio.open_positions()),
            stop_distance=stop_distance, has_stop=has_stop,
        )
        decision = self._risk(binding).evaluate(risk_ctx)
        if decision.rejected:
            self._observability["ordersRejectedByRisk"] += 1
            self.warnings.append(Warning_(
                "RISK_REJECTED",
                f"entry for {symbol} rejected: {', '.join(decision.reasons)}",
                {"symbol": symbol, "reasons": decision.reasons, "adjustments": decision.adjustments},
            ))
            return
        if decision.adjustments:
            self.warnings.append(Warning_(
                "RISK_ADJUSTED", f"{symbol} size adjusted: {', '.join(decision.adjustments)}",
                {"symbol": symbol},
            ))
        # A short that cannot be borrowed must be refused, not quietly modelled
        # as a free, always-available short.
        if side == "sell" and decision.quantity > 0:
            available, reason = borrow_available(strat.execution.borrow, symbol)
            if not available:
                self._observability["borrowRejections"] += 1
                self.warnings.append(Warning_(
                    "BORROW_UNAVAILABLE",
                    f"short entry for {symbol} rejected: {reason}",
                    {"symbol": symbol, "reason": reason},
                ))
                return
        order = self.orders.create(
            symbol, side, "market", decision.quantity, index=i,
            ts=s.timestamps[i], tag="entry", reason=f"{side} entry",
        )
        self.orders.submit(order, i)
        self.orders.accept(order, i)
        self._observability["ordersCreated"] += 1
        self._observability["signals"] += 1

    def _submit_exit(self, binding: StrategyBinding, symbol: str, i: int,
                     reason: str) -> None:
        pos = self.portfolio.position(symbol)
        if pos.is_flat:
            return
        side = "sell" if pos.quantity > 0 else "buy"
        self._cancel_protective(symbol, i)
        order = self.orders.create(
            symbol, side, "market", abs(pos.quantity), index=i,
            ts=self._series[symbol].timestamps[i], tag="exit", reason=reason,
        )
        self.orders.submit(order, i)
        self.orders.accept(order, i)
        self._observability["ordersCreated"] += 1
        self._observability["signals"] += 1

    # ── bar processing ───────────────────────────────────────────────────────
    def _fill_ready_orders(self, symbol: str, bar: BarContext, i: int) -> None:
        sim = self._sim(self.bindings_by_symbol[symbol])
        latency = sim.assumptions.latency_bars
        for order in self.orders.open_orders(symbol):
            if order.submitted_index is None:
                continue
            if i < order.submitted_index + 1 + latency:
                continue
            fill = sim.try_fill(order, bar, current_index=i, allow_same_bar=False)
            if fill is None:
                continue
            self._apply_fill(order, fill, i)
        for warning in sim.consume_warnings():
            self.warnings.append(Warning_(
                warning["code"], warning["message"], warning.get("detail") or {}
            ))

    def _apply_fill(self, order: Order, fill: Fill, i: int) -> None:
        was_flat = self.portfolio.is_flat(order.symbol)
        prior = self.portfolio.position(order.symbol).quantity
        self.orders.apply_fill(order, fill.quantity, fill.price, fill.commission)
        trade = self.portfolio.apply_fill(fill)
        self.fills.append(fill)
        self._observability["fills"] += 1
        if fill.fill_ratio < 1.0 - 1e-9:
            self._observability["partialFills"] += 1
        pos = self.portfolio.position(order.symbol)
        # A short that is newly opened pays the one-off locate fee. Accruing the
        # recurring borrow happens in `_accrue_carry`, not here.
        if prior >= 0 and pos.quantity < 0 and fill.side == "sell":
            terms = self.bindings_by_symbol[order.symbol].strategy.execution.borrow
            fee = locate_fee(abs(pos.quantity) * fill.price, terms.locate_fee_bps)
            if fee:
                self.portfolio.apply_cash(
                    -fee, kind="borrow", index=i, ts=fill.ts,
                    detail={"kind": "locate", "symbol": order.symbol, "bps": terms.locate_fee_bps},
                )
                self._locate_paid += fee
        # Entry fill: create the protective bracket sized to the new position.
        # Size the stop from the DECISION bar (order.submitted_index), not the
        # fill bar, so the fill bar's own high/low cannot leak into the ATR.
        if order.tag == "entry" and was_flat and not pos.is_flat:
            ref = order.submitted_index if order.submitted_index is not None else i
            stop_distance, _ = self._stop_distance(
                self.bindings_by_symbol[order.symbol], order.symbol, ref, fill.price
            )
            self._make_protective(
                self.bindings_by_symbol[order.symbol], order.symbol, i,
                order.side, pos.quantity, fill.price, stop_distance, atr_index=ref,
            )
        if trade is not None:
            self._observability["trades"] += 1
            if pos.is_flat:
                self._cancel_protective(order.symbol, i)

    def _process_protective(self, symbol: str, bar: BarContext, i: int) -> None:
        pos = self.portfolio.position(symbol)
        if pos.is_flat:
            return
        binding = self.bindings_by_symbol[symbol]
        sim = self._sim(binding)
        for oid in list(self._protective.get(symbol, {}).values()):
            order = self.orders.get(oid)
            if order is None or not order.is_open:
                continue
            # Test the barrier BEFORE advancing a trailing stop. Otherwise this
            # bar's favorable extreme could ratchet the stop past a level that
            # this same bar's adverse extreme already breached — an optimistic
            # same-bar sequencing that is not knowable intrabar.
            fill = sim.try_fill(order, bar, current_index=i, allow_same_bar=False)
            if fill is None:
                if order.type == "trailing_stop":
                    sim.update_trailing(order, bar)
                continue
            self._apply_fill(order, fill, i)
            self._cancel_protective(symbol, i, except_id=oid)
            return
        # Time stop.
        time_stop = binding.strategy.rules.exit.time_stop_bars
        if time_stop and pos.entry_index is not None and (i - pos.entry_index) >= time_stop:
            self._submit_exit(binding, symbol, i, "time stop")

    def _evaluate_signals(self, symbol: str, i: int) -> None:
        binding = self.bindings_by_symbol[symbol]
        strat = binding.strategy
        ctx = self.ctx[symbol]
        pos = self.portfolio.position(symbol)
        rules_exit = strat.rules.exit
        if not pos.is_flat:
            if pos.quantity > 0 and rules_exit.long is not None \
                    and rule_eval.evaluate(rules_exit.long, ctx, i):
                self._submit_exit(binding, symbol, i, "exit signal")
                return
            if pos.quantity < 0 and rules_exit.short is not None \
                    and rule_eval.evaluate(rules_exit.short, ctx, i):
                self._submit_exit(binding, symbol, i, "exit signal")
                return
            return
        # Flat: consider entries.
        if self.orders.open_orders(symbol):
            return
        allow_long = strat.risk.allow_long
        allow_short = strat.risk.allow_short
        if allow_long and strat.rules.entry.long is not None \
                and rule_eval.evaluate(strat.rules.entry.long, ctx, i):
            self._submit_entry(binding, symbol, i, "buy", ctx)
        elif allow_short and strat.rules.entry.short is not None \
            and rule_eval.evaluate(strat.rules.entry.short, ctx, i):
            self._submit_entry(binding, symbol, i, "sell", ctx)

    # ── cost of carry, corporate actions, margin ─────────────────────────────
    def _apply_corporate_actions(self, step: int, ts: Optional[str]) -> None:
        if not self._actions_by_date or ts is None:
            return
        day = str(ts)[:10]
        for action in self._actions_by_date.get(day, []):
            effect = self.portfolio.apply_corporate_action(action, index=step, ts=ts)
            if effect is not None:
                self._observability["corporateActions"] += 1
                self.warnings.append(Warning_(
                    "CORPORATE_ACTION_APPLIED",
                    f"{action.kind} applied to {action.symbol} on {action.ex_date}",
                    {"action": action.to_dict(), "effect": effect},
                ))

    def _accrue_carry(self, step: int, ts: Optional[str]) -> None:
        if self._last_carry_ts is None:
            self._last_carry_ts = ts
            return
        days = elapsed_days(self._last_carry_ts, ts)
        self._last_carry_ts = ts
        if days <= 0:
            return

        # Cash financing is a portfolio-level concern; the first binding owns
        # the account's cash terms in a multi-strategy run.
        fin = self.bindings[0].strategy.execution.financing
        cash_carry = financing_cost(
            self.portfolio.cash,
            debit_rate_bps=fin.debit_rate_bps,
            credit_rate_bps=fin.credit_rate_bps,
            days=days, day_count=fin.day_count,
        )
        if cash_carry:
            self.portfolio.apply_cash(
                cash_carry, kind="financing", index=step, ts=ts,
                detail={"cash": self.portfolio.cash, "days": days,
                        "debitBps": fin.debit_rate_bps, "creditBps": fin.credit_rate_bps},
            )
            self._financing_paid += cash_carry

        for symbol, pos in list(self.portfolio.positions.items()):
            if pos.quantity >= 0:
                continue
            price = self.portfolio.last_prices.get(symbol) or pos.last_price
            if not price:
                continue
            terms = self.bindings_by_symbol[symbol].strategy.execution.borrow
            cost = borrow_cost(
                abs(pos.quantity) * price, terms.annual_rate_bps, days,
                day_count=fin.day_count,
            )
            if cost:
                self.portfolio.apply_cash(
                    -cost, kind="borrow", index=step, ts=ts,
                    detail={"symbol": symbol, "days": days,
                            "annualBps": terms.annual_rate_bps},
                )
                self._borrow_paid += cost

    def _force_liquidate(self, step: int, ts: Optional[str],
                         bars: dict[str, BarContext]) -> None:
        """Close the whole book at the current bar (maintenance breach).

        The liquidation goes through the SAME execution simulator, so it pays
        commission/slippage/spread/impact. It is tagged `margin_call` and the
        resulting trade's `exit_reason` records it.
        """
        for order in self.orders.open_orders():
            if order.is_open:
                try:
                    self.orders.cancel(order, step, "margin call liquidation")
                except Exception:  # noqa: BLE001
                    pass
        for symbol, pos in list(self.portfolio.positions.items()):
            if pos.is_flat:
                continue
            bar = bars.get(symbol)
            if bar is None:
                continue
            side = "sell" if pos.quantity > 0 else "buy"
            qty = abs(pos.quantity)
            order = self.orders.create(
                symbol, side, "market", qty, index=step, ts=ts,
                tag="margin_call", reason="margin call liquidation",
            )
            self.orders.submit(order, step)
            self.orders.accept(order, step)
            sim = self._sim(self.bindings_by_symbol[symbol])
            fill = sim.try_fill(order, bar, current_index=step, allow_same_bar=True)
            if fill is None:
                # A halted/zero-volume bar still cannot be ignored: close at the
                # last known price and charge the commission, labelled as such.
                price = bar.close
                fill = Fill(
                    id=f"fill_margin_{order.id}", order_id=order.id, symbol=symbol,
                    side=side, quantity=qty, price=price,
                    commission=sim.commission(qty, price),
                    slippage=0.0, spread_cost=0.0, impact=0.0,
                    index=step, ts=ts, reason="margin call liquidation (forced close)",
                )
            self._apply_fill(order, fill, step)
            self._cancel_protective(symbol, step)
            self._observability["ordersCreated"] += 1

    def _check_margin(self, step: int, ts: Optional[str],
                      bars: dict[str, BarContext]) -> None:
        margin = self.bindings[0].strategy.execution.margin
        if not margin.enabled:
            return
        status = margin_status(
            equity=self.portfolio.equity,
            gross_exposure=self.portfolio.gross_exposure(),
            maintenance_pct=margin.maintenance_pct,
            initial_pct=margin.initial_pct,
        )
        if not status["breached"]:
            return
        self._force_liquidate(step, ts, bars)
        self._observability["marginCalls"] += 1
        self.warnings.append(Warning_(
            "MARGIN_CALL",
            "maintenance margin breached; the book was liquidated at the bar close",
            status,
        ))

    # ── run ──────────────────────────────────────────────────────────────────
    def run(self) -> BacktestResult:
        started = time.monotonic()
        self._prepare()
        equity_curve: list[dict[str, Any]] = []
        drawdown_curve: list[dict[str, Any]] = []
        exposure: list[EquityPoint] = []
        equity_values: list[float] = []
        timestamps: list[Optional[str]] = []

        for step, ts in enumerate(self.timeline):
            touched = [sym for sym, idx in self._bar_index.items() if ts in idx]
            # Corporate actions are effective at the START of their ex-date, so a
            # split is applied before the bar that carries the new price.
            self._apply_corporate_actions(step, ts)
            bars: dict[str, BarContext] = {}
            for symbol in touched:
                i = self._bar_index[symbol][ts]
                bar = self._bar_ctx(symbol, i)
                bars[symbol] = bar
                self.portfolio.mark(symbol, bar.close)
                self._observability["barsProcessed"] += 1
                if i < self._min_bars:
                    continue
                # 1. fill earlier orders
                self._fill_ready_orders(symbol, bar, i)
                # 2. trailing + 3. protective/time stops
                self._process_protective(symbol, bar, i)
                # 4/5. signals at close
                self._evaluate_signals(symbol, i)

            # Carry accrues on elapsed calendar time, then margin is checked
            # against the marked book before the snapshot is recorded.
            self._accrue_carry(step, ts)
            self._check_margin(step, ts, bars)

            # 6. snapshot (mark everything to its latest price)
            eq = self.portfolio.snapshot(step, ts)
            equity_values.append(eq.equity)
            timestamps.append(ts)
            exposure.append(eq)
            equity_curve.append({"index": step, "ts": ts, "equity": eq.equity})
            peak = max(equity_values) if equity_values else 0.0
            dd = (eq.equity / peak - 1.0) * 100.0 if peak else 0.0
            drawdown_curve.append({"index": step, "ts": ts, "drawdown": dd})

        duration_ms = int((time.monotonic() - started) * 1000)
        result = self._build_result(
            equity_values, timestamps, exposure, equity_curve, drawdown_curve, duration_ms
        )
        return result

    def _monthly_returns(self, equity_curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = {}
        order: list[str] = []
        for point in equity_curve:
            ts = point.get("ts")
            if not ts:
                continue
            month = ts[:7]
            if month not in buckets:
                buckets[month] = []
                order.append(month)
            buckets[month].append(point["equity"])
        out: list[dict[str, Any]] = []
        prev_close: Optional[float] = None
        for month in order:
            vals = buckets[month]
            first, last = vals[0], vals[-1]
            base = prev_close if prev_close is not None else first
            ret = ((last / base - 1.0) * 100.0) if base else 0.0
            out.append({"month": month, "return": ret, "endEquity": last})
            prev_close = last
        return out

    def _build_result(
        self, equity_values, timestamps, exposure, equity_curve, drawdown_curve, duration_ms
    ) -> BacktestResult:
        asset_class = self.bindings[0].strategy.asset_class
        metric_inputs = MetricInputs(
            equity=equity_values, timestamps=list(timestamps),
            trades=self.portfolio.trades, exposure=exposure,
            interval=self.primary_tf, initial_capital=self.config.initial_capital,
            risk_free_rate=self.config.risk_free_rate,
        )
        engine = MetricsEngine(metric_inputs, asset_class=asset_class)
        metric_map = engine.compute()
        metrics = {name: mv.value for name, mv in metric_map.items()}
        definitions = {name: mv.to_dict() for name, mv in metric_map.items()}

        config = {
            "initialCapital": self.config.initial_capital,
            "start": self.timeline[0] if self.timeline else None,
            "end": self.timeline[-1] if self.timeline else None,
            "riskFreeRate": self.config.risk_free_rate,
            "randomSeed": self.config.random_seed,
            "interval": self.primary_tf,
            # Top-level execution is the first binding's, for backward-compatible
            # single-strategy payloads; each binding carries its OWN assumptions.
            "execution": self._sim(self.bindings[0]).assumptions_summary(),
            "carry": {
                "financing": round(self._financing_paid, 8),
                "borrow": round(self._borrow_paid, 8),
                "locateFees": round(self._locate_paid, 8),
                "dividends": round(self.portfolio.total_dividends, 8),
                "events": len(self.portfolio.carry_events),
            },
            "corporateActions": len(self._corporate_actions),
            "bindings": [
                {"strategyId": b.strategy.id, "strategyVersion": b.strategy.version,
                 "symbols": b.symbols, "positionSizing": b.strategy.position_sizing.model_dump(),
                 "risk": b.strategy.risk.model_dump(exclude_none=True),
                 "execution": self._sim(b).assumptions_summary()}
                for b in self.bindings
            ],
        }
        metadata = {
            "engineVersion": ENGINE_VERSION,
            "engine": "event-driven",
            "strategyId": self.bindings[0].strategy.id,
            "strategyVersion": self.bindings[0].strategy.version,
            "symbols": sorted(self._series.keys()),
            "timeframes": [self.primary_tf] if len(self.bindings) == 1 else
                          sorted({self.primary_tf}),
            "bars": len(self.timeline),
        }
        observability = dict(self._observability)
        observability["durationMs"] = duration_ms
        observability["equityPoints"] = len(equity_curve)

        capability = {
            "stocks": "available", "crypto": "available", "fx": "available",
            "futures": "partial", "options": "unsupported",
            "multiSymbol": "available", "multiTimeframe": "available",
            "commission": "available", "slippage": "available", "spread": "available",
            "latency": "available", "marketImpact": "available",
            "borrow": "available", "financing": "available", "margin": "available",
            "partialFills": "available", "corporateActions": "available",
            "walkForward": "available", "monteCarlo": "available",
            "optimization": "available", "robustness": "available", "sensitivity": "available",
        }
        manifest = build_run_manifest(
            strategies=[b.strategy for b in self.bindings],
            dataset=self.dataset,
            configuration=config,
            metrics=metrics,
            engine_version=ENGINE_VERSION,
            code_version=self.config.code_version,
            extra={
                "carry": config["carry"],
                "marginCalls": self._observability.get("marginCalls", 0),
                "partialFills": self._observability.get("partialFills", 0),
                "corporateActions": config["corporateActions"],
            },
        )
        metadata["manifestDigest"] = manifest["digest"]
        return BacktestResult(
            metadata=metadata, configuration=config, metrics=metrics,
            metric_definitions=definitions,
            trades=[t.to_dict() for t in self.portfolio.trades],
            orders=[o.to_dict() for o in self.orders.all_orders()],
            fills=[f.to_dict() for f in self.fills],
            positions=[p.to_dict() for p in self.portfolio.open_positions()],
            equity_curve=equity_curve, drawdown_curve=drawdown_curve,
            exposure=[e.to_dict() for e in exposure],
            monthly_returns=self._monthly_returns(equity_curve),
            warnings=[w.to_dict() for w in self.warnings],
            errors=list(self.errors), artifacts={},
            observability=observability, capability=capability,
            manifest=manifest,
        )


# ── Public API ───────────────────────────────────────────────────────────────

def run_backtest(
    strategy: StrategySpec,
    dataset: MarketDataset,
    config: Optional[BacktestConfig] = None,
    *,
    symbols: Optional[list[str]] = None,
) -> BacktestResult:
    cfg = config or BacktestConfig()
    selected = [s.upper() for s in (symbols or strategy.universe.symbols)]
    binding = StrategyBinding(strategy=strategy, symbols=selected)
    return BacktestEngine([binding], dataset, cfg).run()


def run_portfolio_backtest(
    strategies: list[StrategySpec],
    dataset: MarketDataset,
    config: Optional[BacktestConfig] = None,
) -> BacktestResult:
    if not strategies:
        raise MissingData("at least one strategy is required")
    cfg = config or BacktestConfig()
    bindings = [
        StrategyBinding(strategy=s, symbols=[x.upper() for x in s.universe.symbols])
        for s in strategies
    ]
    # Conflicting bindings for the same symbol are ambiguous; reject clearly.
    seen: dict[str, str] = {}
    for b in bindings:
        for sym in b.symbols:
            if sym in seen:
                raise CorruptDataset(
                    f"symbol {sym} is claimed by two strategies in one portfolio",
                    detail={"symbol": sym, "strategies": [seen[sym], b.strategy.id]},
                )
            seen[sym] = b.strategy.id
    return BacktestEngine(bindings, dataset, cfg).run()


__all__ = [
    "ENGINE_VERSION",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "StrategyBinding",
    "build_context",
    "run_backtest",
    "run_portfolio_backtest",
]
