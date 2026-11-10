"""Turn a research problem into a deterministic query set.

A single web query such as "volatility trading strategy" is not a literature
review. This planner expands the user's objective into the *topics* a researcher
would actually search, so the scholarly connectors see more than one phrasing.

It is lexical and pure: no model call, no network. The model may add queries,
but it receives this set as the minimum plan.
"""

from __future__ import annotations

import re
from typing import Any

_TOPICS: dict[str, tuple[str, ...]] = {
    "volatility_forecasting": (
        "volatility forecasting models financial markets",
        "conditional heteroskedasticity models",
        "GARCH model variations volatility",
        "realized volatility forecasting",
        "stochastic volatility models",
        "HAR-RV realized volatility",
        "regime dependent volatility models",
        "volatility clustering and persistence",
        "volatility forecasting under structural breaks",
        "intraday volatility estimation",
        "volatility expansion before directional moves",
    ),
    "mean_reversion": (
        "mean reversion financial time series",
        "Ornstein-Uhlenbeck estimation half-life",
        "Kalman filter pairs trading",
        "cointegration pairs trading",
        "spread mean reversion transaction costs",
    ),
    "regime_detection": (
        "market regime detection hidden Markov model",
        "Markov switching financial returns",
        "change point detection financial time series",
        "structural break detection asset returns",
        "regime classification trend volatility",
    ),
    "statistical_arbitrage": (
        "statistical arbitrage cointegration",
        "pairs trading cointegration out of sample",
        "relative value factor model",
        "hedge ratio estimation stability",
    ),
    "microstructure": (
        "order flow imbalance price impact",
        "VPIN informed trading liquidity",
        "Kyle lambda market depth",
        "market microstructure high frequency data",
        "liquidity imbalance short term returns",
    ),
    "tail_risk": (
        "extreme value theory value at risk",
        "generalized Pareto distribution tail risk",
        "expected shortfall estimation",
        "tail risk forecasting financial returns",
    ),
    "factor_models": (
        "Fama French factor model",
        "CAPM empirical test",
        "principal component factor model returns",
        "factor exposure estimation",
    ),
    "execution": (
        "optimal execution Almgren Chriss",
        "market impact model",
        "transaction cost optimal trading schedule",
        "implementation shortfall",
    ),
    "machine_learning": (
        "machine learning return prediction finance",
        "gradient boosting financial time series",
        "purged walk forward cross validation",
        "feature leakage financial machine learning",
    ),
    "momentum": (
        "time series momentum",
        "cross sectional momentum",
        "trend following transaction costs",
        "momentum crash regimes",
    ),
    "risk_modeling": (
        "risk model covariance estimation",
        "value at risk backtesting",
        "portfolio risk parity",
        "volatility targeting",
    ),
}

_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("volatil", "volatility_forecasting"), ("garch", "volatility_forecasting"),
    ("variance", "volatility_forecasting"), ("heterosked", "volatility_forecasting"),
    ("realized", "volatility_forecasting"), ("har-rv", "volatility_forecasting"),
    ("mean reversion", "mean_reversion"), ("mean-reversion", "mean_reversion"),
    ("ornstein", "mean_reversion"), ("half-life", "mean_reversion"),
    ("half life", "mean_reversion"), ("kalman", "mean_reversion"),
    ("regime", "regime_detection"), ("markov", "regime_detection"),
    ("change point", "regime_detection"), ("structural break", "regime_detection"),
    ("cointegration", "statistical_arbitrage"), ("pairs", "statistical_arbitrage"),
    ("relative value", "statistical_arbitrage"), ("stat arb", "statistical_arbitrage"),
    ("order flow", "microstructure"), ("orderflow", "microstructure"),
    ("liquidity", "microstructure"), ("vpin", "microstructure"),
    ("kyle", "microstructure"), ("imbalance", "microstructure"),
    ("tail risk", "tail_risk"), ("extreme value", "tail_risk"),
    ("cvar", "tail_risk"), ("expected shortfall", "tail_risk"),
    ("var ", "tail_risk"),
    ("factor model", "factor_models"), ("fama", "factor_models"),
    ("capm", "factor_models"), ("pca", "factor_models"),
    ("execution", "execution"), ("market impact", "execution"),
    ("almgren", "execution"), ("slippage", "execution"),
    ("machine learning", "machine_learning"), ("gradient boosting", "machine_learning"),
    ("xgboost", "machine_learning"), ("lightgbm", "machine_learning"),
    ("momentum", "momentum"), ("trend", "momentum"),
    ("risk model", "risk_modeling"), ("risk parity", "risk_modeling"),
    ("drawdown", "risk_modeling"), ("portfolio risk", "risk_modeling"),
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def topics_for(objective: str, problem: str = "") -> list[str]:
    text = f"{_norm(objective)} {_norm(problem)}"
    found: list[str] = []
    for keyword, topic in _KEYWORDS:
        if keyword in text and topic not in found:
            found.append(topic)
    return found


def plan_queries(
    objective: str,
    *,
    problem: str = "",
    instrument: str = "",
    timeframe: str = "",
    extra: list[str] | None = None,
    max_queries: int = 12,
) -> dict[str, Any]:
    """Return the research scope and a deduplicated query set with reasons."""
    objective_text = _norm(objective) or _norm(problem)
    topics = topics_for(objective, problem)
    queries: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(query: str, reason: str) -> None:
        key = _norm(query)
        if not key or key in seen:
            return
        seen.add(key)
        queries.append({"query": query, "reason": reason})

    scope = " ".join(
        part for part in (
            _norm(instrument), _norm(timeframe), objective_text,
        ) if part
    ).strip()
    if scope:
        add(scope, "the user's stated problem")
    if instrument and timeframe:
        add(f"{instrument} {timeframe} empirical study", "instrument and timeframe")
    for topic in topics:
        for query in _TOPICS.get(topic, ()):
            add(query, f"topic: {topic}")
    for query in extra or []:
        add(str(query), "caller supplied")
    if not queries:
        add(objective_text or "quantitative finance method", "fallback problem statement")

    depth = "deep" if len(topics) > 1 or len(queries) >= 8 else "comparative"
    return {
        "objective": objective or problem,
        "instrument": instrument,
        "timeframe": timeframe,
        "topics": topics,
        "queries": queries[:max_queries],
        "researchDepth": depth,
        "note": (
            "Queries are search topics, not conclusions. An empty search result "
            "is not evidence that no research exists."
        ),
    }


__all__ = ["plan_queries", "topics_for"]
