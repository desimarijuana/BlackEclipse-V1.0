"""Factor → strategy promotion (Phase 10).

Turns a validated factor version into a first-class Eclipse strategy WITHOUT
duplicating the strategy engine:

  * the strategy is persisted through the ONE `QuantStore` (immutable versions +
    the existing approval/deployment governance),
  * its execution is delegated to the Factor Lab's cross-sectional quantile
    engine (the honest executor for a factor portfolio — the event-driven
    backtest engine is per-instrument and cannot express cross-sectional sorts),
  * the portfolio run is persisted through `QuantStore.save_experiment` so it
    appears alongside native backtests and is comparable in `/quant/experiments`,
  * full lineage (factor version → strategy → experiment) is recorded in the
    Factor store.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..quant.research import ResearchResult, warn
from ..quant.strategy import parse_strategy, validate_strategy
from ..stats.base import StatsError
from . import engine as E
from . import service as S
from .store import FactorStore


def build_strategy_spec(
    factor: dict[str, Any], ver: dict[str, Any], config: dict[str, Any], symbols: list[str]
):
    """Build a `StrategySpec` whose metadata records the factor lineage.

    The cross-sectional factor portfolio is executed by the Factor Lab engine
    (`metadata.execution = "factor_portfolio"`); the spec carries the exact
    factor version so the strategy is reproducible and traceable.
    """
    strategy_id = f"strategy_factor_{factor['id'].replace('fac_', '')}_{ver['version'].replace('.', '_')}"
    spec_dict = {
        "id": strategy_id,
        "name": str(config.get("name") or f"{factor['name']} ({ver['version']})"),
        "description": f"Factor strategy promoted from {factor['name']}@{ver['version']}",
        "version": "1.0.0",
        "assetClass": "equity",
        "universe": {"symbols": [s.strip().upper() for s in symbols if s and s.strip()]},
        "timeframes": {"primary": str(config.get("interval") or "1d")},
        "metadata": {
            "execution": "factor_portfolio",
            "source": "factor_lab",
            "factorId": factor["id"],
            "factorVersion": ver["version"],
            "expression": ver["expression"],
            "inputs": ver["inputs"],
            "direction": factor.get("direction"),
            "normalization": ver["normalization"],
            "portfolio": {
                "quantiles": int(config.get("quantiles") or 5),
                "weighting": str(config.get("weighting") or "equal"),
                "longShort": bool(config.get("longShort", True)),
                "rebalance": int(config.get("rebalance") or 21),
                "costBps": float(config.get("costBps") or 0.0),
            },
        },
    }
    return parse_strategy(spec_dict), strategy_id


def _portfolio_result_to_experiment(
    *, portfolio: dict[str, Any], factor: dict[str, Any], ver: dict[str, Any],
    symbols: list[str], config: dict[str, Any], duration_ms: int,
) -> ResearchResult:
    ls = portfolio.get("longShortMetrics") or {}
    gross = portfolio.get("grossLongShortMetrics") or {}
    metrics = {
        "netTotalReturn": ls.get("totalReturn"),
        "grossTotalReturn": gross.get("totalReturn"),
        "netAnnualizedReturn": ls.get("annualizedReturn"),
        "netSharpe": ls.get("sharpe"),
        "maxDrawdown": ls.get("maxDrawdown"),
        "hitRate": ls.get("hitRate"),
        "averageTurnover": (portfolio.get("turnover") or {}).get("average"),
        "totalCost": (portfolio.get("cost") or {}).get("totalCost"),
    }
    warnings = [warn("FACTOR_PORTFOLIO",
                     "Execution is the Factor Lab cross-sectional quantile engine, not the "
                     "event-driven backtest engine (which is per-instrument)."),
                ]
    for w in portfolio.get("warnings", [])[:8]:
        warnings.append(warn("FACTOR_DATA", str(w)))
    return ResearchResult(
        kind="factor_portfolio",
        status="OK",
        metadata={
            "symbols": symbols, "interval": str(config.get("interval") or "1d"),
            "engineVersion": E.FACTOR_ENGINE_VERSION, "factorId": factor["id"],
            "factorVersion": ver["version"],
        },
        configuration={
            "factorId": factor["id"], "factorVersion": ver["version"],
            "expression": ver["expression"], "quantiles": portfolio.get("quantiles"),
            "weighting": portfolio.get("weighting"), "rebalance": portfolio.get("rebalance"),
            "costBps": portfolio.get("costBps"), "longShort": portfolio.get("longShort"),
            "periodsPerYear": portfolio.get("periodsPerYear"),
        },
        metrics=metrics,
        warnings=warnings,
        observability={"durationMs": duration_ms},
        capability={"execution": "factor_portfolio"},
        payload={"portfolio": portfolio},
    )


def promote_to_strategy(
    *, factor_id: str, version: Optional[str], config: dict[str, Any], symbols: list[str],
    series_by_symbol: dict[str, dict[str, list[float]]], quant_store: Any,
    actor: Optional[str] = None, request_approval: bool = True,
) -> dict[str, Any]:
    """Persist a factor strategy + its portfolio run through the ONE quant store."""
    store: FactorStore = S.get_factor_store()  # type: ignore[assignment]
    if store is None:
        raise StatsError("UNAVAILABLE", "the factor store is unavailable", 503)
    if quant_store is None:
        raise StatsError("DEPENDENCY_MISSING", "the quant store is unavailable in this runtime", 503)

    factor = store.get_factor(factor_id)
    if factor is None:
        raise StatsError("NOT_FOUND", f"factor {factor_id} not found", 404)
    target_version = version or factor["latestVersion"]
    ver = store.get_version(factor_id, target_version)
    if ver is None:
        raise StatsError("NOT_FOUND", f"factor version {target_version} not found", 404)
    if factor["validationStatus"] != "valid":
        raise StatsError("NOT_VALIDATED", "factor must pass validation before promotion", 409)
    if not symbols:
        raise StatsError("INVALID_INPUT", "symbols are required", 422)

    spec, strategy_id = build_strategy_spec(factor, ver, config, symbols)
    issues = validate_strategy(spec)
    issue_dicts = [{"code": i.code, "message": i.message, "path": i.path,
                    "severity": getattr(i, "severity", "error")} for i in issues]
    hard_errors = [i for i in issue_dicts if i["severity"] == "error"
                   and i["code"] != "NO_ENTRY_RULES"]

    started = time.perf_counter()
    if hard_errors:
        raise StatsError("INVALID_STRATEGY",
                         f"strategy spec has {len(hard_errors)} error(s); first: "
                         f"{hard_errors[0]['message']}", 422)

    # Persist the strategy version (immutable) through the ONE quant store.
    quant_store.save_strategy(spec)
    strategy = quant_store.get_strategy(strategy_id, spec.version)

    # Execute the cross-sectional factor portfolio and persist it as an experiment.
    portfolio = S.quantile_portfolio(
        ver["expression"], series_by_symbol, symbols,
        quantiles=int(config.get("quantiles") or 5), weighting=str(config.get("weighting") or "equal"),
        long_short=bool(config.get("longShort", True)), rebalance=int(config.get("rebalance") or 21),
        cost_bps=float(config.get("costBps") or 0.0), min_obs=int(config.get("minObs") or 5),
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    result = _portfolio_result_to_experiment(portfolio=portfolio, factor=factor, ver=ver,
                                             symbols=symbols, config=config, duration_ms=duration_ms)
    experiment_id = quant_store.save_experiment(
        result, strategy_id=strategy_id, strategy_version=spec.version, kind="factor_portfolio")

    # Lineage: factorVersion -> strategy -> experiment.
    store.add_lineage(child_type="strategy", child_id=strategy_id, parent_type="factorVersion",
                      parent_id=f"{factor_id}@{target_version}", relation="promoted_from")
    store.add_lineage(child_type="experiment", child_id=experiment_id, parent_type="strategyVersion",
                      parent_id=f"{strategy_id}@{spec.version}", relation="executed_for")

    approval = None
    if request_approval:
        approval = quant_store.request_approval(strategy_id, spec.version, actor=actor,
                                                note="promoted from Factor Lab")

    return {
        "strategyId": strategy_id,
        "strategyVersion": spec.version,
        "experimentId": experiment_id,
        "execution": "factor_portfolio",
        "metrics": result.metrics,
        "validationIssues": issue_dicts,
        "approval": approval,
        "lineage": {
            "factorVersion": f"{factor_id}@{target_version}",
            "strategy": f"{strategy_id}@{spec.version}",
            "experiment": experiment_id,
        },
        "note": "Execution is delegated to the Factor Lab quantile engine; the strategy and "
                "its experiment are stored through the ONE quant store and share the native "
                "approval workflow.",
    }


__all__ = ["build_strategy_spec", "promote_to_strategy"]
