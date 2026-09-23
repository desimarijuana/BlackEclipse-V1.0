"""The research flow engine (Phase 4, Milestone 8).

Ties the mandate → retrieval → coverage → claims → validation → receipt path
together over the EXISTING Financial Retrieval Layer. It owns no agent loop and
no data plane: the caller injects an async `retrieve(request)` callable (the
retrieval layer, or a fake in tests).

The engine is deterministic except for the optional synthesis step, which is a
callable the caller supplies (a model-backed synthesizer in production, a stub in
tests). Validation of whatever the synthesizer returns is always deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from ..retrieval.contract import (
    FinancialRetrievalRequest,
    FinancialRetrievalResult,
)
from .citations import ResponseMetadata, build_response_metadata
from .claims import Synthesis, ValidationOutcome, render_prose, validate_claims
from .coverage import CoverageReport, build_coverage
from .mandate import FactLeg, ResearchMandate
from .receipt import ResearchReceipt, build_receipt

RetrieveFn = Callable[[FinancialRetrievalRequest], Awaitable[FinancialRetrievalResult]]
SynthesizeFn = Callable[..., Awaitable[Synthesis]]


@dataclass
class ResearchOutcome:
    mandate: ResearchMandate
    coverage: CoverageReport
    retrievalResults: list[FinancialRetrievalResult] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    validation: Optional[ValidationOutcome] = None
    calculations: list[Any] = field(default_factory=list)
    receipt: Optional[ResearchReceipt] = None
    metadata: Optional[ResponseMetadata] = None
    prose: Optional[str] = None
    repairRounds: int = 0

    @property
    def status(self) -> str:
        if self.validation is not None:
            return self.validation.status
        return self.coverage.status


# Datatype per metric leg — financial statement metrics come from statements.
_LEG_DATA_TYPE = "financial_statements"


def _retrieval_request_for(leg: FactLeg, mandate: ResearchMandate) -> FinancialRetrievalRequest:
    return FinancialRetrievalRequest(
        objective=f"{leg.metric} for {leg.entityRaw or 'the entity'}"
        + (f" in {leg.period}" if leg.period else ""),
        dataType=_LEG_DATA_TYPE,
        instrument=leg.entitySymbol,
        market=mandate.entities[0].market if mandate.entities else None,
        freshnessRequirement="slow",
        asOf=mandate.asOf,
        allowWeb=False,  # a numeric statement leg is never web-sourced
        metadata={
            "metric": leg.metric,
            "period": leg.period,
            "basis": leg.basis,
            "legId": leg.id,
        },
    )


async def run_research(
    mandate: ResearchMandate,
    retrieve: RetrieveFn,
    *,
    synthesize: Optional[SynthesizeFn] = None,
    calculations: Optional[list[Any]] = None,
    run_id: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_repair_rounds: int = 1,
) -> ResearchOutcome:
    """Execute the full research flow for a mandate.

    Unsupported/general mandates are returned untouched (empty coverage) so the
    caller keeps the existing chat path. For a supported `financial_comparison`
    the engine retrieves every leg through `retrieve`, builds deterministic
    coverage, runs (optional) synthesis + validation with at most one bounded
    repair round, and assembles a receipt.
    """
    outcome = ResearchOutcome(mandate=mandate, coverage=CoverageReport(status="accepted"))
    if not mandate.supported:
        return outcome

    evidence: list[Any] = []
    conflicts: list[dict[str, Any]] = []
    retrieval_requests: list[dict[str, Any]] = []

    for leg in mandate.factLegs:
        request = _retrieval_request_for(leg, mandate)
        try:
            result = await retrieve(request)
        except Exception as exc:  # noqa: BLE001 - a failed leg is unavailable, not a crash
            result = FinancialRetrievalResult(
                status="UNAVAILABLE",
                objective=request.objective,
                dataType=request.dataType,
                instrument=request.instrument,
                warnings=[f"retrieval failed: {exc}"],
            )
        outcome.retrievalResults.append(result)
        outcome.evidence.extend(result.evidence)
        conflicts.extend(result.conflicts or [])
        retrieval_requests.append(
            {
                "legId": leg.id,
                "dataType": request.dataType,
                "instrument": request.instrument,
                "asOf": request.asOf,
                "status": result.status,
                "strategy": result.strategy,
                "evidenceCount": len(result.evidence),
            }
        )

    # Deduplicate evidence by id (the same item may serve several legs).
    seen: set[str] = set()
    unique_evidence: list[Any] = []
    for item in outcome.evidence:
        item_id = getattr(item, "id", None)
        if item_id and item_id in seen:
            continue
        if item_id:
            seen.add(item_id)
        unique_evidence.append(item)
    outcome.evidence = unique_evidence
    outcome.conflicts = conflicts
    outcome.calculations = calculations or []

    outcome.coverage = build_coverage(mandate, unique_evidence, conflicts=conflicts)

    # No synthesizer (or a general mandate) → coverage is the whole verdict.
    if synthesize is None:
        outcome.metadata = build_response_metadata(
            mandate, outcome.coverage, unique_evidence,
            conflicts=conflicts, calculations=outcome.calculations,
        )
        outcome.receipt = build_receipt(
            run_id, mandate, coverage=outcome.coverage, evidence=unique_evidence,
            retrieval_requests=retrieval_requests, provider=provider, model=model,
        )
        return outcome

    synthesis = await _safe_synthesize(
        synthesize, mandate, unique_evidence, outcome.coverage, None
    )
    validation = validate_claims(
        mandate, synthesis, unique_evidence, outcome.coverage,
        calculations=outcome.calculations, conflicts=conflicts,
    )

    # One bounded repair round with the exact invalid claims / missing legs.
    while (
        validation.status in ("rejected",)
        and outcome.repairRounds < max_repair_rounds
    ):
        outcome.repairRounds += 1
        repaired = await _safe_synthesize(
            synthesize, mandate, unique_evidence, outcome.coverage,
            {"unresolved": validation.unresolved, "issues": _collect_issues(validation)},
        )
        validation = validate_claims(
            mandate, repaired, unique_evidence, outcome.coverage,
            calculations=outcome.calculations, conflicts=conflicts,
        )
        validation.repaired = True

    outcome.validation = validation
    outcome.prose = render_prose(validation)
    outcome.metadata = build_response_metadata(
        mandate, outcome.coverage, unique_evidence,
        validation=validation, conflicts=conflicts, calculations=outcome.calculations,
    )
    outcome.receipt = build_receipt(
        run_id, mandate, coverage=outcome.coverage, validation=validation,
        evidence=unique_evidence, retrieval_requests=retrieval_requests,
        repair={"rounds": outcome.repairRounds} if outcome.repairRounds else None,
        provider=provider, model=model,
    )
    return outcome


def _collect_issues(validation: ValidationOutcome) -> list[str]:
    issues: list[str] = []
    for claim in validation.claims:
        issues.extend(claim.issues)
    return issues


async def _safe_synthesize(
    synthesize: SynthesizeFn,
    mandate: ResearchMandate,
    evidence: list[Any],
    coverage: CoverageReport,
    repair: Optional[dict[str, Any]],
) -> Synthesis:
    try:
        return await synthesize(mandate, evidence, coverage, repair=repair)
    except Exception as exc:  # noqa: BLE001 - a synthesis failure yields honest gaps
        return Synthesis(gaps=[f"synthesis failed: {exc}"])


__all__ = ["RetrieveFn", "SynthesizeFn", "ResearchOutcome", "run_research"]
