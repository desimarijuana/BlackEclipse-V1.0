"""Turn market structure into testable hypotheses.

A hypothesis is a falsifiable statement with a stated test and acceptance rule.
This module composes those from the diagnostics and the method library — it does
not claim the hypothesis is true. Each one carries its invalidation condition so
a failed test is informative rather than embarrassing.
"""

from __future__ import annotations

from typing import Any, Optional

from .taxonomy import family_by_id


def _hypothesis(method_id: str, statement: str, rationale: str, *,
                acceptance: str, invalidation: str, priority: int,
                test: str) -> dict[str, Any]:
    family = family_by_id(method_id)
    return {
        "methodId": method_id,
        "method": family.name if family else method_id,
        "statement": statement,
        "rationale": rationale,
        "test": test,
        "acceptance": acceptance,
        "invalidation": invalidation,
        "priority": priority,
        "status": "proposed",
    }


def generate_hypotheses(diagnostics: dict[str, Any], *, symbol: str = "",
                        max_hypotheses: int = 8) -> dict[str, Any]:
    structure = diagnostics.get("structure")
    metrics = diagnostics.get("metrics") or {}
    candidates = diagnostics.get("candidateMethods") or []
    stability = diagnostics.get("outOfSampleStability") or {}
    season = diagnostics.get("seasonality") or {}
    out: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        if len(out) < max_hypotheses:
            out.append(item)

    if structure in ("trending", "drifting"):
        hl = metrics.get("meanReversionHalfLifeBars")
        add(_hypothesis(
            "trend_ema_cross",
            f"{symbol or 'The instrument'} exhibits persistent structure; a fast/slow "
            "EMA crossover should capture a positive risk-adjusted trend premium.",
            "Hurst/variance-ratio diagnostics lean persistent; trend following is "
            "the natural expression of that persistence.",
            acceptance="out-of-sample Sharpe > 0.5 after costs, at least 30 OOS trades, "
                       "and a positive result in at least 2 of 3 walk-forward folds.",
            invalidation="OOS Sharpe <= 0, or the edge disappears at 2x costs, or the "
                         "result is concentrated in fewer than 10% of trades.",
            priority=1,
            test="synthesize the EMA-cross spec and run the research suite "
                 "(walk-forward, Monte-Carlo, robustness).",
        ))
        add(_hypothesis(
            "trend_donchian_breakout",
            f"A {symbol or 'instrument'} breakout of its N-bar range should continue "
            "more often than it fails after costs.",
            "Breakouts express the same persistence through a channel rule and can "
            "be more robust to averaging choices.",
            acceptance="positive OOS expectancy and a false-breakout rate low enough "
                       "that average win × win rate exceeds average loss × loss rate.",
            invalidation="breakout entries lose after costs, or the result depends on "
                         "one lookback value.",
            priority=2,
            test="synthesize Donchian and compare lookbacks 20/55 OOS.",
        ))
    elif structure == "mean_reverting":
        hl = metrics.get("meanReversionHalfLifeBars")
        add(_hypothesis(
            "mean_reversion_bollinger",
            f"{symbol or 'The instrument'} dislocations from its moving mean revert "
            "faster than a random walk; a band re-entry should earn the reversion.",
            f"Negative short-horizon autocorrelation/low variance ratio"
            + (f"; half-life ≈ {hl:.0f} bars" if hl else "") + ".",
            acceptance="positive OOS expectancy after costs, with a holding period "
                       "consistent with the measured half-life.",
            invalidation="reversion is weaker than costs, or the left tail (trend "
                         "continuation) dominates.",
            priority=1,
            test="synthesize Bollinger reversion and run costs + tail analysis.",
        ))
        add(_hypothesis(
            "mean_reversion_rsi",
            "RSI exhaustion entries improve the reversion trade by avoiding entries "
            "in the middle of a move.",
            "A momentum oscillator adds an overreaction condition to the mean-"
            "reversion signal.",
            acceptance="OOS Sharpe improves over the unfiltered band rule, not just "
                       "in-sample.",
            invalidation="the RSI filter reduces trades without improving OOS "
                         "risk-adjusted return.",
            priority=2,
            test="compare RSI-filtered and unfiltered reversion OOS.",
        ))
    elif structure == "volatility_clustered":
        add(_hypothesis(
            "volatility_breakout",
            f"{symbol or 'The instrument'} compresses and expands volatility; trading "
            "the range break after compression should capture the expansion.",
            "Absolute-return autocorrelation shows volatility clustering, so a "
            "breakout timed after compression has a conditional edge.",
            acceptance="positive OOS expectancy and a wider return distribution on "
                       "breakout days than on non-breakout days.",
            invalidation="breakouts are indistinguishable from noise after costs.",
            priority=1,
            test="synthesize the volatility-breakout spec and compare expansion vs "
                 "non-expansion days.",
        ))
    else:
        add(_hypothesis(
            "trend_ema_cross",
            f"{symbol or 'The instrument'} may still have a conditional trend edge even "
            "though the unconditional structure looks random.",
            "A near-random unconditional series can hide trend in a sub-sample or "
            "regime; the test must be conditional, not assumed.",
            acceptance="a pre-registered regime split shows a positive OOS effect that "
                       "survives multiple-testing correction.",
            invalidation="no conditional split survives OOS or multiple testing.",
            priority=3,
            test="scan regimes first; only then test a method inside the regime.",
        ))

    if season.get("available"):
        strongest = season.get("strongest") or {}
        add(_hypothesis(
            "seasonality_calendar",
            f"Returns on {strongest.get('day', 'a weekday')} differ materially from the "
            "other weekdays and the effect survives costs.",
            "The weekday buckets differ in the sample; this is a calendar-flow hypothesis.",
            acceptance="the effect holds out-of-sample for at least 5 years and "
                       "survives a multiple-testing correction across 7 weekdays.",
            invalidation="the effect is absent in the OOS years or smaller than costs.",
            priority=3,
            test="long-sample weekday study with a Bonferroni/DSR correction.",
        ))

    if stability.get("available") and not stability.get("stable"):
        out.insert(0, _hypothesis(
            "trend_ema_cross",
            f"The structure of {symbol or 'the series'} changes out-of-sample; any method "
            "must therefore be regime-aware rather than unconditional.",
            "The in-sample and out-of-sample diagnostics disagree, which is a warning "
            "against a single unconditional rule.",
            acceptance="a method conditioned on a causal regime label beats the "
                       "unconditional version OOS.",
            invalidation="the conditional method does not improve OOS results.",
            priority=1,
            test="add a causal regime filter and compare OOS; do not fit the regime "
                 "on the full sample.",
        ))

    # Keep the diagnostics' own candidate ranking visible.
    return {
        "symbol": symbol,
        "structure": structure,
        "hypotheses": out,
        "candidateMethods": candidates,
        "note": "hypotheses are proposals; pre-register the acceptance rule before "
                "running the test, and record the trial.",
    }


__all__ = ["generate_hypotheses"]
