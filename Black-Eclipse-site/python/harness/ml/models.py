"""Versioned data contracts for the ML Research Lab.

Plain dataclasses (JSON-serialisable via ``to_dict``). These define the boundary
between the TypeScript front door, the agent tools and the Python engine. Every
contract carries an explicit ``schema_version`` so a shape change is explicit.

Nothing here touches the database; persistence lives in ``store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..stats.base import StatsError

# Bump when a contract shape or a numeric convention changes so stored results
# stay interpretable (mirrors STATS_VERSION / FACTOR_ENGINE_VERSION).
ML_ENGINE_VERSION = "0.1.0"

CONTRACT_SCHEMA_VERSION = "1.0.0"


class MLError(StatsError):
    """An ML operation could not be performed honestly.

    Inherits ``StatsError`` so the shared HTTP mapping and error envelope apply.
    """


# Canonical error codes specific to the ML surface.
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
QUALITY_BLOCKED = "QUALITY_BLOCKED"
IMMUTABLE_VERSION = "IMMUTABLE_VERSION"
REPRODUCIBILITY_MISMATCH = "REPRODUCIBILITY_MISMATCH"


# ── vocabularies ─────────────────────────────────────────────────────────────

TARGET_KINDS = (
    "forward_return",       # regression on the h-period forward simple return
    "direction_binary",     # 1 if forward return > threshold else 0
    "direction_multiclass", # tercile/quintile bins of the forward return
    "neutral_zone",         # binary with a dead-band around zero
    "volatility",           # regression on forward realized volatility
    "cross_sectional_rank", # per-date percentile rank of the forward return
)

SPLIT_METHODS = ("chronological", "walk_forward", "purged_kfold")

# "expanding" grows the train window; "rolling" uses a fixed-size train window.
WINDOW_MODES = ("expanding", "rolling")

TASK_TYPES = ("classification", "regression", "ranking")

MISSING_POLICIES = ("drop", "forward_fill", "fill_zero")

LIFECYCLE_STATUSES = ("draft", "evaluated", "approved_research", "archived")

# Model families whose pure-NumPy implementation ships with the runtime.
NATIVE_MODEL_FAMILIES = ("dummy", "ridge", "logistic", "random_forest")
# Model families that require an optional third-party wheel.
OPTIONAL_MODEL_FAMILIES = ("sklearn_forest", "sklearn_extra_trees", "lightgbm", "xgboost")
MODEL_FAMILIES = NATIVE_MODEL_FAMILIES + OPTIONAL_MODEL_FAMILIES

# Feature-selection methods fitted ONLY on the training fold.
SELECTION_METHODS = ("none", "variance", "correlation", "univariate", "mutual_information")


@dataclass
class TargetSpec:
    """How the supervised label is constructed from forward prices."""

    kind: str = "direction_binary"
    horizon: int = 5                 # forward periods
    threshold: float = 0.0           # return threshold (direction_binary)
    neutral_band: float = 0.0        # |return| <= band -> neutral class (neutral_zone)
    n_classes: int = 3               # bins (direction_multiclass)
    column: str = "target"           # output column name

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION, "kind": self.kind,
            "horizon": self.horizon, "threshold": self.threshold,
            "neutralBand": self.neutral_band, "nClasses": self.n_classes,
            "column": self.column,
        }


@dataclass
class SplitSpec:
    """A temporal validation design."""

    method: str = "walk_forward"
    n_splits: int = 5
    test_size: int = 0               # periods per test fold (0 => derived)
    window: int = 0                  # rolling train size (0 => expanding)
    window_mode: str = "expanding"
    embargo: int = 0                 # periods dropped after each train label end
    purge: bool = True               # drop train labels overlapping test labels
    min_train_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION, "method": self.method,
            "nSplits": self.n_splits, "testSize": self.test_size, "window": self.window,
            "windowMode": self.window_mode, "embargo": self.embargo, "purge": self.purge,
            "minTrainSize": self.min_train_size,
        }


@dataclass
class DatasetSpec:
    """The inputs required to build one immutable dataset version."""

    symbols: list[str] = field(default_factory=list)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    feature_names: list[str] = field(default_factory=list)
    target: TargetSpec = field(default_factory=TargetSpec)
    missing_policy: str = "drop"
    min_coverage: float = 0.5
    asset_class: str = "equity"
    frequency: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION, "symbols": list(self.symbols),
            "interval": self.interval, "start": self.start, "end": self.end,
            "featureNames": list(self.feature_names), "target": self.target.to_dict(),
            "missingPolicy": self.missing_policy, "minCoverage": self.min_coverage,
            "assetClass": self.asset_class, "frequency": self.frequency,
        }


@dataclass
class ExperimentConfig:
    """The full, reproducible description of one training experiment."""

    dataset_id: str = ""
    dataset_version: str = ""
    title: str = "experiment"
    model_family: str = "logistic"
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=lambda: {"method": "none"})
    split: SplitSpec = field(default_factory=SplitSpec)
    seed: int = 42
    scale: bool = True
    task: Optional[str] = None      # inferred from the target when omitted

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION, "datasetId": self.dataset_id,
            "datasetVersion": self.dataset_version, "title": self.title,
            "modelFamily": self.model_family, "hyperparameters": dict(self.hyperparameters),
            "featureNames": list(self.feature_names), "selection": dict(self.selection),
            "split": self.split.to_dict(), "seed": self.seed, "scale": self.scale,
            "task": self.task,
        }


__all__ = [
    "ML_ENGINE_VERSION",
    "CONTRACT_SCHEMA_VERSION",
    "MLError",
    "MODEL_UNAVAILABLE",
    "LEAKAGE_DETECTED",
    "QUALITY_BLOCKED",
    "IMMUTABLE_VERSION",
    "REPRODUCIBILITY_MISMATCH",
    "TARGET_KINDS",
    "SPLIT_METHODS",
    "WINDOW_MODES",
    "TASK_TYPES",
    "MISSING_POLICIES",
    "LIFECYCLE_STATUSES",
    "NATIVE_MODEL_FAMILIES",
    "OPTIONAL_MODEL_FAMILIES",
    "MODEL_FAMILIES",
    "SELECTION_METHODS",
    "TargetSpec",
    "SplitSpec",
    "DatasetSpec",
    "ExperimentConfig",
]
