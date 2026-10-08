"""BlackEclipse Quant Engine — deterministic trading, backtesting and research.

The engine is the source of truth for trading calculations (P&L, fills, sizing,
drawdown, Sharpe, ...). The LLM orchestrates: it authors and edits *strategy
specifications* and calls tools; it never computes a metric itself.

Modules:
  * `strategy`     — the structured strategy contract + validation + versioning
  * `data`         — market-data adapter, point-in-time dataset, quality checks
  * `indicators`   — causal technical indicators
  * `rules`        — the rule DSL evaluator
  * `orders`       — order lifecycle + state machine
  * `execution`    — commission / slippage / spread / impact simulation
  * `sizing`       — position sizing methods
  * `risk`         — pre-trade risk limits
  * `portfolio`    — cash / positions / P&L / exposure
  * `metrics`      — performance, risk and trade statistics
  * `engine`       — the event-driven backtest loop + result envelope
  * `store`        — experiment/strategy persistence (agent-memory.db) + artifacts
  * `tools`        — agent tools
  * `routers`      — FastAPI surface
"""

from __future__ import annotations

from .engine import (
    ENGINE_VERSION,
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    run_backtest,
    run_portfolio_backtest,
)
from .strategy import (
    StrategySpec,
    bump_version,
    parse_strategy,
    validate_strategy,
)

__all__ = [
    "ENGINE_VERSION",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "StrategySpec",
    "bump_version",
    "parse_strategy",
    "run_backtest",
    "run_portfolio_backtest",
    "validate_strategy",
]
