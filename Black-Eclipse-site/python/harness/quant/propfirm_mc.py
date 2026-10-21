"""Monte-Carlo over a prop-firm evaluation.

`propfirm.py` applies the rules to **one** sequence of trading days. This
module asks the harder question: *given this trading history, how often would
the rules have been satisfied?*

The uncertainty is expressed by **resampling trading days**, not individual
trades. That choice matters: the rules are day-based (a daily loss limit, an
end-of-day drawdown, an access period), and a trader's days cluster — a good
streak is three good days, not three good trades scattered across a month.
Resampling trades would destroy exactly the structure the rules act on.

Two resampling modes:

  * `block` — days are drawn in runs (a stationary bootstrap over the day
    sequence), so streaks of good and bad days survive the resample;
  * `iid` — each day is drawn independently, which flatters the result and is
    the honest lower bar.

Every path is evaluated against the **real** rules, so a path can fail exactly
the way a live account fails: a maximum-loss breach, a daily-loss breach, a
consistency violation, or the access period expiring.

What the engine cannot see is stated, not hidden: prop firms liquidate on
*intraday* equity including unrealised P&L, and a log of closed trades cannot
reconstruct an intraday drawdown that recovered before the close. Every report
carries that caveat.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .propfirm import (
    OUTCOMES,
    PhaseOutcome,
    PropAccountSize,
    PropFirmSpec,
    TradingDay,
    group_by_day,
    normalise_trades,
    simulate_phase,
)


class PropFirmMonteCarloError(ValueError):
    pass


@dataclass
class PropFirmMonteCarloConfig:
    simulations: int = 500
    seed: int = 42
    resample: str = "block"          # block | iid
    block_length: float = 1.0        # mean consecutive days per draw
    fee_per_attempt: float = 0.0     # what one attempt costs the trader
    reset_fee: float = 0.0           # what a failed attempt costs to restart
    simulate_funded: bool = True

    def validate(self) -> None:
        if self.simulations < 1:
            raise PropFirmMonteCarloError("simulations must be >= 1")
        if self.resample not in ("block", "iid"):
            raise PropFirmMonteCarloError(
                f"unknown resample mode {self.resample!r}; expected block or iid")
        if self.block_length <= 0:
            raise PropFirmMonteCarloError("block_length must be > 0")
        if self.fee_per_attempt < 0 or self.reset_fee < 0:
            raise PropFirmMonteCarloError("fees must be >= 0")


def _resample_days(rng: random.Random, days: list[TradingDay], count: int,
                   mode: str, block_length: float) -> list[TradingDay]:
    """Draw `count` trading days, keeping runs of consecutive days intact."""
    total = len(days)
    if total == 0 or count <= 0:
        return []
    if mode == "iid":
        return [days[rng.randrange(total)] for _ in range(count)]
    out: list[TradingDay] = []
    p = 1.0 / max(1.0, float(block_length))
    guard = 0
    while len(out) < count and guard < 100_000:
        guard += 1
        start = rng.randrange(total)
        length = 1
        while rng.random() > p and length < total:
            length += 1
        for j in range(length):
            out.append(days[(start + j) % total])
    return out[:count]


def _percentiles(values: list[float]) -> dict[str, Optional[float]]:
    if not values:
        return {"p5": None, "p25": None, "p50": None, "p75": None, "p95": None,
                "mean": None, "min": None, "max": None}
    arr = np.array(values, dtype=float)
    out: dict[str, Optional[float]] = {}
    for point in (5, 25, 50, 75, 95):
        out[f"p{point}"] = round(float(np.percentile(arr, point)), 4)
    out["mean"] = round(float(arr.mean()), 4)
    out["min"] = round(float(arr.min()), 4)
    out["max"] = round(float(arr.max()), 4)
    return out


def run_prop_firm_monte_carlo(
    trades: list[dict[str, Any]],
    spec: PropFirmSpec,
    size: PropAccountSize,
    config: Optional[PropFirmMonteCarloConfig] = None,
) -> dict[str, Any]:
    """Evaluate a trade log against a firm's rules, then resample it."""
    cfg = config or PropFirmMonteCarloConfig()
    cfg.validate()
    spec.validate()

    warnings: list[str] = []
    if spec.day_offset_hours:
        warnings.append(
            "PROP_SESSION_BOUNDARY_APPROXIMATE: the trading day boundary for this "
            "firm is approximated with a fixed UTC offset; daylight saving is not "
            "modelled, so day-level results are approximate")
    warnings.append(
        "PROP_INTRADAY_EQUITY_NOT_MODELED: prop firms liquidate on intraday "
        "equity including unrealised P&L. This engine sees closed trades only, so "
        "an intraday drawdown that recovered before the close cannot be detected.")

    normalised, trade_warnings = normalise_trades(trades, spec.day_offset_hours)
    warnings.extend(trade_warnings)
    days = group_by_day(normalised)

    if not days:
        return {
            "available": False,
            "reason": "the trade log contains no usable closed trades",
            "firm": spec.to_dict(),
            "size": size.id,
            "warnings": warnings,
        }

    baseline = simulate_phase(days, spec.evaluation, size)
    baseline_funded: Optional[PhaseOutcome] = None
    if cfg.simulate_funded and baseline.status == "passed":
        baseline_funded = simulate_phase(days, spec.funded, size, payouts=True)

    rng = random.Random(cfg.seed)
    outcomes: dict[str, int] = {status: 0 for status in OUTCOMES}
    days_to_pass: list[float] = []
    funded_payouts: list[float] = []
    funded_profits: list[float] = []
    path_ev: list[float] = []
    session_breaks: list[float] = []
    consistency_hits: list[float] = []

    for _ in range(cfg.simulations):
        path = _resample_days(rng, days, len(days), cfg.resample, cfg.block_length)
        result = simulate_phase(path, spec.evaluation, size)
        outcomes[result.status] = outcomes.get(result.status, 0) + 1
        session_breaks.append(float(result.session_breaks))
        consistency_hits.append(float(len(result.consistency_violations)))
        if result.status == "passed":
            days_to_pass.append(float(result.trading_days))
            funded_payout = 0.0
            funded_profit = 0.0
            if cfg.simulate_funded:
                remaining = path[result.trading_days:] or path
                funded = simulate_phase(remaining, spec.funded, size, payouts=True)
                funded_payout = funded.total_payout
                funded_profit = funded.net_profit
            funded_payouts.append(funded_payout)
            funded_profits.append(funded_profit)
            path_ev.append(funded_payout - cfg.fee_per_attempt)
        else:
            path_ev.append(-cfg.fee_per_attempt)

    total = max(1, cfg.simulations)
    passed = outcomes.get("passed", 0)
    pass_probability = passed / total * 100.0

    expected_attempts = (total / passed) if passed else None
    expected_resets = (expected_attempts - 1.0) if expected_attempts else None
    cost_to_pass = None
    if expected_attempts:
        cost_to_pass = cfg.fee_per_attempt + (expected_resets or 0.0) * cfg.reset_fee

    ev = _percentiles(path_ev)
    if not (cfg.fee_per_attempt or cfg.reset_fee):
        # No fee means the economics are an UPPER BOUND. Say so, loudly, in the
        # report - a missing input must never quietly flatter a number.
        warnings.append(
            "PROP_FIRM_NO_FEE_SUPPLIED: no fee or reset fee was supplied, so the "
            "net expected value is GROSS of every cost. Pass the firm's current "
            "price to get a forecast rather than an upper bound.")
    report: dict[str, Any] = {
        "available": True,
        "firm": {
            "id": spec.id, "name": spec.name, "source": spec.source,
            "asOf": spec.as_of, "notes": spec.notes,
        },
        "size": {
            "id": size.id, "label": size.label, "accountSize": size.account_size,
            "profitTarget": size.profit_target, "maxLoss": size.max_loss,
            "dailyLossLimit": size.daily_loss_limit,
            "minTradingDays": size.min_trading_days,
            "maxTradingDays": size.max_trading_days,
            "notes": size.notes,
        },
        "log": {
            "trades": len(normalised),
            "tradingDays": len(days),
            "firstDay": days[0].day,
            "lastDay": days[-1].day,
            "netPnl": round(sum(d.pnl for d in days), 4),
            "bestDay": round(max(d.pnl for d in days), 4),
            "worstDay": round(min(d.pnl for d in days), 4),
        },
        "baseline": {
            "evaluation": baseline.to_dict(),
            "funded": baseline_funded.to_dict() if baseline_funded else None,
        },
        "monteCarlo": {
            "simulations": cfg.simulations,
            "resample": cfg.resample,
            "blockLength": cfg.block_length,
            "seed": cfg.seed,
            "passProbability": round(pass_probability, 4),
            "outcomes": outcomes,
            "tradingDaysToPass": _percentiles(days_to_pass),
            "sessionBreaksPerPath": round(float(np.mean(session_breaks)), 4)
            if session_breaks else None,
            "consistencyViolationsPerPath": round(float(np.mean(consistency_hits)), 4)
            if consistency_hits else None,
            "funded": {
                "payoutProbability": round(len([p for p in funded_payouts if p > 0])
                                          / total * 100.0, 4),
                "payout": _percentiles(funded_payouts),
                "netProfit": _percentiles(funded_profits),
            } if cfg.simulate_funded else None,
            "economics": {
                "netEVPerAttempt": ev["mean"],
                "netEVp5": ev["p5"],
                "netEVp95": ev["p95"],
                "feePerAttempt": cfg.fee_per_attempt,
                "resetFee": cfg.reset_fee,
                "expectedAttempts": round(expected_attempts, 4) if expected_attempts else None,
                "expectedResetsToPass": (round(expected_resets, 4)
                                         if expected_resets is not None else None),
                "costToPass": round(cost_to_pass, 4) if cost_to_pass is not None else None,
            },
        },
        "warnings": warnings,
        "assumptions": {
            "intradayEquityModelled": False,
            "daysResampled": True,
            "resampleUnit": "trading_day",
            "feePerAttempt": cfg.fee_per_attempt,
            "resetFee": cfg.reset_fee,
            "feeSupplied": bool(cfg.fee_per_attempt or cfg.reset_fee),
            "rulesAsOf": spec.as_of,
            "note": ("the net EV above is NET of the fee and reset fee you "
                     "supplied. The engine never invents a price, so with no fee "
                     "supplied the EV is GROSS of every cost - treat it as an "
                     "upper bound, not a forecast."),
        },
    }
    return report


__all__ = [
    "PropFirmMonteCarloConfig",
    "PropFirmMonteCarloError",
    "run_prop_firm_monte_carlo",
]
