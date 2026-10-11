"""Shared contract for the statistical engine.

One envelope, one error type, one provenance record — used by all fourteen
tools so a caller never has to special-case a tool's return shape.

Design rules (see docs/quant-research/STATISTICAL_METHODS.md):

  * Never fabricate: a calculation that cannot be performed honestly raises
    `StatsError` (or returns a response carrying `status="error"`); it never
    invents a plausible number.
  * Every number is reproducible: parameters, tool version, window, missing-data
    policy and (where stochastic) the random seed travel with the result.
  * Large series are returned as plain lists with an explicit truncation flag
    rather than silently dropped.
"""

from __future__ import annotations

import math
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np

# Bump when a formula or convention changes so stored results stay interpretable.
STATS_VERSION = "1.0.0"


class StatsError(Exception):
    """A statistical calculation could not be performed honestly."""

    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


# Canonical error codes — stable, machine-readable.
INVALID_INPUT = "INVALID_INPUT"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NUMERICAL_ERROR = "NUMERICAL_ERROR"
SINGULAR_MATRIX = "SINGULAR_MATRIX"
NOT_CONVERGED = "NOT_CONVERGED"
UNSUPPORTED_METHOD = "UNSUPPORTED_METHOD"
DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
MISSING_DATA = "MISSING_DATA"


def _dependency_versions() -> dict[str, str]:
    return {"numpy": np.__version__, "python": platform.python_version()}


@dataclass
class Provenance:
    """Everything needed to reproduce and interpret a calculation."""

    source: Optional[str] = None
    dataset_id: Optional[str] = None
    symbols: list[str] = field(default_factory=list)
    window: Optional[dict[str, Any]] = None
    frequency: Optional[str] = None
    adjustment: Optional[str] = None
    missing_data_policy: str = "reject"
    tool_version: str = STATS_VERSION
    parameters: dict[str, Any] = field(default_factory=dict)
    dependency_versions: dict[str, str] = field(default_factory=_dependency_versions)
    random_seed: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "datasetId": self.dataset_id,
            "symbols": list(self.symbols),
            "window": self.window,
            "frequency": self.frequency,
            "adjustment": self.adjustment,
            "missingDataPolicy": self.missing_data_policy,
            "toolVersion": self.tool_version,
            "parameters": self.parameters,
            "dependencyVersions": self.dependency_versions,
            "randomSeed": self.random_seed,
            "warnings": list(self.warnings),
            "createdAt": self.created_at,
        }


def make_response(
    tool: str,
    parameters: dict[str, Any],
    *,
    summary: Optional[dict[str, Any]] = None,
    results: Optional[dict[str, Any]] = None,
    diagnostics: Optional[dict[str, Any]] = None,
    warnings: Optional[Sequence[str]] = None,
    errors: Optional[Sequence[dict[str, Any]]] = None,
    provenance: Optional[Provenance] = None,
    execution: Optional[dict[str, Any]] = None,
    artifacts: Optional[Sequence[dict[str, Any]]] = None,
    status: str = "ok",
) -> dict[str, Any]:
    """Build the uniform response envelope shared by every tool."""
    return {
        "status": status,
        "tool": tool,
        "toolVersion": STATS_VERSION,
        "parameters": parameters,
        "summary": summary or {},
        "results": results or {},
        "diagnostics": diagnostics or {},
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "provenance": (provenance or Provenance(parameters=parameters)).to_dict(),
        "executionMetadata": execution or {},
        "artifactReferences": list(artifacts or []),
    }


# ── input validation helpers ─────────────────────────────────────────────────


def to_float_array(values: Any, name: str, *, allow_empty: bool = False) -> np.ndarray:
    """Coerce a JSON list into a finite float64 array, rejecting bad input.

    ``None``/``NaN``/``inf`` are preserved as ``np.nan`` so the caller can apply
    an explicit missing-data policy — they are never silently turned into 0.
    """
    if values is None:
        raise StatsError(INVALID_INPUT, f"{name} is required")
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise StatsError(INVALID_INPUT, f"{name} must be a numeric series: {exc}") from exc
    if arr.ndim != 1:
        raise StatsError(INVALID_INPUT, f"{name} must be one-dimensional")
    if arr.size == 0 and not allow_empty:
        raise StatsError(INSUFFICIENT_DATA, f"{name} is empty", 422)
    # Collapse +/-inf to nan (missing) rather than producing inf-derived stats.
    arr = np.where(np.isfinite(arr), arr, np.nan)
    return arr


def require_min_length(arr: np.ndarray, minimum: int, name: str = "series") -> None:
    if arr.size < minimum:
        raise StatsError(
            INSUFFICIENT_DATA,
            f"{name} has {arr.size} observation(s); at least {minimum} required",
            422,
        )


def require_finite(arr: np.ndarray, name: str, policy: str = "reject") -> np.ndarray:
    """Apply an explicit missing-data policy.

    ``reject``    — raise when any value is missing.
    ``drop``      — return only the finite values (reduces sample size).
    ``fill_zero`` — replace missing with 0.0 (explicit, recorded by the caller).
    """
    if policy not in ("reject", "drop", "fill_zero"):
        raise StatsError(INVALID_INPUT, f"unknown missing-data policy: {policy}")
    mask = np.isfinite(arr)
    if mask.all():
        return arr
    if policy == "reject":
        raise StatsError(MISSING_DATA, f"{name} contains missing (NaN/inf) values", 422)
    if policy == "fill_zero":
        return np.where(mask, arr, 0.0)
    return arr[mask]


def align_series(
    a: np.ndarray, b: np.ndarray, name_a: str = "a", name_b: str = "b", policy: str = "pairwise"
) -> tuple[np.ndarray, np.ndarray]:
    """Align two equal-length series, applying a pairwise-complete policy.

    ``pairwise`` drops positions where either side is missing. ``reject`` raises.
    """
    if a.shape != b.shape:
        raise StatsError(
            INVALID_INPUT, f"{name_a} and {name_b} must have equal length ({a.size} != {b.size})"
        )
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.all():
        return a, b
    if policy == "reject":
        raise StatsError(MISSING_DATA, f"{name_a}/{name_b} contain missing values", 422)
    return a[mask], b[mask]


def finite_mask(*arrays: np.ndarray) -> np.ndarray:
    mask = np.ones(arrays[0].shape, dtype=bool)
    for arr in arrays:
        mask &= np.isfinite(arr)
    return mask


def safe_float(value: Any) -> Optional[float]:
    """Return a JSON-safe float or None for NaN/inf."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def as_list(values: np.ndarray) -> list[Optional[float]]:
    """Convert an array to a JSON list, mapping non-finite values to None."""
    return [None if (isinstance(v, float) and not math.isfinite(v)) else float(v) for v in values]


def get_param(args: dict[str, Any], key: str, default: Any) -> Any:
    value = args.get(key, default)
    return default if value is None else value


def get_int(args: dict[str, Any], key: str, default: int, *, minimum: Optional[int] = None) -> int:
    value = args.get(key, default)
    if value is None:
        value = default
    try:
        iv = int(value)
    except (TypeError, ValueError) as exc:
        raise StatsError(INVALID_INPUT, f"{key} must be an integer") from exc
    if minimum is not None and iv < minimum:
        raise StatsError(INVALID_INPUT, f"{key} must be >= {minimum}")
    return iv


def get_float(args: dict[str, Any], key: str, default: float) -> float:
    value = args.get(key, default)
    if value is None:
        value = default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise StatsError(INVALID_INPUT, f"{key} must be a number") from exc


def get_str(args: dict[str, Any], key: str, default: str) -> str:
    value = args.get(key, default)
    return default if value is None else str(value)


__all__ = [
    "STATS_VERSION",
    "StatsError",
    "Provenance",
    "make_response",
    "to_float_array",
    "require_min_length",
    "require_finite",
    "align_series",
    "finite_mask",
    "safe_float",
    "as_list",
    "get_param",
    "get_int",
    "get_float",
    "get_str",
    "INVALID_INPUT",
    "INSUFFICIENT_DATA",
    "NUMERICAL_ERROR",
    "SINGULAR_MATRIX",
    "NOT_CONVERGED",
    "UNSUPPORTED_METHOD",
    "DEPENDENCY_MISSING",
    "MISSING_DATA",
]
