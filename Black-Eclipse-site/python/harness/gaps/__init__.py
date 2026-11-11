"""Capability gaps and their offers.

One package, one rule: a run that cannot finish names WHAT is missing and the
one permitted next route. It never widens a permission and never offers to
bypass a safety denial.
"""

from .model import CapabilityGap, GapOffer
from .service import GapService
from .store import GapStore
from .taxonomy import (
    CAPABILITY_MISSING,
    CONTEXT_DENIED,
    MALFORMED,
    NOT_CONFIGURED,
    OFFERABLE,
    SAFETY_DENIED,
    TRANSIENT,
    UNKNOWN,
    USER_DENIED,
    classify,
    is_offerable,
    looks_like_bare_refusal,
)

__all__ = [
    "CapabilityGap",
    "GapOffer",
    "GapService",
    "GapStore",
    "CAPABILITY_MISSING",
    "CONTEXT_DENIED",
    "MALFORMED",
    "NOT_CONFIGURED",
    "OFFERABLE",
    "SAFETY_DENIED",
    "TRANSIENT",
    "UNKNOWN",
    "USER_DENIED",
    "classify",
    "is_offerable",
    "looks_like_bare_refusal",
]
