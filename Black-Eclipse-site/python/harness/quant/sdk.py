"""Python Strategy SDK — author a strategy as code, run it on the ONE engine.

A strategy is an ordinary Python class subclassing `Strategy` with lifecycle
hooks. The SDK driver (`run_user_strategy`) executes it over a
`MarketDataset` and produces the SAME `BacktestResult` as a declarative or
visual strategy, because it *subclasses* `BacktestEngine` and reuses its
execution simulator, portfolio accounting, protective-leg handling, risk engine
and metrics — the SDK only supplies the per-bar decisions.

    class MyStrategy(Strategy):
        def initialize(self, ctx):
            ctx.declare_indicator("fast", "ema", {"period": 12})
            ctx.declare_indicator("slow", "ema", {"period": 50})
            ctx.set_stop_loss("atr", 2.0, atr_indicator="atr")
        def on_data(self, ctx, bar):
            if ctx.indicator("fast") is None:
                return
            if ctx.indicator("fast") > ctx.indicator("slow") and ctx.position().is_flat:
                ctx.buy(weight=0.95, reason="ema cross")

Bar-processing order, warm-up gating, fills (next-bar), slippage/commission and
costs are identical to the declarative engine because the code path is shared.

Determinism: every random draw comes from `ctx.rng` (seeded from
`BacktestConfig.random_seed`); the SDK never uses the global RNG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .data import MarketDataset
from .engine import (
    ENGINE_VERSION,
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    StrategyBinding,
)
from .models import Fill, Warning_
from .risk import RiskContext
from .strategy import (
    EntryRules,
    ExecutionAssumptions,
    ExitRules,
    IndicatorDecl,
    PositionSizing,
    RiskRules,
    Rules,
    StopSpec,
    StrategySpec,
    TakeProfitSpec,
    Timeframes,
    TrailingStopSpec,
    Universe,
)

SDK_VERSION = "1.0.0"


class SdkError(Exception):
    """A strategy-authoring error (bad declaration, bad run)."""

    code = "SDK_ERROR"


@dataclass
class BarData:
    symbol: str
    index: int
    ts: Optional[str]
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderIntent:
    symbol: str
    side: str                 # "buy" | "sell"
    quantity: Optional[float]
    weight: Optional[float]
    reason: str = ""


class Context:
    """The per-run strategy context (market access + order intents + state)."""

    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self.logs: list[str] = []
        self._decls: list[IndicatorDecl] = []
        self._engine: Optional[BacktestEngine] = None
        self._series: dict[str, Any] = {}
        self._arrays: dict[str, dict[str, np.ndarray]] = {}
        self._symbol: Optional[str] = None
        self._index: int = 0
        self._intents: list[OrderIntent] = []
        self._rng: Optional[np.random.Generator] = None
        # Risk/exit/sizing defaults (configurable in initialize).
        self._stop_loss: Optional[StopSpec] = None
        self._take_profit: Optional[TakeProfitSpec] = None
        self._trailing: Optional[TrailingStopSpec] = None
        self._sizing_type: str = "percent_equity"
        self._sizing_value: float = 90.0
        self._default_weight: float = 0.95
        self._risk: RiskRules = RiskRules()

    # ── Parameters ───────────────────────────────────────────────────────────
    def param(self, name: str, default: Any = None) -> Any:
        return self.params.get(name, default)

    # ── Declarations (call in initialize) ────────────────────────────────────
    def declare_indicator(self, id: str, type: str, params: Optional[dict] = None,
                          source: Optional[str] = None) -> None:
        self._decls.append(IndicatorDecl(id=id, type=type, params=params or {}, source=source))

    def set_stop_loss(self, type: str = "atr", value: float = 2.0,
                      atr_indicator: Optional[str] = None) -> None:
        self._stop_loss = StopSpec(type=type, value=value, atr_indicator=atr_indicator)  # type: ignore[arg-type]

    def set_take_profit(self, type: str = "risk_reward", value: float = 2.0) -> None:
        self._take_profit = TakeProfitSpec(type=type, value=value)  # type: ignore[arg-type]

    def set_trailing_stop(self, type: str = "atr", value: float = 3.0,
                          atr_indicator: Optional[str] = None) -> None:
        self._trailing = TrailingStopSpec(type=type, value=value, atr_indicator=atr_indicator)  # type: ignore[arg-type]

    def set_sizing(self, type: str = "percent_equity", value: float = 90.0,
                   default_weight: float = 0.95) -> None:
        self._sizing_type, self._sizing_value = type, value
        self._default_weight = default_weight

    def set_risk(self, **kwargs: Any) -> None:
        self._risk = RiskRules(**kwargs)

    # ── Market access ────────────────────────────────────────────────────────
    @property
    def rng(self) -> np.random.Generator:
        assert self._rng is not None
        return self._rng

    @property
    def symbol(self) -> Optional[str]:
        return self._symbol

    @property
    def bar(self) -> BarData:
        sym = self._symbol
        assert sym is not None and sym in self._series
        s = self._series[sym]
        i = self._index
        return BarData(sym, i, s.timestamps[i], float(s.open[i]), float(s.high[i]),
                       float(s.low[i]), float(s.close[i]), float(s.volume[i]))

    def indicator(self, id: str, symbol: Optional[str] = None) -> Optional[float]:
        arrays = self._arrays.get(symbol or self._symbol or "", {})
        arr = arrays.get(id)
        if arr is None:
            return None
        v = float(arr[self._index]) if self._index < len(arr) else float("nan")
        return None if np.isnan(v) else v

    def history(self, field: str = "close", n: int = 1, symbol: Optional[str] = None) -> np.ndarray:
        s = self._series[symbol or self._symbol or ""]
        arr = getattr(s, field)
        end = self._index + 1
        start = max(0, end - max(1, int(n)))
        return np.asarray(arr[start:end], dtype=float)

    @property
    def cash(self) -> float:
        assert self._engine is not None
        return self._engine.portfolio.cash

    @property
    def equity(self) -> float:
        assert self._engine is not None
        return self._engine.portfolio.equity

    def position(self, symbol: Optional[str] = None):
        assert self._engine is not None
        return self._engine.portfolio.position(symbol or self._symbol or "")

    def positions(self):
        assert self._engine is not None
        return self._engine.portfolio.open_positions()

    # ── Order intents ────────────────────────────────────────────────────────
    def order(self, side: str, symbol: Optional[str] = None, size: Optional[float] = None,
              weight: Optional[float] = None, reason: str = "") -> None:
        if side not in ("buy", "sell"):
            raise SdkError(f"order side must be 'buy' or 'sell', got {side!r}")
        self._intents.append(OrderIntent(symbol or self._symbol or "", side, size, weight, reason))

    def buy(self, symbol: Optional[str] = None, size: Optional[float] = None,
            weight: Optional[float] = None, reason: str = "") -> None:
        self.order("buy", symbol, size, weight, reason)

    def sell(self, symbol: Optional[str] = None, size: Optional[float] = None,
             weight: Optional[float] = None, reason: str = "") -> None:
        self.order("sell", symbol, size, weight, reason)

    def close(self, symbol: Optional[str] = None, reason: str = "close") -> None:
        pos = self.position(symbol)
        if not pos.is_flat:
            self.order("sell" if pos.quantity > 0 else "buy", symbol,
                       size=abs(pos.quantity), reason=reason)

    def log(self, message: str) -> None:
        self.logs.append(str(message))


class Strategy:
    """Base class for a Python strategy. Override the hooks you need."""

    name: str = "strategy"
    version: str = "1.0.0"

    def initialize(self, ctx: Context) -> None:  # pragma: no cover - default no-op
        pass

    def on_data(self, ctx: Context, bar: BarData) -> None:  # pragma: no cover - default no-op
        pass

    def on_fill(self, ctx: Context, fill: dict[str, Any]) -> None:  # pragma: no cover
        pass

    def on_order_update(self, ctx: Context, order: dict[str, Any]) -> None:  # pragma: no cover
        pass

    def on_stop(self, ctx: Context) -> None:  # pragma: no cover - default no-op
        pass


# ── Driver ───────────────────────────────────────────────────────────────────

class _SdkEngine(BacktestEngine):
    """Runs a user `Strategy` on the shared engine (accounting is identical)."""

    def __init__(self, user: Strategy, ctx: Context, dataset: MarketDataset,
                 config: BacktestConfig, spec: StrategySpec) -> None:
        super().__init__([StrategyBinding(spec, list(spec.universe.symbols))], dataset, config)
        self._user = user
        self.sdk_ctx = ctx
        self._aborted = False
        ctx._engine = self
        ctx._series = self._series
        ctx._arrays = self.ctx
        ctx._rng = np.random.default_rng(config.random_seed)

    # per-bar callback replaces rule evaluation
    def _evaluate_signals(self, symbol: str, i: int) -> None:
        if self._aborted:
            return
        ctx = self.sdk_ctx
        ctx._symbol, ctx._index, ctx._intents = symbol, i, []
        try:
            self._user.on_data(ctx, ctx.bar)
        except Exception as exc:  # noqa: BLE001 - user code boundary
            self._fail(exc, symbol)
            return
        self._apply_intents(i)

    def _apply_intents(self, i: int) -> None:
        for intent in list(self.sdk_ctx._intents):
            try:
                self._submit_user_order(intent, i)
            except Exception as exc:  # noqa: BLE001
                self._fail(exc, intent.symbol)

    def _fail(self, exc: Exception, symbol: str) -> None:
        self._aborted = True
        self.errors.append({"type": type(exc).__name__, "message": str(exc), "symbol": symbol})
        self.warnings.append(Warning_(
            "SDK_STRATEGY_ERROR", f"{type(exc).__name__}: {exc}", {"symbol": symbol}))

    def _submit_user_order(self, intent: OrderIntent, i: int) -> None:
        symbol = intent.symbol
        if symbol not in self._series:
            self.warnings.append(Warning_("SDK_UNKNOWN_SYMBOL",
                                          f"order for unknown symbol {symbol!r}", {"symbol": symbol}))
            return
        current_ts = self._series[self.sdk_ctx._symbol].timestamps[i]  # type: ignore[index]
        j = self._bar_index.get(symbol, {}).get(current_ts)
        if j is None:
            self.warnings.append(Warning_("SDK_NO_BAR",
                                          f"no bar for {symbol!r} at {current_ts}", {"symbol": symbol}))
            return
        price = float(self._series[symbol].close[j])
        pos = self.portfolio.position(symbol)
        # Size.
        qty = intent.quantity
        if qty is None:
            weight = intent.weight if intent.weight is not None else self.sdk_ctx._default_weight
            equity = self.portfolio.equity
            qty = (equity * float(weight)) / price if price > 0 else 0.0
        qty = abs(float(qty))
        if qty <= 0:
            self.warnings.append(Warning_("SDK_ZERO_SIZE",
                                          f"no size for {symbol!r} order", {"symbol": symbol}))
            return
        binding = self.bindings_by_symbol[symbol]
        closing = (not pos.is_flat) and ((pos.quantity > 0) != (intent.side == "buy"))
        if closing:
            qty = min(qty, abs(pos.quantity))
            risk_ctx = RiskContext(
                equity=self.portfolio.equity, side=intent.side, price=price,
                proposed_quantity=qty, is_opening=False,
                current_symbol_value=pos.quantity * price,
                gross_exposure=self.portfolio.gross_exposure(),
                open_positions=len(self.portfolio.open_positions()), has_stop=True,
            )
        else:
            risk_ctx = RiskContext(
                equity=self.portfolio.equity, side=intent.side, price=price,
                proposed_quantity=qty, is_opening=True,
                current_symbol_value=pos.quantity * price,
                gross_exposure=self.portfolio.gross_exposure(),
                open_positions=len(self.portfolio.open_positions()),
                has_stop=self.sdk_ctx._stop_loss is not None or self.sdk_ctx._trailing is not None,
            )
        decision = self._risk(binding).evaluate(risk_ctx)
        if decision.rejected:
            self._observability["ordersRejectedByRisk"] += 1
            self.warnings.append(Warning_(
                "RISK_REJECTED", f"{symbol} order rejected: {', '.join(decision.reasons)}",
                {"symbol": symbol, "reasons": decision.reasons}))
            return
        qty = decision.quantity
        if closing:
            self._cancel_protective(symbol, j)
        order = self.orders.create(
            symbol, intent.side, "market", qty, index=j, ts=self._series[symbol].timestamps[j],
            tag="exit" if closing else "entry",
            reason=intent.reason or f"{intent.side} ({'close' if closing else 'open'})",
        )
        self.orders.submit(order, j)
        self.orders.accept(order, j)
        self._observability["ordersCreated"] += 1
        self._observability["signals"] += 1
        if not self._aborted:
            try:
                self._user.on_order_update(self.sdk_ctx, order.to_dict())
            except Exception as exc:  # noqa: BLE001
                self._fail(exc, symbol)

    def _apply_fill(self, order, fill: Fill, i: int) -> None:
        super()._apply_fill(order, fill, i)
        if not self._aborted:
            try:
                self._user.on_fill(self.sdk_ctx, fill.to_dict())
            except Exception as exc:  # noqa: BLE001
                self._fail(exc, fill.symbol)

    def run(self) -> BacktestResult:
        result = super().run()
        if not self._aborted:
            try:
                self._user.on_stop(self.sdk_ctx)
            except Exception as exc:  # noqa: BLE001
                self._fail(exc, "")
        result.artifacts["logs"] = list(self.sdk_ctx.logs)
        if self._aborted:
            result.status = "FAILED"
        return result


def run_user_strategy(
    user: Strategy,
    dataset: MarketDataset,
    config: Optional[BacktestConfig] = None,
    *,
    params: Optional[dict[str, Any]] = None,
    symbols: Optional[list[str]] = None,
    strategy_id: Optional[str] = None,
) -> BacktestResult:
    """Run a user strategy over `dataset` and return a full `BacktestResult`."""
    cfg = config or BacktestConfig()
    ctx = Context()
    ctx.params = dict(params or {})
    try:
        user.initialize(ctx)
    except Exception as exc:  # noqa: BLE001 - user boundary
        raise SdkError(f"initialize() failed: {type(exc).__name__}: {exc}") from exc

    syms = [s.upper() for s in (symbols or list(dataset.series.keys()))]
    if not syms:
        raise SdkError("no symbols to trade")
    spec = StrategySpec(
        id=strategy_id or getattr(user, "name", "python_strategy"),
        name=getattr(user, "name", "python_strategy"),
        version=getattr(user, "version", "1.0.0"),
        universe=Universe(symbols=syms),
        timeframes=Timeframes(primary=dataset.primary_interval()),
        indicators=list(ctx._decls),
        rules=Rules(
            entry=EntryRules(),
            exit=ExitRules(stop_loss=ctx._stop_loss, take_profit=ctx._take_profit,
                           trailing_stop=ctx._trailing),
        ),
        risk=ctx._risk,
        position_sizing=PositionSizing(type=ctx._sizing_type, value=ctx._sizing_value),  # type: ignore[arg-type]
        execution=ExecutionAssumptions(),
    )
    return _SdkEngine(user, ctx, dataset, cfg, spec).run()


__all__ = [
    "BarData",
    "Context",
    "OrderIntent",
    "SDK_VERSION",
    "SdkError",
    "Strategy",
    "run_user_strategy",
]
