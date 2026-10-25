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
from ..quant.montecarlo import MonteCarloConfig, MonteCarloEngine, MonteCarloError
from ..quant.optimize import (
    OptimizationConfig,
    OptimizationEngine,
    OptimizationError,
    objective_score,
)
from ..quant.params import ParamSpace
from ..quant.strategy import parse_strategy
from ..quant.validation import ValidationError_, bootstrap_ci, returns_from_equity, split_index
from ..quant.walkforward import WalkForwardConfig, WalkForwardEngine, WalkForwardError
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BARS = 20_000
MAX_SIMULATIONS = 100_000
METRIC_KEYS = ("total_return", "sharpe", "max_drawdown", "trade_count")


def _rows(value: Any, node_type: str = "quant.backtest") -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows = value.get("rows")
    elif isinstance(value, list):
        rows = value
    else:
        rows = None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{node_type} needs an OHLCV series with at least one row")
    if len(rows) > MAX_BARS:
        raise ValueError(f"{node_type} is bounded to {MAX_BARS} bars (got {len(rows)})")
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


def _prepare_quant(context: NodeExecContext, node_type: str):
    """Adapt the graph's OHLCV payload and strategy config once for a node."""
    series = context.inputs.get("series")
    rows = _rows(series, node_type)
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
    return rows, symbol, interval, strategy, dataset


def _json_object(config: dict[str, Any], key: str) -> dict[str, Any]:
    raw = str(config.get(key) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{key} must be a JSON object")
    return parsed


def _objectives(config: dict[str, Any], default: str) -> list[str]:
    raw = str(config.get("objectivesJson") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"objectivesJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed or not all(isinstance(x, str) for x in parsed):
        raise ValueError("objectivesJson must be a non-empty JSON array of objective names")
    return [str(x) for x in parsed]


def _metric_subset(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics.get(key) for key in METRIC_KEYS}


def exec_optimize(context: NodeExecContext) -> dict[str, Any]:
    _, symbol, _, strategy, dataset = _prepare_quant(context, "quant.optimize")
    try:
        space = ParamSpace.from_dict(_param_space(context.config))
        config = OptimizationConfig(
            method=str(context.config.get("method") or "random"),
            objective=str(context.config.get("objective") or "sharpe"),
            objectives=_objectives(context.config, "sharpe"),
            max_evaluations=int(context.config.get("maxEvaluations", 60)),
            seed=int(context.config.get("randomSeed", 42)),
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            leaderboard_size=int(context.config.get("leaderboardSize", 15)),
        )
        result = OptimizationEngine(strategy, dataset, space, config).run()
    except (OptimizationError, QuantError) as exc:
        raise ValueError(f"optimization failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"optimization failed: {type(exc).__name__}: {exc}") from exc

    payload = result.to_dict()
    best = payload.get("best")
    leaderboard = payload.get("leaderboard") or []
    context.emit(
        f"{symbol} optimize: {result.status}, "
        f"{result.observability.get('trials', 0)} trial(s)"
    )
    return {
        "result": payload,
        "best": best,
        "leaderboard": leaderboard,
        "metrics": result.metrics,
    }


def exec_montecarlo(context: NodeExecContext) -> dict[str, Any]:
    _, symbol, _, strategy, dataset = _prepare_quant(context, "quant.montecarlo")
    try:
        config = MonteCarloConfig(
            method=str(context.config.get("method") or "trade_reshuffle"),
            simulations=int(context.config.get("simulations", 1_000)),
            seed=int(context.config.get("randomSeed", 42)),
            ruin_threshold=float(context.config.get("ruinThreshold", 0.5)),
            perturbation_pct=float(context.config.get("perturbationPct", 0.10)),
            perturbation=_json_object(context.config, "perturbationJson"),
            execution_perturbation=_json_object(context.config, "executionPerturbationJson"),
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            regime_mix=str(context.config.get("regimeMix") or "resample"),
            regime_block_length=float(context.config.get("regimeBlockLength", 1.0)),
        )
        result = MonteCarloEngine(strategy, dataset, config).run()
    except (MonteCarloError, QuantError) as exc:
        raise ValueError(f"monte carlo failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"monte carlo failed: {type(exc).__name__}: {exc}") from exc

    payload = result.to_dict()
    context.emit(
        f"{symbol} monte carlo: {config.simulations} simulation(s), "
        f"{result.payload.get('successful', 0)} usable"
    )
    return {
        "result": payload,
        "metrics": result.metrics,
        "summary": {
            "method": config.method,
            "simulations": config.simulations,
            "successful": result.payload.get("successful"),
            "probabilityOfRuin": result.payload.get("probabilityOfRuin"),
            "status": result.status,
        },
    }


def _backtest_rows(context: NodeExecContext, strategy, symbol: str, rows: list[dict[str, Any]], interval: str):
    if not rows:
        raise ValueError("one side of the split has no bars")
    bar_series = quant_data.series_from_rows(symbol, interval, rows, source="graph", asset_type="equity")
    split_dataset = quant_data.build_dataset({symbol: bar_series})
    config = BacktestConfig(
        initial_capital=float(context.config.get("initialCapital", 100_000.0)),
        risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
        random_seed=int(context.config.get("randomSeed", 42)),
    )
    return run_backtest(strategy, split_dataset, config, symbols=[symbol])


def exec_oos(context: NodeExecContext) -> dict[str, Any]:
    """Chronological in-sample / out-of-sample holdout evaluation."""
    rows, symbol, interval, strategy, _dataset = _prepare_quant(context, "quant.oos")
    start_index = int(context.config.get("oosStartIndex", 0))
    fraction = float(context.config.get("oosFraction", 0.3))
    try:
        if start_index > 0:
            split_at, _ = split_index(len(rows), oos_start_index=start_index)
        else:
            split_at, _ = split_index(len(rows), oos_fraction=fraction)
    except ValidationError_ as exc:
        raise ValueError(f"invalid split: {exc}") from exc

    try:
        in_sample = _backtest_rows(context, strategy, symbol, rows[:split_at], interval)
        out_sample = _backtest_rows(context, strategy, symbol, rows[split_at:], interval)
    except QuantError as exc:
        raise ValueError(f"out-of-sample evaluation failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"out-of-sample evaluation failed: {type(exc).__name__}: {exc}") from exc

    objective = str(context.config.get("objective") or "sharpe")
    is_score = objective_score(objective, in_sample.metrics)
    oos_score = objective_score(objective, out_sample.metrics)
    divergence: dict[str, Any] = {"objective": objective, "inSample": is_score, "outOfSample": oos_score}
    warnings: list[dict[str, Any]] = []
    if is_score is not None and oos_score is not None:
        divergence["ratio"] = (oos_score / is_score) if is_score else None
        if is_score > 0 and oos_score < is_score * 0.5:
            warnings.append({
                "code": "IS_OOS_DIVERGENCE",
                "message": (
                    f"out-of-sample {objective} is materially weaker than in-sample "
                    f"({oos_score:.3f} vs {is_score:.3f})"
                ),
                "detail": {"inSample": is_score, "outOfSample": oos_score},
            })

    bootstrap = None
    iterations = int(context.config.get("bootstrapIterations", 1_000))
    if iterations > 0:
        equity = [point["equity"] for point in out_sample.equity_curve if point.get("equity")]
        try:
            bootstrap = bootstrap_ci(
                returns_from_equity(equity),
                method="block",
                statistic="mean",
                iterations=iterations,
                seed=int(context.config.get("randomSeed", 42)),
                confidence=float(context.config.get("confidence", 0.95)),
                interval=interval,
            )
        except ValidationError_ as exc:
            warnings.append({
                "code": "BOOTSTRAP_UNAVAILABLE",
                "message": f"out-of-sample confidence interval unavailable: {exc}",
            })

    in_metrics = _metric_subset(in_sample.metrics)
    out_metrics = _metric_subset(out_sample.metrics)
    payload = {
        "kind": "out_of_sample",
        "status": "OK",
        "symbol": symbol,
        "split": {"index": split_at, "inSampleBars": split_at, "outOfSampleBars": len(rows) - split_at},
        "inSample": in_metrics,
        "outOfSample": out_metrics,
        "divergence": divergence,
        "bootstrap": bootstrap,
        "warnings": warnings + list(in_sample.warnings) + list(out_sample.warnings),
    }
    context.emit(
        f"{symbol} OOS: {objective} {is_score} -> {oos_score} "
        f"({split_at}/{len(rows)} bars)"
    )
    return {
        "result": payload,
        "inSample": in_metrics,
        "outOfSample": out_metrics,
        "divergence": divergence,
    }


_STRATEGY_FIELDS = (
    ConfigField("preset", "enum", "ema_cross", enum=("ema_cross", "rsi_reversion")),
    ConfigField("strategyJson", "string", "", max_length=20_000),
    ConfigField("symbol", "string", "", max_length=40),
    ConfigField("interval", "string", "1d", max_length=10),
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
)


def build_quant_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.optimize", version="1.0.0", label="Optimize parameters",
            category="quant",
            inputs=(PortDef(id="series", name="OHLCV", type=PortType.OHLCV),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="best", name="Best", type=PortType.OBJECT),
                PortDef(id="leaderboard", name="Leaderboard", type=PortType.ARRAY),
                PortDef(id="metrics", name="Metrics", type=PortType.OBJECT),
            ),
            config_fields=_STRATEGY_FIELDS + (
                ConfigField("paramSpaceJson", "string", "", max_length=20_000),
                ConfigField("method", "enum", "random", enum=("grid", "random", "evolutionary", "bayesian")),
                ConfigField("objective", "string", "sharpe", max_length=40),
                ConfigField("objectivesJson", "string", "", max_length=400),
                ConfigField("maxEvaluations", "integer", 60, minimum=1, maximum=2_000),
                ConfigField("leaderboardSize", "integer", 15, minimum=1, maximum=100),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_optimize,
            metadata={
                "docs": (
                    "Parameter search through harness/quant/optimize.py over a "
                    "paramSpaceJson grid. Reports the leaderboard, stability and the "
                    "chosen best trial; nothing is auto-adopted."
                ),
            },
        ),
        NodeDef(
            type="quant.montecarlo", version="1.0.0", label="Monte Carlo",
            category="quant",
            inputs=(PortDef(id="series", name="OHLCV", type=PortType.OHLCV),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="metrics", name="Metrics", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=_STRATEGY_FIELDS + (
                ConfigField("method", "enum", "trade_reshuffle", enum=(
                    "trade_reshuffle", "return_bootstrap", "regime_block_bootstrap",
                    "parameter_perturbation", "execution_perturbation",
                )),
                ConfigField("simulations", "integer", 1_000, minimum=1, maximum=MAX_SIMULATIONS),
                ConfigField("ruinThreshold", "number", 0.5, minimum=0.0, maximum=1.0),
                ConfigField("perturbationPct", "number", 0.10, minimum=0.0, maximum=1.0),
                ConfigField("perturbationJson", "string", "", max_length=10_000),
                ConfigField("executionPerturbationJson", "string", "", max_length=10_000),
                ConfigField("regimeMix", "enum", "resample", enum=("resample", "preserve")),
                ConfigField("regimeBlockLength", "number", 1.0, minimum=0.1, maximum=50.0),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_montecarlo,
            metadata={
                "docs": (
                    "Resampling/perturbation stress test through harness/quant/montecarlo.py. "
                    "Reports return percentiles, loss/ruin probability and drawdowns; "
                    "the base run is deterministic."
                ),
            },
        ),
        NodeDef(
            type="quant.oos", version="1.0.0", label="Out-of-sample evaluation",
            category="quant",
            inputs=(PortDef(id="series", name="OHLCV", type=PortType.OHLCV),),
            outputs=(
                PortDef(id="result", name="Result", type=PortType.OBJECT),
                PortDef(id="inSample", name="In-sample", type=PortType.OBJECT),
                PortDef(id="outOfSample", name="Out-of-sample", type=PortType.OBJECT),
                PortDef(id="divergence", name="Divergence", type=PortType.OBJECT),
            ),
            config_fields=_STRATEGY_FIELDS + (
                ConfigField("oosFraction", "number", 0.3, minimum=0.01, maximum=0.99),
                ConfigField("oosStartIndex", "integer", 0, minimum=0, maximum=MAX_BARS),
                ConfigField("objective", "string", "sharpe", max_length=40),
                ConfigField("bootstrapIterations", "integer", 1_000, minimum=0, maximum=10_000),
                ConfigField("confidence", "number", 0.95, minimum=0.5, maximum=0.999),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_oos,
            metadata={
                "docs": (
                    "Chronological holdout: the tail is never optimized on. Reports "
                    "in-sample vs out-of-sample metrics, their objective divergence and "
                    "a block-bootstrap confidence interval for the OOS mean return."
                ),
            },
        ),
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


__all__ = [
    "build_quant_nodes",
    "exec_backtest",
    "exec_walkforward",
    "exec_optimize",
    "exec_montecarlo",
    "exec_oos",
]
