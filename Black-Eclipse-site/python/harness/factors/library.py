"""Built-in factor library.

Each factor is a *documented, versioned* definition whose behaviour is produced
by the SAME safe formula engine the statistical layer uses
(`harness.stats.formula`). Expressions are per-instrument time series over the
supported inputs, so a universe panel is assembled by evaluating the formula for
each instrument and stacking the results.

`available` is honest: a factor is unavailable when its required inputs cannot be
supplied by the current data surface. Value / quality / carry factors need
point-in-time fundamentals (and, for carry, contract specifications); they are
declared here with `available=False` and a reason rather than fabricated from
prices.
"""

from __future__ import annotations

from typing import Any

# formula-input names understood by the engine's dataset adapter
PRICE_INPUTS = ["close", "open", "high", "low", "volume"]

BUILTIN_FACTORS: list[dict[str, Any]] = [
    # ── momentum ─────────────────────────────────────────────────────────────
    {"name": "momentum_1m", "family": "momentum", "direction": "positive", "lookback": 21,
     "description": "Trailing 1-month price momentum (21 trading sessions).",
     "expression": "pct_change(close, 21)", "inputs": ["close"], "available": True},
    {"name": "momentum_3m", "family": "momentum", "direction": "positive", "lookback": 63,
     "description": "Trailing 3-month price momentum (63 trading sessions).",
     "expression": "pct_change(close, 63)", "inputs": ["close"], "available": True},
    {"name": "momentum_6m", "family": "momentum", "direction": "positive", "lookback": 126,
     "description": "Trailing 6-month price momentum (126 trading sessions).",
     "expression": "pct_change(close, 126)", "inputs": ["close"], "available": True},
    {"name": "momentum_12m", "family": "momentum", "direction": "positive", "lookback": 252,
     "description": "Trailing 12-month price momentum (252 trading sessions).",
     "expression": "pct_change(close, 252)", "inputs": ["close"], "available": True},
    {"name": "momentum_12_1", "family": "momentum", "direction": "positive", "lookback": 252,
     "description": "12-month momentum excluding the most recent month (reversal-adjusted).",
     "expression": "pct_change(lag(close, 21), 231)", "inputs": ["close"], "available": True},
    {"name": "risk_adjusted_momentum", "family": "momentum", "direction": "positive", "lookback": 252,
     "description": "12-month return scaled by its realised volatility.",
     "expression": "pct_change(close, 252) / rolling_std(pct_change(close, 1), 252)",
     "inputs": ["close"], "available": True},

    # ── reversal ─────────────────────────────────────────────────────────────
    {"name": "reversal_1w", "family": "reversal", "direction": "negative", "lookback": 5,
     "description": "Short-horizon reversal (1-week return, sign-flipped).",
     "expression": "-pct_change(close, 5)", "inputs": ["close"], "available": True},
    {"name": "reversal_1m", "family": "reversal", "direction": "negative", "lookback": 21,
     "description": "1-month reversal, normalised by 3-month volatility.",
     "expression": "-pct_change(close, 21) / rolling_std(pct_change(close, 1), 63)",
     "inputs": ["close"], "available": True},

    # ── low volatility ───────────────────────────────────────────────────────
    {"name": "low_volatility_3m", "family": "low_volatility", "direction": "negative", "lookback": 63,
     "description": "Realised 3-month volatility (63 sessions); low value = low risk.",
     "expression": "rolling_std(pct_change(close, 1), 63)", "inputs": ["close"], "available": True},
    {"name": "downside_volatility_6m", "family": "low_volatility", "direction": "negative", "lookback": 126,
     "description": "Realised 6-month volatility (proxy for downside risk at daily frequency).",
     "expression": "rolling_std(pct_change(close, 1), 126)", "inputs": ["close"], "available": True},

    # ── trend ────────────────────────────────────────────────────────────────
    {"name": "trend_50_200", "family": "trend", "direction": "positive", "lookback": 200,
     "description": "50/200-session moving-average trend spread.",
     "expression": "sma(close, 50) - sma(close, 200)", "inputs": ["close"], "available": True},

    # ── liquidity ────────────────────────────────────────────────────────────
    {"name": "turnover_1m", "family": "liquidity", "direction": "negative", "lookback": 21,
     "description": "Average daily traded volume over 1 month (liquidity proxy).",
     "expression": "rolling_mean(volume, 21)", "inputs": ["volume"], "available": True},
    {"name": "dollar_volume_1m", "family": "liquidity", "direction": "negative", "lookback": 21,
     "description": "Average daily dollar volume (close x volume) over 1 month.",
     "expression": "rolling_mean(close * volume, 21)", "inputs": ["close", "volume"], "available": True},

    # ── factors declared but not evaluable from the current data surface ─────
    {"name": "earnings_yield", "family": "value", "direction": "positive", "lookback": 1,
     "description": "Trailing earnings / price. Requires point-in-time fundamentals.",
     "expression": "", "inputs": ["earnings_per_share", "close"], "available": False,
     "unavailableReason": "point-in-time fundamentals are not supplied by the current data surface"},
    {"name": "book_to_price", "family": "value", "direction": "positive", "lookback": 1,
     "description": "Book value / price. Requires point-in-time fundamentals.",
     "expression": "", "inputs": ["book_value_per_share", "close"], "available": False,
     "unavailableReason": "point-in-time fundamentals are not supplied by the current data surface"},
    {"name": "return_on_equity", "family": "quality", "direction": "positive", "lookback": 1,
     "description": "Net income / equity. Requires point-in-time fundamentals.",
     "expression": "", "inputs": ["net_income", "equity"], "available": False,
     "unavailableReason": "point-in-time fundamentals are not supplied by the current data surface"},
    {"name": "log_market_cap", "family": "size", "direction": "negative", "lookback": 1,
     "description": "log(market capitalisation). Requires shares outstanding.",
     "expression": "", "inputs": ["shares_outstanding", "close"], "available": False,
     "unavailableReason": "shares outstanding are not supplied by the current data surface"},
    {"name": "funding_rate_carry", "family": "carry", "direction": "positive", "lookback": 1,
     "description": "Crypto perpetual funding-rate carry. Requires derivatives data.",
     "expression": "", "inputs": ["funding_rate"], "available": False,
     "unavailableReason": "derivatives funding data is not supplied by the current data surface"},
]


#: The Alpha Zoo (documented factor definitions on the SAME safe engine).
#: Merged by name so a zoo entry can never shadow a builtin; a duplicate is
#: dropped rather than silently replacing the builtin's definition.
from .zoo import ZOO_FACTORS as _ZOO_FACTORS  # noqa: E402  (after BUILTIN_FACTORS)

_BUILTIN_NAMES = {f["name"] for f in BUILTIN_FACTORS}
BUILTIN_FACTORS.extend(f for f in _ZOO_FACTORS if f["name"] not in _BUILTIN_NAMES)


def list_builtins(*, available_only: bool = False) -> list[dict[str, Any]]:
    if available_only:
        return [f for f in BUILTIN_FACTORS if f.get("available", True)]
    return [dict(f) for f in BUILTIN_FACTORS]

def get_builtin(name: str) -> dict[str, Any] | None:
    for f in BUILTIN_FACTORS:
        if f["name"] == name:
            return dict(f)
    return None


__all__ = ["BUILTIN_FACTORS", "PRICE_INPUTS", "list_builtins", "get_builtin"]
