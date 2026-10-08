"""Optimization engine — grid / random / evolutionary / Bayesian.

Objectives are scalar scores derived deterministically from the backtest metrics
(all oriented so **higher is better**; `max_drawdown` is negated). Multi-objective
runs return a Pareto front instead of a single winner. The framework exposes
performance, risk, trade count and parameter stability, and it refuses to
present a result as "robust" without evidence — a low-trade-count or
raw-return-only winner is flagged.

Every optimizer is deterministic given a seed.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from . import strategy as S
from .data import MarketDataset
from .engine import ENGINE_VERSION, BacktestConfig, run_backtest
from .params import ParamSpace, apply_params, summarize_space
from .research import ResearchResult, warn
from .strategy import StrategySpec, errors_only

# Objective → higher-is-better score. `max_drawdown` is negated (it is negative).
_DEFAULT_OBJECTIVE = "sharpe"
_KNOWN_OBJECTIVES = {
    "sharpe", "sortino", "calmar", "omega", "profit_factor", "expectancy",
    "total_return", "cagr", "annualized_return", "max_drawdown", "return_drawdown",
    "win_rate", "trade_count",
}
_RAW_RETURN_OBJECTIVES = {"total_return", "annualized_return"}
_MIN_TRADES = 1


class OptimizationError(ValueError):
    pass


def objective_score(name: str, metrics: dict[str, Any]) -> Optional[float]:
    if name == "return_drawdown":
        cagr = metrics.get("cagr")
        dd = metrics.get("max_drawdown")
        if cagr is None or dd is None or dd == 0:
            return None
        return float(cagr) / abs(float(dd))
    value = metrics.get(name)
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    if name == "max_drawdown":
        return -abs(v)
    return v


@dataclass
class Trial:
    params: dict[str, Any]
    score: Optional[float]
    metrics: dict[str, Any]
    status: str = "ok"           # ok | failed | invalid
    error: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"params": self.params, "score": self.score, "status": self.status,
                "error": self.error, "metrics": self.metrics, "durationMs": self.duration_ms}


Evaluator = Callable[[dict[str, Any]], Trial]


# ── Low-level optimizers ─────────────────────────────────────────────────────

def _order_trials(trials: list[Trial]) -> list[Trial]:
    return sorted(
        [t for t in trials if t.score is not None],
        key=lambda t: (-float(t.score), repr(sorted(t.params.items()))),
    )


def _grid(space: ParamSpace, evaluate: Evaluator, max_evaluations: int) -> list[Trial]:
    trials: list[Trial] = []
    for params in space.grid():
        if len(trials) >= max_evaluations:
            break
        trials.append(evaluate(params))
    return trials


def _random(space: ParamSpace, evaluate: Evaluator, max_evaluations: int,
            rng: random.Random) -> list[Trial]:
    return [evaluate(p) for p in space.sample(max_evaluations, rng)]


def _mutate(params: dict[str, Any], space: ParamSpace, rng: random.Random) -> dict[str, Any]:
    child = dict(params)
    if not space.axes:
        return child
    for path in space.axes:
        if rng.random() < 0.4:
            child[path] = rng.choice(space.axes[path])
    return child


def _crossover(a: dict[str, Any], b: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    child: dict[str, Any] = {}
    for path in set(a) | set(b):
        child[path] = a.get(path) if rng.random() < 0.5 else b.get(path)
    return child


def _evolutionary(space: ParamSpace, evaluate: Evaluator, max_evaluations: int,
                  rng: random.Random, *, population: int = 8) -> list[Trial]:
    pop = space.sample(min(population, max_evaluations), rng)
    trials = [evaluate(p) for p in pop]
    while len(trials) < max_evaluations:
        ranked = _order_trials(trials)[:max(2, population // 2)]
        if len(ranked) < 2:
            trials.append(evaluate(space.sample(1, rng)[0]))
            continue
        parent_a = rng.choice(ranked).params
        parent_b = rng.choice(ranked).params
        child = _mutate(_crossover(parent_a, parent_b, rng), space, rng)
        trials.append(evaluate(child))
    return trials


def _encode(params: dict[str, Any], paths: list[str], space: ParamSpace) -> np.ndarray:
    vec = []
    for path in paths:
        values = space.axes[path]
        try:
            idx = values.index(params.get(path))
        except ValueError:
            idx = 0
        vec.append(idx / max(1, len(values) - 1))
    return np.array(vec, dtype=float)


def _bayesian(space: ParamSpace, evaluate: Evaluator, max_evaluations: int,
              rng: random.Random, *, init_points: int = 5, xi: float = 0.01) -> list[Trial]:
    """GP-EI surrogate optimization (a genuine Bayesian optimizer).

    Observations are the evaluated trials; candidates are the discrete grid (or
    a seeded pool when the grid is large). The surrogate is a Gaussian process
    with an RBF kernel; the acquisition is Expected Improvement. The history is
    capped so the O(n^3) inversion stays bounded.
    """
    paths = space.paths()
    candidates = list(space.grid())
    if len(candidates) > 4000:
        candidates = space.sample(4000, rng)
    if not candidates:
        candidates = [{}]
    trials: list[Trial] = []
    seeded = space.sample(min(init_points, max_evaluations), rng)
    for params in seeded:
        trials.append(evaluate(params))
    candidate_x = np.array([_encode(c, paths, space) for c in candidates]) if paths else None

    def gp_ei(obs_x: np.ndarray, obs_y: np.ndarray, cand_x: np.ndarray, best: float) -> np.ndarray:
        length_scale = 0.3
        noise = 1e-6
        d2 = ((obs_x[:, None, :] - obs_x[None, :, :]) ** 2).sum(-1)
        k = np.exp(-d2 / (2 * length_scale ** 2)) + noise * np.eye(len(obs_x))
        try:
            k_inv = np.linalg.inv(k)
        except np.linalg.LinAlgError:
            k_inv = np.linalg.pinv(k)
        dc2 = ((cand_x[:, None, :] - obs_x[None, :, :]) ** 2).sum(-1)
        k_s = np.exp(-dc2 / (2 * length_scale ** 2))
        mu = k_s @ k_inv @ obs_y
        var = 1.0 - np.sum((k_s @ k_inv) * k_s, axis=1)
        var = np.clip(var, 1e-12, None)
        sigma = np.sqrt(var)
        z = (mu - best - xi) / sigma
        from math import erf, sqrt
        cdf = 0.5 * (1.0 + np.vectorize(erf)(z / sqrt(2)))
        pdf = np.exp(-0.5 * z ** 2) / sqrt(2 * math.pi)
        return (mu - best - xi) * cdf + sigma * pdf

    while len(trials) < max_evaluations:
        ok = [t for t in trials if t.score is not None]
        if not paths or len(ok) < 2:
            trials.append(evaluate(space.sample(1, rng)[0]))
            continue
        # Bound the observation set (best + most recent) so inversion stays cheap.
        ok_sorted = sorted(ok, key=lambda t: -float(t.score))
        observations = ok_sorted[:150] + [t for t in trials if t.score is not None][-50:]
        obs_x = np.array([_encode(t.params, paths, space) for t in observations])
        obs_y = np.array([float(t.score) for t in observations])
        best = float(obs_y.max())
        ei = gp_ei(obs_x, obs_y, candidate_x, best)
        chosen_index = int(np.argmax(ei))
        trials.append(evaluate(candidates[chosen_index]))
    return trials


def run_optimizer(
    method: str,
    space: ParamSpace,
    evaluate: Evaluator,
    *,
    max_evaluations: int,
    seed: int,
) -> list[Trial]:
    rng = random.Random(seed)
    method = method.lower()
    if method == "grid":
        return _grid(space, evaluate, max_evaluations)
    if method == "random":
        return _random(space, evaluate, max_evaluations, rng)
    if method == "evolutionary":
        return _evolutionary(space, evaluate, max_evaluations, rng)
    if method == "bayesian":
        return _bayesian(space, evaluate, max_evaluations, rng)
    raise OptimizationError(f"unknown optimization method {method!r}")


# ── Pareto ───────────────────────────────────────────────────────────────────

def pareto_front(trials: list[Trial], objectives: list[str]) -> list[dict[str, Any]]:
    scored = []
    for t in trials:
        vals = [objective_score(o, t.metrics) for o in objectives]
        if all(v is not None for v in vals):
            scored.append((t, [float(v) for v in vals]))  # type: ignore[arg-type]
    front: list[dict[str, Any]] = []
    for t, vals in scored:
        dominated = any(
            all(v2 >= v1 for v1, v2 in zip(vals, other))
            and any(v2 > v1 for v1, v2 in zip(vals, other))
            for _, other in scored
        )
        if not dominated:
            front.append({"params": t.params, "score": t.score,
                          "objectives": dict(zip(objectives, vals)), "metrics": t.metrics})
    front.sort(key=lambda item: repr(sorted(item["params"].items())))
    return front


# ── Engine ───────────────────────────────────────────────────────────────────

@dataclass
class OptimizationConfig:
    method: str = "random"
    objective: str = _DEFAULT_OBJECTIVE
    objectives: list[str] = field(default_factory=list)
    max_evaluations: int = 60
    seed: int = 42
    initial_capital: float = 100_000.0
    risk_free_rate: float = 0.0
    start: Optional[str] = None
    end: Optional[str] = None
    symbols: Optional[list[str]] = None
    leaderboard_size: int = 15


class OptimizationEngine:
    def __init__(self, strategy: StrategySpec, dataset: MarketDataset,
                 space: ParamSpace, config: Optional[OptimizationConfig] = None,
                 *, progress: Optional[Callable[[str, int, int], None]] = None) -> None:
        self.strategy = strategy
        self.dataset = dataset
        self.space = space
        self.config = config or OptimizationConfig()
        self._progress = progress
        if self.space.is_empty():
            raise OptimizationError("an optimization needs at least one parameter axis")
        objectives = self.config.objectives or [self.config.objective]
        for name in objectives:
            if name not in _KNOWN_OBJECTIVES:
                raise OptimizationError(f"unknown objective {name!r}")
        self.objectives = objectives
        self._base_dict = strategy.to_dict()
        self._seq = 0

    def _evaluate(self, params: dict[str, Any]) -> Trial:
        started = time.monotonic()
        self._seq += 1
        try:
            spec_dict = apply_params(self._base_dict, params)
            spec = StrategySpec.model_validate(spec_dict)
        except Exception as exc:  # noqa: BLE001
            return Trial(params=params, score=None, metrics={}, status="invalid", error=str(exc))
        errs = errors_only(S.validate_strategy(spec))
        if errs:
            return Trial(params=params, score=None, metrics={},
                         status="invalid", error="; ".join(e.message for e in errs))
        try:
            result = run_backtest(
                spec, self.dataset,
                BacktestConfig(
                    initial_capital=self.config.initial_capital,
                    risk_free_rate=self.config.risk_free_rate, random_seed=self.config.seed,
                ),
                symbols=self.config.symbols,
            )
        except Exception as exc:  # noqa: BLE001
            return Trial(params=params, score=None, metrics={}, status="failed", error=str(exc))
        score = objective_score(self.objectives[0], result.metrics)
        if self._progress is not None:
            try:
                self._progress("evaluating", self._seq, self.config.max_evaluations)
            except Exception:  # noqa: BLE001 - progress must never break a run
                pass
        return Trial(params=params, score=score, metrics=result.metrics, status="ok",
                     duration_ms=int((time.monotonic() - started) * 1000))

    def _stability(self, trials: list[Trial]) -> dict[str, Any]:
        ok = [t for t in trials if t.score is not None]
        if not ok:
            return {}
        best = max(float(t.score) for t in ok)
        tol = 0.10 * (abs(best) if best else 1.0) + 1e-9
        out: dict[str, Any] = {}
        for path, values in self.space.axes.items():
            value_scores: dict[str, float] = {}
            for t in ok:
                v = repr(t.params.get(path))
                value_scores[v] = max(value_scores.get(v, -math.inf), float(t.score))
            near = [v for v, s in value_scores.items() if best - s <= tol]
            out[path] = {
                "bestValue": repr(next((t.params.get(path) for t in ok
                                        if float(t.score) == best), None)),
                "values": len(values),
                "nearBest": len(near),
                "stable": len(near) >= max(2, len(values) // 2),
                "scoreByValue": value_scores,
            }
        return out

    def run(self) -> ResearchResult:
        started = time.monotonic()
        trials = run_optimizer(
            self.config.method, self.space, self._evaluate,
            max_evaluations=self.config.max_evaluations, seed=self.config.seed,
        )
        ordered = _order_trials(trials)
        valid = [t for t in ordered if t.metrics.get("trade_count")]
        eligible = [t for t in valid if (t.metrics.get("trade_count") or 0) >= _MIN_TRADES]
        warnings: list[dict[str, Any]] = []

        best = eligible[0] if eligible else (valid[0] if valid else (ordered[0] if ordered else None))
        status = "OK"
        if best is None:
            status = "NO_VALID_TRIALS"
            warnings.append(warn("NO_VALID_TRIALS", "no trial produced a defined objective"))
        stability = self._stability(trials)

        if self.config.objective in _RAW_RETURN_OBJECTIVES:
            warnings.append(warn(
                "RAW_RETURN_OBJECTIVE",
                f"objective {self.config.objective!r} ignores risk; prefer a risk-adjusted objective",
            ))
        if best is not None:
            tc = best.metrics.get("trade_count") or 0
            if tc < 30:
                warnings.append(warn(
                    "LOW_SAMPLE_SIZE",
                    f"best configuration has only {int(tc)} trades; results are not robust",
                    {"tradeCount": tc},
                ))
            unstable = [p for p, s in stability.items() if not s.get("stable")]
            if unstable:
                warnings.append(warn(
                    "PARAMETER_SENSITIVE",
                    f"objective is sensitive to: {', '.join(unstable)}",
                    {"parameters": unstable},
                ))

        pareto = pareto_front(trials, self.objectives) if len(self.objectives) > 1 else []
        evaluated = len(trials)
        failures = sum(1 for t in trials if t.status != "ok")
        payload = {
            "method": self.config.method,
            "objective": self.config.objective,
            "objectives": self.objectives,
            "space": summarize_space(self.space),
            "best": best.to_dict() if best else None,
            "leaderboard": [t.to_dict() for t in ordered[: self.config.leaderboard_size]],
            "trials": [t.to_dict() for t in trials[:200]],
            "stability": stability,
            "pareto": pareto,
        }
        metrics = best.metrics if best else {}
        metadata = {
            "engineVersion": ENGINE_VERSION,
            "strategyId": self.strategy.id,
            "strategyVersion": self.strategy.version,
            "symbols": self.config.symbols or self.strategy.universe.symbols,
            "interval": self.dataset.primary_interval(),
        }
        configuration = {
            "method": self.config.method, "objective": self.config.objective,
            "objectives": self.objectives, "maxEvaluations": self.config.max_evaluations,
            "seed": self.config.seed, "initialCapital": self.config.initial_capital,
            "riskFreeRate": self.config.risk_free_rate, "start": self.config.start,
            "end": self.config.end, "space": summarize_space(self.space),
        }
        observability = {
            "trials": evaluated, "failed": failures,
            "durationMs": int((time.monotonic() - started) * 1000),
        }
        return ResearchResult(
            kind="optimization", status=status, metadata=metadata, configuration=configuration,
            metrics=metrics, warnings=warnings, observability=observability,
            capability={"optimization": "available"}, payload=payload,
        )


__all__ = [
    "OptimizationConfig",
    "OptimizationEngine",
    "OptimizationError",
    "Trial",
    "objective_score",
    "pareto_front",
    "run_optimizer",
]
