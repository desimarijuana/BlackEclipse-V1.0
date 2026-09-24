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
from .budget import ResearchBudget
from .citations import ResponseMetadata, build_response_metadata
from .claims import Synthesis, ValidationOutcome, render_prose, validate_claims
from .comparability import ComparabilityVerdict, descriptor_from_leg, check_comparability
from .coverage import CoverageReport, build_coverage
from .escalation import escalate_web
from .mandate import FactLeg, ResearchMandate
from .receipt import ResearchReceipt, build_receipt

# Coverage statuses that mean "structured did not fully answer this leg" and
# therefore justify a bounded web escalation:
#   unavailable        — nothing retrieved
#   no_matching_period — evidence exists but not for the requested fiscal period
#   stale              — only a stale observation exists
#   unknown            — a required blocking field is unconfirmed
#   qualified          — the value is present but required metadata (e.g. basis)
#                        is unconfirmed; escalation may confirm it from a primary
#                        source, and leaves the leg qualified if it cannot
_ESCALATABLE = {"unavailable", "no_matching_period", "stale", "unknown", "qualified"}

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
    budget: Optional[dict[str, Any]] = None
    escalation: Optional[dict[str, Any]] = None
    # Phase 6: per-leg retrieval status + diagnostics, and WHY the loop stopped.
    legStatus: list[dict[str, Any]] = field(default_factory=list)
    stopReason: Optional[str] = None
    # Phase 7 WS6: the deterministic identity/comparability verdict. A blocked
    # comparison is reported instead of a misleading change.
    comparability: Optional[ComparabilityVerdict] = None

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
    bridge: Any = None,
    extractor: Any = None,
    budget: Optional[ResearchBudget] = None,
    on_event: Any = None,
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
    leg_status: list[dict[str, Any]] = []

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
                # Every attempt is preserved in the audit trail, including why a
                # route failed (timeout/block/http/parse), not just that it did.
                "diagnostics": result.diagnostics,
            }
        )
        leg_status.append(
            {
                "legId": leg.id,
                "metric": leg.metric,
                "period": leg.period,
                "retrievalStatus": result.status,
                "strategy": result.strategy,
                "diagnostics": result.diagnostics,
            }
        )

    # Deduplicate evidence by id (the same item may serve several legs).
    unique_evidence: list[Any] = _dedupe_evidence(outcome.evidence)
    outcome.evidence = unique_evidence
    outcome.conflicts = conflicts
    outcome.calculations = calculations or []

    outcome.coverage = build_coverage(mandate, unique_evidence, conflicts=conflicts)

    # ── Deterministic identity/comparability gate (WS6) ──────────────────────
    # Before any derived change is presented, verify the legs describe the same
    # fact (entity, security, period, duration, metric, basis, currency, unit,
    # scale). A blocked pair is named exactly; each verified leg is still shown.
    descriptors = []
    for leg in mandate.factLegs:
        identity = None
        for entity in mandate.entities:
            if entity.symbol and entity.symbol == leg.entitySymbol:
                identity = entity.canonical
                break
        descriptors.append(descriptor_from_leg(leg, identity=identity))
    outcome.comparability = check_comparability(descriptors)
    comparability_blocked = outcome.comparability.to_dict()

    # ── Bounded web escalation ───────────────────────────────────────────────
    # When structured sources left required legs unsatisfied (empty, wrong
    # period, stale, or metadata-incomplete), escalate to trusted web sources
    # before synthesis. Primary sources first, then bounded secondary. Only legs
    # that actually need it are targeted.
    budget = budget or ResearchBudget()
    escalation_audit: Optional[dict[str, Any]] = None
    unsatisfied = [
        leg for leg, cov in zip(mandate.factLegs, outcome.coverage.legs)
        if cov.status in _ESCALATABLE and leg.required
    ]
    if unsatisfied and bridge is not None and extractor is not None:
        budget.note("escalation:triggered")
        escalation = await escalate_web(
            mandate,
            unsatisfied,
            bridge=bridge,
            extractor=extractor,
            budget=budget,
            on_event=on_event,
        )
        escalation_audit = {
            "stages": escalation.stagesRun,
            "attempts": escalation.attempts,
            "notes": escalation.notes,
            "budget": escalation.budget,
            "acceptedEvidence": len(escalation.evidence),
            "diagnostics": escalation.diagnostics,
        }
        if escalation.evidence:
            outcome.evidence = _dedupe_evidence([*outcome.evidence, *escalation.evidence])
            unique_evidence = outcome.evidence
            outcome.coverage = build_coverage(mandate, unique_evidence, conflicts=conflicts)
    elif unsatisfied:
        escalation_audit = {
            "stages": [],
            "attempts": [*budget.attempted, "escalation:unavailable(no bridge/extractor)"],
            "notes": [],
            "budget": budget.snapshot(),
            "acceptedEvidence": 0,
        }

    outcome.budget = budget.snapshot()
    outcome.escalation = escalation_audit
    outcome.legStatus = _merge_leg_status(
        leg_status, outcome.coverage,
        escalation_diagnostics=(escalation_audit or {}).get("diagnostics") or [],
    )
    outcome.stopReason = _stop_reason(outcome.coverage, budget, outcome.legStatus)

    # No synthesizer (or a general mandate) → coverage is the whole verdict.
    if synthesize is None:
        outcome.metadata = build_response_metadata(
            mandate, outcome.coverage, unique_evidence,
            conflicts=conflicts, calculations=outcome.calculations,
            comparability=comparability_blocked,
        )
        outcome.receipt = build_receipt(
            run_id, mandate, coverage=outcome.coverage, evidence=unique_evidence,
            retrieval_requests=retrieval_requests, provider=provider, model=model,
            budget=outcome.budget, escalation=escalation_audit,
            leg_status=outcome.legStatus, stop_reason=outcome.stopReason,
            comparability=comparability_blocked,
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
        comparability=comparability_blocked,
    )
    outcome.receipt = build_receipt(
        run_id, mandate, coverage=outcome.coverage, validation=validation,
        evidence=unique_evidence, retrieval_requests=retrieval_requests,
        repair={"rounds": outcome.repairRounds} if outcome.repairRounds else None,
        provider=provider, model=model,
        budget=outcome.budget, escalation=escalation_audit,
        leg_status=outcome.legStatus, stop_reason=outcome.stopReason,
        comparability=comparability_blocked,
    )
    return outcome


def _merge_leg_status(
    leg_status: list[dict[str, Any]],
    coverage: CoverageReport,
    *,
    escalation_diagnostics: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Attach the final deterministic coverage status to each leg's attempt row.

    The retrieval status ("did a provider answer") and the coverage status
    ("does the evidence satisfy the leg") are distinct and both are preserved.
    Escalation diagnostics are merged into the leg they were attempted for so the
    final answer can name every route that was tried.
    """
    by_id = {row["legId"]: row for row in leg_status}
    esc_by_leg: dict[str, list[dict[str, Any]]] = {}
    for diagnostic in escalation_diagnostics or []:
        leg_id = diagnostic.get("legId")
        if leg_id:
            esc_by_leg.setdefault(leg_id, []).append(diagnostic)
    merged: list[dict[str, Any]] = []
    for leg in coverage.legs:
        row = dict(by_id.get(leg.legId, {"legId": leg.legId}))
        row["coverageStatus"] = leg.status
        row["coverageReason"] = leg.reason
        row["diagnostics"] = [*(row.get("diagnostics") or []), *esc_by_leg.get(leg.legId, [])]
        merged.append(row)
    return merged


# Human-readable stop reasons for the run, so the answer can say WHY it ended.
_STOP_BUDGET = "budget_exhausted"
_STOP_RESOLVED = "all_required_legs_resolved"
_STOP_PROVIDER = "provider_routes_unavailable"
_STOP_PARTIAL = "unresolved_facts_remain"


def _stop_reason(
    coverage: CoverageReport,
    budget: ResearchBudget,
    leg_status: list[dict[str, Any]],
) -> str:
    """Why the research loop stopped. Never claims success it did not reach."""
    if coverage.complete:
        return _STOP_RESOLVED
    if budget.exhausted or budget.timed_out:
        return _STOP_BUDGET
    # If every unresolved leg's only attempts show transport/provider failures
    # (no provider ever answered), the routes were unavailable — that is distinct
    # from "an answer came back but did not cover the leg".
    unresolved = [
        row for row in leg_status
        if row.get("coverageStatus")
        in ("unavailable", "unknown", "stale", "no_matching_period", "qualified", "conflicting")
    ]
    if unresolved and all(_only_transport_failures(row.get("diagnostics") or []) for row in unresolved):
        return _STOP_PROVIDER
    return _STOP_PARTIAL


def _only_transport_failures(diagnostics: list[dict[str, Any]]) -> bool:
    """True when diagnostics exist and every one is a hard transport/provider failure."""
    return bool(diagnostics) and all(d.get("normalizedStatus") == "failed" for d in diagnostics)


def _dedupe_evidence(items: list[Any]) -> list[Any]:
    """De-duplicate evidence by id, preserving first-seen order."""
    seen: set[str] = set()
    out: list[Any] = []
    for item in items:
        item_id = getattr(item, "id", None)
        if item_id and item_id in seen:
            continue
        if item_id:
            seen.add(item_id)
        out.append(item)
    return out


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
