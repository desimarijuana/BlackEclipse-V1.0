"""Monte-Carlo analysis.

Five perturbation families over a base backtest:

  * `trade_reshuffle`      — reorder the realized trade P&L sequence,
  * `return_bootstrap`     — resample the periodic returns with replacement,
  * `regime_block_bootstrap` — resample **blocks of consecutive trades that
    happened in the same market regime**, so the serial clustering of good and
    bad conditions survives the resample,
  * `parameter_perturbation` — re-run with parameters jittered within a band,
  * `execution_perturbation` — re-run with commission/slippage scaled.

Every simulation is seeded, so the same inputs and seed reproduce the same
distribution. Outputs the 5/25/50/75/95 percentiles of return, probability of
loss, probability of ruin, expected and worst drawdown, and the return
distribution.

The three resampling families are not interchangeable. `trade_reshuffle` and
`return_bootstrap` treat observations as independent, which understates the
tail of any strategy whose edge clusters in one market condition. The regime
block method exists to answer the harder question: *how does this edge behave
when the conditions that produced it come in runs, as they actually do?*
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .data import MarketDataset
from .engine import ENGINE_VERSION, BacktestConfig, run_backtest
from .params import get_path, set_path
from .research import ResearchResult, warn
from .strategy import StrategySpec


class MonteCarloError(ValueError):
    pass


_METHODS = {"trade_reshuffle", "return_bootstrap", "regime_block_bootstrap",
            "parameter_perturbation", "execution_perturbation"}

#: How the regime block method treats the mix of regimes across the sample.
REGIME_MIX_MODES = ("resample", "preserve")


@dataclass
class MonteCarloConfig:
    method: str = "trade_reshuffle"
    simulations: int = 1000
    seed: int = 42
    ruin_threshold: float = 0.5           # fraction of initial capital
    perturbation_pct: float = 0.10
    perturbation: dict[str, float] = field(default_factory=dict)
    execution_perturbation: dict[str, float] = field(default_factory=dict)
    initial_capital: float = 100_000.0
    risk_free_rate: float = 0.0
    # `regime_block_bootstrap` only.
    regime_mix: str = "resample"          # resample | preserve
    regime_block_length: float = 1.0      # mean consecutive blocks per draw
    regime_config: dict[str, Any] = field(default_factory=dict)


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 0.0
    worst = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak:
            worst = min(worst, v / peak - 1.0)
    return worst * 100.0


def _numeric_paths(spec_dict: dict[str, Any]) -> list[str]:
    """Numeric leaves eligible for parameter perturbation."""
    paths: list[str] = []
    for i, decl in enumerate(spec_dict.get("indicators", [])):
        for key, value in (decl.get("params") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                paths.append(f"indicators.{i}.params.{key}")
    for path in ("rules.exit.stop_loss.value", "rules.exit.take_profit.value",
                 "rules.exit.trailing_stop.value", "position_sizing.value",
                 "position_sizing.atr_multiplier"):
        value = get_path(spec_dict, path, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            paths.append(path)
    return paths


def _percentiles(values: list[float], points: list[int]) -> dict[str, float]:
    arr = np.array(values, dtype=float)
    out: dict[str, float] = {}
    for p in points:
        out[f"p{p}"] = float(np.percentile(arr, p))
    out["mean"] = float(arr.mean())
    out["std"] = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    return out


def _resample_blocks_shuffling(rng: random.Random, blocks: list[list[int]],
                               target: int, mean_length: float) -> list[int]:
    """Draw whole blocks with replacement until `target` trades are collected.

    Blocks are drawn in random order, so the *arrival* of conditions changes
    between paths while the clustering inside a block does not. `mean_length` is
    the expected number of consecutive blocks per draw (1.0 = classic block
    bootstrap; higher values preserve longer runs).
    """
    count = len(blocks)
    if count == 0 or target <= 0:
        return []
    out: list[int] = []
    p = 1.0 / max(1.0, float(mean_length))
    guard = 0
    while len(out) < target and guard < 100_000:
        guard += 1
        start = rng.randrange(count)
        length = 1
        while rng.random() > p and length < count:
            length += 1
        for j in range(length):
            out.extend(blocks[(start + j) % count])
    return out[:target]


def _resample_blocks_preserving_mix(rng: random.Random, blocks: list[list[int]],
                                    labels: list[Optional[str]]) -> list[int]:
    """Replace every original block with a drawn block of the same regime.

    The chronology and the regime mix of the original run are kept exactly;
    only the *content* of each block changes. This answers "what if the same
    conditions had produced different trades?".
    """
    pools: dict[str, list[list[int]]] = {}
    for block in blocks:
        key = labels[block[0]] if block else None
        key = key if key is not None else "unassigned"
        pools.setdefault(key, []).append(block)

    drawn: list[int] = []
    for block in blocks:
        key = labels[block[0]] if block else None
        key = key if key is not None else "unassigned"
        pool = pools.get(key) or []
        if not pool:
            drawn.extend(block)
            continue
        same_length = [b for b in pool if len(b) == len(block)]
        pick = rng.choice(same_length) if same_length else rng.choice(pool)
        drawn.extend(pick)
    return drawn


class _Recorded:
    """A recorded run: the trades and the curve, without a strategy to re-run.

    The perturbation families that only need the realised trade sequence (the
    reshuffle and the regime-block methods) work on this. The families that
    re-run the strategy (parameter and execution perturbation) do not, and say
    so.
    """

    def __init__(self, trades: list[dict[str, Any]], metrics: dict[str, Any],
                 equity_curve: list[dict[str, Any]]) -> None:
        self.trades = trades
        self.metrics = metrics
        self.equity_curve = equity_curve


class MonteCarloEngine:
    def __init__(self, strategy: StrategySpec, dataset: MarketDataset,
                 config: Optional[MonteCarloConfig] = None,
                 *, progress: Optional[Any] = None) -> None:
        self.strategy = strategy
        self.dataset = dataset
        self.config = config or MonteCarloConfig()
        self._progress = progress
        self._recorded: Optional[_Recorded] = None
        if self.config.method not in _METHODS:
            raise MonteCarloError(f"unknown monte-carlo method {self.config.method!r}")
        if self.config.simulations < 1:
            raise MonteCarloError("simulations must be >= 1")

    @classmethod
    def from_recorded(
        cls,
        *,
        trades: list[dict[str, Any]],
        equity_curve: list[dict[str, Any]],
        metrics: Optional[dict[str, Any]] = None,
        config: Optional[MonteCarloConfig] = None,
    ) -> "MonteCarloEngine":
        """Analyse a run that was RECORDED rather than re-run.

        A Pine strategy cannot be re-run with perturbed parameters, but its
        realised trade sequence can still be resampled - so the same
        uncertainty machinery serves it. Only the families that need the
        strategy itself are unavailable, and they refuse with a named reason.
        """
        engine = cls.__new__(cls)
        engine.strategy = None  # type: ignore[assignment]
        engine.dataset = None  # type: ignore[assignment]
        engine.config = config or MonteCarloConfig()
        engine._progress = None
        engine._recorded = _Recorded(list(trades or []), dict(metrics or {}),
                                    list(equity_curve or []))
        if engine.config.method not in _METHODS:
            raise MonteCarloError(
                f"unknown monte-carlo method {engine.config.method!r}")
        if engine.config.simulations < 1:
            raise MonteCarloError("simulations must be >= 1")
        if engine.config.method in ("parameter_perturbation", "execution_perturbation"):
            raise MonteCarloError(
                f"the {engine.config.method!r} method re-runs the strategy, which a "
                f"recorded run does not have; use 'trade_reshuffle' or "
                f"'regime_block_bootstrap'")
        return engine

    def _report(self, done: int, total: int) -> None:
        if self._progress is None:
            return
        try:
            self._progress("simulating", done, total)
        except Exception:  # noqa: BLE001 - progress must never break a run
            pass

    def _base(self) -> Any:
        if self._recorded is not None:
            return self._recorded
        return run_backtest(
            self.strategy, self.dataset,
            BacktestConfig(initial_capital=self.config.initial_capital,
                           risk_free_rate=self.config.risk_free_rate,
                           random_seed=self.config.seed),
        )

    def _path_stats(self, equity: list[float]) -> tuple[float, float, bool]:
        initial = self.config.initial_capital
        final = equity[-1] if equity else initial
        total_return = (final / initial - 1.0) * 100.0
        ruined = min(equity) <= initial * self.config.ruin_threshold if equity else False
        return total_return, _max_drawdown(equity), ruined

    def run(self) -> ResearchResult:
        started = time.monotonic()
        base = self._base()
        rng = random.Random(self.config.seed)
        c = self.config
        returns: list[float] = []
        drawdowns: list[float] = []
        ruinations = 0
        failures = 0
        warnings: list[dict[str, Any]] = []
        regime_attribution: dict[str, Any] = {}
        regime_blocks_count = 0
        regime_mix = c.regime_mix
        regime_pnl_samples: dict[str, list[float]] = {}
        regime_count_samples: dict[str, list[int]] = {}

        if c.method == "trade_reshuffle":
            pnls = [t["netPnl"] for t in base.trades]
            if not pnls:
                warnings.append(warn("NO_TRADES", "base run produced no trades; nothing to resample"))
            for _i in range(c.simulations):
                self._report(_i + 1, c.simulations)
                seq = list(pnls)
                rng.shuffle(seq)
                equity = [c.initial_capital]
                for pnl in seq:
                    equity.append(equity[-1] + pnl)
                r, dd, ruined = self._path_stats(equity)
                returns.append(r); drawdowns.append(dd); ruinations += int(ruined)
        elif c.method == "return_bootstrap":
            eq = [p["equity"] for p in base.equity_curve]
            rets = [eq[i] / eq[i - 1] - 1.0 for i in range(1, len(eq)) if eq[i - 1]]
            if not rets:
                warnings.append(warn("NO_RETURNS", "base equity curve is empty"))
            for _i in range(c.simulations):
                self._report(_i + 1, c.simulations)
                sample = [rng.choice(rets) for _ in range(len(rets))] if rets else []
                equity = [c.initial_capital]
                for r0 in sample:
                    equity.append(equity[-1] * (1.0 + r0))
                r, dd, ruined = self._path_stats(equity)
                returns.append(r); drawdowns.append(dd); ruinations += int(ruined)
        elif c.method == "regime_block_bootstrap":
            from .regime import (RegimeConfig, attribute_regimes, classify_dataset,
                                 label_trades, regime_blocks)

            if c.regime_mix not in REGIME_MIX_MODES:
                raise MonteCarloError(
                    f"unknown regime mix {c.regime_mix!r}; expected one of "
                    f"{', '.join(REGIME_MIX_MODES)}")
            try:
                regime_config = RegimeConfig(**(c.regime_config or {}))
            except (TypeError, ValueError) as exc:
                raise MonteCarloError(f"invalid regime config: {exc}") from exc

            series_by_symbol = classify_dataset(self.dataset, regime_config)
            labels, placement = label_trades(base.trades, series_by_symbol)
            if placement["unassigned"]:
                warnings.append(warn(
                    "REGIME_LABEL_UNAVAILABLE",
                    f"{placement['unassigned']} trade(s) could not be attached to a "
                    "market regime; they were resampled as their own group",
                    detail=placement["unassignedReasons"]))
            pnls = [float(t.get("netPnl") or 0.0) for t in base.trades]
            regime_attribution = attribute_regimes(base.trades, labels)
            blocks = regime_blocks(labels)
            regime_blocks_count = len(blocks)
            if not pnls:
                warnings.append(warn("NO_TRADES",
                                     "base run produced no trades; nothing to resample"))
            regime_pnl_samples: dict[str, list[float]] = {}
            regime_count_samples: dict[str, list[int]] = {}
            total = len(pnls)
            for _i in range(c.simulations):
                self._report(_i + 1, c.simulations)
                if c.regime_mix == "preserve":
                    drawn = _resample_blocks_preserving_mix(rng, blocks, labels)
                else:
                    drawn = _resample_blocks_shuffling(
                        rng, blocks, total, c.regime_block_length)
                equity = [c.initial_capital]
                pnl_path: dict[str, float] = {}
                count_path: dict[str, int] = {}
                for idx in drawn:
                    pnl = pnls[idx]
                    equity.append(equity[-1] + pnl)
                    key = labels[idx] if labels[idx] is not None else "unassigned"
                    pnl_path[key] = pnl_path.get(key, 0.0) + pnl
                    count_path[key] = count_path.get(key, 0) + 1
                r, dd, ruined = self._path_stats(equity)
                returns.append(r); drawdowns.append(dd); ruinations += int(ruined)
                for key, value in pnl_path.items():
                    regime_pnl_samples.setdefault(key, []).append(value)
                for key, value in count_path.items():
                    regime_count_samples.setdefault(key, []).append(value)
        elif c.method == "parameter_perturbation":
            base_dict = self.strategy.to_dict()
            paths = list(c.perturbation.keys()) or _numeric_paths(base_dict)
            if not paths:
                warnings.append(warn("NO_PARAMETERS", "no numeric parameters to perturb"))
            for _i in range(c.simulations):
                self._report(_i + 1, c.simulations)
                spec_dict = self.strategy.to_dict()
                for path in paths:
                    base_val = get_path(spec_dict, path, None)
                    if not isinstance(base_val, (int, float)) or isinstance(base_val, bool):
                        continue
                    pct = c.perturbation.get(path, c.perturbation_pct)
                    set_path(spec_dict, path, max(0.0, float(base_val) * (1.0 + rng.uniform(-pct, pct))))
                try:
                    spec = StrategySpec.model_validate(spec_dict)
                    res = run_backtest(spec, self.dataset, BacktestConfig(
                        initial_capital=c.initial_capital, risk_free_rate=c.risk_free_rate,
                        random_seed=self.config.seed))
                    r = res.metrics.get("total_return")
                    dd = res.metrics.get("max_drawdown")
                    if r is None or dd is None:
                        failures += 1
                        continue
                    returns.append(float(r)); drawdowns.append(float(dd))
                    eq = [p["equity"] for p in res.equity_curve]
                    ruinations += int(bool(eq) and min(eq) <= c.initial_capital * c.ruin_threshold)
                except Exception:  # noqa: BLE001
                    failures += 1
        else:  # execution_perturbation
            factors = c.execution_perturbation or {"commission": 1.5, "slippage": 1.5}
            for _i in range(c.simulations):
                self._report(_i + 1, c.simulations)
                spec_dict = self.strategy.to_dict()
                exec_cfg = spec_dict.setdefault("execution", {})
                for key, factor in factors.items():
                    block = exec_cfg.get(key)
                    if isinstance(block, dict) and isinstance(block.get("value"), (int, float)):
                        block = dict(block)
                        block["value"] = float(block["value"]) * float(factor)
                        exec_cfg[key] = block
                try:
                    spec = StrategySpec.model_validate(spec_dict)
                    res = run_backtest(spec, self.dataset, BacktestConfig(
                        initial_capital=c.initial_capital, risk_free_rate=c.risk_free_rate,
                        random_seed=self.config.seed))
                    r = res.metrics.get("total_return")
                    dd = res.metrics.get("max_drawdown")
                    if r is None or dd is None:
                        failures += 1
                        continue
                    returns.append(float(r)); drawdowns.append(float(dd))
                except Exception:  # noqa: BLE001
                    failures += 1

        n = max(1, len(returns))
        pct = _percentiles(returns, [5, 25, 50, 75, 95])
        arr = np.array(returns, dtype=float)
        span = float(arr.max() - arr.min()) if arr.size else 0.0
        if arr.size == 0:
            hist_edges, hist_counts = np.array([]), np.array([])
        elif span <= 1e-9:
            # Degenerate (e.g. a single-trade reshuffle): one bin, no crash.
            hist_edges, hist_counts = np.array([arr[0], arr[0] + 1e-9]), np.array([arr.size])
        else:
            hist_counts, hist_edges = np.histogram(arr, bins=min(20, max(1, arr.size)))
        payload = {
            "method": c.method,
            "simulations": c.simulations,
            "successful": len(returns),
            "failures": failures,
            "returnPercentiles": pct,
            "probabilityOfLoss": sum(1 for r in returns if r < 0) / n * 100.0,
            "probabilityOfRuin": ruinations / n * 100.0,
            "expectedDrawdown": float(np.mean(drawdowns)) if drawdowns else None,
            "worstDrawdown": float(np.min(drawdowns)) if drawdowns else None,
            "returnDistribution": {
                "bins": [round(float(e), 4) for e in hist_edges],
                "counts": [int(x) for x in hist_counts],
            },
            "baseMetrics": {k: base.metrics.get(k) for k in
                            ("total_return", "sharpe", "max_drawdown", "trade_count")},
        }
        if c.method == "regime_block_bootstrap":
            contributions: dict[str, Any] = {}
            for label, samples in regime_pnl_samples.items():
                arr = np.array(samples, dtype=float)
                counts = regime_count_samples.get(label) or []
                contributions[label] = {
                    "meanPnl": round(float(arr.mean()), 6) if arr.size else None,
                    "p5Pnl": round(float(np.percentile(arr, 5)), 6) if arr.size else None,
                    "p95Pnl": round(float(np.percentile(arr, 95)), 6) if arr.size else None,
                    "meanTrades": round(float(np.mean(counts)), 4) if counts else None,
                    "pathsObserved": int(arr.size),
                }
            payload["regimeAttribution"] = regime_attribution
            payload["regimeBlocks"] = regime_blocks_count
            payload["regimeMix"] = regime_mix
            payload["regimeContributions"] = contributions
        metrics = {
            "expected_return": pct["mean"], "median_return": pct["p50"],
            "p5_return": pct["p5"], "p95_return": pct["p95"],
            "probability_of_loss": payload["probabilityOfLoss"],
            "probability_of_ruin": payload["probabilityOfRuin"],
            "expected_drawdown": payload["expectedDrawdown"],
            "worst_drawdown": payload["worstDrawdown"],
        }
        metadata = {
            "engineVersion": ENGINE_VERSION,
            "strategyId": getattr(self.strategy, "id", None) or "recorded",
            "strategyVersion": getattr(self.strategy, "version", None),
            "symbols": list(getattr(getattr(self.strategy, "universe", None),
                                   "symbols", []) or []),
            "interval": (self.dataset.primary_interval()
                         if self.dataset is not None else None),
        }
        configuration = {
            "method": c.method, "simulations": c.simulations, "seed": c.seed,
            "ruinThreshold": c.ruin_threshold, "perturbationPct": c.perturbation_pct,
            "executionPerturbation": c.execution_perturbation,
            "initialCapital": c.initial_capital,
        }
        if c.method == "regime_block_bootstrap":
            configuration["regimeMix"] = c.regime_mix
            configuration["regimeBlockLength"] = c.regime_block_length
            configuration["regimeConfig"] = dict(c.regime_config or {})
        return ResearchResult(
            kind="monte_carlo", status="OK", metadata=metadata, configuration=configuration,
            metrics=metrics, warnings=warnings,
            observability={"simulations": c.simulations, "successful": len(returns),
                           "durationMs": int((time.monotonic() - started) * 1000)},
            capability={"monteCarlo": "available"}, payload=payload,
        )


__all__ = ["MonteCarloConfig", "MonteCarloEngine", "MonteCarloError"]
