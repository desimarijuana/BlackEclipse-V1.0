"""Portfolio backtest node: several strategies, one book.

`run_portfolio_backtest` already exists in `harness/quant/engine.py`; this node
only adapts a `{symbol: OHLCV}` map into one `MarketDataset` and produces the
strategy list. Nothing about portfolio accounting, shared cash, leverage or
conflicting-symbol detection is reimplemented here.

Two ways to describe the portfolio:

  * `strategiesJson` - a JSON array of full `StrategySpec` objects. Each must
    declare `universe.symbols`, and every one of those symbols must exist in the
    series map; a missing or doubly-claimed symbol is an explicit failure.
  * the preset route - one preset strategy per symbol in the map (the default),
    which is the useful case for "run this rule across a basket".

A portfolio is not a second data path: the series map is the same shape
`quant.align` produces, so aligning and then backtesting is a valid graph.
"""

from __future__ import annotations

import json
from typing import Any

from ..quant import data as quant_data
from ..quant.engine import BacktestConfig, run_portfolio_backtest
from ..quant.errors import QuantError
from ..quant.strategy import parse_strategy
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .quant_nodes import STRATEGY_FIELDS, preset_spec
from .quant_structure_nodes import series_map
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BARS = 20_000
MAX_STRATEGIES = 20
MAX_STRATEGIES_JSON = 40_000

# Everything the preset knobs need, minus the two single-series fields a
# portfolio cannot honour (one `symbol`, one `strategyJson`).
_PORTFOLIO_FIELDS = tuple(
    field for field in STRATEGY_FIELDS if field.name not in ("symbol", "strategyJson")
)


def _strategies(
    context: NodeExecContext, available: list[str]
) -> list[Any]:
    raw = str(context.config.get("strategiesJson") or "").strip()
    if not raw:
        preset = str(context.config.get("preset") or "ema_cross")
        return [parse_strategy(preset_spec(preset, symbol, context.config)) for symbol in available]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"strategiesJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("strategiesJson must be a non-empty JSON array of StrategySpec objects")
    if len(parsed) > MAX_STRATEGIES:
        raise ValueError(f"strategiesJson is bounded to {MAX_STRATEGIES} strategies")

    known = set(available)
    strategies: list[Any] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"strategiesJson[{index}] must be an object")
        try:
            strategy = parse_strategy(item)
        except Exception as exc:  # noqa: BLE001 - a schema failure is node data
            raise ValueError(f"strategiesJson[{index}] is not a valid strategy: {exc}") from exc
        symbols = [str(symbol).strip().upper() for symbol in strategy.universe.symbols]
        if not symbols:
            raise ValueError(
                f"strategiesJson[{index}] ({strategy.id}) must declare universe.symbols"
            )
        missing = [symbol for symbol in symbols if symbol not in known]
        if missing:
            raise ValueError(
                f"strategiesJson[{index}] ({strategy.id}) references symbols that are "
                f"not in the series map: {', '.join(missing)}"
            )
        strategies.append(strategy)
    return strategies


def exec_portfolio_backtest(context: NodeExecContext) -> dict[str, Any]:
    raw_map = series_map(context.inputs.get("series"), "quant.portfolio_backtest")
    default_interval = str(context.config.get("interval") or "1d")

    bars: dict[str, Any] = {}
    for symbol, value in raw_map.items():
        interval = str(value.get("interval") or default_interval) if isinstance(value, dict) else default_interval
        rows = value.get("rows") if isinstance(value, dict) else value
        try:
            bars[symbol] = quant_data.series_from_rows(
                symbol, interval, list(rows),
                source=str(value.get("provider") or "graph") if isinstance(value, dict) else "graph",
                asset_type=str(value.get("assetType") or "equity") if isinstance(value, dict) else "equity",
            )
        except Exception as exc:  # noqa: BLE001 - a bad bar is an honest failure
            raise ValueError(f"portfolio backtest: '{symbol}' could not be adapted: {exc}") from exc

    try:
        dataset = quant_data.build_dataset(bars)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"portfolio backtest: dataset could not be built: {exc}") from exc

    strategies = _strategies(context, sorted(bars))

    try:
        config = BacktestConfig(
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            random_seed=int(context.config.get("randomSeed", 42)),
            max_bars=int(context.config.get("maxBars", 0)) or None,
        )
        result = run_portfolio_backtest(strategies, dataset, config)
    except QuantError as exc:
        raise ValueError(f"portfolio backtest failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"portfolio backtest failed: {type(exc).__name__}: {exc}") from exc

    include_series = bool(context.config.get("includeSeries", False))
    context.emit(
        f"portfolio: {len(strategies)} strategy(ies) over {len(bars)} symbol(s), "
        f"{result.metrics.get('trade_count', 0)} trades, status {result.status}"
    )
    return {
        "result": result.to_dict(include_series=include_series),
        "metrics": result.metrics,
        "trades": result.trades,
    }


def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_quant_portfolio_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.portfolio_backtest",
            version="1.0.0",
            label="Portfolio backtest",
            category="quant",
            inputs=(_port("series", "Series map", PortType.OBJECT),),
            outputs=(
                _port("result", "Result", PortType.OBJECT),
                _port("metrics", "Metrics", PortType.OBJECT),
                _port("trades", "Trades", PortType.ARRAY),
            ),
            config_fields=_PORTFOLIO_FIELDS + (
                ConfigField("strategiesJson", "string", "", max_length=MAX_STRATEGIES_JSON),
                ConfigField("includeSeries", "boolean", False),
                ConfigField("maxBars", "integer", 0, minimum=0, maximum=MAX_BARS),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_portfolio_backtest,
            metadata={
                "docs": (
                    "Runs harness/quant/engine.py `run_portfolio_backtest` over a "
                    "{symbol: OHLCV} map: shared cash, one book, every strategy "
                    "bound to its own symbols. Default is one preset strategy per "
                    "symbol; strategiesJson replaces that with explicit StrategySpecs. "
                    "A symbol claimed twice, referenced but absent, or an invalid spec "
                    "is an explicit failure."
                ),
            },
        ),
    ]


__all__ = ["build_quant_portfolio_nodes", "exec_portfolio_backtest"]
