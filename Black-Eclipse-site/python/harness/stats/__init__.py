"""BlackEclipse Statistical Analysis & Feature Engineering Engine.

A deterministic, reusable statistical computing service. Every tool shares:

  * a validated input contract (`base.validate_*`),
  * a uniform response envelope (`base.make_response`),
  * explicit error semantics (`base.StatsError`),
  * provenance + reproducibility metadata (`base.Provenance`).

The engine is pure NumPy + the Python standard library so it installs and runs
under the same vendored interpreter the rest of the harness uses, with no heavy
scientific dependency added. Where a method needs a distribution (Student-t,
chi-square, F, normal) the CDF/quantile is implemented in `dist` and unit-tested
against published values.

Public surface:

  * `STATS_VERSION`   — engine version recorded in every response.
  * `StatsError`      — structured, non-fabricating error.
  * `TOOLS`           — the registry of the fourteen statistical tools.
  * `run_tool(name, args)` / `get_tool(name)` — deterministic dispatch.

The fourteen tools:
  calculate_returns, calculate_volatility, calculate_correlation,
  calculate_beta, calculate_drawdown, calculate_stationarity,
  calculate_cointegration, calculate_autocorrelation, calculate_regression,
  calculate_regime, build_features, detect_outliers, analyze_lead_lag,
  calculate_information_coefficient
"""

from __future__ import annotations

from .base import STATS_VERSION, Provenance, StatsError, make_response
from .registry import TOOLS, TOOL_NAMES, get_tool, register, run_tool, run_tool_safe

__all__ = [
    "STATS_VERSION",
    "Provenance",
    "StatsError",
    "TOOLS",
    "TOOL_NAMES",
    "get_tool",
    "make_response",
    "register",
    "run_tool",
    "run_tool_safe",
]
