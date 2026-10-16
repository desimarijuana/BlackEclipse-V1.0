"""Advisory verification — the Fiduciary Gate.

An actionable recommendation (buy/sell/rebalance/allocate/hedge/harvest) must be
either COMPUTED from the run's portfolio engine or SOURCED from what the run
actually consulted; otherwise it is disclosed as UNVERIFIED advice. This is the
advisory analogue of `finance_facts.enforce` and `research.release_gate`: pure,
deterministic, additive, and it never executes a trade.
"""

from __future__ import annotations

from .claims import extract_claims
from .collector import AdvisoryCollector
from .gate import (
    AdvisoryEnforcement,
    ClaimVerdict,
    apply,
    enforce_advisory_answer,
)
from .model import AdvisoryClaim, COMPUTED, SOURCED, UNVERIFIED
from .service import AdvisoryService
from .store import AdvisoryStore

__all__ = [
    "AdvisoryClaim",
    "AdvisoryCollector",
    "AdvisoryEnforcement",
    "AdvisoryService",
    "AdvisoryStore",
    "ClaimVerdict",
    "COMPUTED",
    "SOURCED",
    "UNVERIFIED",
    "apply",
    "enforce_advisory_answer",
    "extract_claims",
]
