"""Quant engine error taxonomy.

Every failure is a typed, structured error — never a silent zero, a fabricated
number, or a bare string. The codes are stable and used by the API layer, the
agent tools and the tests. A backtest never raises for a *data* or *strategy*
problem the caller can fix; instead it returns the error in `BacktestResult`
(so the UI can show it) while the tool/route surfaces it honestly.
"""

from __future__ import annotations

from typing import Any, Optional


class QuantError(Exception):
    """Base class for every quant-engine error."""

    code = "QUANT_ERROR"
    http_status = 400

    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


# ── Strategy errors ──────────────────────────────────────────────────────────

class StrategyNotFound(QuantError):
    code = "STRATEGY_NOT_FOUND"
    http_status = 404


class StrategyVersionNotFound(QuantError):
    code = "STRATEGY_VERSION_NOT_FOUND"
    http_status = 404


class InvalidStrategy(QuantError):
    """A strategy failed structural validation (schema / semantic)."""

    code = "INVALID_STRATEGY"


class StrategyValidationFailed(QuantError):
    """A strategy failed validation; `detail["errors"]` lists every problem."""

    code = "STRATEGY_VALIDATION_FAILED"


class StrategyVersionImmutable(QuantError):
    """A persisted version cannot be rewritten because an experiment references it.

    Immutable history is a contract: once a version has been used by an
    experiment, it is frozen. Editing produces a NEW version instead.
    """

    code = "STRATEGY_VERSION_IMMUTABLE"
    http_status = 409


class UnsupportedSchemaVersion(QuantError):
    """A serialized strategy declares a schema version this runtime cannot load."""

    code = "UNSUPPORTED_SCHEMA_VERSION"
    http_status = 422


class StrategyBundleError(QuantError):
    """A portable strategy bundle is malformed, unsafe, or too large."""

    code = "STRATEGY_BUNDLE_ERROR"


class ApprovalRequired(QuantError):
    """An action needs an approved version (e.g. deploying to paper)."""

    code = "APPROVAL_REQUIRED"
    http_status = 409


class LiveTradingDisabled(QuantError):
    """Live order routing is not available and is never auto-enabled."""

    code = "LIVE_TRADING_DISABLED"
    http_status = 403


# ── Data errors ──────────────────────────────────────────────────────────────

class DataError(QuantError):
    code = "DATA_ERROR"


class MissingData(QuantError):
    code = "MISSING_DATA"
    http_status = 404


class InvalidSymbol(QuantError):
    code = "INVALID_SYMBOL"


class InsufficientHistory(QuantError):
    """Not enough bars to satisfy indicator warm-up / the requested window."""

    code = "INSUFFICIENT_HISTORY"


class TimezoneMismatch(QuantError):
    code = "TIMEZONE_MISMATCH"


class CorruptDataset(QuantError):
    code = "CORRUPT_DATASET"


class UnsupportedAsset(QuantError):
    code = "UNSUPPORTED_ASSET"


class UnsupportedTimeframe(QuantError):
    code = "UNSUPPORTED_TIMEFRAME"


class InvalidDataSource(QuantError):
    """A caller-named data source is malformed (no dataset name / bad values)."""

    code = "INVALID_DATA_SOURCE"


class CustomSourceUnavailable(QuantError):
    """An operator-declared data source could not be read.

    Never silently replaced by a built-in market provider: a backtest that names
    its own source either uses it or fails honestly.
    """

    code = "CUSTOM_SOURCE_UNAVAILABLE"
    http_status = 502


# ── Order / execution / portfolio errors ─────────────────────────────────────

class InvalidOrder(QuantError):
    code = "INVALID_ORDER"


class IllegalOrderTransition(QuantError):
    code = "ILLEGAL_ORDER_TRANSITION"


class InsufficientCapital(QuantError):
    code = "INSUFFICIENT_CAPITAL"


class MarginViolation(QuantError):
    code = "MARGIN_VIOLATION"


class ExecutionFailure(QuantError):
    code = "EXECUTION_FAILURE"


class RiskRejected(QuantError):
    """A risk rule rejected or reduced an order. Not fatal — surfaced as an event."""

    code = "RISK_REJECTED"


# ── Experiment / artifact errors ─────────────────────────────────────────────

class ExperimentNotFound(QuantError):
    code = "EXPERIMENT_NOT_FOUND"
    http_status = 404


class ArtifactNotFound(QuantError):
    code = "ARTIFACT_NOT_FOUND"
    http_status = 404


class StoreUnavailable(QuantError):
    """The persistence layer is not configured; honest, never faked."""

    code = "STORE_UNAVAILABLE"
    http_status = 503


__all__ = [
    "QuantError",
    "StrategyNotFound",
    "StrategyVersionNotFound",
    "InvalidStrategy",
    "StrategyValidationFailed",
    "StrategyVersionImmutable",
    "UnsupportedSchemaVersion",
    "StrategyBundleError",
    "ApprovalRequired",
    "LiveTradingDisabled",
    "DataError",
    "MissingData",
    "InvalidSymbol",
    "InsufficientHistory",
    "TimezoneMismatch",
    "CorruptDataset",
    "UnsupportedAsset",
    "UnsupportedTimeframe",
    "InvalidDataSource",
    "CustomSourceUnavailable",
    "InvalidOrder",
    "IllegalOrderTransition",
    "InsufficientCapital",
    "MarginViolation",
    "ExecutionFailure",
    "RiskRejected",
    "ExperimentNotFound",
    "ArtifactNotFound",
    "StoreUnavailable",
]
