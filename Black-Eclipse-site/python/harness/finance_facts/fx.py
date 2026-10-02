"""Currency & unit normalization (Universal Financial Data Accuracy, §18).

Never compare USD/EUR/TRY/PKR/JPY without knowing the FX basis. Every normalized
value records original currency + value, the conversion currency, the FX rate, its
timestamp and source — and distinguishes reported vs constant-currency vs
translated vs spot vs average-period FX.

Scale words (thousands/millions/billions/trillions) are normalized to a canonical
unit explicitly, never silently. A bare number is never assumed to be in any scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Scale multiplier → the canonical unit suffix. A value is stored as
# (number, unit) where unit is one of these, so a "2.7" and a "2,700" cannot be
# compared as if equal.
SCALE_FACTORS: dict[str, float] = {
    "thousand": 1e3, "thousands": 1e3, "k": 1e3,
    "million": 1e6, "millions": 1e6, "mn": 1e6, "m": 1e6,
    "billion": 1e9, "billions": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "trillions": 1e12, "tn": 1e12,
}

# The canonical unit the engine normalizes large magnitudes to (billions) for
# DISPLAY only — the original scale is always retained.
CANONICAL_UNIT = "billions"

# How a value came to be in its currency (§18).
FX_BASIS_TYPES = ("reported", "constant_currency", "translated", "spot", "average_period")


@dataclass(frozen=True)
class FXConversion:
    original_currency: Optional[str]
    original_value: Optional[float]
    conversion_currency: Optional[str]
    fx_rate: Optional[float]
    fx_timestamp: Optional[str]
    fx_source: Optional[str]
    basis: str  # one of FX_BASIS_TYPES
    note: Optional[str] = None


@dataclass(frozen=True)
class NormalizedValue:
    value: Optional[float]
    currency: Optional[str]
    unit: Optional[str]           # scaled unit, e.g. "billions"
    original_value: Optional[float]
    original_unit: Optional[str]


def parse_scale(text: Optional[str]) -> Optional[float]:
    """The multiplier implied by a scale word, or None when there is none."""
    if not text:
        return None
    return SCALE_FACTORS.get(str(text).strip().lower())


def normalize_scale(value: Optional[float], unit: Optional[str], *, to_unit: str = CANONICAL_UNIT) -> NormalizedValue:
    """Convert (value, scale word) into a canonical unit, RETAINING the original.

    A value with no recognised scale word is returned unchanged with its unit and
    is NOT assumed to be in any scale.
    """
    if value is None:
        return NormalizedValue(None, None, unit, None, unit)
    factor = parse_scale(unit)
    if factor is None:
        return NormalizedValue(float(value), None, unit, float(value), unit)
    target = SCALE_FACTORS.get(to_unit, 1e9)
    converted = float(value) * factor / target
    return NormalizedValue(converted, None, to_unit, float(value), unit)


def convert(value: Optional[float], fx: FXConversion, *, target_currency: Optional[str] = None) -> Optional[float]:
    """Apply a conversion ONLY when a rate and its basis are known.

    No rate or an unknown basis → None. A wrong FX number is worse than an honest
    gap, so the engine never assumes 1:1.
    """
    if value is None or fx.fx_rate is None:
        return None
    if target_currency and fx.conversion_currency and target_currency.upper() != fx.conversion_currency.upper():
        return None
    if fx.basis not in FX_BASIS_TYPES:
        return None
    return float(value) * float(fx.fx_rate)


def same_currency(a: Optional[str], b: Optional[str]) -> bool:
    """True only when both currencies are known and identical. Unknown ≠ equal."""
    return bool(a) and bool(b) and str(a).upper() == str(b).upper()


__all__ = [
    "CANONICAL_UNIT",
    "FX_BASIS_TYPES",
    "FXConversion",
    "NormalizedValue",
    "SCALE_FACTORS",
    "convert",
    "normalize_scale",
    "parse_scale",
    "same_currency",
]
