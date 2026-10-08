"""Shared envelope for research runs (optimization / walk-forward / Monte-Carlo
/ robustness).

`ResearchResult` is duck-type compatible with the backtest `BacktestResult` as
far as `QuantStore.save_experiment` is concerned — it exposes `to_dict`,
`configuration`, `metadata`, `metrics`, `status`, `warnings` and
`observability` — so research runs persist through the SAME store and artifact
path as backtests, with no second storage mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ResearchResult:
    kind: str
    status: str = "OK"
    metadata: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    observability: dict[str, Any] = field(default_factory=dict)
    capability: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "status": self.status, "metadata": self.metadata,
            "configuration": self.configuration, "metrics": self.metrics,
            "warnings": self.warnings, "observability": self.observability,
            "capability": self.capability,
        }

    def to_dict(self, *, include_series: bool = True) -> dict[str, Any]:
        data = self.summary()
        data.update(self.payload)
        return data


def warn(code: str, message: str, detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail or {}}


__all__ = ["ResearchResult", "warn"]
