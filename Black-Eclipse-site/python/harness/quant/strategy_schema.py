"""The `StrategySpec` schema the agent sees (ADR-H242).

The quant tools declare their inputs as JSON Schema. `create_strategy` used to
declare its `strategy` argument as a bare `object`, so the model had to guess
the shape from validation errors. The schema here publishes the REAL spec
fields with a minimal working example — it is derived from the same model the
engine validates, so it cannot drift.

Kept in its own module so `quant/tools.py` stays under the size ceiling.
"""

from __future__ import annotations

from typing import Any

#: The strategy spec, as the agent must write it.
STRATEGY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "The strategy spec. id and name are required; every other block has "
        "defaults. universe.symbols = the instruments; timeframes.primary = the "
        "bar size (e.g. '1d'); indicators = [{id, type, params}] where type is a "
        "registered indicator (sma, ema, rsi, macd, roc, atr, bollinger); "
        "rules.entry/rules.exit = the entry and exit conditions; risk = the "
        "exposure limits (max_position_pct, max_gross_exposure, "
        "max_open_positions, allow_long/allow_short); position_sizing = "
        "{type: 'percent_equity', value: 1.0}; execution = the cost assumptions "
        "(commission, slippage, spread). A minimal working spec: {id: 'mom', "
        "name: 'Momentum', universe: {symbols: ['SPY']}, indicators: [{id: 'f', "
        "type: 'sma', params: {period: 50}}], rules: {entry: {indicator: 'f', "
        "comparison: 'gt', value: 0}, exit: {indicator: 'f', comparison: 'lt', "
        "value: 0}}}."
    ),
    "properties": {
        "id": {"type": "string", "description": "Stable id, e.g. 'momentum-50'."},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "version": {"type": "string", "description": "Semver, e.g. '1.0.0'."},
        "asset_class": {"type": "string"},
        "universe": {
            "type": "object",
            "properties": {
                "asset_classes": {"type": "array", "items": {"type": "string"}},
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
        },
        "timeframes": {
            "type": "object",
            "properties": {
                "primary": {"type": "string", "description": "e.g. '1d', '1h'."},
                "confirmation": {"type": "array", "items": {"type": "string"}},
            },
        },
        "indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "params": {"type": "object"},
                    "source": {"type": "string"},
                    "timeframe": {"type": "string"},
                },
            },
        },
        "rules": {
            "type": "object",
            "properties": {
                "entry": {"type": "object"},
                "exit": {"type": "object"},
            },
        },
        "risk": {"type": "object"},
        "position_sizing": {"type": "object"},
        "execution": {"type": "object"},
        "metadata": {"type": "object"},
    },
    "required": ["id", "name"],
}


__all__ = ["STRATEGY_SCHEMA"]
