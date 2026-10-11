"""Data contracts for the Factor & Alpha Research Lab.

Plain dataclasses (JSON-serialisable via ``to_dict``). Persistence and the
engine accept these or equivalent dicts; nothing here reaches the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

FACTOR_FAMILIES = (
    "momentum", "reversal", "value", "quality", "size", "carry",
    "low_volatility", "liquidity", "trend", "growth", "profitability",
    "risk", "market_sensitivity", "composite", "custom",
)

LIFECYCLE_STATUSES = ("draft", "active", "deprecated", "archived")
VALIDATION_STATUSES = ("unvalidated", "valid", "warning", "invalid", "validated-static")


@dataclass
class FactorDefinition:
    """A stable factor identity plus the metadata for its next version."""

    name: str
    description: str = ""
    family: str = "custom"
    owner: Optional[str] = None
    direction: Optional[str] = None          # "positive" | "negative" | None
    frequency: str = "1d"
    asset_class: str = "equity"
    expression: str = ""
    inputs: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    normalization: str = "cross_sectional_zscore"
    missing_policy: str = "drop"
    lookback: int = 1
    output_type: str = "float"
    tags: list[str] = field(default_factory=list)
    pit_safe: bool = True
    factor_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "factorId": self.factor_id, "name": self.name, "description": self.description,
            "family": self.family, "owner": self.owner, "direction": self.direction,
            "frequency": self.frequency, "assetClass": self.asset_class,
            "expression": self.expression, "inputs": list(self.inputs),
            "parameters": dict(self.parameters), "normalization": self.normalization,
            "missingPolicy": self.missing_policy, "lookback": self.lookback,
            "outputType": self.output_type, "tags": list(self.tags), "pitSafe": self.pit_safe,
        }


__all__ = ["FactorDefinition", "FACTOR_FAMILIES", "LIFECYCLE_STATUSES", "VALIDATION_STATUSES"]
