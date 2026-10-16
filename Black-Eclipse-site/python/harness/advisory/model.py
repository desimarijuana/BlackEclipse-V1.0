"""The advisory domain vocabulary (Fiduciary Gate).

An `AdvisoryClaim` is an ACTIONABLE recommendation extracted deterministically
from the final answer: a directive verb (buy/sell/rebalance/…), the symbols it
names, and any numeric target (a weight, an amount, a share count). Its truth
status is one of:

  * `COMPUTED`   — a portfolio computation the run actually performed backs it
                   (reproducible: re-run the engine and get the same numbers);
  * `SOURCED`    — the run consulted the symbol(s) through a portfolio read, so
                   the claim is grounded in the user's own ledger even without a
                   numeric target;
  * `UNVERIFIED` — neither: the recommendation rests on nothing the run produced
                   and MUST be disclosed, never presented as clean advice.

This is a PURE data module: no I/O, no retrieval, no model. The LLM reasons about
advice; this records what can actually be proven about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Truth statuses (the closed vocabulary).
COMPUTED = "computed"
SOURCED = "sourced"
UNVERIFIED = "unverified"

STATUSES: tuple[str, ...] = (COMPUTED, SOURCED, UNVERIFIED)


@dataclass(frozen=True)
class AdvisoryClaim:
    """One actionable recommendation found in an answer.

    `target` is the human-readable target the sentence stated ("5%", "$10k",
    "100 shares", "60/40"); `values` is the same target as plain floats, used
    only for deterministic matching against a computation. A claim with no
    numeric target (`values` empty) is matched by symbol alone.
    """

    action: str
    symbols: tuple[str, ...] = ()
    target: Optional[str] = None
    values: tuple[float, ...] = ()
    sentence: str = ""

    def describe(self) -> str:
        who = " ".join(self.symbols) if self.symbols else "the portfolio"
        to = f" to {self.target}" if self.target else ""
        return f"{self.action} {who}{to}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "symbols": list(self.symbols),
            "target": self.target,
            "values": list(self.values),
        }


@dataclass
class ClaimVerdict:
    """The gate's verdict for one claim."""

    claim: AdvisoryClaim
    status: str
    reason: Optional[str] = None

    @property
    def verified(self) -> bool:
        return self.status in (COMPUTED, SOURCED)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.claim.to_dict(),
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class AdvisoryEnforcement:
    """The gate's verdict for one answer."""

    verdicts: list[ClaimVerdict] = field(default_factory=list)
    unverified: list[AdvisoryClaim] = field(default_factory=list)
    disclosure: Optional[str] = None

    @property
    def released(self) -> bool:
        """True when no claim requires a disclosure."""
        return not self.unverified

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.released else "unverified",
            "claims": [v.to_dict() for v in self.verdicts],
            "unverified": [c.to_dict() for c in self.unverified],
        }


__all__ = [
    "AdvisoryClaim",
    "AdvisoryEnforcement",
    "ClaimVerdict",
    "COMPUTED",
    "SOURCED",
    "STATUSES",
    "UNVERIFIED",
]
