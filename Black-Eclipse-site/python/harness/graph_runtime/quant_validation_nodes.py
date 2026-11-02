"""Quant validation nodes: does the graph's evidence deserve trust?

The quant research pack (`quant_nodes.py`) produces measurements — a backtest,
an optimizer leaderboard, a Monte-Carlo distribution. These nodes answer the
questions that follow: **is this good, is it comparable, is it on the right
clock, and would it survive being traded?** They are thin adapters over engines
that already exist and are already tested:

  * `quant.grade`            → `harness/quant/verdict.py` (`grade_edge`)
  * `quant.benchmark`        → `harness/quant/benchmark.py` (`benchmark_metrics`)
  * `quant.resample`         → `harness/quant/transform.py` (`resample_rows`)
  * `quant.robustness`       → `harness/quant/robustness.py` (`RobustnessEngine`)
  * `quant.trade_analysis`   → `harness/quant/trade_log.py` (`analyse_trade_log`)
  * `quant.multiple_testing` → `harness/quant/multiple_testing.py`
                                (`deflated_sharpe`, `pbo_cscv`)

No grading rule, benchmark statistic, aggregation rule, robustness check or
overfitting correction is reimplemented here. What the adapters DO own is honesty
about shape:

  * a missing metrics object is a node failure, not a silent zero;
  * a backtest result without `equityCurve` is named as such (the fix —
    `includeSeries` — is in the message), never replaced by a straight line;
  * resampling to a finer interval is refused by the engine, because it would
    have to manufacture prices;
  * a trade with no matching bars is reported `unclassified`, never assigned a
    regime;
  * an overfitting statistic whose inputs are missing is `available: false` with
    the reason, and a node with no computable statistic fails and says why.
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from ..quant.benchmark import benchmark_metrics
from ..quant.costs import CostModelError, simulate_costs
from ..quant.edge_report import EdgeReportError, build_edge_report
from ..quant.errors import QuantError
from ..quant.multiple_testing import deflated_sharpe, pbo_cscv
from ..quant.robustness import RobustnessConfig, RobustnessEngine, RobustnessError
from ..quant.trade_log import analyse_trade_log
from ..quant.transform import TransformError, resample_rows
from ..quant.validation import returns_from_equity
from ..quant.verdict import VerdictConfig, VerdictError, grade_edge
from .finance_nodes import series_rows
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .quant_nodes import STRATEGY_FIELDS, param_space_from_config, prepare_quant
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BARS = 20_000
_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo")
_ASSET_CLASSES = ("equity", "crypto")


# ── Input adapters ──────────────────────────────────────────────────────────


def _object_port(context: NodeExecContext, port: str, label: str) -> Optional[dict[str, Any]]:
    value = context.inputs.get(port)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} expects an object on '{port}'")
    return value


def _equity_curve(result: Optional[dict[str, Any]], label: str) -> Optional[list[dict[str, Any]]]:
    """Find the engine's equity curve, or say why it is missing."""
    if not isinstance(result, dict):
        return None
    curve = result.get("equityCurve")
    if curve is None and isinstance(result.get("result"), dict):
        # A graph may wire a node's whole output object instead of its `result`.
        curve = result["result"].get("equityCurve")
    if curve is None:
        return None
    if not isinstance(curve, list) or not all(isinstance(point, dict) for point in curve):
        raise ValueError(
            f"{label}: 'equityCurve' must be a list of {{ts, equity}} points"
        )
    return [point for point in curve if point.get("equity") is not None]


# ── Executors ───────────────────────────────────────────────────────────────


def exec_grade(context: NodeExecContext) -> dict[str, Any]:
    metrics = context.inputs.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError(
            "quant.grade needs the engine's metrics object; wire "
            "quant.backtest.metrics (or quant.oos.inSample.outOfSample)"
        )

    trades = context.inputs.get("trades")
    if trades is not None and not isinstance(trades, list):
        raise ValueError("quant.grade expects 'trades' to be an array")

    monte_carlo = _object_port(context, "monteCarlo", "quant.grade")
    result = _object_port(context, "result", "quant.grade")
    equity = _equity_curve(result, "quant.grade")

    config = VerdictConfig(
        min_trades=int(context.config.get("minTrades", 30)),
        good_trades=int(context.config.get("goodTrades", 100)),
        high_probability_of_loss=float(context.config.get("highProbabilityOfLoss", 35.0)),
    )
    try:
        verdict = grade_edge(
            metrics=metrics,
            trades=trades,
            equity_curve=equity,
            monte_carlo=monte_carlo,
            config=config,
        )
    except VerdictError as exc:
        raise ValueError(f"verdict failed: {exc}") from exc

    context.emit(
        f"edge verdict {verdict['grade']} ({verdict['score']}/100), "
        f"{verdict['flagCounts']['critical']} critical flag(s)"
    )
    return {
        "verdict": verdict,
        "summary": verdict["summary"],
        "flags": verdict["flags"],
    }


def exec_benchmark(context: NodeExecContext) -> dict[str, Any]:
    result = _object_port(context, "result", "quant.benchmark")
    if result is None:
        raise ValueError("quant.benchmark needs a backtest result object")
    equity = _equity_curve(result, "quant.benchmark")
    if not equity:
        raise ValueError(
            "quant.benchmark needs an equity curve in the result; run the backtest "
            "with includeSeries on, then wire its Result output"
        )

    try:
        rows = series_rows(context.inputs.get("benchmark"))
    except ValueError as exc:
        raise ValueError(f"quant.benchmark needs a benchmark OHLCV series: {exc}") from exc
    if len(rows) > MAX_BARS:
        raise ValueError(f"quant.benchmark is bounded to {MAX_BARS} benchmark bars (got {len(rows)})")

    interval = str(context.config.get("interval") or "1d")
    asset_class = str(context.config.get("assetClass") or "equity")
    if asset_class not in _ASSET_CLASSES:
        raise ValueError(f"assetClass must be one of {', '.join(_ASSET_CLASSES)}")

    payload = benchmark_metrics(
        equity,
        rows,
        interval=interval,
        risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
        asset_class=asset_class,
    )
    if payload.get("available"):
        summary = (
            f"vs benchmark over {payload['observations']} aligned returns: "
            f"alpha {payload['alpha']} / beta {payload['beta']} / "
            f"IR {payload['informationRatio']}"
        )
    else:
        summary = f"not available: {payload.get('reason', 'unknown reason')}"
    context.emit(summary)
    return {"metrics": payload, "summary": summary}


def exec_resample(context: NodeExecContext) -> dict[str, Any]:
    target = str(context.config.get("targetInterval") or "1d")
    if target not in _INTERVALS:
        raise ValueError(f"targetInterval must be one of {', '.join(_INTERVALS)}")

    payload = context.inputs.get("series")
    try:
        rows = series_rows(payload)
    except ValueError as exc:
        raise ValueError(f"quant.resample needs an OHLCV series: {exc}") from exc
    if len(rows) > MAX_BARS:
        raise ValueError(f"quant.resample is bounded to {MAX_BARS} bars (got {len(rows)})")

    source = str(context.config.get("sourceInterval") or "").strip().lower()
    if not source and isinstance(payload, dict):
        source = str(payload.get("interval") or "").strip().lower()

    try:
        output = resample_rows(rows, target, source_interval=source or None)
    except TransformError as exc:
        raise ValueError(str(exc)) from exc

    metadata = output["metadata"]
    series: dict[str, Any] = {
        "interval": metadata["targetInterval"],
        "sourceInterval": metadata.get("sourceInterval"),
        "rows": output["rows"],
    }
    if isinstance(payload, dict):
        for key in ("symbol", "provider", "retrievedAt", "adjusted", "assetType"):
            if payload.get(key) is not None:
                series[key] = payload[key]

    context.emit(
        f"resampled {metadata['inputBars']} -> {metadata['outputBars']} bars at "
        f"{metadata['targetInterval']} ({metadata['partialBuckets']} partial)"
    )
    return {"series": series, "metadata": metadata}


def exec_robustness(context: NodeExecContext) -> dict[str, Any]:
    _, symbol, _, strategy, dataset = prepare_quant(context, "quant.robustness")
    try:
        config = RobustnessConfig(
            param_ranges=param_space_from_config(context.config),
            objective=str(context.config.get("objective") or "sharpe"),
            cost_multipliers=_cost_multipliers(context.config),
            cost_material_drop=float(context.config.get("costMaterialDrop", 0.5)),
            concentration_top_n=int(context.config.get("concentrationTopN", 5)),
            concentration_threshold=float(context.config.get("concentrationThreshold", 0.8)),
            min_trades=int(context.config.get("minTrades", 30)),
            splits=int(context.config.get("splits", 2)),
            initial_capital=float(context.config.get("initialCapital", 100_000.0)),
            risk_free_rate=float(context.config.get("riskFreeRate", 0.0)),
            seed=int(context.config.get("randomSeed", 42)),
        )
        result = RobustnessEngine(strategy, dataset, config).run()
    except (RobustnessError, QuantError) as exc:
        raise ValueError(f"robustness failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - a bad bar is an honest failure
        raise ValueError(f"robustness failed: {type(exc).__name__}: {exc}") from exc

    verdict = str(result.payload.get("verdict") or "unknown")
    conclusions = list(result.payload.get("conclusions") or [])
    context.emit(f"{symbol} robustness: {verdict} ({len(conclusions)} conclusion(s))")
    return {
        "result": result.to_dict(),
        "metrics": result.metrics,
        "conclusions": conclusions,
    }


def _cost_multipliers(config: dict[str, Any]) -> list[float]:
    raw = str(config.get("costMultipliersJson") or "").strip()
    if not raw:
        return [1.0, 2.0, 5.0]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"costMultipliersJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("costMultipliersJson must be a non-empty JSON array of numbers")
    if len(parsed) > 8:
        raise ValueError("costMultipliersJson is bounded to 8 multipliers")
    multipliers: list[float] = []
    for value in parsed:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("costMultipliersJson must contain numbers only")
        if not (0 < float(value) <= 100):
            raise ValueError("every cost multiplier must be greater than 0 and at most 100")
        multipliers.append(float(value))
    return multipliers


def exec_trade_analysis(context: NodeExecContext) -> dict[str, Any]:
    trades = context.inputs.get("trades")
    if not isinstance(trades, list) or not trades:
        raise ValueError(
            "quant.trade_analysis needs a non-empty trades array; wire "
            "quant.backtest.trades"
        )
    if not all(isinstance(trade, dict) for trade in trades):
        raise ValueError("every trade must be an object")

    series_by_symbol: dict[str, list[dict[str, Any]]] = {}
    series = context.inputs.get("series")
    if series is not None:
        try:
            rows = series_rows(series)
        except ValueError as exc:
            raise ValueError(f"quant.trade_analysis needs an OHLCV series: {exc}") from exc
        if len(rows) > MAX_BARS:
            raise ValueError(f"quant.trade_analysis is bounded to {MAX_BARS} bars (got {len(rows)})")
        symbol = str(
            (series.get("symbol") if isinstance(series, dict) else "")
            or context.config.get("symbol")
            or ""
        ).strip().upper()
        if not symbol:
            raise ValueError(
                "the series has no symbol; set the node's symbol so trades can be "
                "matched to their own bars"
            )
        series_by_symbol[symbol] = rows

    try:
        analysis = analyse_trade_log(
            trades,
            series_by_symbol,
            max_entries=int(context.config.get("maxEntries", 400)),
        )
    except Exception as exc:  # noqa: BLE001 - a malformed trade is node data
        raise ValueError(f"trade analysis failed: {type(exc).__name__}: {exc}") from exc

    payload = analysis.to_dict()
    totals = payload.get("totals") or {}
    coverage = payload.get("coverage") or {}
    summary = (
        f"{payload.get('entryCount', 0)} analysed entries, "
        f"net P&L {totals.get('netPnl')}, "
        f"{coverage.get('regimeCount', 0)} regime(s) seen"
    )
    context.emit(summary)
    return {"analysis": payload, "summary": summary}


def exec_multiple_testing(context: NodeExecContext) -> dict[str, Any]:
    periods = int(context.config.get("periodsPerYear", 252))
    if periods < 1:
        raise ValueError("periodsPerYear must be >= 1")

    result = _object_port(context, "result", "quant.multiple_testing")
    equity = _equity_curve(result, "quant.multiple_testing")
    returns: list[float] = []
    if equity:
        levels = [float(point["equity"]) for point in equity]
        returns = [float(value) for value in returns_from_equity(levels)]

    annualized, source = _annualized_trial_sharpes(context)
    deflated: dict[str, Any]
    if not returns:
        deflated = {
            "available": False,
            "reason": "deflation needs the selected strategy's return series; run the "
                      "backtest with includeSeries on and wire its Result output",
        }
    elif len(annualized) < 2:
        deflated = {
            "available": False,
            "reason": "deflation needs the trial Sharpe variance: wire the optimize "
                      "leaderboard/trials array or set trialSharpesJson",
        }
    else:
        per_period = [value / math.sqrt(periods) for value in annualized]
        try:
            deflated = deflated_sharpe(returns, trial_sharpes=per_period)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"deflated Sharpe failed: {type(exc).__name__}: {exc}") from exc
        deflated["source"] = source
        deflated["annualization"] = periods

    try:
        matrix = _returns_matrix(context.config)
    except ValueError as exc:
        raise ValueError(f"quant.multiple_testing: {exc}") from exc
    if not matrix:
        pbo: dict[str, Any] = {
            "available": False,
            "reason": "PBO needs a returns matrix: set returnsMatrixJson to one return "
                      "series per configuration",
        }
    else:
        try:
            pbo = pbo_cscv(matrix, n_splits=int(context.config.get("nSplits", 16)))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"PBO failed: {type(exc).__name__}: {exc}") from exc

    if not deflated.get("available") and not pbo.get("available"):
        raise ValueError(
            "no overfitting statistic could be computed: "
            f"{deflated.get('reason')} / {pbo.get('reason')}"
        )

    parts: list[str] = []
    if deflated.get("available"):
        parts.append(
            f"deflated Sharpe {deflated['deflatedSharpeRatio']:.3f} "
            f"across {deflated['trialCount']} trials"
        )
    if pbo.get("available"):
        parts.append(
            f"PBO {pbo['probabilityOfBacktestOverfitting'] * 100:.1f}% "
            f"over {pbo['combinations']} partitions"
        )
    summary = "; ".join(parts)
    context.emit(summary)
    return {"deflated": deflated, "pbo": pbo, "summary": summary}


def _annualized_trial_sharpes(
    context: NodeExecContext,
) -> tuple[list[float], str]:
    """Trial Sharpes from the wired trials array, else from the JSON fallback."""
    trials = context.inputs.get("trials")
    if trials is not None:
        if not isinstance(trials, list):
            raise ValueError("quant.multiple_testing expects 'trials' to be an array")
        values: list[float] = []
        for row in trials:
            if not isinstance(row, dict):
                continue
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            for candidate in (metrics.get("sharpe"), row.get("sharpe"), row.get("score")):
                if candidate is None:
                    continue
                try:
                    values.append(float(candidate))
                except (TypeError, ValueError):
                    continue
                break
        if len(values) >= 2:
            return values, "trials"

    raw = str(context.config.get("trialSharpesJson") or "").strip()
    if not raw:
        return [], ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"trialSharpesJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in parsed
    ):
        raise ValueError("trialSharpesJson must be a JSON array of numbers")
    return [float(value) for value in parsed], "trialSharpesJson"


def _returns_matrix(config: dict[str, Any]) -> list[list[float]]:
    raw = str(config.get("returnsMatrixJson") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"returnsMatrixJson is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("returnsMatrixJson must be a JSON array of return series")
    matrix: list[list[float]] = []
    for row in parsed:
        if not isinstance(row, list) or not row:
            raise ValueError("every returnsMatrixJson row must be a non-empty array")
        series: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("returnsMatrixJson may contain numbers only")
            series.append(float(value))
        matrix.append(series)
    if len(matrix) > 200:
        raise ValueError("returnsMatrixJson is bounded to 200 configurations")
    return matrix


def exec_costs(context: NodeExecContext) -> dict[str, Any]:
    orders = context.inputs.get("orders")
    if not isinstance(orders, list) or not orders:
        raise ValueError(
            "quant.costs needs a non-empty orders array "
            "([{side, quantity, price, symbol?}])"
        )
    if len(orders) > 5_000:
        raise ValueError(f"quant.costs is bounded to 5,000 orders (got {len(orders)})")
    kind = str(context.config.get("kind") or "transaction")

    raw = str(context.config.get("executionJson") or "").strip()
    execution: Optional[dict[str, Any]] = None
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"executionJson is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("executionJson must be a JSON object (the execution block)")
        execution = parsed

    try:
        payload = simulate_costs(
            kind, orders, execution,
            seed=int(context.config.get("randomSeed", 42)),
        )
    except CostModelError as exc:
        raise ValueError(f"cost simulation failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cost simulation failed: {type(exc).__name__}: {exc}") from exc

    summary = (
        f"{kind}: {payload['orderCount']} order(s), total {payload['total']}"
        + (" (frictionless model)" if payload.get("frictionless") else "")
    )
    context.emit(summary)
    return {"costs": payload, "total": payload["total"], "summary": summary}


def exec_edge_report(context: NodeExecContext) -> dict[str, Any]:
    artifact = _object_port(context, "result", "quant.edge_report")
    if artifact is None:
        raise ValueError(
            "quant.edge_report needs a backtest result object; run the backtest with "
            "includeSeries on and wire its Result output"
        )
    monte_carlo = _object_port(context, "monteCarlo", "quant.edge_report")
    try:
        report = build_edge_report(artifact, monte_carlo)
    except EdgeReportError as exc:
        raise ValueError(f"edge report failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"edge report failed: {type(exc).__name__}: {exc}") from exc

    context.emit(
        f"edge report: grade {report.verdict.get('grade')} "
        f"({len(report.charts)} chart(s), {len(report.markdown)} chars)"
    )
    return {
        "report": report.markdown,
        "charts": report.charts,
        "verdict": report.verdict,
    }


# ── Definitions ─────────────────────────────────────────────────────────────

def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_quant_validation_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.grade",
            version="1.0.0",
            label="Edge verdict",
            category="quant",
            inputs=(
                _port("metrics", "Metrics", PortType.OBJECT),
                _port("trades", "Trades", PortType.ARRAY, optional=True),
                _port("monteCarlo", "Monte Carlo", PortType.OBJECT, optional=True),
                _port("result", "Result", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("verdict", "Verdict", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
                _port("flags", "Flags", PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("minTrades", "integer", 30, minimum=1, maximum=10_000),
                ConfigField("goodTrades", "integer", 100, minimum=1, maximum=100_000),
                ConfigField("highProbabilityOfLoss", "number", 35.0, minimum=0, maximum=100),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_grade,
            metadata={
                "docs": (
                    "Grades the evidence behind a strategy's edge through "
                    "harness/quant/verdict.py: an A-F grade from edge, robustness, risk "
                    "and sample components. An axis that could not be judged has its "
                    "weight redistributed and is named in the flags - never scored as "
                    "zero or as perfect."
                ),
            },
        ),
        NodeDef(
            type="quant.benchmark",
            version="1.0.0",
            label="Benchmark comparison",
            category="quant",
            inputs=(
                _port("result", "Backtest result", PortType.OBJECT),
                _port("benchmark", "Benchmark OHLCV", PortType.OHLCV),
            ),
            outputs=(
                _port("metrics", "Metrics", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField("interval", "enum", "1d", enum=_INTERVALS),
                ConfigField("assetClass", "enum", "equity", enum=_ASSET_CLASSES),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_benchmark,
            metadata={
                "docs": (
                    "Alpha, beta, correlation, tracking error and information ratio "
                    "against a benchmark price series, aligned on timestamps through "
                    "harness/quant/benchmark.py. Fewer than three aligned returns is "
                    "reported as unavailable with the reason, never as zero."
                ),
            },
        ),
        NodeDef(
            type="quant.resample",
            version="1.0.0",
            label="Resample OHLCV",
            category="quant",
            inputs=(_port("series", "OHLCV", PortType.OHLCV),),
            outputs=(
                _port("series", "OHLCV", PortType.OHLCV),
                _port("metadata", "Metadata", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField(
                    "targetInterval", "enum", "1d", enum=_INTERVALS,
                ),
                ConfigField("sourceInterval", "string", "", max_length=10),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_resample,
            metadata={
                "docs": (
                    "Aggregates OHLCV rows into a wider interval "
                    "(harness/quant/transform.py): open=first, high=max, low=min, "
                    "close=last, volume=sum, UTC buckets. A bucket with too few "
                    "members is marked partial; a finer target is refused because it "
                    "would have to manufacture prices."
                ),
            },
        ),
        NodeDef(
            type="quant.robustness",
            version="1.0.0",
            label="Robustness",
            category="quant",
            inputs=(_port("series", "OHLCV", PortType.OHLCV),),
            outputs=(
                _port("result", "Result", PortType.OBJECT),
                _port("metrics", "Metrics", PortType.OBJECT),
                _port("conclusions", "Conclusions", PortType.ARRAY),
            ),
            config_fields=STRATEGY_FIELDS + (
                ConfigField("paramSpaceJson", "string", "", max_length=20_000),
                ConfigField("objective", "string", "sharpe", max_length=40),
                ConfigField("costMultipliersJson", "string", "", max_length=200),
                ConfigField("costMaterialDrop", "number", 0.5, minimum=0, maximum=1),
                ConfigField("concentrationTopN", "integer", 5, minimum=1, maximum=100),
                ConfigField("concentrationThreshold", "number", 0.8, minimum=0, maximum=1),
                ConfigField("minTrades", "integer", 30, minimum=1, maximum=10_000),
                ConfigField("splits", "integer", 2, minimum=1, maximum=20),
                ConfigField("initialCapital", "number", 100_000.0, minimum=1_000, maximum=1_000_000_000),
                ConfigField("riskFreeRate", "number", 0.0, minimum=-0.5, maximum=0.5),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=900_000,
            executor=exec_robustness,
            metadata={
                "docs": (
                    "Sensitivity + robustness through harness/quant/robustness.py: a "
                    "parameter sweep, a cost-multiplier curve, trade concentration and "
                    "per-regime splits produce a deterministic verdict "
                    "(robust / fragile / insufficient_evidence) and plain-language "
                    "conclusions derived from the measured evidence."
                ),
            },
        ),
        NodeDef(
            type="quant.trade_analysis",
            version="1.0.0",
            label="Trade analysis",
            category="quant",
            inputs=(
                _port("trades", "Trades", PortType.ARRAY),
                _port("series", "OHLCV", PortType.OHLCV, optional=True),
            ),
            outputs=(
                _port("analysis", "Analysis", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField("maxEntries", "integer", 400, minimum=1, maximum=5_000),
                ConfigField("symbol", "string", "", max_length=40),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_trade_analysis,
            metadata={
                "docs": (
                    "Reads a trade log against the conditions it traded in "
                    "(harness/quant/trade_log.py): regime, trend and volatility at each "
                    "entry, per-regime P&L, concentration and coverage. A trade whose "
                    "symbol has no bars is counted in the totals and reported as "
                    "unclassified, never given a regime it was not measured in."
                ),
            },
        ),
        NodeDef(
            type="quant.multiple_testing",
            version="1.0.0",
            label="Overfitting check",
            category="quant",
            inputs=(
                _port("result", "Backtest result", PortType.OBJECT, optional=True),
                _port("trials", "Trials", PortType.ARRAY, optional=True),
            ),
            outputs=(
                _port("deflated", "Deflated Sharpe", PortType.OBJECT),
                _port("pbo", "PBO", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField("periodsPerYear", "integer", 252, minimum=1, maximum=1_000),
                ConfigField("nSplits", "integer", 16, minimum=2, maximum=64),
                ConfigField("trialSharpesJson", "string", "", max_length=20_000),
                ConfigField("returnsMatrixJson", "string", "", max_length=200_000),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_multiple_testing,
            metadata={
                "docs": (
                    "Deflated Sharpe (Bailey & Lopez de Prado 2014) over the selected "
                    "return series and the trial Sharpes, plus Probability of Backtest "
                    "Overfitting (CSCV) over a supplied returns matrix - both from "
                    "harness/quant/multiple_testing.py. Missing inputs are an explicit "
                    "unavailable with a reason, never a fabricated statistic."
                ),
            },
        ),
        NodeDef(
            type="quant.costs",
            version="1.0.0",
            label="Transaction costs",
            category="quant",
            inputs=(_port("orders", "Orders", PortType.ARRAY),),
            outputs=(
                _port("costs", "Costs", PortType.OBJECT),
                _port("total", "Total", PortType.NUMBER),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField(
                    "kind", "enum", "transaction",
                    enum=("transaction", "slippage", "spread", "impact"),
                ),
                ConfigField("executionJson", "string", "", max_length=20_000),
                ConfigField("randomSeed", "integer", 42, minimum=0, maximum=2_147_483_647),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_costs,
            metadata={
                "docs": (
                    "One cost family (transaction / slippage / spread / impact) over "
                    "an order list through harness/quant/costs.py: per-order values, "
                    "the total and the exact model used. A model missing its input "
                    "(volume for impact, a bar spread for historical spread) is "
                    "reported as a warning and contributes zero - never guessed."
                ),
            },
        ),
        NodeDef(
            type="quant.edge_report",
            version="1.0.0",
            label="Edge report",
            category="quant",
            inputs=(
                _port("result", "Backtest result", PortType.OBJECT),
                _port("monteCarlo", "Monte Carlo", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("report", "Report (Markdown)", PortType.STRING),
                _port("charts", "Charts", PortType.ARRAY),
                _port("verdict", "Verdict", PortType.OBJECT),
            ),
            config_fields=(),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_edge_report,
            metadata={
                "docs": (
                    "Builds the Edge Report through harness/quant/edge_report.py: the "
                    "grade, a Markdown document and bounded chart specs from the same "
                    "artifact. A report without a Monte Carlo or an equity curve says "
                    "which figures are absent instead of drawing empty ones."
                ),
            },
        ),
    ]


__all__ = [
    "build_quant_validation_nodes",
    "exec_grade",
    "exec_benchmark",
    "exec_resample",
    "exec_robustness",
    "exec_trade_analysis",
    "exec_multiple_testing",
    "exec_costs",
    "exec_edge_report",
]
