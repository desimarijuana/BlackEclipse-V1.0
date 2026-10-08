"""Sensitivity and robustness analysis, with explicit overfitting safeguards.

`SensitivityEngine` sweeps one parameter at a time and reports, per parameter,
the objective curve, the best value, whether the objective collapses away from
the optimum, and whether it is stable (flat) across the range.

`RobustnessEngine` combines that with cost sensitivity, trade concentration,
sample size and regime dependence to produce a **deterministic verdict**
(`robust` / `fragile` / `insufficient_evidence`) and plain-language conclusions
derived from measured evidence — never hallucinated. A strategy is never called
robust without passing every check.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .data import MarketDataset
from .engine import ENGINE_VERSION, BacktestConfig, run_backtest
from .optimize import objective_score
from .params import ParamSpace, apply_params
from .research import ResearchResult, warn
from .strategy import StrategySpec


class RobustnessError(ValueError):
    pass


def _run(strategy: StrategySpec, dataset: MarketDataset, cfg: BacktestConfig, symbols=None):
    return run_backtest(strategy, dataset, cfg, symbols=symbols)


def _cost_multiplied(strategy_dict: dict[str, Any], multiplier: float) -> dict[str, Any]:
    spec = dict(strategy_dict)
    exec_cfg = dict(spec.get("execution") or {})
    for key in ("commission", "slippage"):
        block = exec_cfg.get(key)
        if isinstance(block, dict) and isinstance(block.get("value"), (int, float)):
            block = dict(block)
            block["value"] = float(block["value"]) * multiplier
            exec_cfg[key] = block
    spec["execution"] = exec_cfg
    return spec


# ── Sensitivity ──────────────────────────────────────────────────────────────

@dataclass
class SensitivityConfig:
    param_ranges: dict[str, Any] = field(default_factory=dict)
    objective: str = "sharpe"
    initial_capital: float = 100_000.0
    risk_free_rate: float = 0.0
    seed: int = 42
    collapse_threshold: float = 0.30     # fraction drop from best = collapse


class SensitivityEngine:
    def __init__(self, strategy: StrategySpec, dataset: MarketDataset,
                 config: Optional[SensitivityConfig] = None) -> None:
        self.strategy = strategy
        self.dataset = dataset
        self.config = config or SensitivityConfig()
        self.space = ParamSpace.from_dict(self.config.param_ranges)
        if self.space.is_empty():
            raise RobustnessError("sensitivity analysis needs at least one parameter range")
        self._base = strategy.to_dict()

    def _score_for(self, path: str, value: Any) -> Optional[float]:
        spec = StrategySpec.model_validate(apply_params(self._base, {path: value}))
        res = run_backtest(spec, self.dataset, BacktestConfig(
            initial_capital=self.config.initial_capital,
            risk_free_rate=self.config.risk_free_rate, random_seed=self.config.seed))
        return objective_score(self.config.objective, res.metrics)

    def _sweep(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for path, values in self.space.axes.items():
            scores = [self._score_for(path, v) for v in values]
            defined = [s for s in scores if s is not None]
            best = max(defined) if defined else None
            worst = min(defined) if defined else None
            # collapse: does any value fall below best by more than threshold?
            collapse = False
            if best is not None and best != 0:
                floor = best - abs(best) * self.config.collapse_threshold
                collapse = any(s is not None and s < floor for s in scores)
            near_best = 0
            if best is not None:
                tol = abs(best) * 0.10 + 1e-9
                near_best = sum(1 for s in scores if s is not None and best - s <= tol)
            out[path] = {
                "values": values, "scores": scores, "best": best, "worst": worst,
                "collapse": collapse, "nearBest": near_best,
                "stable": near_best >= max(2, len(values) // 2),
            }
        return out

    def run(self) -> ResearchResult:
        started = time.monotonic()
        sweeps = self._sweep()
        warnings: list[dict[str, Any]] = []
        unstable = [p for p, s in sweeps.items() if s["collapse"]]
        if unstable:
            warnings.append(warn("PERFORMANCE_COLLAPSE",
                                 f"objective collapses for: {', '.join(unstable)}",
                                 {"parameters": unstable}))
        payload = {"objective": self.config.objective, "parameters": sweeps}
        return ResearchResult(
            kind="sensitivity", status="OK",
            metadata={"engineVersion": ENGINE_VERSION, "strategyId": self.strategy.id,
                      "symbols": self.strategy.universe.symbols,
                      "interval": self.dataset.primary_interval()},
            configuration={"objective": self.config.objective,
                           "paramRanges": self.config.param_ranges,
                           "initialCapital": self.config.initial_capital},
            metrics={}, warnings=warnings,
            observability={"parameters": len(sweeps),
                           "durationMs": int((time.monotonic() - started) * 1000)},
            capability={"robustness": "available"}, payload=payload,
        )


# ── Robustness ───────────────────────────────────────────────────────────────

@dataclass
class RobustnessConfig:
    param_ranges: dict[str, Any] = field(default_factory=dict)
    objective: str = "sharpe"
    cost_multipliers: list[float] = field(default_factory=lambda: [1.0, 2.0, 5.0])
    cost_material_drop: float = 0.50     # objective drop that counts as material
    concentration_top_n: int = 5
    concentration_threshold: float = 0.80
    min_trades: int = 30
    splits: int = 2
    initial_capital: float = 100_000.0
    risk_free_rate: float = 0.0
    seed: int = 42


class RobustnessEngine:
    def __init__(self, strategy: StrategySpec, dataset: MarketDataset,
                 config: Optional[RobustnessConfig] = None,
                 *, progress: Optional[Any] = None) -> None:
        self.strategy = strategy
        self.dataset = dataset
        self.config = config or RobustnessConfig()
        self._progress = progress

    def _report(self, done: int, total: int) -> None:
        if self._progress is None:
            return
        try:
            self._progress("stage", done, total)
        except Exception:  # noqa: BLE001
            pass

    def _base(self):
        return _run(self.strategy, self.dataset, BacktestConfig(
            initial_capital=self.config.initial_capital,
            risk_free_rate=self.config.risk_free_rate, random_seed=self.config.seed))

    def _cost_sensitivity(self) -> list[dict[str, Any]]:
        base_dict = self.strategy.to_dict()
        out: list[dict[str, Any]] = []
        for mult in self.config.cost_multipliers:
            spec = StrategySpec.model_validate(_cost_multiplied(base_dict, mult))
            res = _run(spec, self.dataset, BacktestConfig(
                initial_capital=self.config.initial_capital,
                risk_free_rate=self.config.risk_free_rate, random_seed=self.config.seed))
            out.append({
                "multiplier": mult,
                "objective": objective_score(self.config.objective, res.metrics),
                "totalReturn": res.metrics.get("total_return"),
                "tradeCount": res.metrics.get("trade_count"),
            })
        return out

    def _concentration(self, base) -> dict[str, Any]:
        trades = base.trades
        wins = [t["netPnl"] for t in trades if t["netPnl"] > 0]
        gross_profit = sum(wins)
        top = sorted(wins, reverse=True)[: self.config.concentration_top_n]
        share = (sum(top) / gross_profit) if gross_profit > 0 else None
        return {
            "topN": self.config.concentration_top_n,
            "grossProfit": gross_profit,
            "topShare": share,
            "concentrated": bool(share is not None and share >= self.config.concentration_threshold),
        }

    def _regime(self) -> list[dict[str, Any]]:
        timeline = self.dataset.timeline()
        n = len(timeline)
        if n < self.config.splits * 2:
            return []
        size = n // self.config.splits
        out: list[dict[str, Any]] = []
        for i in range(self.config.splits):
            a = i * size
            b = n if i == self.config.splits - 1 else (i + 1) * size
            ds = self.dataset.slice_by_timestamps(timeline[a], timeline[b - 1])
            res = _run(self.strategy, ds, BacktestConfig(
                initial_capital=self.config.initial_capital,
                risk_free_rate=self.config.risk_free_rate, random_seed=self.config.seed))
            out.append({
                "start": timeline[a], "end": timeline[b - 1],
                "objective": objective_score(self.config.objective, res.metrics),
                "totalReturn": res.metrics.get("total_return"),
                "tradeCount": res.metrics.get("trade_count"),
            })
        return out

    def run(self) -> ResearchResult:
        started = time.monotonic()
        self._report(0, 4)
        base = self._base()
        base_obj = objective_score(self.config.objective, base.metrics)
        warnings: list[dict[str, Any]] = []
        conclusions: list[str] = []

        sensitivity = None
        if self.config.param_ranges:
            sensitivity = SensitivityEngine(self.strategy, self.dataset, SensitivityConfig(
                param_ranges=self.config.param_ranges, objective=self.config.objective,
                initial_capital=self.config.initial_capital,
                risk_free_rate=self.config.risk_free_rate, seed=self.config.seed,
            )).run()
            collapses = [p for p, s in sensitivity.payload["parameters"].items() if s["collapse"]]
            if collapses:
                conclusions.append("Strategy appears parameter-sensitive.")
        else:
            collapses = []

        self._report(2, 4)
        cost = self._cost_sensitivity()
        material = False
        if base_obj is not None:
            for row in cost:
                if row["multiplier"] > 1.0 and row["objective"] is not None:
                    if base_obj != 0 and row["objective"] < base_obj * (1.0 - self.config.cost_material_drop):
                        material = True
        if material:
            conclusions.append(
                "Performance deteriorates materially under realistic transaction costs.")

        concentration = self._concentration(base)
        if concentration["concentrated"]:
            conclusions.append(
                "Strategy performance is concentrated in a small number of trades.")

        self._report(3, 4)
        regime = self._regime()
        regime_dependent = False
        if regime:
            objs = [r["objective"] for r in regime if r["objective"] is not None]
            if len(objs) >= 2 and (min(objs) < 0 <= max(objs) or
                                   (max(objs) != 0 and min(objs) < max(objs) * 0.25)):
                regime_dependent = True
        if regime_dependent:
            conclusions.append("Strategy performance is regime-dependent.")

        trade_count = base.metrics.get("trade_count") or 0
        insufficient = trade_count < self.config.min_trades
        if insufficient:
            warnings.append(warn("LOW_SAMPLE_SIZE",
                                 f"only {int(trade_count)} trades; evidence is insufficient",
                                 {"tradeCount": trade_count}))

        if insufficient:
            verdict = "insufficient_evidence"
        elif collapses or material or concentration["concentrated"] or regime_dependent:
            verdict = "fragile"
        else:
            verdict = "robust"

        payload = {
            "objective": self.config.objective,
            "verdict": verdict,
            "conclusions": conclusions,
            "base": {k: base.metrics.get(k) for k in
                     ("total_return", "sharpe", "sortino", "max_drawdown", "trade_count",
                      "profit_factor", "expectancy")},
            "sensitivity": sensitivity.payload if sensitivity else None,
            "costSensitivity": cost,
            "concentration": concentration,
            "regime": regime,
            "tradeCount": trade_count,
        }
        return ResearchResult(
            kind="robustness", status="OK",
            metadata={"engineVersion": ENGINE_VERSION, "strategyId": self.strategy.id,
                      "strategyVersion": self.strategy.version,
                      "symbols": self.strategy.universe.symbols,
                      "interval": self.dataset.primary_interval()},
            configuration={"objective": self.config.objective,
                           "costMultipliers": self.config.cost_multipliers,
                           "paramRanges": self.config.param_ranges,
                           "minTrades": self.config.min_trades},
            metrics={k: base.metrics.get(k) for k in
                     ("total_return", "sharpe", "max_drawdown", "trade_count", "profit_factor")},
            warnings=warnings,
            observability={"durationMs": int((time.monotonic() - started) * 1000)},
            capability={"robustness": "available"}, payload=payload,
        )


__all__ = [
    "RobustnessConfig",
    "RobustnessEngine",
    "RobustnessError",
    "SensitivityConfig",
    "SensitivityEngine",
]
