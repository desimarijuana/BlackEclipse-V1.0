"""The Fiduciary Gate — deterministic verification of actionable advice.

Runs at the answer seam (`graph.execute_run`), after the finance-fact gate and
alongside the citation release gate. It asks one question of every actionable
recommendation in the final answer:

    Was this produced by a portfolio computation this run performed, or grounded
    in a source/symbol this run consulted? If neither, it is unverified advice.

It is deliberately narrow and honest:

  * narrow — it inspects only extracted claims (a directive + a symbol/target);
    an answer with no recommendation is returned byte-for-byte unchanged;
  * deterministic — no model call, so it works with any provider (or none);
  * honest — it never rewrites or deletes the advice; it appends a disclosure
    and, when it can, names a computation that backs the claim.

It never places a trade. Every claim is a proposal.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .claims import extract_claims
from .model import (
    AdvisoryClaim,
    AdvisoryEnforcement,
    ClaimVerdict,
    COMPUTED,
    SOURCED,
    UNVERIFIED,
)

# A 1% relative tolerance absorbs rounding in a rendered answer (5% vs 0.05).
_TOL = 0.01


def _close(a: float, b: float) -> bool:
    """True when two numbers agree within tolerance, allowing a percent scale."""
    if a == b:
        return True
    for scale in (1.0, 100.0, 0.01):
        target = b * scale
        denom = max(abs(a), abs(target), 1e-9)
        if abs(a - target) / denom <= _TOL:
            return True
    return False


def _value_matches(claim_values: tuple[float, ...], numbers: Iterable[float]) -> bool:
    """A claim with no target matches on symbol alone; one with a target needs a
    matching number in the computation."""
    if not claim_values:
        return True
    for c in claim_values:
        for n in numbers:
            if _close(c, float(n)):
                return True
    return False


def _supported_by(claim: AdvisoryClaim, comp: dict[str, Any]) -> bool:
    comp_syms = {str(s).upper() for s in comp.get("symbols") or []}
    numbers = comp.get("numbers") or []
    if claim.symbols:
        if comp_syms and not (set(claim.symbols) & comp_syms):
            return False
        if not comp_syms:
            # A computation naming no symbol can only ground a named claim when
            # its numeric target matches; a symbol-only claim needs the symbol.
            return bool(claim.values) and _value_matches(claim.values, numbers)
    return _value_matches(claim.values, numbers)


def _classify(
    claim: AdvisoryClaim,
    computations: list[dict[str, Any]],
    consulted: set[str],
) -> tuple[str, str]:
    for comp in computations:
        if comp.get("compute") and _supported_by(claim, comp):
            tool = comp.get("tool") or "a portfolio computation"
            return COMPUTED, f"supported by `{tool}`"
    if not claim.values:
        for comp in computations:
            if _supported_by(claim, comp):
                return SOURCED, "grounded in the portfolio this run consulted"
        if claim.symbols and set(claim.symbols) <= {s.upper() for s in consulted}:
            return SOURCED, "the symbol was consulted in this run"
    return UNVERIFIED, "no portfolio computation or consulted source backs it"


def enforce_advisory_answer(
    answer: str,
    computations: Optional[list[dict[str, Any]]] = None,
    *,
    consulted: Optional[Iterable[str]] = None,
) -> AdvisoryEnforcement:
    """Classify every actionable recommendation against the run's computations.

    Pure and testable; does not rewrite `answer` (the caller appends the
    disclosure). Returns an `AdvisoryEnforcement`.
    """
    computations = list(computations or [])
    consulted_set = set(consulted or [])
    result = AdvisoryEnforcement()
    for claim in extract_claims(answer):
        status, reason = _classify(claim, computations, consulted_set)
        verdict = ClaimVerdict(claim=claim, status=status, reason=reason)
        result.verdicts.append(verdict)
        if status == UNVERIFIED:
            result.unverified.append(claim)
    if result.unverified:
        listed = "; ".join(c.describe() for c in result.unverified)
        result.disclosure = (
            "Advisory note: the following recommendation(s) are not backed by a "
            "portfolio calculation or a consulted source, so they are unverified "
            f"advice, not verified analysis: {listed}."
        )
    return result


async def apply(
    answer: str,
    computations: Optional[list[dict[str, Any]]] = None,
    *,
    consulted: Optional[Iterable[str]] = None,
    emitter: Any = None,
) -> tuple[str, Optional[dict[str, Any]]]:
    """Run the gate; append any disclosure and emit the verdict.

    Returns `(answer, verdict_dict_or_None)`. Never raises: enforcement at the
    answer seam is additive and must never fail a run. An answer with no
    actionable claim is returned byte-for-byte and yields `None`.
    """
    try:
        verdict = enforce_advisory_answer(answer, computations, consulted=consulted)
    except Exception:  # noqa: BLE001 - never fatal
        return answer, None
    if not verdict.verdicts:
        return answer, None
    blob = verdict.to_dict()
    if verdict.disclosure:
        answer = f"{answer}\n\n{verdict.disclosure}" if answer.strip() else verdict.disclosure
    if emitter is not None:
        try:
            await emitter.emit("advisory.gate", blob)
        except Exception:  # noqa: BLE001 - emission is best-effort
            pass
    return answer, blob


__all__ = ["apply", "enforce_advisory_answer"]
