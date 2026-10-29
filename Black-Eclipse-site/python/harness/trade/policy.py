"""Deterministic pre-trade limits for demo execution (P1).

The broker's own `order_check` proves the order is *possible*; this policy decides
whether it is *allowed*. Every rule is a plain number from the connection config,
so an operator can explain a refusal without reading code.

Defaults are deliberately visible and conservative where they cost nothing:
`maxOpenPositions=20`, `maxSpreadPoints=50`. A value of 0 (or an empty allowlist)
turns that rule off. P1 is demo-only; live arming is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import BrokerConnection


@dataclass(frozen=True)
class TradePolicy:
    max_margin: float = 0.0
    max_volume: float = 0.0
    max_open_positions: int = 20
    max_spread_points: float = 50.0
    symbol_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_connection(cls, connection: BrokerConnection) -> "TradePolicy":
        config = connection.config or {}

        def number(key: str, default: float) -> float:
            try:
                return float(config.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        def integer(key: str, default: int) -> int:
            try:
                return int(config.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        allowlist = config.get("symbolAllowlist") or ()
        if not isinstance(allowlist, (list, tuple)):
            allowlist = ()
        return cls(
            max_margin=number("maxMargin", 0.0),
            max_volume=number("maxVolume", 0.0),
            max_open_positions=integer("maxOpenPositions", 20),
            max_spread_points=number("maxSpreadPoints", 50.0),
            symbol_allowlist=tuple(str(item).strip().upper() for item in allowlist if str(item).strip()),
        )

    def evaluate(self, preview: dict[str, Any]) \
            -> dict[str, Any]:
        """Return `{allowed, reasons, rules}` for one broker preview."""
        reasons: list[str] = []
        rules: list[str] = []
        symbol = str(preview.get("symbol") or "").upper()
        if self.symbol_allowlist and symbol not in self.symbol_allowlist:
            rules.append("policy.symbol-not-allowed")
            reasons.append(
                f"{symbol or 'this symbol'} is not on the connection's symbol allowlist."
            )

        margin = _num(preview.get("margin"))
        if self.max_margin > 0 and margin is not None and margin > self.max_margin:
            rules.append("policy.max-margin")
            reasons.append(
                f"The order needs {margin:,.2f} margin, above the {self.max_margin:,.2f} cap."
            )

        volume = _num(preview.get("volume"))
        if self.max_volume > 0 and volume is not None and volume > self.max_volume:
            rules.append("policy.max-volume")
            reasons.append(
                f"Volume {volume:g} exceeds the {self.max_volume:g} cap."
            )

        spread = _num(preview.get("spreadPoints"))
        if self.max_spread_points > 0 and spread is not None and spread > self.max_spread_points:
            rules.append("policy.max-spread")
            reasons.append(
                f"The spread is {spread:g} points, above the {self.max_spread_points:g}-point cap."
            )

        open_positions = _num(preview.get("openPositions"))
        if (
            self.max_open_positions > 0
            and open_positions is not None
            and open_positions >= self.max_open_positions
        ):
            rules.append("policy.max-open-positions")
            reasons.append(
                f"There are already {int(open_positions)} open positions "
                f"(cap {self.max_open_positions})."
            )

        return {"allowed": not reasons, "reasons": reasons, "rules": rules}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


__all__ = ["TradePolicy"]
