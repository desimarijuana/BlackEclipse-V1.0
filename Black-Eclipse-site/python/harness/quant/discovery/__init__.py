"""Quant method discovery — find, adapt and invent tradable methods.

This package is the *point* of quant mode, not a side feature:

  * `taxonomy`    — the method families a user can understand and choose from;
  * `library`     — method cards and fit-ranked recommendations;
  * `diagnostics` — what the data actually looks like (trend, mean reversion,
                    seasonality, volatility clustering, cointegration);
  * `hypotheses`  — testable hypotheses derived from those diagnostics;
  * `synthesize`  — turn a method into a valid StrategySpec;
  * `miner`       — search parameterizations and compositions, with IS/OOS
                    evidence and an honest trial count.

The engine computes; the library records. Nothing here invents a result.
"""

from __future__ import annotations

from .diagnostics import analyze_structure
from .hypotheses import generate_hypotheses
from .library import get_method_card, list_method_families, recommend_methods
from .miner import mine_methods
from .synthesize import build_strategy, build_combination

__all__ = [
    "analyze_structure",
    "build_combination",
    "build_strategy",
    "generate_hypotheses",
    "get_method_card",
    "list_method_families",
    "mine_methods",
    "recommend_methods",
]
