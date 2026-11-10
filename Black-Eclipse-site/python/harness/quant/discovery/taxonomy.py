"""The method taxonomy — what a quant method is, in plain language.

A method is not a secret indicator. It is a *hypothesis about why a price moves*
plus the rules that express it, the data it needs, the conditions in which it
should work, and the ways it usually fails. This library makes those parts
explicit so a user can choose a method they understand instead of copying a
backtest they cannot defend.

Fields are deliberately descriptive, not predictive: `best_regimes` is a prior,
never a promise. The evidence status is a literature/runtime judgement, not a
measured result for the user's data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class MethodFamily:
    id: str
    name: str
    category: str
    thesis: str
    edge_source: str
    instruments: tuple[str, ...]
    horizons: tuple[str, ...]
    data_requirements: tuple[str, ...]
    signals: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)
    failure_modes: tuple[str, ...] = field(default_factory=tuple)
    best_regimes: tuple[str, ...] = field(default_factory=tuple)
    worst_regimes: tuple[str, ...] = field(default_factory=tuple)
    validation: str = ""
    capacity: str = ""
    complexity: int = 2                 # 1 simple .. 5 research-heavy
    evidence: int = 3                   # 1 weak .. 5 well-documented
    turnover: str = "medium"
    references: tuple[str, ...] = field(default_factory=tuple)
    builder: str = ""                   # synthesize.py builder key
    requires: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("instruments", "horizons", "data_requirements", "signals",
                    "failure_modes", "best_regimes", "worst_regimes",
                    "references", "requires"):
            data[key] = list(data[key])
        return data


FAMILIES: tuple[MethodFamily, ...] = (
    MethodFamily(
        id="trend_ema_cross",
        name="Trend following — EMA crossover",
        category="trend",
        thesis="Prices trend because information diffuses gradually and flows "
               "persist; a fast average crossing a slow average marks a change in "
               "the dominant flow.",
        edge_source="behavioural under-reaction, slow institutional rebalancing, "
                    "and the risk premium for holding trend exposure",
        instruments=("equity index", "single stocks", "FX", "crypto", "commodities"),
        horizons=("swing", "position", "long-term"),
        data_requirements=("OHLCV", "enough history for the slow average"),
        signals=("fast EMA vs slow EMA", "slope filter", "ADX"),
        params={"fast": 20, "slow": 50, "atr_period": 14, "stop_atr": 2.0,
                "target_r": 2.0},
        failure_modes=("whipsaw in flat markets", "late entries after gaps",
                       "parameter-sensitive in low volatility"),
        best_regimes=("trending up", "trending down", "normal/high volatility"),
        worst_regimes=("flat", "low volatility", "mean-reverting"),
        validation="walk-forward + regime attribution + cost sensitivity",
        capacity="high in liquid futures/FX; lower in small caps",
        complexity=1, evidence=4, turnover="low-medium",
        references=("Moskowitz, Ooi & Pedersen (2012), Time Series Momentum",
                    "Hurst, Ooi & Pedersen (2017), A Century of Evidence on Trend-Following"),
        builder="ema_cross",
    ),
    MethodFamily(
        id="trend_donchian_breakout",
        name="Trend following — Donchian breakout",
        category="trend",
        thesis="New highs/lowest lows reveal that buyers/sellers are willing to "
               "transact at prices not seen for a long window; breakouts capture "
               "the start of a new trend.",
        edge_source="anchoring and disposition effects, stop-run liquidity",
        instruments=("futures", "FX", "crypto", "equity index"),
        horizons=("swing", "position"),
        data_requirements=("OHLCV",),
        signals=("N-bar high/low", "ATR", "trend filter"),
        params={"lookback": 20, "exit_lookback": 10, "atr_period": 14,
                "stop_atr": 2.5},
        failure_modes=("false breakouts", "gap risk", "crowded levels"),
        best_regimes=("trending", "high volatility expansion"),
        worst_regimes=("range-bound", "low volatility"),
        validation="walk-forward + false-breakout rate + cost sensitivity",
        capacity="high in liquid futures",
        complexity=1, evidence=4, turnover="medium",
        references=("Donchian (1960), channel breakout", "Turtle Traders rules"),
        builder="donchian",
    ),
    MethodFamily(
        id="momentum_cross_sectional",
        name="Cross-sectional momentum",
        category="factor",
        thesis="Assets that outperformed over the past 3–12 months tend to "
               "continue outperforming relative to peers; losers continue to "
               "underperform.",
        edge_source="under-reaction, herding, career risk, slow information diffusion",
        instruments=("equities", "futures", "crypto"),
        horizons=("position", "long-term"),
        data_requirements=("cross-sectional prices", "universe membership", "survivorship control"),
        signals=("12-1 momentum", "rank", "volatility scaling"),
        params={"lookback": 252, "skip": 21, "quantiles": 5, "rebalance": 21},
        failure_modes=("momentum crashes", "crowding", "high turnover costs",
                       "survivorship bias"),
        best_regimes=("trending markets", "recoveries"),
        worst_regimes=("sharp reversals", "high dispersion"),
        validation="factor lab: IC/rank-IC, decay, quantile portfolio, promotion gate",
        capacity="limited by turnover and liquidity",
        complexity=3, evidence=5, turnover="medium-high",
        references=("Jegadeesh & Titman (1993)", "Asness, Moskowitz & Pedersen (2013)"),
        builder="cross_sectional", requires=("factor_lab",),
    ),
    MethodFamily(
        id="mean_reversion_bollinger",
        name="Mean reversion — Bollinger/z-score",
        category="mean_reversion",
        thesis="Short-horizon price dislocations away from a moving mean tend to "
               "partially revert when there is no new information.",
        edge_source="liquidity provision, overreaction, inventory effects",
        instruments=("equity index", "FX", "crypto", "single stocks"),
        horizons=("intraday", "swing"),
        data_requirements=("OHLCV", "volume for liquidity filter"),
        signals=("z-score of close vs SMA", "Bollinger bands", "RSI"),
        params={"period": 20, "entry_z": 2.0, "exit_z": 0.5, "stop_atr": 2.0},
        failure_modes=("catching a falling knife", "regime shift", "gap risk",
                       "transaction costs in high turnover"),
        best_regimes=("range-bound", "low volatility", "normal liquidity"),
        worst_regimes=("strong trends", "crises", "illiquid"),
        validation="walk-forward + cost sensitivity + tail/regime analysis",
        capacity="medium; turnover-bound",
        complexity=1, evidence=3, turnover="high",
        references=("Bollinger (2001)", "Potter (1999), mean-reversion strategies"),
        builder="bollinger",
    ),
    MethodFamily(
        id="mean_reversion_rsi",
        name="Mean reversion — RSI exhaustion",
        category="mean_reversion",
        thesis="A sustained run of one-sided closes marks exhaustion; odds of a "
               "short-term bounce rise once the move is stretched.",
        edge_source="overreaction and forced selling/buying",
        instruments=("equity index", "single stocks", "crypto"),
        horizons=("swing",),
        data_requirements=("OHLCV",),
        signals=("RSI", "trend filter", "ATR"),
        params={"period": 14, "oversold": 30, "overbought": 70, "stop_atr": 2.0},
        failure_modes=("trend continuation", "value traps", "earnings gaps"),
        best_regimes=("range-bound", "moderate volatility"),
        worst_regimes=("persistent downtrends", "panic"),
        validation="walk-forward + regime attribution + cost sensitivity",
        capacity="medium",
        complexity=1, evidence=3, turnover="medium-high",
        references=("Wilder (1978), New Concepts in Technical Trading Systems",),
        builder="rsi",
    ),
    MethodFamily(
        id="pairs_cointegration",
        name="Statistical arbitrage — cointegrated pairs",
        category="stat_arb",
        thesis="Two economically linked assets share a long-run equilibrium; a "
               "temporary spread widening tends to converge.",
        edge_source="relative-value liquidity provision and slow convergence",
        instruments=("equities", "ETFs", "futures", "crypto"),
        horizons=("intraday", "swing"),
        data_requirements=("synchronised prices", "borrow/locate for shorts",
                           "corporate actions"),
        signals=("cointegration test", "spread z-score", "half-life"),
        params={"lookback": 120, "entry_z": 2.0, "exit_z": 0.5, "max_half_life": 30},
        failure_modes=("structural break", "one leg halts", "borrow recall",
                       "spurious cointegration"),
        best_regimes=("range-bound", "stable dispersion"),
        worst_regimes=("structural shocks", "one-sided sector moves"),
        validation="out-of-sample cointegration + half-life stability + borrow costs",
        capacity="low-medium; pair-specific",
        complexity=4, evidence=3, turnover="high",
        references=("Gatev, Goetzmann & Rouwenhorst (2006)", "Engle & Granger (1987)"),
        builder="pairs", requires=("stats_cointegration", "shorting"),
    ),
    MethodFamily(
        id="carry_futures",
        name="Carry — futures term structure",
        category="carry",
        thesis="A futures curve in backwardation pays a roll yield to the long; "
               "contango pays the short. Carry is compensation for storage, "
               "financing and convenience yield.",
        edge_source="risk transfer, convenience yield, financing frictions",
        instruments=("commodity futures", "bond futures", "FX", "equity index futures"),
        horizons=("position", "long-term"),
        data_requirements=("multiple contract expiries", "roll schedule", "margin/costs"),
        signals=("annualized carry", "curve shape", "open interest"),
        params={"min_carry_bps": 100, "rebalance": 21, "max_contracts": 3},
        failure_modes=("curve inversion", "storage shocks", "roll cost > carry",
                       "delivery/contract risk"),
        best_regimes=("stable curves", "supply tightness"),
        worst_regimes=("demand collapse", "storage glut"),
        validation="term-structure data + roll-cost accounting + stress",
        capacity="high in liquid futures",
        complexity=3, evidence=4, turnover="low",
        references=("Gorton & Rouwenhorst (2006)", "Koijen et al. (2018), Carry"),
        builder="carry", requires=("futures_term_structure",),
    ),
    MethodFamily(
        id="crypto_funding_basis",
        name="Crypto — funding / basis carry",
        category="carry",
        thesis="Perpetual funding and futures basis reflect leveraged demand; a "
               "systematic short perp / long spot (or basis) position earns the "
               "funding premium while bearing liquidation and exchange risk.",
        edge_source="leverage demand, retail positioning, exchange frictions",
        instruments=("crypto perpetuals", "crypto futures", "spot"),
        horizons=("intraday", "swing", "position"),
        data_requirements=("funding rates", "perp + spot prices", "exchange fees",
                           "margin rules"),
        signals=("funding rate", "basis", "open interest", "liquidation map"),
        params={"min_funding_bps": 2, "max_leverage": 2.0, "rebalance_hours": 8},
        failure_modes=("exchange/counterparty risk", "liquidation cascade",
                       "funding flip", "withdrawal freezes"),
        best_regimes=("bullish leverage demand", "high funding"),
        worst_regimes=("deleveraging", "exchange stress"),
        validation="funding history + fee/margin modelling + stress",
        capacity="exchange-dependent",
        complexity=3, evidence=2, turnover="medium",
        references=("Crypto carry literature; exchange funding mechanics",),
        builder="funding", requires=("funding_data",),
    ),
    MethodFamily(
        id="low_volatility",
        name="Low-volatility / min-variance",
        category="factor",
        thesis="Lower-risk assets have historically delivered higher risk-adjusted "
               "returns than high-risk assets, contrary to simple CAPM.",
        edge_source="leverage constraints, lottery preference, benchmark hugging",
        instruments=("equities", "ETFs", "crypto"),
        horizons=("position", "long-term"),
        data_requirements=("cross-sectional returns", "universe membership"),
        signals=("realized volatility rank", "beta", "covariance"),
        params={"lookback": 126, "quantiles": 5, "rebalance": 21},
        failure_modes=("crowding", "rate shocks", "value/growth rotation"),
        best_regimes=("risk-off", "stable rates"),
        worst_regimes=("sharp risk-on rallies", "rate spikes"),
        validation="factor lab + portfolio construction + stress",
        capacity="medium-high",
        complexity=3, evidence=5, turnover="low-medium",
        references=("Ang et al. (2006)", "Frazzini & Pedersen (2014), Betting Against Beta"),
        builder="low_vol", requires=("factor_lab", "cross_section"),
    ),
    MethodFamily(
        id="seasonality_calendar",
        name="Seasonality / calendar effects",
        category="seasonality",
        thesis="Recurring calendar flows (month-end rebalancing, day-of-week, "
               "commodity seasons) create predictable pressure.",
        edge_source="scheduled flows, tax/liquidity cycles, behavioural patterns",
        instruments=("equities", "FX", "commodities"),
        horizons=("intraday", "swing"),
        data_requirements=("long history", "calendar/timezone", "transaction costs"),
        signals=("day-of-week", "month-end", "turn-of-month", "commodity season"),
        params={"min_years": 5, "effect": "day_of_week"},
        failure_modes=("data mining", "regime change", "cost > effect",
                       "multiple-testing"),
        best_regimes=("stable calendar flows",),
        worst_regimes=("structural market changes",),
        validation="long sample + multiple-testing correction + OOS years",
        capacity="high in liquid markets, low in niche ones",
        complexity=2, evidence=2, turnover="high",
        references=("Ariel (1987), monthly effect", "French (1980), weekend effect"),
        builder="seasonality",
    ),
    MethodFamily(
        id="volatility_breakout",
        name="Volatility breakout / range expansion",
        category="volatility",
        thesis="Volatility clusters: a compression is often followed by an "
               "expansion. Trading the expansion captures the directional move "
               "after a quiet period.",
        edge_source="volatility clustering, stop-run liquidity",
        instruments=("FX", "futures", "crypto", "equity index"),
        horizons=("intraday", "swing"),
        data_requirements=("OHLCV", "ATR/realized vol"),
        signals=("ATR compression", "NR7", "breakout of prior range"),
        params={"compression_lookback": 10, "breakout_lookback": 20, "atr_period": 14},
        failure_modes=("false expansion", "gap risk", "whipsaw"),
        best_regimes=("post-compression", "event-driven"),
        worst_regimes=("persistent low volatility", "thin liquidity"),
        validation="walk-forward + event-window analysis + costs",
        capacity="medium",
        complexity=2, evidence=3, turnover="medium",
        references=("Volatility clustering literature; NR7/inside-day patterns",),
        builder="vol_breakout",
    ),
    MethodFamily(
        id="ml_direction",
        name="Machine-learning direction model",
        category="ml",
        thesis="Non-linear combinations of returns, volatility and cross-sectional "
               "features may predict the sign of the next move better than a "
               "single rule.",
        edge_source="non-linearities, feature interactions, alternative data",
        instruments=("equities", "crypto", "FX", "futures"),
        horizons=("intraday", "swing", "position"),
        data_requirements=("leakage-safe features", "purged CV", "large sample",
                           "naive baseline"),
        signals=("returns", "realized vol", "breadth", "fundamentals", "alt data"),
        params={"horizon": 1, "model": "gradient_boosting", "purge": 5,
                "embargo": 2, "min_rows": 500},
        failure_modes=("leakage", "overfitting", "regime shift", "feature drift",
                       "low signal-to-noise"),
        best_regimes=("stable feature relationships",),
        worst_regimes=("structural breaks",),
        validation="ML lab: purged walk-forward, naive baseline, drift, registry",
        capacity="strategy-dependent",
        complexity=5, evidence=3, turnover="medium",
        references=("Gu, Kelly & Xiu (2020), Empirical Asset Pricing via Machine Learning",),
        builder="ml", requires=("ml_lab",),
    ),
    MethodFamily(
        id="options_income",
        name="Options income — covered call / cash-secured put",
        category="options",
        thesis="Selling volatility earns the variance risk premium; the seller "
               "accepts capped upside or downside in exchange for premium.",
        edge_source="variance risk premium, insurance demand, dealer positioning",
        instruments=("equity index options", "single-stock options", "crypto options"),
        horizons=("swing", "position"),
        data_requirements=("option chains", "IV surface", "margin", "assignment"),
        signals=("IV vs realized", "skew", "delta", "term structure"),
        params={"delta": 0.30, "dte": 30, "roll_dte": 7, "max_notional_pct": 50},
        failure_modes=("gap risk", "vol spike", "assignment", "liquidity"),
        best_regimes=("high IV / calm realised", "range-bound"),
        worst_regimes=("crash", "vol expansion"),
        validation="chain-marked backtest + stress + assignment modelling",
        capacity="liquidity-dependent",
        complexity=4, evidence=4, turnover="medium",
        references=("Carr & Wu (2009), Variance Risk Premiums",),
        builder="options_income", requires=("option_chain_history", "margin"),
    ),
    MethodFamily(
        id="event_drift",
        name="Event-driven — post-earnings / announcement drift",
        category="event",
        thesis="Prices under-react to new information; the drift after an earnings "
               "or guidance surprise persists for days/weeks.",
        edge_source="information diffusion, limited attention, slow institutional flow",
        instruments=("single stocks", "equity index"),
        horizons=("swing",),
        data_requirements=("event calendar", "surprise data", "point-in-time fundamentals"),
        signals=("earnings surprise", "guidance change", "price reaction"),
        params={"surprise_threshold": 0.05, "hold_days": 20, "stop_atr": 2.0},
        failure_modes=("survivorship", "look-ahead in surprise data",
                       "crowding", "reversal"),
        best_regimes=("dispersion", "earnings season"),
        worst_regimes=("macro-driven markets",),
        validation="point-in-time events + event-window study + OOS",
        capacity="medium; liquidity-dependent",
        complexity=4, evidence=4, turnover="medium",
        references=("Bernard & Thomas (1989)", "Ball & Brown (1968)"),
        builder="event", requires=("event_calendar", "point_in_time_fundamentals"),
    ),
)


_BY_ID = {family.id: family for family in FAMILIES}


def all_families() -> tuple[MethodFamily, ...]:
    return FAMILIES


def family_by_id(method_id: str) -> Optional[MethodFamily]:
    return _BY_ID.get(str(method_id))


__all__ = ["FAMILIES", "MethodFamily", "all_families", "family_by_id"]
