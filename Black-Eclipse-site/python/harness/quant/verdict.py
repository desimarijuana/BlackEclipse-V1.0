"""The Edge Verdict — an honest grade for a strategy's demonstrated edge.

The verdict answers one question a backtest cannot: **should this strategy be
trusted with real capital?** It is not a second backtest and it never computes
its own numbers — it reads the metrics, trades and (optionally) the Monte-Carlo
distribution an engine already produced, and grades them on four axes:

  * **edge** — is there an edge at all? (profit factor, Sharpe, expectancy)
  * **robustness** — does it survive resampling? (Monte-Carlo probability of
    loss, tail return)
  * **risk** — what does it cost to hold? (drawdown, ulcer index)
  * **sample** — is there enough evidence to say anything? (trade count)

Every axis carries its own weight. When an axis cannot be judged — no
Monte-Carlo, no trades — its weight is redistributed and the verdict says so
out loud rather than silently scoring it as zero or as perfect.

The grade is also **capped**. A critical flag (a negative expectancy, a
profit factor below one, a sample too small to distinguish from luck) cannot
be averaged away by a good Sharpe.

This module is a *judgement about evidence*, not advice. It grades what was
measured and names what was not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from .errors import QuantError


class VerdictError(QuantError):
    code = "VERDICT_ERROR"


GRADES: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")

#: Score floor for each grade, highest first.
GRADE_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("A", 85.0),
    ("B", 72.0),
    ("C", 60.0),
    ("D", 45.0),
    ("E", 30.0),
)

#: The best grade a verdict may carry while a critical flag is present.
CRITICAL_FLAG_MAX_GRADE = "D"


@dataclass(frozen=True)
class VerdictConfig:
    """Thresholds of the grader. Every one is explicit and inspectable."""

    min_trades: int = 30
    good_trades: int = 100
    smooth_curve_autocorrelation: float = 0.90
    concentration_top_fraction: float = 0.05
    concentration_share: float = 0.60
    single_regime_share: float = 70.0
    high_probability_of_loss: float = 35.0
    weights: tuple[tuple[str, float], ...] = (
        ("edge", 0.35),
        ("robustness", 0.25),
        ("risk", 0.25),
        ("sample", 0.15),
    )

    def validate(self) -> None:
        if self.min_trades < 1:
            raise VerdictError("min_trades must be >= 1")
        if self.good_trades < self.min_trades:
            raise VerdictError("good_trades must be >= min_trades")
        if not (0.0 < self.concentration_top_fraction <= 1.0):
            raise VerdictError("concentration_top_fraction must be in (0, 1]")
        if not (0.0 < self.concentration_share <= 1.0):
            raise VerdictError("concentration_share must be in (0, 1]")
        if not (0.0 < self.single_regime_share <= 100.0):
            raise VerdictError("single_regime_share must be in (0, 100]")
        total = sum(w for _, w in self.weights)
        if total <= 0:
            raise VerdictError("weights must sum to a positive number")


def _lerp_score(value: float, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear score from a descending table of (threshold, score)."""
    if value is None or not math.isfinite(value):
        return 0.0
    for threshold, score in points:
        if value >= threshold:
            return score
    return points[-1][1]


def _lag1_autocorrelation(values: list[float]) -> Optional[float]:
    """Lag-1 autocorrelation of a series; `None` when it is undefined."""
    n = len(values)
    if n < 4:
        return None
    mean = sum(values) / n
    dev = [v - mean for v in values]
    denom = sum(d * d for d in dev)
    if denom <= 0:
        return None
    num = sum(dev[i] * dev[i - 1] for i in range(1, n))
    return num / denom


def _percentile(values: list[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _trade_pnls(trades: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for trade in trades or []:
        value = trade.get("netPnl")
        if value is None:
            value = trade.get("net_pnl")
        if value is None:
            continue
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _score_edge(metrics: dict[str, Any], pnls: list[float]) -> tuple[float, dict[str, Any]]:
    profit_factor = metrics.get("profit_factor")
    sharpe = metrics.get("sharpe")
    expectancy = metrics.get("expectancy")
    if expectancy is None and pnls:
        expectancy = sum(pnls) / len(pnls)

    pf_score = _lerp_score(profit_factor, [(2.0, 100.0), (1.5, 82.0), (1.2, 64.0),
                                            (1.0, 42.0), (0.0, 8.0)])
    sharpe_score = _lerp_score(sharpe, [(2.0, 100.0), (1.5, 86.0), (1.0, 68.0),
                                        (0.5, 45.0), (0.0, 10.0)])
    expectancy_score = 0.0
    if expectancy is not None and math.isfinite(float(expectancy)):
        expectancy_score = 100.0 if float(expectancy) > 0 else 0.0

    score = 0.5 * pf_score + 0.3 * sharpe_score + 0.2 * expectancy_score
    detail = {
        "profitFactor": profit_factor,
        "sharpe": sharpe,
        "expectancy": expectancy,
        "profitFactorScore": round(pf_score, 2),
        "sharpeScore": round(sharpe_score, 2),
        "expectancyScore": round(expectancy_score, 2),
    }
    return score, detail


def _score_robustness(monte_carlo: Optional[dict[str, Any]]) -> tuple[Optional[float], dict[str, Any]]:
    if not monte_carlo:
        return None, {"tested": False,
                      "reason": "no Monte-Carlo distribution was supplied"}
    prob_loss = monte_carlo.get("probabilityOfLoss")
    if prob_loss is None:
        prob_loss = (monte_carlo.get("metrics") or {}).get("probability_of_loss")
    percentiles = monte_carlo.get("returnPercentiles") or {}
    p5 = percentiles.get("p5")
    if prob_loss is None and p5 is None:
        return None, {"tested": False,
                      "reason": "the Monte-Carlo result carries no loss probability "
                                "and no tail return"}

    loss_score = _lerp_score(-float(prob_loss) if prob_loss is not None else -100.0,
                              [(-10.0, 100.0), (-20.0, 86.0), (-35.0, 66.0),
                               (-50.0, 44.0), (-100.0, 18.0)])
    tail_score = 100.0 if (p5 is not None and float(p5) > 0) else 35.0
    score = 0.7 * loss_score + 0.3 * tail_score
    return score, {
        "tested": True,
        "probabilityOfLoss": prob_loss,
        "p5Return": p5,
        "probabilityOfRuin": monte_carlo.get("probabilityOfRuin"),
        "lossScore": round(loss_score, 2),
        "tailScore": round(tail_score, 2),
    }


def _score_risk(metrics: dict[str, Any]) -> tuple[Optional[float], dict[str, Any]]:
    max_dd = metrics.get("max_drawdown")
    if max_dd is None:
        return None, {"tested": False, "reason": "no maximum drawdown was measured"}
    ulcer = metrics.get("ulcer_index")
    dd_score = _lerp_score(-abs(float(max_dd)),
                           [(-10.0, 100.0), (-20.0, 86.0), (-30.0, 68.0),
                            (-45.0, 46.0), (-100.0, 18.0)])
    ulcer_score = 100.0
    if ulcer is not None and math.isfinite(float(ulcer)):
        ulcer_score = _lerp_score(-abs(float(ulcer)),
                                  [(-3.0, 100.0), (-6.0, 82.0), (-12.0, 62.0),
                                   (-25.0, 38.0), (-100.0, 15.0)])
    score = 0.75 * dd_score + 0.25 * ulcer_score
    return score, {
        "tested": True,
        "maxDrawdown": max_dd,
        "ulcerIndex": ulcer,
        "drawdownScore": round(dd_score, 2),
        "ulcerScore": round(ulcer_score, 2),
    }


def _score_sample(metrics: dict[str, Any], trade_count: int) -> tuple[float, dict[str, Any]]:
    score = _lerp_score(float(trade_count), [(100.0, 100.0), (50.0, 78.0),
                                             (30.0, 58.0), (15.0, 34.0), (0.0, 12.0)])
    return score, {"tested": True, "tradeCount": trade_count,
                   "metricTradeCount": metrics.get("trade_count")}


def _grade_for(score: float) -> str:
    for grade, floor in GRADE_THRESHOLDS:
        if score >= floor:
            return grade
    return "F"


def _cap_grade(grade: str, ceiling: str) -> str:
    order = list(GRADES)
    if order.index(grade) < order.index(ceiling):
        return ceiling
    return grade


def grade_edge(
    *,
    metrics: dict[str, Any],
    trades: Optional[list[dict[str, Any]]] = None,
    equity_curve: Optional[list[dict[str, Any]]] = None,
    monte_carlo: Optional[dict[str, Any]] = None,
    regimes: Optional[dict[str, Any]] = None,
    config: Optional[VerdictConfig] = None,
) -> dict[str, Any]:
    """Grade the evidence behind a strategy's edge.

    `metrics` is the engine's own metric map. `trades`, `equity_curve`,
    `monte_carlo` and `regimes` are optional enrichments; each one that is
    absent lowers what the verdict can say, and says so.
    """
    cfg = config or VerdictConfig()
    cfg.validate()

    metrics = dict(metrics or {})
    trade_list = list(trades or [])
    pnls = _trade_pnls(trade_list)
    trade_count = len(pnls) if pnls else int(metrics.get("trade_count") or 0)

    flags: list[dict[str, Any]] = []

    edge_score, edge_detail = _score_edge(metrics, pnls)
    robustness_score, robustness_detail = _score_robustness(monte_carlo)
    risk_score, risk_detail = _score_risk(metrics)
    sample_score, sample_detail = _score_sample(metrics, trade_count)

    components: dict[str, dict[str, Any]] = {
        "edge": {"score": round(edge_score, 2), "basis": "profit factor, Sharpe, expectancy",
                 "detail": edge_detail},
        "robustness": {"score": (round(robustness_score, 2)
                                 if robustness_score is not None else None),
                       "basis": "Monte-Carlo probability of loss and tail return",
                       "detail": robustness_detail},
        "risk": {"score": round(risk_score, 2) if risk_score is not None else None,
                 "basis": "maximum drawdown and ulcer index",
                 "detail": risk_detail},
        "sample": {"score": round(sample_score, 2),
                   "basis": "number of closed trades",
                   "detail": sample_detail},
    }

    weights = {name: weight for name, weight in cfg.weights}
    for name, component in components.items():
        if component["score"] is None:
            flags.append({
                "code": f"{name.upper()}_NOT_TESTED",
                "severity": "info",
                "message": f"the {name} axis could not be judged; its weight was "
                           f"redistributed across the axes that could",
            })

    available = {name: weight for name, weight in weights.items()
                 if components[name]["score"] is not None}
    total_weight = sum(available.values()) or 1.0
    weighted = sum(components[name]["score"] * weight for name, weight in available.items())
    score = weighted / total_weight

    # ── Overfit and evidence flags ───────────────────────────────────────────
    expectancy = edge_detail.get("expectancy")
    if expectancy is not None and math.isfinite(float(expectancy)) and float(expectancy) <= 0:
        flags.append({
            "code": "EXPECTANCY_NOT_POSITIVE",
            "severity": "critical",
            "message": "average P&L per trade is not positive; there is no demonstrated "
                       "edge to size against",
        })

    profit_factor = metrics.get("profit_factor")
    if profit_factor is not None and math.isfinite(float(profit_factor)) \
            and float(profit_factor) < 1.0:
        flags.append({
            "code": "PROFIT_FACTOR_BELOW_ONE",
            "severity": "critical",
            "message": f"gross profit is below gross loss (profit factor "
                       f"{float(profit_factor):.3f})",
        })

    if trade_count < cfg.min_trades:
        flags.append({
            "code": "SAMPLE_TOO_SMALL",
            "severity": "critical",
            "message": f"{trade_count} closed trade(s) is below the {cfg.min_trades} "
                       f"needed to tell an edge apart from luck",
        })

    if equity_curve:
        equity = [float(p["equity"]) for p in equity_curve if "equity" in p]
        returns = [(equity[i] / equity[i - 1] - 1.0) if equity[i - 1] else 0.0
                   for i in range(1, len(equity))]
        autocorr = _lag1_autocorrelation(returns)
        if autocorr is not None and autocorr > cfg.smooth_curve_autocorrelation \
                and len(returns) >= 30:
            flags.append({
                "code": "EQUITY_CURVE_SUSPICIOUSLY_SMOOTH",
                "severity": "warning",
                "message": f"the equity curve's per-period returns have a lag-1 "
                           f"autocorrelation of {autocorr:.3f}; a curve that smooth in "
                           f"real trading is a curve that was fitted",
            })

    if pnls:
        positive = sorted((p for p in pnls if p > 0), reverse=True)
        gross_positive = sum(positive)
        if gross_positive > 0:
            top_n = max(1, int(math.ceil(len(pnls) * cfg.concentration_top_fraction)))
            top_share = sum(positive[:top_n]) / gross_positive * 100.0
            if top_share >= cfg.concentration_share * 100.0:
                flags.append({
                    "code": "PNL_CONCENTRATED_IN_FEW_TRADES",
                    "severity": "warning",
                    "message": f"the best {top_n} of {len(pnls)} trades carry "
                               f"{top_share:.1f}% of gross profit; the edge depends on "
                               f"trades that may not repeat",
                })

    if monte_carlo:
        prob_loss = monte_carlo.get("probabilityOfLoss")
        if prob_loss is None:
            prob_loss = (monte_carlo.get("metrics") or {}).get("probability_of_loss")
        if prob_loss is not None and float(prob_loss) > cfg.high_probability_of_loss:
            flags.append({
                "code": "MONTE_CARLO_PROBABILITY_OF_LOSS_HIGH",
                "severity": "warning",
                "message": f"{float(prob_loss):.1f}% of resampled paths finish below "
                           f"zero",
            })

    if regimes:
        buckets = regimes.get("regimes") or {}
        net_total = sum(float(b.get("netPnl") or 0.0) for b in buckets.values())
        if net_total > 0 and buckets:
            top_label, top_bucket = max(
                buckets.items(), key=lambda kv: float(kv[1].get("netPnl") or 0.0))
            share = float(top_bucket.get("netPnl") or 0.0) / net_total * 100.0
            if share >= cfg.single_regime_share:
                flags.append({
                    "code": "SINGLE_REGIME_DEPENDENT",
                    "severity": "warning",
                    "message": f"{share:.1f}% of net P&L comes from one market regime "
                               f"({top_label}); the edge may exist only when that "
                               f"condition is present",
                })

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: severity_rank.get(f.get("severity", "info"), 3))

    grade = _grade_for(score)
    if any(f.get("severity") == "critical" for f in flags):
        grade = _cap_grade(grade, CRITICAL_FLAG_MAX_GRADE)
    if edge_score < 40.0:
        grade = _cap_grade(grade, "C")

    critical = [f for f in flags if f.get("severity") == "critical"]
    warnings_ = [f for f in flags if f.get("severity") == "warning"]

    return {
        "available": True,
        "grade": grade,
        "score": round(score, 2),
        "components": components,
        "flags": flags,
        "flagCounts": {"critical": len(critical), "warning": len(warnings_),
                       "info": len(flags) - len(critical) - len(warnings_)},
        "summary": _summarise(grade, score, flags),
        "assumptions": {
            "weights": dict(cfg.weights),
            "minTrades": cfg.min_trades,
            "gradedOn": sorted(available.keys()),
            "notGradedOn": sorted(set(weights) - set(available)),
        },
    }


def _summarise(grade: str, score: float, flags: list[dict[str, Any]]) -> str:
    critical = [f for f in flags if f.get("severity") == "critical"]
    if critical:
        return (f"Grade {grade} ({score:.0f}/100): {critical[0]['message']}.")
    warnings_ = [f for f in flags if f.get("severity") == "warning"]
    if warnings_:
        return (f"Grade {grade} ({score:.0f}/100): the edge is measurable, but "
                f"{warnings_[0]['message']}.")
    return (f"Grade {grade} ({score:.0f}/100): the edge is measurable, survives "
            f"resampling and is not concentrated in one condition.")


__all__ = [
    "CRITICAL_FLAG_MAX_GRADE",
    "GRADES",
    "GRADE_THRESHOLDS",
    "VerdictConfig",
    "VerdictError",
    "grade_edge",
]
