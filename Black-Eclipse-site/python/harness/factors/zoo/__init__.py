"""The Alpha Zoo: families of documented factors, each on the safe engine."""

from __future__ import annotations

from .academic import ZOO_FACTORS as ACADEMIC_FACTORS
from .alpha101 import ALPHA101_FACTORS
from .fundamental import FUNDAMENTAL_FACTORS
from .gtja191 import GTJA191_FACTORS
from .qlib158 import QLIB158_FACTORS

#: Every zoo family, in one list. `factors.library` merges these by name and
#: never lets a zoo entry shadow a builtin.
ZOO_FACTORS: list[dict] = [
    *ACADEMIC_FACTORS, *ALPHA101_FACTORS, *QLIB158_FACTORS, *GTJA191_FACTORS,
    *FUNDAMENTAL_FACTORS,
]

__all__ = [
    "ACADEMIC_FACTORS",
    "ALPHA101_FACTORS",
    "FUNDAMENTAL_FACTORS",
    "GTJA191_FACTORS",
    "QLIB158_FACTORS",
    "ZOO_FACTORS",
]
