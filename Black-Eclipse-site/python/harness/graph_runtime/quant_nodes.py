"""Quant research nodes.

The FIRST node in this pack is `quant.backtest`: it adapts the graph's OHLCV
payload into the tested quant dataset and calls `harness/quant/engine.py`. No
backtest math is reimplemented here. A strategy is either a documented preset or
a full `StrategySpec` JSON; preset/strategy errors are explicit node failures.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..quant import data as quant_data
from ..quant.engine import BacktestConfig, run_backtest
from ..quant.errors import QuantError
from ..quant.strategy import parse_strategy
from ..quant.walkforward import WalkForwardConfig, WalkForwardEngine, WalkForwardError
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BARS = 20_000


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows = value.get("rows")
    elif isinstance(value, list):
        rows = value
    else:
        rows = None
    if not isinstance(rows, list) or not rows:
        raise ValueError("quant.backtest needs an OHLCV series with at least one row")
    if len(rows) > MAX_BARS:
        raise ValueError(f"quant.backtest is bounded to {MAX_BARS} bars (got {len(rows)})")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("every OHLCV row must be an object")
    return rows


def _preset_spec(preset: str, symbol: str, config: dict[str, Any]) -> dict[str, Any]:
    if preset == "ema_cross":
        fast = int(config.get("fast", 12))
        slow = int(config.get("slow", 50))
        atr_period = int(config.get("atrPeriod", 14))
        return {
            "strategy": {"id": "ema_cross", "name": "EMA cross", "version": "1.0.0"},
            "universe": {"symbols": [symbol]},
            "indicators": [
                {"id": "ema_fast", "type": "ema", "params": {"period": fast}},
                {"id": "ema_slow", "type": "ema", "params": {"period": slow}},
                {"id": "atr", "type": "atr", "params": {"period": atr_period}},
            ],
            "rules": {
                "entry": {"long": {"conditions": [
                    {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}},
                ]}},
                "exit": {
                    "stop_loss": {"type": "atr", "value": float(config.get("atrMult", 2.0))},
                    "take_profit": {"type": "risk_reward", "value": float(config.get("reward", 2.0))},
                },
            },
            "position_sizing": {"type": "percent_equity", "value": float(config.get("sizePct", 90))},
        }
    if preset == "rsi_reversion":
        return {
            "strategy": {"id": "rsi_reversion", "name": "RSI reversion", "version": "1.0.0"},
            "universe": {"symbols": [symbol]},
            "indicators": [
                {"id": "rsi", "type": "rsi", "params": {"period": int(config.get("rsiPeriod", 14))}},
            ],
            "rules": {
                "entry": {"long": {"conditions": [
                    {"left": {"ref": "rsi"}, "op": "<", "right": {"value": float(config.get("oversold", 30))}},
                ]}},
                "exit": {
                    "long": {"conditions": [
                        {"left": {"ref": "rsi"}, "op": ">", "right": {"value": float(config.get("overbought", 55))}},
                    ]},
                    "stop_loss": {"type": "percent", "value": float(config.get("stopPct", 5.0))},
                },
            },
            "position_sizing": {"type": "percent_equity", "value": float(config.get("sizePct", 50))},
        }
    raise ValueError(f"unsupported strategy preset {preset!r}")


def _strategy_source(symbol: str, config: dict[str, Any]) -> dict[str, Any]:
    raw = str(config.get("strategyJson") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"strategyJson is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("strategyJson must be a JSON object")
        source = parsed
        # The input series is authoritative; never backtest a different symbol
        # than the one the graph actually supplied.
        universe = source.setdefault("universe", {})
        if isinstance(universe, dict):
            universe["symbols"] = [symbol]
        return source
    return _preset_spec(str(config.get("preset") or "ema_cross"), symbol, config)


def exec_backtest(context: NodeExecContext) -> dict[str, Any]:
    series = context.inputs.get("series")
    rows = _rows(series)
    payload = series if isinstance(series, dict) else {}
    symbol = str(
        payload.get("symbol") or context.config.get("symbol") or ""
    ).strip().upper()
    if not symbol:
        raise ValueError("the OHLCV series has no symbol and no symbol was configured")
    interval = str(payload.get("interval") or context.config.get("interval") or "1d")

    source = _strategy_source(symbol, context.config)
    try:
        strategy = parse_strategy(source)
    except Exception as exc:  # noqa: BLE001 - schema failures are node data
        raise ValueError(f"invalid strategy: {exc}") from exc

    try:
        bar_series = quant_data.series_from_rows(
            symbol, interval, rows,
            source=str(payload.get("provider") or "graph"),
            asset_type=str(payload.get("assetType") or "equity"),
        )
        dataset = quant_data.build_dataset({symbol: bar_series})
    except Exception as exc:  # noqa: BLE001 - a bad bar is an honest failure
        raise ValueError(f"series could not be adapted: {exc}") from exc

    try:
        max_bars = int(context.config.get("maxBars", 0)) or None
        config = BacktestConfig(
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            random_seed=int(context.config.get("randomSeed", 42)),
            max_bars=max_bars,
        )
        result = run_backtest(strategy, dataset, config, symbols=[symbol])
    except QuantError as exc:
        raise ValueError(f"backtest failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"backtest failed: {type(exc).__name__}: {exc}") from exc

    include_series = bool(context.config.get("includeSeries", False))
    result_payload = result.to_dict(include_series=include_series)
    context.emit(
        f"{symbol} {strategy.name}: {result.metrics.get('trade_count', 0)} trades, "
        f"status {result.status}"
    )
    return {
        "result": result_payload,
        "metrics": result.metrics,
        "trades": result.trades,
    }


def _default_space(preset: str) -> dict[str, Any]:
    if preset == "ema_cross":
        return {
            "indicators.0.params.period": [5, 8, 12],
            "indicators.1.params.period": [20, 30, 50],
        }
    if preset == "rsi_reversion":
        return {
            "indicators.0.params.period": [10, 14, 20],
            "rules.entry.long.conditions.0.right.value": [25, 30, 35],
            "rules.exit.long.conditions.0.right.value": [50, 55, 60],
        }
    return {}


def _param_space(config: dict[str, Any]) -> dict[str, Any]:
    raw = str(config.get("paramSpaceJson") or "").strip()
    if not raw:
        return _default_space(str(config.get("preset") or "ema_cross"))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"paramSpaceJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("paramSpaceJson must be a non-empty JSON object")
    return parsed


def exec_walkforward(context: NodeExecContext) -> dict[str, Any]:
    series = context.inputs.get("series")
    rows = _rows(series)
    payload = series if isinstance(series, dict) else {}
    symbol = str(payload.get("symbol") or context.config.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("the OHLCV series has no symbol and no symbol was configured")
    interval = str(payload.get("interval") or context.config.get("interval") or "1d")

    source = _strategy_source(symbol, context.config)
    try:
        strategy = parse_strategy(source)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid strategy: {exc}") from exc
    try:
        bar_series = quant_data.series_from_rows(
            symbol, interval, rows,
            source=str(payload.get("provider") or "graph"),
            asset_type=str(payload.get("assetType") or "equity"),
        )
        dataset = quant_data.build_dataset({symbol: bar_series})
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"series could not be adapted: {exc}") from exc

    try:
        step = int(context.config.get("stepBars", 0)) or None
        wf_config = WalkForwardConfig(
            train_bars=int(context.config.get("trainBars", 250)),
            test_bars=int(context.config.get("testBars", 60)),
            step_bars=step,
            method=str(context.config.get("method") or "random"),
            objective=str(context.config.get("objective") or "sharpe"),
            param_space=_param_space(context.config),
            max_evaluations=int(context.config.get("maxEvaluations", 40)),
            seed=int(context.config.get("randomSeed", 42)),
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            anchored=bool(context.config.get("anchored", False)),
        )
        result = WalkForwardEngine(strategy, dataset, wf_config).run()
    except (WalkForwardError, QuantError) as exc:
        raise ValueError(f"walk-forward failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"walk-forward failed: {type(exc).__name__}: {exc}") from exc

    result_payload = result.to_dict()
    context.emit(
        f"{symbol} walk-forward: {result.status}, "
        f"{result.observability.get('windows', 0)} window(s)"
    )
    return {
        "result": result_payload,
        "windows": result.payload.get("windows", []),
        "metrics": result.metrics,
    }


def build_quant_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.walkforward", version="1.0.0", label="Walk-forward",
            category="quant",
            inputs=(PortDef(id="series", name="OHLCV", type=PortType.OHLCV),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="windows", name="Windows", type=PortType.ARRAY),
                PortDef(id="metrics", name="Metrics", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("preset", "enum", "ema_cross", enum=("ema_cross", "rsi_reversion")),
                ConfigField("strategyJson", "string", "", max_length=20_000),
                ConfigField("paramSpaceJson", "string", "", max_length=20_000),
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("interval", "string", "1d", max_length=10),
                ConfigField("trainBars", "integer", 250, minimum=20, maximum=5_000),
                ConfigField("testBars", "integer", 60, minimum=5, maximum=2_000),
                ConfigField("stepBars", "integer", 0, minimum=0, maximum=2_000),
                ConfigField("method", "enum", "random", enum=("grid", "random", "evolutionary", "bayesian")),
                ConfigField("objective", "string", "sharpe", max_length=40),
                ConfigField("maxEvaluations", "integer", 40, minimum=1, maximum=2_000),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
                ConfigField("anchored", "boolean", False),
                ConfigField("fast", "integer", 12, minimum=1, maximum=500),
                ConfigField("slow", "integer", 50, minimum=2, maximum=500),
                ConfigField("atrPeriod", "integer", 14, minimum=1, maximum=500),
                ConfigField("atrMult", "number", 2.0, minimum=0.1, maximum=20),
                ConfigField("reward", "number", 2.0, minimum=0.1, maximum=20),
                ConfigField("sizePct", "number", 90.0, minimum=1, maximum=100),
                ConfigField("rsiPeriod", "integer", 14, minimum=2, maximum=500),
                ConfigField("oversold", "number", 30.0, minimum=1, maximum=49),
                ConfigField("overbought", "number", 55.0, minimum=51, maximum=99),
                ConfigField("stopPct", "number", 5.0, minimum=0.1, maximum=100),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_walkforward,
            metadata={
                "docs": (
                    "Rolling train/test validation through harness/quant/walkforward.py. "
                    "Parameters are optimized on the training window only; the report "
                    "separates in-sample, out-of-sample and combined metrics."
                ),
            },
        ),
        NodeDef(
            type="quant.backtest", version="1.0.0", label="Backtest",
            category="quant",
            inputs=(PortDef(id="series", name="OHLCV", type=PortType.OHLCV),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="metrics", name="Metrics", type=PortType.OBJECT),
                PortDef(id="trades", name="Trades", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("preset", "enum", "ema_cross", enum=("ema_cross", "rsi_reversion")),
                ConfigField("strategyJson", "string", "", max_length=20_000),
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("interval", "string", "1d", max_length=10),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
                ConfigField("maxBars", "integer", 0, minimum=0, maximum=MAX_BARS),
                ConfigField("includeSeries", "boolean", False),
                ConfigField("fast", "integer", 12, minimum=1, maximum=500),
                ConfigField("slow", "integer", 50, minimum=2, maximum=500),
                ConfigField("atrPeriod", "integer", 14, minimum=1, maximum=500),
                ConfigField("atrMult", "number", 2.0, minimum=0.1, maximum=20),
                ConfigField("reward", "number", 2.0, minimum=0.1, maximum=20),
                ConfigField("sizePct", "number", 90.0, minimum=1, maximum=100),
                ConfigField("rsiPeriod", "integer", 14, minimum=2, maximum=500),
                ConfigField("oversold", "number", 30.0, minimum=1, maximum=49),
                ConfigField("overbought", "number", 55.0, minimum=51, maximum=99),
                ConfigField("stopPct", "number", 5.0, minimum=0.1, maximum=100),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_backtest,
            metadata={
                "docs": (
                    "Deterministic backtest through harness/quant/engine.py. "
                    "Uses the documented ema_cross/rsi_reversion presets or a full "
                    "StrategySpec JSON; the input series symbol is authoritative."
                ),
            },
        ),
    ]


__all__ = ["build_quant_nodes", "exec_backtest", "exec_walkforward"]
