"""Instrument-specific nodes: multi-leg options and continuous futures.

Both engines already exist and are already tested; these nodes only adapt the
graph's shapes:

  * `quant.options_strategy` → `harness/quant/options.py`
    (`analyze_option_strategy`: expiry payoff, break-evens, boundedness, and
    net Greeks when a valuation spot + time-to-expiry are supplied)
  * `quant.futures_continuous` → `harness/quant/futures.py`
    (`splice_continuous`: ordered contracts + roll dates → one continuous
    series, with `none` / `difference` / `ratio` back-adjustment)

Two honesty rules are enforced here:

  * an option strategy's payoff range is never guessed from thin air: it is
    either configured (`spotMin`/`spotMax`) or derived from the strikes and the
    wired valuation spot, and the derivation is recorded in the payload;
  * a spliced futures series is a BACKTEST PROXY, not a deliverable contract.
    The engine says so and the node carries that note through to the OHLCV
    payload instead of letting it look like a real instrument.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..quant.futures import FuturesError, splice_continuous
from ..quant.options import OptionError, analyze_option_strategy
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_LEGS = 16
MAX_CONTRACTS = 24
MAX_POINTS = 2_001
_ADJUSTMENTS = ("none", "difference", "ratio")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _optional_number(context: NodeExecContext, port: str) -> Optional[float]:
    raw = context.inputs.get(port)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{port}' must be a number") from None


def _payoff_range(
    legs: list[Any], spot: Optional[float], config: dict[str, Any]
) -> tuple[float, float, str]:
    """Configured range, else derived from the strikes and the valuation spot."""
    spot_min = float(config.get("spotMin", 0.0))
    spot_max = float(config.get("spotMax", 0.0))
    if spot_min > 0 and spot_max > spot_min:
        return spot_min, spot_max, "configured"

    if spot_min > 0 or spot_max > 0:
        raise ValueError("spotMin and spotMax must be set together, with spotMax > spotMin")

    strikes = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        try:
            strike = float(leg.get("strike"))
        except (TypeError, ValueError):
            continue
        if strike > 0:
            strikes.append(strike)
    base = spot if spot and spot > 0 else (sum(strikes) / len(strikes) if strikes else None)
    if not base:
        raise ValueError(
            "quant.options_strategy needs a payoff range: set spotMin/spotMax, or "
            "wire a spot / use legs with strikes so it can be derived"
        )
    return base * 0.7, base * 1.3, "derivedFromStrikes"


# ── Executors ──────────────────────────────────────────────────────────────


def exec_options_strategy(context: NodeExecContext) -> dict[str, Any]:
    legs = context.inputs.get("legs")
    if not isinstance(legs, list) or not legs:
        raise ValueError(
            "quant.options_strategy needs a non-empty legs array "
            "([{type, strike, quantity, premium}])"
        )
    if len(legs) > MAX_LEGS:
        raise ValueError(f"quant.options_strategy is bounded to {MAX_LEGS} legs")

    spot = _optional_number(context, "spot")
    spot_min, spot_max, range_source = _payoff_range(legs, spot, context.config)
    time_to_expiry = _optional_number(context, "timeToExpiry")

    try:
        analysis = analyze_option_strategy(
            legs,
            spot_min=spot_min,
            spot_max=spot_max,
            points=int(context.config.get("points", 201)),
            valuation_spot=spot,
            time_to_expiry=time_to_expiry,
            iv=_optional_number(context, "iv"),
            risk_free=float(context.config.get("riskFree", 0.05)),
        )
    except OptionError as exc:
        raise ValueError(f"option strategy failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"option strategy failed: {type(exc).__name__}: {exc}") from exc

    analysis["spotRangeSource"] = range_source
    context.emit(
        f"{len(legs)} leg(s): {analysis['strategyType']}, "
        f"{len(analysis['breakEvens'])} break-even(s), "
        f"{'bounded' if analysis['bounded'] else 'unbounded'} payoff"
    )
    return {
        "analysis": analysis,
        "summary": (
            f"{len(legs)} leg(s) {analysis['strategyType']}: "
            f"max profit {analysis['maxProfit']}, max loss {analysis['maxLoss']}, "
            f"break-evens {analysis['breakEvens']}"
        ),
    }


def exec_futures_continuous(context: NodeExecContext) -> dict[str, Any]:
    contracts = context.inputs.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError(
            "quant.futures_continuous needs a non-empty contracts array "
            "([{symbol, rows: [{timestamp, open, high, low, close, volume}]}])"
        )
    if len(contracts) > MAX_CONTRACTS:
        raise ValueError(f"quant.futures_continuous is bounded to {MAX_CONTRACTS} contracts")
    if not all(isinstance(contract, dict) for contract in contracts):
        raise ValueError("every contract must be an object with symbol and rows")

    raw = str(context.config.get("rollDatesJson") or "").strip()
    if not raw:
        raise ValueError(
            "rollDatesJson is required: one ISO date per roll "
            f"({max(0, len(contracts) - 1)} needed)"
        )
    try:
        roll_dates = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"rollDatesJson is not valid JSON: {exc}") from exc
    if not isinstance(roll_dates, list) or not all(isinstance(item, str) for item in roll_dates):
        raise ValueError("rollDatesJson must be a JSON array of ISO date strings")

    adjustment = str(context.config.get("adjustment") or "difference")
    if adjustment not in _ADJUSTMENTS:
        raise ValueError(f"adjustment must be one of {', '.join(_ADJUSTMENTS)}")

    try:
        spliced = splice_continuous(contracts, [str(item) for item in roll_dates], adjustment=adjustment)
    except FuturesError as exc:
        raise ValueError(f"continuous futures failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"continuous futures failed: {type(exc).__name__}: {exc}") from exc

    symbols = [str(contract.get("symbol") or "") for contract in contracts]
    symbol = str(context.config.get("symbol") or "").strip().upper() or "CONTINUOUS"
    series = {
        "symbol": symbol,
        "interval": str(context.config.get("interval") or "1d"),
        "provider": "futures-splice",
        "rows": spliced["bars"],
        "contractSymbols": symbols,
        "adjustment": spliced["adjustment"],
        "proxy": True,
        "note": spliced["note"],
    }
    metadata = {key: value for key, value in spliced.items() if key != "bars"}
    metadata["barCount"] = spliced["barCount"]

    context.emit(
        f"{symbol}: {spliced['barCount']} bar(s) spliced from {len(contracts)} contract(s) "
        f"({spliced['adjustment']})"
    )
    return {"series": series, "metadata": metadata}


# ── Definitions ─────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_quant_instrument_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.options_strategy",
            version="1.0.0",
            label="Options strategy",
            category="quant",
            inputs=(
                _port("legs", "Legs", PortType.ARRAY),
                _port("spot", "Spot", PortType.NUMBER, optional=True),
                _port("timeToExpiry", "Time to expiry (years)", PortType.NUMBER, optional=True),
                _port("iv", "Implied volatility", PortType.NUMBER, optional=True),
            ),
            outputs=(
                _port("analysis", "Analysis", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField("spotMin", "number", 0.0, minimum=0),
                ConfigField("spotMax", "number", 0.0, minimum=0),
                ConfigField("points", "integer", 201, minimum=3, maximum=MAX_POINTS),
                ConfigField("riskFree", "number", 0.05, minimum=-0.5, maximum=0.5),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_options_strategy,
            metadata={
                "docs": (
                    "Expiry payoff, break-evens, max profit/loss and boundedness "
                    "through harness/quant/options.py. Net Greeks are added only when "
                    "a valuation spot AND a time-to-expiry are wired. An unbounded "
                    "tail is null with `bounded: false`, never a made-up max loss. "
                    "spotMin/spotMax default to a range derived from the strikes or "
                    "the wired spot, and the payload records which."
                ),
            },
        ),
        NodeDef(
            type="quant.futures_continuous",
            version="1.0.0",
            label="Continuous futures",
            category="quant",
            inputs=(_port("contracts", "Contracts", PortType.ARRAY),),
            outputs=(
                _port("series", "OHLCV", PortType.OHLCV),
                _port("metadata", "Metadata", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("rollDatesJson", "string", "", max_length=4_000),
                ConfigField("adjustment", "enum", "difference", enum=_ADJUSTMENTS),
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("interval", "string", "1d", max_length=10),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_futures_continuous,
            metadata={
                "docs": (
                    "Splices ordered contracts at the supplied roll dates through "
                    "harness/quant/futures.py (none / difference / ratio). The output "
                    "is an OHLCV series marked `proxy: true` with the engine's own "
                    "note: a continuous series is a backtest proxy, not a deliverable "
                    "contract, and the most recent contract stays unadjusted."
                ),
            },
        ),
    ]


__all__ = [
    "build_quant_instrument_nodes",
    "exec_options_strategy",
    "exec_futures_continuous",
]
